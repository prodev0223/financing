# -*- coding: utf-8 -*-
import os
import subprocess
import requests
import time
import logging
from base64 import b64decode
from odoo import _, api, exceptions, fields, models


_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    gpais_username = fields.Char(string='GPAIS prisijungimo vardas',
                                 groups='robo_electronics.robo_electronics_reports')
    gpais_cert = fields.Binary(string='GPAIS privatus raktas', inverse='_update_cert',
                               groups='robo_electronics.robo_electronics_reports')

    def __init__(self, pool, cr):
        init_res = super(ResUsers, self).__init__(pool, cr)
        type(self).SELF_WRITEABLE_FIELDS = list(self.SELF_WRITEABLE_FIELDS)
        type(self).SELF_WRITEABLE_FIELDS.extend(['gpais_username', 'gpais_cert'])
        type(self).SELF_WRITEABLE_FIELDS = list(set(type(self).SELF_WRITEABLE_FIELDS))
        type(self).SELF_READABLE_FIELDS = list(self.SELF_READABLE_FIELDS)
        type(self).SELF_READABLE_FIELDS.extend(['gpais_username', 'gpais_cert'])
        type(self).SELF_READABLE_FIELDS = list(set(type(self).SELF_READABLE_FIELDS))
        return init_res

    @api.one
    def _update_cert(self):
        if self.gpais_cert:
            path = '/opt/repo/gpais/keys/%s_%s.key' % (self._cr.dbname, self.id)
            key = '-----BEGIN RSA PRIVATE KEY-----\n%s\n-----END RSA PRIVATE KEY-----' % b64decode(self.gpais_cert)
            f = open(path, 'wb')
            f.write(key)
            f.close()

    @api.model
    def get_gpais_domain(self):
        if self.env.user.sudo().company_id.gpais_testing:
            return 'https://tst.gpais.eu'
        else:
            return 'https://www.gpais.eu'

    @api.model
    def get_gpais_product_url(self):
        return self.get_gpais_domain() + '/o/vvs/srv/products/import'

    @api.model
    def get_gpais_journal_url(self):
        return self.get_gpais_domain() + '/o/vvs/zrn/journal/import'

    @api.multi
    def upload_gpais_xml(self, xml, xml_type='products'):
        self.ensure_one()
        # Additional pass of sudo(uid) here because the environment user is superuser
        self.env['res.users'].sudo(self.id).check_global_readonly_access()
        if xml_type == 'products':
            url = self.get_gpais_product_url()
        elif xml_type == 'journal':
            url = self.get_gpais_journal_url()
        else:
            raise exceptions.UserError(_('Nenurodytas XML tipas.'))
        username = self.gpais_username
        if not username:
            raise exceptions.UserError(_('Nenurodytas GPAIS prisijungimo vardas.'))
        if not self.gpais_cert:
            raise exceptions.UserError(_('Neįkeltas GPAIS privatus raktas.'))
        key = '-----BEGIN RSA PRIVATE KEY-----\n%s\n-----END RSA PRIVATE KEY-----' % b64decode(self.gpais_cert)
        path = '/opt/repo/gpais/keys/%s_%s.key' % (self._cr.dbname, self.id)
        if not os.path.isfile(path):
            f = open(path, 'wb')
            f.write(key)
            f.close()
        command = 'echo -n "%s|"`date +%%s%%3N` | openssl pkeyutl -sign -inkey %s | base64 -w 0' % \
                  (self.env.user.sudo().company_id.company_registry, path)
        e_password = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE).stdout.read()
        time.sleep(1.5)
        headers = {'content-type': 'application/xml;charset=UTF-8'}
        r = requests.post(url, data=xml, headers=headers, auth=(username, e_password))
        if r.status_code == 200 or r.status_code == 202:
            _logger.info('GPAIS request returned with status %s.' % r.status_code)
            return True
        elif r.status_code == 401:
            raise exceptions.UserError(_('Nepavyko pateikti dokumento į GPAIS sistemą. Autentikavimo klaida.'))
        elif r.status_code == 403:
            raise exceptions.UserError(
                _('Nepavyko pateikti dokumento į GPAIS sistemą. Neturite teisių atstovauti subjektą.'))
        elif r.status_code == 400:
            _logger.info(_('GPAIS pateikta byla apdorojama. Statusas %s.') % r.status_code)
            return True
        else:
            _logger.info(_('GPAIS nežinoma klaida. Statusas %s.') % r.status_code)
            return True
