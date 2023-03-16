# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions, tools
from suds.client import Client
from suds.transport.http import HttpAuthenticated, Reply
from suds.plugin import MessagePlugin
import requests
import logging
import time
import io
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta
from zipfile import ZipFile
from tempfile import SpooledTemporaryFile
import base64
import subprocess
import magic

_logger = logging.getLogger(__name__)
account_number_count = 10


class RequestsTransport(HttpAuthenticated):
    def __init__(self, **kwargs):
        self.cert = kwargs.pop('cert', None)
        HttpAuthenticated.__init__(self, **kwargs)

    def open(self, request):
        self.addcredentials(request)
        resp = requests.get(request.url, data=request.message,
                             headers=request.headers, cert=self.cert)
        result = io.StringIO(resp.content.decode('utf-8'))
        return result

    def send(self, request):
        self.addcredentials(request)
        resp = requests.post(request.url, data=request.message,
                             headers=request.headers, cert=self.cert)
        result = Reply(resp.status_code, resp.headers, resp.content)
        return result


class RoboParser(MessagePlugin):
    def received(self, context):
        reply = context.reply
        context.reply = reply[reply.find("<soap:Envelope"):reply.find("</soap:Envelope>")+len('</soap:Envelope>')]


class VMICertificates(models.Model):
    _name = 'vmi.certificates'

    name = fields.Char(string='Pavadinimas')
    date_added = fields.Datetime(string='Pridėjimo data')
    user_id = fields.Many2one('res.users', string='Pridėjęs asmuo')
    attachment_id = fields.Many2one('ir.attachment', string='Sertifikato failas', ondelete='set null')
    is_key = fields.Boolean(default=False)


VMICertificates()


