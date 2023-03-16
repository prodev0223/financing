# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions, tools
from suds.client import Client
from suds.wsse import Security, UsernameToken
from suds.sax.element import Element
from suds.sax.date import DateTime
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


wssens = \
    ('wsse',
     'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd')


class UsernameTokenRobo(UsernameToken):

    def xml(self):
        root = Element('UsernameToken', ns=wssens)
        u = Element('Username', ns=wssens)
        u.setText(self.username)
        root.append(u)
        p = Element('Password', ns=wssens)
        p.set('Type', 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText')
        p.setText(self.password)
        root.append(p)
        if self.nonce is not None:
            n = Element('Nonce', ns=wssens)
            n.set('EncodingType', 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary')
            n.setText(self.nonce)
            root.append(n)
        if self.created is not None:
            n = Element('Created', ns=wssens)
            n.setText(str(DateTime(self.created)))
            root.append(n)
        return root


class ResUsers(models.Model):
    _inherit = 'res.users'

    def __init__(self, pool, cr):
        init_res = super(ResUsers, self).__init__(pool, cr)
        type(self).SELF_WRITEABLE_FIELDS = list(self.SELF_WRITEABLE_FIELDS)
        type(self).SELF_WRITEABLE_FIELDS.extend(['sodra_username', 'sodra_password'])
        type(self).SELF_WRITEABLE_FIELDS = list(set(type(self).SELF_WRITEABLE_FIELDS))
        type(self).SELF_READABLE_FIELDS = list(self.SELF_READABLE_FIELDS)
        type(self).SELF_READABLE_FIELDS.extend(['sodra_username', 'sodra_password'])
        type(self).SELF_READABLE_FIELDS = list(set(type(self).SELF_READABLE_FIELDS))
        return init_res

    sodra_username = fields.Char(string='SODRA prisijungimo vardas', groups='robo_basic.group_robo_premium_accountant')
    sodra_password = fields.Char(string='SODRA slaptažodis', groups='robo_basic.group_robo_premium_accountant')

    @api.model
    def get_sodra_api(self):
        if not self.sodra_username or not self.sodra_password:
            raise exceptions.UserError(_('Nenurodyti prisijungimo duomenys'))
        url = 'https://draudejai.sodra.lt/edas-external/services/DataService?wsdl'
        token = UsernameTokenRobo(username=self.sodra_username, password=self.sodra_password)
        token.setcreated()
        token.setnonce('')
        security = Security()
        security.tokens.append(token)
        return Client(url, wsse=security, faults=False)


ResUsers()


doc_states = {
    'ERR': 'rejected',
    'DRF': 'confirmed',
    'PRC': 'sent',
}


class SodraDocumentExport(models.Model):
    _name = 'sodra.document.export'
    _order = 'last_update_date desc, upload_date desc'

    doc_name = fields.Char(string='Pavadinimas')
    signing_url = fields.Char(string='Pasirašymo nuoroda')
    ext_id = fields.Char(string='Išorinis identifikatorius')
    upload_date = fields.Datetime(string='Įkėlimo data')
    last_update_date = fields.Datetime(string='Paskutinio atnaujinimo data')
    state = fields.Selection([('confirmed', 'Patvirtinta'),
                              ('rejected', 'Atmesta'),
                              ('sent', 'Pateikta')], default='sent', string='Būsena')
    document_date = fields.Date(string='Dokumento data')

    @api.model
    def cron_data_update(self):
        to_update = self.search([('state', '=', 'sent')])
        for rec in to_update:
            client = self.env.user.get_sodra_api()
            try:
                doc = client.service.getDocumentStatus(rec.ext_id)
            except Exception as exc:
                _logger.info('Sodra Update Exception: %s. Tracking number: %s' % (str(exc.args), rec.ext_id))
                doc = False
            if not doc:
                state = 'sent'
            else:
                if type(doc) == tuple and doc[0] == 200:
                    try:
                        data = dict(doc[1])
                        state = data.get('docStatus', '')
                        if state:
                            state = doc_states[state]
                        else:
                            state = 'rejected'
                    except (ValueError, IndexError):
                        state = 'rejected'
                else:
                    state = 'rejected'
            rec.write({'state': state,
                       'last_update_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})


SodraDocumentExport()