class ResUsers(models.Model):
    _inherit = 'res.users'

    def __init__(self, pool, cr):
        init_res = super(ResUsers, self).__init__(pool, cr)
        type(self).SELF_WRITEABLE_FIELDS = list(self.SELF_WRITEABLE_FIELDS)
        type(self).SELF_WRITEABLE_FIELDS.extend(['eds_username', 'eds_password', 'cert_data', 'key_data', 'cert_name', 'key_name'])
        type(self).SELF_WRITEABLE_FIELDS = list(set(type(self).SELF_WRITEABLE_FIELDS))
        type(self).SELF_READABLE_FIELDS = list(self.SELF_READABLE_FIELDS)
        type(self).SELF_READABLE_FIELDS.extend(['eds_username', 'eds_password', 'cert_data', 'key_data', 'cert_name', 'key_name'])
        type(self).SELF_READABLE_FIELDS = list(set(type(self).SELF_READABLE_FIELDS))
        return init_res

    eds_username = fields.Char(string='VMI EDS prisijungimo vardas',
                               groups='robo_basic.group_robo_premium_accountant')
    eds_password = fields.Char(string='VMI EDS slaptažodis', groups='robo_basic.group_robo_premium_accountant')

    cert_data = fields.Binary(string='VMI sertifikato failas', required=False)
    cert_name = fields.Char(string='Sertifikato failo pavadinimas', size=128, required=False)
    key_data = fields.Binary(string='VMI rakto failas')
    key_name = fields.Char(string='Rakto failo pavadinimas', size=128, required=False)

    @api.multi
    def upload_key(self):
        self.ensure_one()
        if not self.key_data or not self.key_name:
            raise exceptions.Warning(_('Nepateiktas failas!'))
        if not self.key_name.lower().endswith('.key'):
            raise exceptions.Warning(_('Netinkamas failo formatas!'))
        try:
            key_data = base64.decodestring(self.key_data)
            if os.path.isdir('/tmp/'):
                with open('/tmp/temp_key', 'w+') as fh:
                    fh.write(key_data)
            file_type = magic.from_file('/tmp/temp_key')
            if file_type != 'PEM RSA private key':
                raise exceptions.Warning(_('Netinkamas failo formatas!'))
            res_id = self.env['vmi.certificates'].create({
                'name': self.env['ir.sequence'].next_by_code('vmi_cert') + '.key',
                'date_added': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                'user_id': self.env.user.id,
                'is_key': True,
            })
            attach_id = self.env['ir.attachment'].create({
                'res_model': 'vmi.certificates',
                'res_id': res_id.id,
                'type': 'binary',
                'name': res_id.name + '.key',
                'datas_fname': res_id.name + '.key',
                'store_fname': res_id.name + '.key',
                'datas': self.key_data
            })
            res_id.write({'attachment_id': attach_id.id})
        except Exception as exc:
            _logger.info('VMI key exception %s' % str(exc.args))
            if os.path.isfile('/tmp/temp_key'):
                os.remove('/tmp/temp_key')
            raise exceptions.Warning(_('Nepavyko įkelti rakto, klaidos pranešimas: %s' % str(exc.args)))

        self.key_data = False
        self.key_name = False
        if os.path.isfile('/tmp/temp_key'):
            os.remove('/tmp/temp_key')
        self.env.cr.commit()
        raise exceptions.Warning(_('Raktas įkeltas!'))

    @api.multi
    def upload_cert(self):
        self.ensure_one()
        corresponding_file = None
        temp_crt = '/tmp/temp_cert.crt'
        temp_pem = '/tmp/temp_cert.pem'
        static_filename = 'certificate.crt'  # todo, find better solution
        if not self.cert_data:
            raise exceptions.Warning(_('Nepateiktas failas!'))
        try:
            cert_data = base64.decodestring(self.cert_data)
            with SpooledTemporaryFile() as tmp:
                tmp.write(cert_data)
                archive = ZipFile(tmp, 'r')
                for file_data in archive.filelist:
                    content = archive.read(file_data.filename)
                    if file_data.filename == static_filename:
                        corresponding_file = content
                        break
                if os.path.isdir('/tmp/'):
                    with open(temp_crt, 'w+') as fh:
                        fh.write(corresponding_file)
                res = self.with_context(convert=True).process_cert()
        except Exception as exc:
            _logger.info('VMI Certificate exception %s' % str(exc.args))
            # check if PEM or CRT
            if not self.cert_data:
                raise exceptions.Warning(_('Nepateiktas failas!'))
            cert_data = base64.decodestring(self.cert_data)
            if self.cert_name:
                if self.cert_name.lower().endswith('.crt'):
                    if os.path.isdir('/tmp/'):
                        with open(temp_crt, 'w+') as fh:
                            fh.write(cert_data)
                    res = self.with_context(convert=True).process_cert()
                elif self.cert_name.lower().endswith('.pem'):
                    if os.path.isdir('/tmp/'):
                        with open(temp_pem, 'w+') as fh:
                            fh.write(cert_data)
                    res = self.with_context(convert=False).process_cert()
                else:
                    raise exceptions.Warning(_('Netinkamas failo formatas!'))
            else:
                raise exceptions.Warning(_('Netinkamas failo formatas!'))
        if res:
            raise exceptions.Warning(_('Failas įkeltas!'))

    @api.multi
    def process_cert(self):
        self.ensure_one()
        try:
            convert = self._context.get('convert', True)
            temp_crt = '/tmp/temp_cert.crt'
            temp_pem = '/tmp/temp_cert.pem'
            if convert:
                command = 'openssl x509 -inform der -in ' + temp_crt + ' -out ' + temp_pem
                subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
            time.sleep(1.5)
            if not os.path.isfile(temp_pem):
                raise exceptions.Warning(_('Netinkamas failo formatas!'))
            else:
                res_id = self.env['vmi.certificates'].create({
                    'name': self.env['ir.sequence'].next_by_code('vmi_cert') + '.' + self.env.cr.dbname,
                    'date_added': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                    'user_id': self.env.user.id,
                })
                with open(temp_pem, 'rb') as pem_file:
                    encoded_pem = base64.b64encode(pem_file.read())
                    attach_id = self.env['ir.attachment'].create({
                        'res_model': 'vmi.certificates',
                        'res_id': res_id.id,
                        'type': 'binary',
                        'name': res_id.name + '.pem',
                        'datas_fname': res_id.name + '.pem',
                        'store_fname': res_id.name + '.pem',
                        'datas': encoded_pem
                    })
                res_id.write({'attachment_id': attach_id.id})
                # Cleanup
                self.clean_certs()
                if os.path.exists(temp_crt):
                    os.remove(temp_crt)
                if os.path.exists(temp_pem):
                    os.remove(temp_pem)
                self.env.cr.commit()
                return True
        except Exception as exc:
            raise exceptions.Warning('Operacija nepavyko, klaidos pranešimas: %s' % str(exc.args))

    @api.multi
    def clean_certs(self):
        for rec in self:
            rec.cert_data = False
            rec.cert_name = False

    @api.multi
    def get_registry(self):
        return self.env.user.company_id.company_registry

    @api.model
    def upload_eds_file(self, file_base64, file_name, document_date, registry_num=None):
        """
        Tries to upload passed FF-data file to VMI,
        and creates document export job record
        :param file_base64: file-to-upload in base64 (str)
        :param file_name: file name (str)
        :param document_date: document date (str)
        :param registry_num: company registry number to use
            in case of substitute partner, different registry
            can be passed (str)
        :return: None
        """

        # Get the company registry number
        registry_num = self.get_registry() if registry_num is None else registry_num

        if not self.eds_username or not self.eds_password or not registry_num:
            raise exceptions.UserError(_('Nenurodyti VMI prisijungimo duomenys'))
        url = 'https://deklaravimas.vmi.lt/EDSWebServiceUploadFile/EDSWebServiceUploadFile.asmx?wsdl'
        client = Client(url)
        try:
            res = client.service.SubmitFile(
                file_base64, file_name, '', 'ROBO',
                self.eds_username, self.eds_password, registry_num
            )
        except Exception as exc:
            _logger.info('%s exception: %s' % (file_name, str(exc.args)))
            res = None

        if res and not res.Result:
            raise exceptions.UserError(res.Message)
        if not res:
            raise exceptions.UserError(_('Nepavyko įkelti rinkmenos'))
        track_num = res.FileId
        try:
            res_check = client.service.CheckFileState(track_num, 'ROBO', self.eds_username, self.eds_password)
        except Exception as exc:
            _logger.info('%s exception: %s' % (file_name, str(exc.args)))
            res_check = None

        if res_check:
            if res_check.Result:
                state = 'confirmed'
            else:
                state = 'rejected'
        else:
            state = 'sent'
        vals = {
            'doc_name': file_name,
            'ext_id': track_num,
            'upload_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            'last_update_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            'state': state,
            'file_type': 'ffdata',
            'document_date': document_date
        }
        self.env['vmi.document.export'].create(vals)

    @api.model
    def get_isaf_api(self, account_no=1, database=False):
        if not self.env.user.is_accountant():
            return False
        pem_file = False
        certs = self.env['vmi.certificates'].search([('is_key', '=', False)], order='date_added desc')
        for cert in certs:
            if not cert.attachment_id:
                continue
            filepath = '/opt/repo/isaf/robolabs.lt.%s-%s.pem' % (database, cert.attachment_id.id)
            if os.path.isfile(filepath):
                pem_file = filepath
                break
            data = cert.attachment_id.datas
            if not data:
                continue
            datas = base64.b64decode(data)
            try:
                f = open(filepath, 'w+b')
                f.write(datas)
                f.close()
            except Exception as exc:
                _logger.info('Could not create file %s. Exception: %s', filepath, exc)
                continue
            if os.path.isfile(filepath):
                pem_file = filepath
                break
        if not pem_file:
            if database:
                pem_file = '/opt/repo/isaf/robolabs.lt.%s.pem' % database
            else:
                pem_file = '/opt/repo/isaf/robolabs.lt.%s.pem' % account_no
            if not os.path.isfile(pem_file):
                return False

        key_file = False
        keys = self.env['vmi.certificates'].search([('is_key', '=', True)])
        for key in keys:
            if not key.attachment_id:
                continue
            filepath = '/opt/repo/isaf/robolabs.lt.%s-%s.key' % (database, key.attachment_id.id)
            if os.path.isfile(filepath):
                key_file = filepath
                break
            data = key.attachment_id.datas
            if not data:
                continue
            datas = base64.b64decode(data)
            try:
                f = open(filepath, 'w+b')
                f.write(datas)
                f.close()
            except Exception as exc:
                _logger.info('Could not create file %s. Exception: %s', filepath, exc)
                continue
            if os.path.isfile(filepath):
                key_file = filepath
                break
        if not key_file:
            key_file = '/opt/repo/isaf/robolabs.lt.key'
            if not os.path.isfile(key_file):
                return False

        url = 'https://imas-ws.vmi.lt/isaf-uploader/services/uploader?wsdl'
        t = RequestsTransport(cert=(pem_file, key_file))
        headers = {"Content-Type": "text/xml;charset=UTF-8"}

        try:
            client = Client(url, headers=headers, transport=t, plugins=[RoboParser()])
            return client
        except Exception as exc:
            _logger.info('VMI Certificate error: %s' % str(exc.args))
            return False

    @api.model
    def upload_isaf(self, xml_base64, document_date):
        def upload(client, env):
            if not client:
                return False
            try:
                res = client.service.Upload(xml_base64)
            except Exception as exc:
                _logger.info('iSAF exception: %s' % str(exc.args))
                res = False
            status = str(res.operationStatus).strip() if res else False
            if not res or status != 'SUCCESS':
                _logger.info('iSAF exception: %s != %s. \nReply: %s' % (status, 'SUCCESS', res))
                raise exceptions.UserError(_('Nepavyko įkelti rinkmenos'))
            else:
                track_num = res.trackingNumber
                try:
                    message = '''<?xml version="1.0" encoding="UTF-8"?><SOAP-ENV:Envelope xmlns:ns0="urn:isaf:uploader:v1" xmlns:ns1="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"><SOAP-ENV:Header/><ns1:Body><ns0:CheckStateRequest><ns0:trackingNumber>%s</ns0:trackingNumber></ns0:CheckStateRequest></ns1:Body></SOAP-ENV:Envelope>''' % track_num
                    res_check = client.service.CheckState(__inject={'msg': message})
                except Exception as exc:
                    _logger.info('Exception: %s. Tracking number: %s' % (str(exc.args), track_num))
                    res_check = False
                if res_check:
                    if str(res_check.operationStatus) != 'SUCCESS':
                        state = 'sent'
                    else:
                        if str(res_check.state) == 'ACCEPTED':
                            state = 'confirmed'
                        elif str(res_check.state) == 'REJECTED':
                            return False
                        else:
                            state = 'sent'
                else:
                    state = 'sent'

                vals = {
                    'doc_name': 'iSAF',
                    'ext_id': track_num,
                    'upload_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                    'last_update_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                    'state': state,
                    'file_type': 'xml',
                    'document_date': document_date
                }
                env['vmi.document.export'].create(vals)
                return True

        client = self.env.user.get_isaf_api(database=self.env.cr.dbname)
        if client:
            r = upload(client, self.env)
            if r:
                return True
        n = 1
        while n < account_number_count:
            client = self.env.user.get_isaf_api(account_no=n)
            n += 1
            if not client:
                continue
            r = upload(client, self.env)
            if r:
                return True
        return False


ResUsers()


class VMIDocumentExport(models.Model):
    _name = 'vmi.document.export'
    _order = 'last_update_date desc, upload_date desc'

    doc_name = fields.Char(string='Pavadinimas')
    ext_id = fields.Char(string='Išorinis identifikatorius')
    upload_date = fields.Datetime(string='Įkėlimo data')
    last_update_date = fields.Datetime(string='Paskutinio atnaujinimo data')
    state = fields.Selection([('confirmed', 'Priimta'),
                              ('rejected', 'Atmesta'),
                              ('sent', 'Pateikta')], default='sent', string='Būsena')
    file_type = fields.Selection([('xml', 'XML Formatas'),
                                  ('ffdata', 'FFData Formatas')], string='Failo tipas')
    document_date = fields.Date(string='Dokumento data')
    error_message = fields.Text(string='Klaidos pranešimas')

    @api.multi
    def name_get(self):
        return [(rec.id, _('Dokumentas ') + str(rec.doc_name or '')) for rec in self]

    @api.model
    def cron_data_update(self):
        date_min = (datetime.utcnow() - relativedelta(days=7)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        to_update_xml = self.search([('state', '=', 'sent'), ('file_type', '=', 'xml'), ('create_date', '>=', date_min)])
        if to_update_xml:
            client = self.env.user.get_isaf_api(database=self.env.cr.dbname)
            if not client:
                n = 1
                while True:
                    client = self.env.user.get_isaf_api(account_no=n)
                    if client:
                        self.upload_xml(client, to_update_xml)
                        break
                    n += 1
                    if n > account_number_count:
                        break
            else:
                self.upload_xml(client, to_update_xml)

        to_update_ff = self.search([('state', '=', 'sent'), ('file_type', '=', 'ffdata')])
        url = 'https://deklaravimas.vmi.lt/EDSWebServiceUploadFile/EDSWebServiceUploadFile.asmx?wsdl'
        try:
            client = Client(url)
        except Exception as exc:
            _logger.info('VMI URL exception: %s' % (str(exc.args)))
            return False
        for rec in to_update_ff:
            track_num = rec.ext_id
            try:
                res_check = client.service.CheckFileState(track_num, 'ROBO',
                                                          self.env.user.eds_username, self.env.user.eds_password)
            except Exception as exc:
                _logger.info('%s exception: %s' % (rec.doc_name, str(exc.args)))
                res_check = {}
            message = 'VMI Atsakymas: '
            if res_check:
                res_check = dict(res_check)
                if res_check.get('Result', False):
                    state = 'confirmed'
                else:
                    state = 'rejected'
                message += res_check.get('Message', 'Nenumatyta klaida')
            else:
                state = 'sent'
                message += 'Laukiama'
            rec.write({'state': state,
                       'last_update_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                       'error_message': message})

    def upload_xml(self, client, to_update_xml):
        for rec in to_update_xml:
            track_num = rec.ext_id
            try:
                message = '''<?xml version="1.0" encoding="UTF-8"?><SOAP-ENV:Envelope xmlns:ns0="urn:isaf:uploader:v1" xmlns:ns1="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"><SOAP-ENV:Header/><ns1:Body><ns0:CheckStateRequest><ns0:trackingNumber>%s</ns0:trackingNumber></ns0:CheckStateRequest></ns1:Body></SOAP-ENV:Envelope>''' % track_num
                res_check = client.service.CheckState(__inject={'msg': message})
            except Exception as exc:
                _logger.info('VMI Update status Exception: %s. Tracking number: %s' % (str(exc.args), track_num))
                res_check = {}
            message = 'VMI Atsakymas: '
            if not res_check:
                state = 'sent'
                message += 'Laukiama'
            else:
                res_check = dict(res_check)
                status = res_check.get('state', res_check.get('operationStatus', False))
                try:
                    message += dict(res_check).get('errors').error[0].detail
                except:
                    if str(status) != 'ACCEPTED':
                        body = 'VMI EXPORT, UNEXPECTED STRUCTURE: %s' % str(res_check)
                        _logger.info(body)
                        message += 'Nenumatyta klaida'
                if not status:
                    body = 'VMI EXPORT, UNEXPECTED ERROR: %s' % str(res_check)
                    _logger.info(body)
                    continue
                if str(status) == 'ACCEPTED':
                    state = 'confirmed'
                elif str(status) in ['REJECTED', 'ERROR']:
                    state = 'rejected'
                else:
                    state = 'sent'
            rec.write({'state': state,
                       'last_update_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                       'error_message': message})

    def send_bug(self, body):
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'error_message': body,
        })


VMIDocumentExport()


# class iSAFTrackingNumbers(models.Model):
#     _name = 'isaf.tracking.number'
#
#     name = fields.Char(string='Sekimo kodas')
#     state = fields.Char(string='Būsena', default='UPLOADED')
#
#     @api.model
#     def cron_check_tracking_numbers(self):
#         for track_id in self.search([('state', '=', 'UPLOADED')]):
#             pass
#
#
# iSAFTrackingNumbers()
