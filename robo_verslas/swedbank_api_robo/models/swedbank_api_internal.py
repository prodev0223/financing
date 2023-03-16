# -*- encoding: utf-8 -*-
from odoo import fields, models, _, api, exceptions, tools, sql_db, SUPERUSER_ID
from datetime import datetime
import pytz
import os
import subprocess32 as subprocess
from lxml import etree, objectify
from lxml.etree import XMLSyntaxError
import logging
import base64
import psutil
import random
from dateutil.relativedelta import relativedelta
from six import iteritems
import traceback
import math

_logger = logging.getLogger(__name__)
swed_bic = '73000'
subprocess_timeout = 2*60  # 2 min

# Indicates for how long swed-bank files should be kept
# until their deletion (in days)
DAYS_TO_KEEP = 90

# Indicates a substring - if found in a file name,
# file is deleted ignoring DAYS_TO_KEEP parameter
SUBSTRING_TO_REMOVE = '__bal__'


# If this message was received in the response of the bank
# accountant should not be informed, since it's either duplicate
# payment or it was rejected in the bank itself
STATIC_RESPONSE_DRAFT_DISCARDED = 'Cancelled!'


def e_invoice_fail_reason_mapper(fail_reason, reason_type):
    reasons = {
        '51': 'Incorrect XML file structure',
        '0': 'An error code if any other error occurs, that is not defined in this table',
        '62': 'Oversized file is being sent',
        '59': 'No reference to the DTD or XSD file',
        '85': 'The file sender or receiver is indicated incorrectly',
        '64': 'A file with the same ID has already been received',
        '56': 'The total amount of the E-invoices does not coincide with the '
              'TotalAmount element available in the Footer',
        '58': 'File was received in via not agreed channel',
        '61': 'The total sum of the E-invoices does not coincide with the TotalNumberInvoices available in the Footer.',
        '81': 'The AppId field is filled in incorrectly',
        '63': 'The file name does not comply with the standard',
        '82': 'The file does not specify the E-invoice address (ChannelAddress)',
        '3': 'The indicated E-invoice address does not exist',
        '10': 'The indicated E-invoice address does not exist',
        '22': 'The E-invoice address is not intended for sending',
        '20': 'The E-invoice is temporarily unavailable (e.g. blocked user, blocked internet banking agreement)',
        '33': 'No possibility to present E-invoice for customer',
        '86': 'E-invoice accepted, but no possibility to present full E-invoice for customer.',
        '78': 'No e-invoice channel has been specified (ChannelId)',
        '65': 'E-invoice with same ID already exist in the file',
        '87': 'File already contains e-invoice with then same invoiceGlobUniqId or '
              'matching invoiceId and channelAddress',
        '80': 'The serviceID field is indicated incorrectly (Supplier indicated '
              'field ServiceId is validating accruing rules, that supplier has set)',
        '90': 'An incorrect templateId parameter - its format was not agreed upon with the bank',
        '94': 'InvoiceGlobUniqId may not be empty',
        '14': 'The data required for the processing off actoring are incorrect',
        '106': 'Duplicate E-invoice (in 5 day period there already was sent '
               'E-invoice to the same address, with the same invoice number and amount) Bank specific.',
        '11': 'The E-invoice Sender information in the Einvoice is indicated incorrectly (registrationNumber)',
        '57': 'The agreement between the E-invoice Sender and the Bank receiver '
              'has not been found (globalE- invoice SenderContractId)',
        '70': 'The E-invoice Sender does not have the right to send E-invoices',
        '25': 'The combination PresentmenType=No and Payable=No is not allowed. '
              'This is not applicable for credit E-invoices',
        '6': 'Incorrectly indicated PaymentRefId field (the reference number is inaccurate or inappropriate)',
        '50': 'The payment order fields do not have the payment order number '
              'and description PaymentRefId="", PaymentDescription="")',
        '9': 'An improper payment sum in the PaymentTotalSum box',
        '7': 'The currency indicated in the Currency box is incorrect',
        '49': 'The E-invoice payment date is illogical',
        '12': 'The E-invoice with the same PaymentId from the same E-invoice Sender already exists',
        '48': 'The PaymentId box is not indicated Bank specific. In Bank for this error will be used 51 error code.',
        '54': 'Incorrectly indicated receiver account PayToAccount',
        '55': 'The E-invoice Senders name PayToName is indicated incorrectly',
        '88': 'The PayToBIC is indicated incorrectly',
        '35': 'The accounts of the Customer and Einvoice Sender cant be the same Bank specific.',
        '96': 'No Payer name Bank specific. In Bank for this error will be used 51 error code.',
        '97': 'No E-invoice Sender name.',
        '98': 'InvoiceDate is not filled in',
        '91': 'No debit invoice which could be linked with the credit invoice',
        '92': 'The debit invoice linked with the credit invoice is already paid',
        '93': 'A credit invoice may not be Payable=Yes',
        '102': 'More than one invoice found. No invoices or automated payment orders cancelled',
        '103': 'Debit invoice cancelled, automated payment order not found',
        '104': 'Debit invoice cancelled, automated payment order not cancelled',
        '105': 'Invoice and automated payment order cancelled',
    }

    res = reasons.get(fail_reason) or 'Unexpected %s %s' % (reason_type, fail_reason)
    return res


def automated_payment_fail_reason_mapper(fail_reason, reason_type):
    reasons = {
        '1': 'Neteisinga XML duomenų bylos struktūra',
        '3': 'Dubliuota duomenų byla (duomenų byla su tuo pačiu senderId, fileId ir appId jau buvo gauta)',
        '2': 'E. sąskaitų siuntėjas neturi aktyvios E. sąskaitų pateikimo sutarties',
        '4': 'E. sąskaitų siuntėjas neturi aktyvios Automatinio mokėjimo sutarčių administravimo paslaugos',
        '7': 'Dubliuota Mokėjimo sutartis',
        '8': 'Keičiama Mokėjimo sutartis neegzistuoja',
        '9': 'Neleidžiamas banko sąskaitos tipas arba būsena',
        '10': 'Nurodyta mokėjimo diena (PaymentDay ) neatitinka reikalavimų',
        '11': 'Mokėjimo sutarties įsigaliojimo data (Startdate) yra praeityje',
        '12': 'Mokėjimo sutarties galiojimo pabaigos data (Enddate) '
              'yra ankstesnė nei sutarties įsigaliojimo data (Startdate).',
        '13': 'Neteisingai nurodytas mėnesio limitas (MonthLimit)',
        '14': 'Nesutampa sąskaitos savininko duomenys',
    }

    res = reasons.get(fail_reason, False) if reasons.get(fail_reason, False) else \
        'Unexpected %s %s' % (reason_type, fail_reason)
    return res


def check_soa_payment_report(data):
    """
    Method that checks whether passed file is SOA Payment Report, if yes return True - We ignore report files
    but we need to identify them so they are not passed to 'Error' folder in Swedbank structure
    :return: True or False
    """
    try:
        root = etree.fromstring(
            data, parser=etree.XMLParser(recover=True))
    except etree.XMLSyntaxError:
        return False
    try:
        tag = root.tag
    except AttributeError:
        return False
    if tag != 'EInvoiceSOAPaymentReport':
        return False
    else:
        return True


def random_name(size=15):
    digits = '0123456789'
    token = ''.join(random.SystemRandom().choice(digits) for i in xrange(size))
    return token


def get_transaction_state(parent_state, child_state):
    # todo ignore parent_state for now
    if child_state in ['PDNG']:
        return 'accepted'
    elif child_state in ['RJCT']:
        return 'rejected'
    elif child_state in ['ACCP', 'ACSP', 'ACWC', 'ACSC']:
        return 'processed'


def get_partial_state(state):
    """
    Map state string to specific partial state string
    :param state: state string
    :return: partial state string
    """
    partial_state_mapper = {'accepted': 'accepted_partial',
                            'rejected': 'rejected_partial',
                            'processed': 'processed_partial',
                            'revoked': 'revoked_partial'}
    return partial_state_mapper.get(state, 'no_action')


def parse(node, expected_type, date=False):
    if node is not None:
        if date:
            return node.text.replace('T', ' ')
        else:
            return node.text
    else:
        if date:
            return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        elif expected_type is int:
            return 0
        elif expected_type is str:
            return ''
        else:
            return False


def get_swed_data(env):
    """
    Method that fetches all of the SwedBank config data
    Key folders that must exist:
    root_directory-
        -received
        -sending
        -certs
        -processed
        -sent
    :return: SwedBank config data in dict format
    """
    config = env['ir.config_parameter'].sudo()
    return {
        'directory_path': config.get_param('swed_directory_path'),
        'cert_path': config.get_param('swed_cert_path'),
        'main_url': config.get_param('swed_main_url'),
    }


def xml_validator(some_xml_string, xsd_file=None):
    """
    Method that checks whether specific XML version passes the schema
    :return: True or False
    """
    try:
        schema = etree.XMLSchema(file=xsd_file)
        parser = objectify.makeparser(schema=schema)
        objectify.fromstring(some_xml_string, parser)
        return True
    except XMLSyntaxError:
        return False


def check_is_agreement_file(data):
    try:
        root = etree.fromstring(
            data, parser=etree.XMLParser(recover=True))
    except etree.XMLSyntaxError:
        return False
    try:
        if root.tag == 'GatewayAgreements':
            data = []
            agreements = root.findall('.//Agreement')
            for agreement in agreements:
                if agreement.get('closeAction', False):
                    close = True
                else:
                    close = False
                reg_num_node = agreement.find('RegistrationNumber')
                reg_num = reg_num_node.text if reg_num_node is not None else False
                data.append({
                    'agreement_id': agreement.get('id', False),
                    'company_code': reg_num,
                    'close': close
                })
            return data
    except Exception as exc:
        _logger.info('Agreement file checking exception: %s' % tools.ustr(exc))
        return False


def check_version(data):
    """
    Method that checks whether passed version can be validated in our system
    :return: True or False
    """
    is_052 = xml_validator(data, xsd_file=os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', 'xsd_schemas')) + '/camt.052.001.02.xsd')
    if is_052:
        return True
    is_053 = xml_validator(data, xsd_file=os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', 'xsd_schemas')) + '/camt.053.001.02.xsd')
    if is_053:
        return True
    is_053 = xml_validator(data, xsd_file=os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', 'xsd_schemas')) + '/camt.060.001.03.xsd')
    if is_053:
        return True
    return False


def extract_client_data(data):
    """
    Method that extracts IBAN number of corresponding company from XML file
    :return: IBAN in string format or False
    """
    existing_version = check_version(data)
    if not existing_version:
        return False
    try:
        root = etree.fromstring(
            data, parser=etree.XMLParser(recover=True))
    except etree.XMLSyntaxError:
        root = etree.fromstring(
            data.decode('iso-8859-15').encode('utf-8'))
    if root is None:
        raise exceptions.Warning(_('Netinkamas failo formatas'))
    try:
        ns = root.tag[1:root.tag.index("}")]
    except Exception as exc:
        _logger.info('Skipped SwedBank file import, error message: %s' % tools.ustr(exc))
        raise exceptions.Warning(_('Netinkamas failo formatas'))
    path = str('{' + ns + '}')
    iban_node = root.find('.//' + path + 'Stmt/' + path + 'Acct/' + path + 'Id/' + path + 'IBAN')
    currency_node = root.find('.//' + path + 'Stmt/' + path + 'Acct/' + path + 'Ccy')
    company_code_node = root.find('.//' + path + 'Stmt/' + path + 'Acct/' + path + 'Ownr/' + path +
                                  'Id/' + path + 'OrgId/' + path + 'Othr/' + path + 'Id')
    return_data = {}
    if iban_node is not None and currency_node is not None and company_code_node is not None:
        return_data['client_iban'] = iban_node.text
        return_data['iban_currency'] = currency_node.text
        return_data['company_code'] = company_code_node.text
    return return_data


def kill(proc_pid):
    """
    Kill process
    :return: None
    """
    process = psutil.Process(proc_pid)
    for proc in process.children(recursive=True):
        proc.kill()
    process.kill()


def handle_timeout(proc, seconds):
    """
    Wait for a process to finish, or kill it after timeout
    :return: None
    """
    try:
        proc.wait(seconds)
    except subprocess.TimeoutExpired:
        kill(proc.pid)


def rename_file(path, extra_kw, only_convert=False):
    """
    Add IBAN and Datetime to passed filename
    :return: file path
    """
    new_name = path + '_' + datetime.utcnow().strftime('%m-%d-%Y_%H:%M:%S') + '_' + extra_kw
    if not only_convert:
        os.rename(path, new_name)
    return path


class DatabaseMapper(models.Model):
    _inherit = 'database.mapper'

    swed_bank_agreement_id = fields.Integer(string='SwedBank Agreement ID', inverse='_set_swed_bank_agreement_id', groups='base.group_system', track_visibility='onchange')
    swedbank_ids = fields.One2many('swedbank.mapper', 'mapper_id')
    e_invoice_aggreement_number = fields.Char(string='eInvoice aggreement', inverse='_set_einvoice_aggreement', groups='base.group_system')
    e_invoice_aggreement_date = fields.Date(string='eInvoice aggreement date', inverse='_set_einvoice_aggreement', groups='base.group_system')
    automated_payment = fields.Boolean(string='Automatic payment agreement', inverse='_set_automated_payment',
                                       default=False, groups='base.group_system')
    automated_payment_enabled = fields.Boolean(string='Automatic payment enabled', groups='base.group_system')

    @api.one
    def _set_automated_payment(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        with api.Environment.manage():
            r_mapper = self.search([('database', '=', 'r')], limit=1)
            cr = sql_db.db_connect(r_mapper.sudo().database_url, allow_uri=True).cursor()
            env = api.Environment(cr, SUPERUSER_ID, {'lang': 'lt_LT'})
            partner_id = env['res.partner'].search([('kodas', '=', self.company_code)], limit=1)
            if partner_id:
                bank_id = env['res.partner.bank'].search(
                    [('partner_id', '=', partner_id.id), ('bank_id.bic', '=', 'HABALT22')], limit=1)
                if bank_id:
                    if self.automated_payment:
                        partner_id.write({
                            'automated_payment_agreed': True,
                            'res_partner_bank_e_invoice_id': bank_id.id,
                            'monthly_limit': math.ceil((self.fixed_payment * 3.0) / 100.0) * 100.0
                        })
                        self.automated_payment_enabled = True
                        cr.commit()
                    else:
                        partner_id.write({
                            'automated_payment_agreed': False,
                        })
                        cr.commit()
            cr.close()

    @api.one
    def _set_einvoice_aggreement(self):
        if not self.env.user.has_group('base.group_user'):
            return False
        with api.Environment.manage():
            cr = sql_db.db_connect(self.database_url, allow_uri=True).cursor()
            env = api.Environment(cr, SUPERUSER_ID, {'lang': 'lt_LT'})
            env.user.company_id.write({
                'activate_e_invoices': True,
                'e_invoice_agreement_date': self.e_invoice_aggreement_date,
                'global_e_invoice_agreement_id': self.e_invoice_aggreement_number
            })
            cr.commit()
            cr.close()

    @api.one
    def _set_swed_bank_agreement_id(self):
        if not self.env.user.has_group('base.group_user'):
            return False
        with api.Environment.manage():
            cr = sql_db.db_connect(self.database_url, allow_uri=True).cursor()
            env = api.Environment(cr, SUPERUSER_ID, {'lang': 'lt_LT'})
            company_id = env.user.company_id
            company_id.write({
                'swed_bank_agreement_id': self.swed_bank_agreement_id,
            })
            cr.commit()
            cr.close()


DatabaseMapper()


class SwedBankAPIExport(models.TransientModel):
    _name = 'swed.bank.export.internal'
    _description = 'Transient model that is used for automatic bank ' \
                   'statement exports from SwedBank using API solutions. Located in internal.'

    @api.model
    def inform_partner(self, env, message, partner):
        # If there's no partner email, use findir email
        email_to_use = partner.email
        if not email_to_use:
            email_to_use = env.user.sudo().company_id.findir.partner_id.email
        database = env.cr.dbname
        subject = '{} // [{}]'.format('Swedbank -- Atmestas(-i) mokėjimas(-ai)', database)
        self.env['script'].send_email(emails_to=[email_to_use],
                                      subject=subject,
                                      body=message)

    def update_object_status(self, obj_data, sepa_instruction_id, file_name, file_data):
        """
        Method that matches invoices or front bank statements by sepa instruction ID and updates their states
        based on received PAIN response file.
        :return: swed.bank.export.mapper records that were found
        """
        sender_iban = obj_data.get('sender_iban')
        mapper_id = self.env['swedbank.mapper'].get_mapper(sender_iban)
        if not mapper_id:
            self.env['script'].send_email(['support@robolabs.lt'],
                                          'SWEDBANK API alert',
                                          'Could not update payment status, because %s bank account was not found.' % sender_iban)
        state = obj_data.get('state')
        error_message = obj_data.get('error_message')

        # If we get the static response non inform, we force the state to
        # revoked (so export is possible again) form separate body message and
        # DO NOT inform the findir.
        base_message = 'Mokėjimo eksportavimas (-ai) į Swedbank buvo'
        if error_message == STATIC_RESPONSE_DRAFT_DISCARDED:
            state = 'revoked'
            body = base_message + ' priimtas (-i), tačiau jis buvo atšauktas naudotojo arba pažymėtas kaip dublikatas.'
        else:
            body = base_message + ' {}.\n'.format('atmestas (-i)' if state == 'rejected' else 'priimtas (-i)')
            if error_message:
                body += ' Klaidos pranešimas - {}\n'.format(error_message)

        data = {'mapper': mapper_id} if mapper_id else {}
        with api.Environment.manage():
            cr = sql_db.db_connect(mapper_id.database_url, allow_uri=True).cursor()
            env = api.Environment(cr, SUPERUSER_ID, {'lang': 'lt_LT'})
            ceo_part_id = env.user.company_id.vadovas.user_id.partner_id.ids
            main_acc_part_id = env['res.users'].search([('main_accountant', '=', True)]).mapped('partner_id.id')
            exports = env['bank.export.job'].search([
                ('sepa_instruction_id', '=', sepa_instruction_id),
                ('xml_file_download', '=', False),
                ('export_state', 'not in', ['file_export', 'no_action']),
            ])
            try:
                if not exports:
                    if state in ['rejected', 'rejected_partial']:
                        body = 'Atmestas mokėjimo siuntimas į Swedbank. Gavėjo sąskaita - %s, suma - %s %s, ' \
                               'mokėjimo data - %s' % (obj_data.get('receiver_iban'), obj_data.get('tr_amount'),
                                                       obj_data.get('tr_currency'), obj_data.get('tr_date'))
                        partner_ids = main_acc_part_id + ceo_part_id
                        env.user.company_id.post_announcement(
                            html=body, subject='Atmestas Swedbank mokėjimas', partner_ids=partner_ids)
                # Group exports by partner to which
                exports_by_partner = {}
                exports_by_state = {}
                for export in exports:
                    # Determine the state of the export
                    export_state = state
                    if export.partial_payment:
                        export_state = get_partial_state(state)
                    # Group exports by partner
                    exports_by_partner.setdefault(export.partner_id, export)
                    exports_by_partner[export.partner_id] |= export
                    # Group exports by state
                    exports_by_state.setdefault(export_state, export)
                    exports_by_state[export_state] |= export
                # Check if overall state is rejected
                if state in ['rejected', 'rejected_partial']:
                    # Loop through grouped records and send messages
                    for partner, exports in exports_by_partner.items():
                        attachments = [('swedbank_export.xml', file_data)]
                        failed_inv = failed_aml = failed_statements = str()
                        invoices = exports.mapped('invoice_ids')
                        if invoices:
                            # Post general message to the invoices, and include the attachment
                            for invoice in invoices:
                                invoice.robo_message_post(
                                    subtype='mt_comment', body=body, priority='low', attachments=attachments)
                            failed_inv = 'Saskaitos faktūros -- {}\n\n'.format(
                                ', '.join([inv.reference or inv.number for inv in invoices])
                            )
                        # We only want to display AMLs if they are not
                        # related to current invoice batch
                        move_lines = exports.mapped('move_line_ids')
                        if move_lines and not invoices:
                            # Post general message to the moves, and include the attachment
                            for move in move_lines.mapped('move_id'):
                                move.robo_message_post(
                                    subtype='mt_comment', body=body, priority='low', attachments=attachments)
                            failed_aml = 'Žurnalo elementai -- {}\n\n'.format(
                                ', '.join(move_lines.mapped('name'))
                            )
                        front_statements = exports.mapped('front_statement_line_id.statement_id')
                        if front_statements:
                            failed_statements = 'Mokėjimo ruošiniai -- {}\n\n'.format(
                                ', '.join(front_statements.mapped('name'))
                            )
                        if failed_aml or failed_inv or failed_statements:
                            final_msg = body + failed_inv + failed_aml + failed_statements
                            self.inform_partner(env, final_msg, partner)
                # Write the states
                for exp_state, rel_exports in exports_by_state.items():
                    rel_exports.write({'export_state': exp_state, 'last_error_message': error_message})
                # Post messages to exports
                exports.post_message_to_related()
            except Exception as exc:
                _logger.info('Exception: %s\nTraceback: %s', exc, traceback.format_exc())
                data.update({'external_failure': True})
                cr.rollback()
            if mapper_id:
                data.update({'related_ids': exports.ids})
            # Only commit after one file was successfully processed
            cr.commit()
            cr.close()
        return data

    def process_pain_response(self, data, file_name):
        """
        Method that checks whether passed file is pain response, and if it is,
        checks whether file is accepted or rejected and updates corresponding object states.
        :return: False if file is not PAIN, otherwise True
        """
        filedata = data
        is_pain_file = xml_validator(data, xsd_file=os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', 'xsd_schemas')) + '/pain.001.001.03.xsd')
        if not is_pain_file:
            is_pain_file = xml_validator(data, xsd_file=os.path.abspath(
                os.path.join(os.path.dirname(__file__), '..', 'xsd_schemas')) + '/pain.002.001.03.xsd')
            if not is_pain_file:
                return False
        try:
            root = etree.fromstring(
                data, parser=etree.XMLParser(recover=True))
        except etree.XMLSyntaxError:
            return False
        try:
            ns = root.tag[1:root.tag.index("}")]
            path = str('{' + ns + '}')
        except Exception as exc:
            _logger.info('Skipped SwedBank file import, error message: %s' % tools.ustr(exc))
            return False
        try:
            status_report = root.find('.//' + path + 'CstmrPmtStsRpt/' + path + 'OrgnlGrpInfAndSts')
            if status_report is None:
                return False
            payment_status = status_report.find(path + 'GrpSts')
            if payment_status is None:
                status_report = root.find('.//' + path + 'CstmrPmtStsRpt/' + path + 'OrgnlPmtInfAndSts')
                payment_status = status_report.find(path + 'PmtInfSts')
            if payment_status is not None:
                parent_state = payment_status.text
                transaction_reports = root.findall('.//' + path + 'CstmrPmtStsRpt/' + path +
                                                   'OrgnlPmtInfAndSts/' + path + 'TxInfAndSts')
                export_objects = {}
                for tr_report in transaction_reports:
                    export_id = tr_report.find(path + 'OrgnlInstrId').text
                    child_state = tr_report.find(path + 'TxSts').text
                    tr_state = get_transaction_state(parent_state, child_state)
                    error_message = parse(tr_report.find(path + 'StsRsnInf/' + path + 'AddtlInf'), str) \
                        if tr_state in ['rejected'] else str()
                    curr_node = tr_report.find(path + 'OrgnlTxRef/' + path + 'Amt/' + path + 'InstdAmt')
                    data = {
                        'sender_iban': parse(tr_report.find(path + 'OrgnlTxRef/' + path +
                                                            'DbtrAcct/' + path + 'Id/' + path + 'IBAN'), str),
                        'receiver_iban': parse(tr_report.find(path + 'OrgnlTxRef/' + path + 'CdtrAcct/' +
                                                              path + 'Id/' + path + 'IBAN'), str),
                        'state': tr_state,
                        'tr_amount': parse(tr_report.find(path + 'OrgnlTxRef/' + path + 'Amt/' +
                                                          path + 'InstdAmt'), int),
                        'tr_currency': curr_node.attrib.get('Ccy') if curr_node is not None else 'EUR',
                        'tr_date': parse(tr_report.find(path + 'OrgnlTxRef/' + path + 'ReqdExctnDt'), str),
                        'error_message': error_message,
                    }
                    record_data = self.update_object_status(
                        obj_data=data, sepa_instruction_id=export_id, file_name=file_name, file_data=filedata)

                    # If we get external failure we return False without updating anything
                    if record_data.get('external_failure'):
                        return False

                    # Returned data is of such format - {'mapper_id': SWED_MAPPER_RECORD, 'related_ids': [1, 2, 3..]}
                    if record_data:
                        export_objects.setdefault(record_data['mapper'], [])
                        export_objects[record_data['mapper']] += record_data['related_ids']

                if export_objects:
                    for mapper, bank_export_ids in iteritems(export_objects):
                        with api.Environment.manage():
                            cr = sql_db.db_connect(mapper.database_url, allow_uri=True).cursor()
                            env = api.Environment(cr, SUPERUSER_ID, {'lang': 'lt_LT'})
                            try:
                                bank_exports = env['bank.export.job'].browse(bank_export_ids)
                                bank_exports.inform_ceo()
                                cr.commit()
                            except Exception as exc:
                                _logger.info(
                                    'SWED CEO Informing Exception: %s\nTraceback: %s', exc, traceback.format_exc())
                                cr.rollback()
                            cr.close()
                return True
            else:
                body = 'Swedbank API Error: Bank returned corrupt PAIN file. File name - %s' % file_name
                self.env['script'].send_email(['support@robolabs.lt'],
                                              u'Swedbank API - Rejected PAIN file.',
                                              body)
                return False
        except Exception as exc:
            _logger.info('Pain file checking exception: %s' % tools.ustr(exc))
            return False

    def process_balance_response(self, data, file_name):
        if not xml_validator(data, xsd_file=os.path.abspath(
                os.path.join(os.path.dirname(__file__), '..', 'xsd_schemas')) + '/camt.052.001.02.xsd'):
            try:
                root = etree.fromstring(
                    data, parser=etree.XMLParser(recover=True))
            except etree.XMLSyntaxError:
                _logger.info('SWEDBANK API: XMLSyntaxError')
                return False
            error_code = root.find('.//HGWError/Code')
            if error_code is not None:
                if 'AccountNotAllowed' in error_code.text:
                    body = 'Swedbank API Info: Bank refused to return balance due to access rights. File name - %s' % file_name
                    _logger.info(body)
                    # self.env['script'].send_email(['support@robolabs.lt'],
                    #                               u'Swedbank API - Balance.', body)
            return False
        try:
            root = etree.fromstring(
                data, parser=etree.XMLParser(recover=True))
        except etree.XMLSyntaxError:
            _logger.info('SWEDBANK API: XMLSyntaxError')
            return False
        try:
            ns = root.tag[1:root.tag.index("}")]
            path = str('{' + ns + '}')
        except Exception as exc:
            _logger.info('Skipped SwedBank file import, error message: %s' % tools.ustr(exc))
            return False

        rpt_vals = root.findall('.//' + path + 'BkToCstmrAcctRpt/' + path + 'Rpt')
        if rpt_vals is None:
            _logger.info('SWEDBANK API: no rpt_vals')
            return False
        data = []
        for rpt_val in rpt_vals:
            acct = rpt_val.find(path + 'Acct')
            if acct is None:
                body = 'Swedbank API Info: Corrupt BAL FILE. No Acct was found - %s' % file_name
                self.env['script'].send_email(['support@robolabs.lt'],
                                              u'Swedbank API - Balance.', body)
            company_iban = parse(acct.find(path + 'Id/' + path + 'IBAN'), str)
            company_code = parse(acct.find(path + 'Ownr/' + path + 'Id/' + path + 'OrgId/' +
                                           path + 'Othr/' + path + 'Id'), str)
            balance_date = parse(rpt_val.find(path + 'CreDtTm'), str)
            bal_vals = rpt_val.findall(path + 'Bal')
            balances = []
            for bal_val in bal_vals:
                # todo fetch all balances, however only ITAV is used for now
                bal_tp = bal_val.find(path + 'Tp/' + path + 'CdOrPrtry/' + path + 'Prtry')
                if bal_tp is None:
                    bal_tp = bal_val.find(path + 'Tp/' + path + 'CdOrPrtry/' + path + 'Cd')
                balance = {
                    'bal_type': parse(bal_tp, str),
                    'bal_amount': parse(bal_val.find(path + 'Amt'), int),
                    'bal_currency': bal_val.find(path + 'Amt').attrib.get('Ccy') if
                    bal_val.find(path + 'Amt') is not None else 'EUR',
                }
                balances.append(balance)
            data.append({
                'bank_iban': company_iban,
                'company_code': company_code,
                'balance_date': balance_date,
                'balances': balances
            })
        for line in data:
            company_code = line.get('company_code')
            balance_date = line.get('balance_date', '').replace('T', ' ')
            balance_date_dt = datetime.strptime(balance_date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            offset = int(datetime.now(pytz.timezone('Europe/Vilnius')).strftime('%z')[1:3])
            balance_date_dt -= relativedelta(hours=offset)
            balance_date = balance_date_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            bank_iban = line.get('bank_iban')
            balance_data = filter(lambda x: x['bal_type'] == 'ITAV', line['balances'])
            if not balance_data:
                balance_data = filter(lambda x: x['bal_type'] == 'ITBD', line['balances'])
            balance_amount = float(balance_data[0].get('bal_amount', 0.0))
            balance_currency = balance_data[0].get('bal_currency', 'EUR')
            mapper = self.env['database.mapper'].search(
                [('company_code', '=', company_code), ('swed_bank_agreement_id', '!=', False)])
            if len(mapper) != 1:
                self.env['script'].send_email(['support@robolabs.lt'],
                                              u'SWEDBANK API alert',
                                              u'Could not find a client for %s bank account. Company code: %s.' % (
                                              bank_iban, company_code))
                continue
            with api.Environment.manage():
                cr = sql_db.db_connect(mapper.database_url, allow_uri=True).cursor()
                env = api.Environment(cr, SUPERUSER_ID, {'lang': 'lt_LT'})
                journal_obj = env['account.journal']
                bank_id = env['res.bank'].search([('kodas', '=', '73000')], limit=1)
                try:
                    if not bank_id:
                        self.env['script'].send_email(['support@robolabs.lt'],
                                                      u'SWEDBANK API alert',
                                                      u'Could not find a bank for %s bank account. Company code: %s.' % (
                                                          bank_iban, company_code))
                        continue
                    domain = [('type', '=', 'bank'), ('bank_id', '=', bank_id.id),
                                                     ('bank_acc_number', '=', bank_iban)]
                    if balance_currency == 'EUR':
                        domain += [('currency_id', '=', False)]
                    else:
                        domain += [('currency_id.name', '=', balance_currency)]
                    journal_id = journal_obj.search(domain)
                    if not journal_id:
                        _logger.info('SWEDBANK API: Could not find bank account %s in %s database' % (bank_iban, cr.dbname))
                        continue  # alert: we do not inform, should be automatically created with periodic import
                    journal_id.write({
                        'api_balance_update_date': balance_date,
                        'api_end_balance': balance_amount
                    })
                    cr.commit()
                except Exception as exc:
                    cr.rollback()
                    body = 'SwedBank -- Automatic CronJob fail: process_balance_response was not ' \
                           'successful. Error: %s.' % exc
                    subject = 'SwedBank -- Automatic CronJob, process_balance_response fail'
                    self.env['script'].send_email(['support@robolabs.lt'],
                                                  subject,
                                                  body)
                cr.close()
        return True

    def process_e_invoice_response(self, data, file_name):
        try:
            root = etree.fromstring(
                data, parser=etree.XMLParser(recover=True))
        except etree.XMLSyntaxError:
            return False
        try:
            tag = root.tag
        except AttributeError:
            return False
        if tag not in ['FailedInvoice', 'EinvoiceIncoming']:
            return False
        if tag == 'EinvoiceIncoming':
            try:
                einvoice_contract = root.find('.//ContractId').text
                date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                company_code = einvoice_contract[:9]
                mapper_id = self.env['database.mapper'].search([('company_code', '=', company_code)], limit=1)
                if mapper_id:
                    mapper_id.write({
                        'e_invoice_aggreement_number': einvoice_contract,
                        'e_invoice_aggreement_date': date
                    })
            except:
                body = 'Swedbank API Error: Contract ID undefined' \
                       'File name - %s' % file_name
                self.env['script'].send_email(['support@robolabs.lt'], body=body,
                                              subject='Swedbank API - Contract ID undefined.')
                return False
            return
        else:
            header = root.find('.//Header')
            if header is None:
                return False
            fail_reason = header.attrib.get('fileFailReason', False)
            file_id = header.attrib.get('infileId', '')
            failed_numbers = {}
            parent_fail_message = str()
            if not file_id:
                body = 'Swedbank API Error: eInvoice Got empty file ID. ' \
                       'File name - %s' % file_name
                self.env['script'].send_email(['support@robolabs.lt'], body=body, subject='Swedbank API - Corrupt eInvoice.')
                return False
            if not fail_reason:
                try:
                    tot_count = int(root.find('.//Footer').attrib.get('totalNr'))
                except AttributeError:
                    body = 'Swedbank API Error: Got a corrupt eInvoice. Cant fetch Total Failed Count. ' \
                           'File name - %s' % file_name
                    self.env['script'].send_email(['support@robolabs.lt'], body=body, subject='Swedbank API - Corrupt eInvoice.')
                    return False
                if tot_count:
                    parent_status = 'failed_partial'
                    invoices = root.findall('.//Invoice')
                    for invoice in invoices:
                        unique_id = parse(invoice.find('.//InvoiceGlobUniqId'), str)
                        fail_reason_inv = parse(invoice.find('.//FailReason'), str)
                        reason = e_invoice_fail_reason_mapper(fail_reason_inv, 'FailReason')
                        failed_numbers.update({unique_id: reason})
                        # body = 'Swedbank API Error: Got a failed eInvoice. error - %s ' \
                        #        'File name - %s' % (reason, file_name)
                        # self.env['script'].send_email(['support@robolabs.lt'], body=body,
                        #                               subject='Swedbank API - Corrupt eInvoice.')
                else:
                    parent_status = 'success_all'
            else:
                reason = e_invoice_fail_reason_mapper(fail_reason, 'FileFailReason')
                parent_fail_message = reason
                body = 'Swedbank API Error: Got a failed eInvoice. error - %s ' \
                       'File name - %s' % (reason, file_name)
                self.env['script'].send_email(['support@robolabs.lt'], body=body,
                                              subject='Swedbank API - Corrupt eInvoice.')
                parent_status = 'failed_all'
        try:
            database_name = file_id.split('__')[1]
        except IndexError:
            body = 'Swedbank API Error: Got an eInvoice with corrupt FILE ID.' \
                   ' File name - %s, FILE ID - %s' % (file_name, file_id)
            self.env['script'].send_email(['support@robolabs.lt'], body=body, subject='Swedbank API - Instruction ID mismatch.')
            return

        mapper = self.env['database.mapper'].search([('database', '=', database_name)], limit=1)
        if mapper:
            with api.Environment.manage():
                cr = sql_db.db_connect(mapper.database_url, allow_uri=True).cursor()
                env = api.Environment(cr, SUPERUSER_ID, {'lang': 'lt_LT'})
                # Find all exports for e_invoices with current file ID
                exports = env['bank.export.job'].search(
                    [('e_invoice_file_id', '=', file_id), ('export_data_type', '=', 'e_invoice')])
                if exports:
                    try:
                        if parent_status in ['success_all', 'failed_all']:
                            state = 'rejected' if parent_status == 'failed_all' else 'accepted'
                            exports.write({'export_state': state, 'last_error_message': parent_fail_message})
                        else:
                            for export in exports:
                                if export.e_invoice_global_unique_id in failed_numbers:
                                    error_message = failed_numbers[export.e_invoice_global_unique_id]
                                    export.write({'export_state': 'rejected', 'last_error_message': error_message})
                                else:
                                    export.write({'export_state': 'accepted'})
                        exports.post_message_to_related()
                        cr.commit()
                    except Exception as exc:
                        cr.rollback()
                        self.env['script'].send_email(['support@robolabs.lt'], body='Exception: %s' % tools.ustr(exc),
                                                      subject='Swedbank API - Failed updating client DB %s.' % database_name)
                else:
                    body = 'Swedbank API Error: Got an eInvoice FILE ID that does not match ' \
                           'any entries in the system. File name - %s, FILE ID - %s' % (file_name, file_id)
                    self.env['script'].send_email(['support@robolabs.lt'], body=body, subject='Swedbank API - Instruction ID mismatch.')
        else:
            self.env['script'].send_email(['support@robolabs.lt'], body='Could not find database with this name "%s"' % database_name,
                                          subject='Swedbank API - database not found.')
        return True

    def process_e_invoice_application_response(self, xml_data, file_name):
        try:
            root = etree.fromstring(
                xml_data, parser=etree.XMLParser(recover=True))
        except etree.XMLSyntaxError:
            return False
        try:
            tag = root.tag
        except AttributeError:
            return False
        if tag != 'ApplicationBank':
            return False
        application_roots = root.findall('.//Application')
        if not application_roots or application_roots is None:
            return False
        application_data = []
        for node in application_roots:
            seller_reg = parse(node.find('SellerRegNumber'), str)
            seller_contract_id = parse(node.find('GlobalSellerContractId'), str)
            buyer_iban = parse(node.find('ChannelAddress'), str)
            if not seller_reg or not seller_contract_id or not buyer_iban:
                # Crucial field checker
                body = 'Swedbank API Error: Got Corrupt application file.' \
                       'Missing crucial fields. File name - %s' % file_name
                self.env['script'].send_email(['support@robolabs.lt'],
                                              u'Swedbank API - Application fields.',
                                              body)
                continue

            application_data.append({
                'seller_company_code': seller_reg,
                'seller_contract_id': seller_contract_id,
                'action': parse(node.find('Action'), str),
                'service_id': parse(node.find('ServiceId'), str),
                'buyer_iban': buyer_iban,
                'buyer_presentment_type': parse(node.find('PresentmentType'), str),
                'buyer_company_code': parse(node.find('CustomerIdCode'), str),
                'buyer_name': parse(node.find('CustomerName'), str),
                'buyer_email': parse(node.find('CustomerEmail'), str),
                'application_date': parse(node.find('TimeStamp'), str, date=True),
            })

        for data in application_data:
            company_code = data.get('seller_company_code')
            buyer_company_code = data.get('buyer_company_code')
            e_invoice_service_id = data.get('service_id')
            buyer_name = data.get('buyer_name', '').upper()
            buyer_email = data.get('buyer_email')
            mapper = self.env['database.mapper'].search(
                [('company_code', '=', company_code)])
            if len(mapper) != 1:
                self.env['script'].send_email(['support@robolabs.lt'],
                                              u'SWEDBANK API alert',
                                              u'Could not find a client. Data: %s.' % (
                                                  data))
                continue
            with api.Environment.manage():
                cr = sql_db.db_connect(mapper.database_url, allow_uri=True).cursor()
                env = api.Environment(cr, SUPERUSER_ID, {'lang': 'lt_LT'})
                partner_obj = env['res.partner']
                periodic_obj = env['periodic.invoice']
                partner = partner_obj.search([('kodas', '=', buyer_company_code)], limit=1)
                if not partner and e_invoice_service_id:
                    partner = partner_obj.search([('e_invoice_service_id', '=', e_invoice_service_id)], limit=1)
                if not partner:
                    partner = partner_obj.search([('sanitized_name', '=ilike', buyer_name)])
                    if len(partner) > 1:
                        partner = partner_obj
                if not partner and buyer_email:
                    partner = partner_obj.search([('email', '=', buyer_email)])
                    if len(partner) > 1:
                        partner = partner_obj
                if not partner:
                    try:
                        partner = partner_obj.create({
                            'kodas': buyer_company_code,
                            'e_invoice_service_id': e_invoice_service_id,
                            'name': buyer_name,
                            'is_company': False,
                        })
                        partner.vz_read()
                    except Exception as exc:
                        cr.rollback()
                        body = 'Swedbank API Error: Could not create the partner. ' \
                               'in the client system (%s). File name - %s. Detailed error - %s' % \
                               (company_code, file_name, exc)
                        self.env['script'].send_email(['support@robolabs.lt'],
                                                      u'Swedbank API - Application fields.',
                                                      body,
                                                      attachments=[(0, 0, {
                                                          'name': 'swedbank.xml',
                                                          'datas_fname': 'swedbank.xml',
                                                          'type': 'binary',
                                                          'datas': base64.b64encode(xml_data)
                                                      })],
                                                      )
                        continue
                if data.get('action') in ['ADD']:
                    bank_id = partner.bank_ids.filtered(lambda x: x.acc_number == data.get('buyer_iban'))
                    if not bank_id:
                        bank_id = env['res.partner.bank'].create({'acc_number': data.get('buyer_iban'),
                                                                  'partner_id': partner.id})
                        bank_id.onchange_acc_number()
                    partner.write({'send_e_invoices': True,
                                   'e_invoice_application_date': data.get('application_date'),
                                   'res_partner_bank_e_invoice_id': bank_id.id})

                elif data.get('action') in ['DEL']:
                    partner.write({'send_e_invoices': False, 'e_invoice_application_date': False})
                    periodic_obj.search([('partner_id', '=', partner.id), ('create_einvoice', '=', True)]).write({
                        'create_einvoice': False
                    })
                cr.commit()
                cr.close()
        return True

    def process_automated_e_invoice_payment_response(self, data, file_name):
        try:
            root = etree.fromstring(
                data, parser=etree.XMLParser(recover=True))
        except etree.XMLSyntaxError:
            return False
        try:
            tag = root.tag
        except AttributeError:
            return False
        if tag != 'EinvoiceStandingOrderAgreementResponse':
            return False
        header = root.find('.//Header')
        if header is None:
            return False
        fail_reason = header.attrib.get('fileFailReason', False)
        file_id = header.attrib.get('infileId', '')
        failed_numbers = {}
        parent_fail_message = str()
        if not file_id:
            body = 'Swedbank API Error: AutoPayment Agreement response Got empty file ID. ' \
                   'File name - %s' % file_name
            self.env['script'].send_email(['support@robolabs.lt'],
                                          u'Swedbank API - Corrupt AutoPayment response.',
                                          body)
            return False
        if not fail_reason:
            try:
                tot_count = int(root.find('.//Footer').attrib.get('totalNr'))
            except AttributeError:
                body = 'Swedbank API Error: Got a corrupt AutoPayment. Cant fetch Total Failed Count. ' \
                       'File name - %s' % file_name
                self.env['script'].send_email(['support@robolabs.lt'],
                                              u'Swedbank API - Corrupt AutoPayment response.',
                                              body)
                return False
            if tot_count:
                parent_status = 'failed_partial'
                agreements = root.findall('.//Agreement')
                for agreement in agreements:
                    partner_id = parse(agreement.find('.//ServiceId'), str)
                    fail_reason_agr = parse(agreement.find('.//FailureCode'), str)
                    # reason = automated_payment_fail_reason_mapper(fail_reason_agr, 'FailReason')
                    failed_numbers.update({partner_id: fail_reason_agr})
            else:
                parent_status = 'success_all'
        else:
            reason = automated_payment_fail_reason_mapper(fail_reason, 'FileFailReason')
            body = 'Swedbank API Error: Got a failed AutoPayment. error - %s ' \
                   'File name - %s' % (reason, file_name)
            parent_fail_message = reason
            self.env['script'].send_email(['support@robolabs.lt'],
                                          u'Swedbank API - Failed AutoPayment response.',
                                          body)
            parent_status = 'failed_all'

        try:
            database_name = file_id.split('__')[1]
        except IndexError:
            body = 'Swedbank API Error: Got an AutoPayment with corrupt FILE ID.' \
                   ' File name - %s, FILE ID - %s' % (file_name, file_id)
            self.env['script'].send_email(['support@robolabs.lt'],
                                          u'Swedbank API - Instruction ID mismatch.',
                                          body)
            return

        mapper = self.env['database.mapper'].search(
            [('database', '=', database_name), ('swed_bank_agreement_id', '!=', False)])
        if len(mapper) != 1:
            self.env['script'].send_email(['support@robolabs.lt'],
                                          u'SWEDBANK API alert',
                                          u'Could not find a client with %s database name.' %
                                          database_name)
            return
        with api.Environment.manage():
            cr = sql_db.db_connect(mapper.database_url, allow_uri=True).cursor()
            env = api.Environment(cr, SUPERUSER_ID, {'lang': 'lt_LT'})
            exports = env['bank.export.job'].search(
                [('e_invoice_file_id', '=', file_id), ('export_data_type', '=', 'automatic_e_invoice_payment')])
            partners = exports.mapped('e_invoice_auto_payment_partner_id')
            if exports:
                if parent_status in ['success_all', 'failed_all']:
                    failed = parent_status == 'failed_all'
                    partners.reverse_auto_payment_write(failed=failed)
                    exports.write({
                        'export_state': 'rejected' if failed else 'accepted',
                        'last_error_message': parent_fail_message,
                    })
                else:
                    for export in exports:
                        failed = export.e_invoice_global_unique_id in failed_numbers
                        error = failed_numbers.get(export.e_invoice_global_unique_id, str())
                        export.write({'export_state': 'rejected' if failed else 'accepted', 'last_error_message': error})
                        export.e_invoice_auto_payment_partner_id.reverse_auto_payment_write(failed=failed)
                exports.post_message_to_related()
            else:
                body = 'Swedbank API Error: Got an AutoPayment response FILE ID that does not match ' \
                       'any entries in the system. File name - %s, FILE ID - %s' % (file_name, file_id)
                self.env['script'].send_email(['support@robolabs.lt'],
                                              u'Swedbank API - Instruction ID mismatch.',
                                              body)
            cr.commit()
            cr.close()
        return True

    @api.model
    def cron_fetch_statements(self):
        """
        Method that is used to fetch requested bank statement XML files to the system.
        Fetches XML files matching CAMT schema.
        :return: None
        """

        sd = get_swed_data(self.env)
        os.chdir(sd.get('directory_path'))
        if not os.path.isdir(sd.get('directory_path') + '/received'):
            os.mkdir(sd.get('directory_path') + '/received')
        if os.path.isfile('receive.sh'):
            command = './receive.sh url=%s dir=received cert=certs/%s' % \
                      (sd.get('main_url'), sd.get('cert_path'))
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=None, executable='/bin/bash', shell=True)
            handle_timeout(process, subprocess_timeout)
        else:
            raise exceptions.Warning(_('File receive.sh is not found!'))

    @api.model
    def cron_collect_statements(self):
        """
        Method that is used to collect fetched bank statement files. After file collection method calls
        coda_parsing function which creates bank statements in the system
        :return: None
        """
        # File limit in one cron run
        file_limit = 40
        sd = get_swed_data(self.env)
        path = sd.get('directory_path') + '/received'
        statement_file_paths = []

        collected_files = []
        for r, d, f in os.walk(path):
            for st_file in f:
                if '.xml' in st_file.lower():
                    f_path = os.path.join(r, st_file)
                    c_time = os.path.getctime(f_path)
                    statement_file_paths.append((f_path, st_file, c_time))
                    collected_files.append(st_file)
                    # We only care about breaking this inner loop
                    if len(statement_file_paths) >= file_limit:
                        break

        statement_file_paths = sorted(statement_file_paths, key=lambda x: x[2])
        statements_base64 = []
        for file_path in statement_file_paths:
            with open(file_path[0], 'rb') as st_file:
                st_base_64 = st_file.read().encode('base64')
                statements_base64.append((st_base_64, file_path[0], file_path[1]))

        valid_statement_list = []
        files_to_keep = []
        for st_b64, file_path, file_name in statements_base64:
            xml_stream = base64.b64decode(st_b64)
            client_data = extract_client_data(xml_stream)
            if client_data:
                extracted_iban = client_data.get('client_iban')
                company_code = client_data.get('company_code')
                iban_currency = client_data.get('iban_currency')
                if extracted_iban and extracted_iban not in file_path:
                    file_path_re = rename_file(file_path, extracted_iban)
                    file_name_re = rename_file(file_name, extracted_iban, only_convert=True)
                else:
                    file_path_re = file_path
                    file_name_re = file_name
                valid_statement_list.append({'xml_file_path': file_path_re, 'xml_b64': st_b64,
                                             'xml_iban': extracted_iban, 'file_name': file_name_re,
                                             'company_code': company_code, 'iban_currency': iban_currency})
            else:
                if not self.process_pain_response(xml_stream, file_name) and not \
                        self.process_balance_response(xml_stream, file_name) and not \
                        self.process_e_invoice_response(xml_stream, file_name) and not \
                        self.process_e_invoice_application_response(xml_stream, file_name) and not \
                        self.process_automated_e_invoice_payment_response(xml_stream, file_name) and not \
                        check_soa_payment_report(xml_stream):
                    data = check_is_agreement_file(xml_stream)
                    if data:
                        for agreement in data:
                            company_code = agreement.get('company_code', False)
                            agreement_id = agreement.get('agreement_id', False)
                            close = agreement.get('close', False)
                            if company_code and agreement_id:
                                db_id = self.env['database.mapper'].search([('company_code', '=', company_code)])
                                if not close:
                                    db_id.write({'swed_bank_agreement_id': agreement_id})
                                else:
                                    db_id.write({'swed_bank_agreement_id': False})
                                if not db_id:
                                    self.env['script'].send_email(['support@robolabs.lt'],
                                                                  u'SWEDBANK API alert',
                                                                  u'Could not find a client (company code: %s) for %s contract number.' % (company_code, agreement_id),
                                                                  attachments=[(0, 0, {
                                                                      'name': 'swedbank.xml',
                                                                      'datas_fname': 'swedbank.xml',
                                                                      'type': 'binary',
                                                                      'datas': st_b64
                                                                  })],
                                                                  )
                    else:
                        files_to_keep.append(file_name)
        for file_data in valid_statement_list:
            company_code = file_data.get('company_code')
            iban_currency = file_data.get('iban_currency')
            xml_iban = file_data.get('xml_iban')
            mapper = self.env['database.mapper'].search([('company_code', '=', company_code), ('swed_bank_agreement_id', '!=', False)])
            if len(mapper) != 1:
                self.env['script'].send_email(['support@robolabs.lt'],
                                              u'SWEDBANK API alert',
                                              u'Could not find a client for %s bank account. Company code: %s.' % (xml_iban, company_code))
                files_to_keep.append(file_data.get('file_name'))
                continue
            with api.Environment.manage():
                with sql_db.db_connect(mapper.database_url, allow_uri=True).cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {'lang': 'lt_LT'})
                    journal_obj = env['account.journal']
                    fetch_jobs = env['bank.statement.fetch.job']
                    bank_id = env['res.bank'].search([('kodas', '=', '73000')], limit=1)
                    try:
                        if not bank_id:
                            raise exceptions.UserError(_('Swedbank bank was not found'))
                        currency_id = env['res.currency'].search([('name', '=', iban_currency)], limit=1)
                        if not currency_id:
                            raise exceptions.UserError(_('Currency not found'))
                        domain = [
                            # ('type', '=', 'bank'), #  make domain wider as some bank accounts are not reconciled
                            ('bank_id.kodas', '=', '73000'),
                            ('bank_acc_number', '=', xml_iban),
                            ('currency_id', '=', False if iban_currency == 'EUR' else currency_id.id)
                        ]
                        journal = journal_obj.search(domain, limit=1)
                        if journal and journal.type != 'bank':
                            continue

                        file_data = file_data.get('xml_b64')
                        # Check for statement fetch jobs for this specific journal
                        # It will usually only be one job, but in case of multiple
                        # and since there's no end to end traceability, we just update all of them
                        fetch_jobs = env['bank.statement.fetch.job'].search(
                            [('state', '=', 'in_progress_external'), ('journal_id', '=', journal.id)],
                            limit=1, order='create_date asc'
                        )
                        fetch_jobs.write({
                            'fetched_file': file_data,
                            'fetched_file_name': 'Swed Statement.xml'.format(journal.name),
                        })
                        wizard = env['account.sepa.import'].create({
                            'coda_data': file_data,
                            'skip_currency_rate_checks': True,
                        })
                        wizard.coda_parsing()
                        fetch_jobs.close_statement_fetch_job(state='succeeded', error_message=str())
                        cr.commit()
                        env.all.todo = {}
                        env.cache.clear()
                    except Exception as exc:
                        cr.rollback()
                        env.all.todo = {}
                        env.cache.clear()
                        # Write failed state to the related Jobs
                        error_message = _('Išrašų traukimo klaida - {}').format(tools.ustr(exc))
                        if fetch_jobs:
                            fetch_jobs.close_statement_fetch_job(state='failed', error_message=error_message)
                            cr.commit()
                        try:
                            file_name = file_data.get('file_name')
                            xml_b64 = file_data.get('xml_b64')
                        except:
                            file_name = '-'
                            xml_b64 = file_data
                        body = 'SwedBank -- Automatic CronJob fail: Fetching of files was ' \
                               'successful, but error occurred on coda parsing, exception message: %s\n Filename: %s' % (exc, file_name)
                        subject = 'SwedBank -- Automatic CronJob, file creation fail [%s]' % mapper.database
                        self.env['script'].send_email(['support@robolabs.lt'],
                                                      subject,
                                                      attachments=[(0, 0, {
                                                          'name': 'swedbank.xml',
                                                          'datas_fname': 'swedbank.xml',
                                                          'type': 'binary',
                                                          'datas': xml_b64
                                                      })],
                                                      body=body)

                        # If we fail to create the file, we keep the file
                        files_to_keep.append(file_name)
        self.incoming_file_cleanup(collected_files, files_to_keep=files_to_keep)

    def incoming_file_cleanup(self, collected_files, files_to_keep=None):
        """
        Method that is used to move already imported XML files
        :return: None
        """
        fail_count = 3
        sd = get_swed_data(self.env)
        path = sd.get('directory_path') + '/received'
        path_to_move = sd.get('directory_path') + '/processed'
        error_path = sd.get('directory_path') + '/error'
        if not os.path.isdir(path_to_move):
            os.mkdir(path_to_move)
        if not os.path.isdir(error_path):
            os.mkdir(error_path)
        os.chdir(path)
        potentially_movable = []
        for r, d, f in os.walk(path):
            for st_file in f:
                if '.xml' in st_file.lower() and st_file in collected_files:
                    f_path = os.path.join(r, st_file)
                    c_time = os.path.getctime(f_path)
                    potentially_movable.append((st_file, c_time))

        potentially_movable = sorted(potentially_movable, key=lambda c: c[1])
        resorted = [x[0] for x in potentially_movable]
        files_to_move = list(set(resorted) - set(files_to_keep))
        for st_file in files_to_move:
            move_to = path_to_move + '/' + st_file
            if os.path.isfile(move_to):
                move_to += '.%s_%s' % (datetime.now().strftime('%Y_%m_%d_%H%M%S'), random_name(10))
            os.rename(path + '/' + st_file, move_to)
        for st_file in files_to_keep:
            current_path = path + '/' + st_file
            if 'fail' not in st_file.lower():
                # If file name does not contain 'fail' rename the file
                # by appending 'fail_1' and continue
                try:
                    os.rename(current_path, current_path + 'fail_1')
                except Exception as exc:
                    _logger.info('Swedbank: OS Error - {}. Current path - {}. File name - {}'.format(
                        tools.ustr(exc), current_path, st_file,
                    ))
                continue
            else:
                try:
                    # If file name does contain 'fail', check the attempt
                    # and either continue or move the file to error
                    fail_index = st_file.index('fail')
                    file_fail_count = int(st_file[fail_index:].split('_')[1])
                    if file_fail_count < fail_count:
                        file_fail_count += 1
                        new_path = path + '/' + st_file[:fail_index] + 'fail_{}'.format(file_fail_count)
                        os.rename(current_path, new_path)
                        continue
                except Exception as exc:
                    _logger.info('Swedbank fail index fetching exception - {}'.format(tools.ustr(exc)))

            move_to = error_path + '/' + st_file
            if os.path.isfile(move_to):
                move_to += '.%s_%s' % (datetime.now().strftime('%Y_%m_%d_%H%M%S'), random_name(10))
            if os.path.isfile(path + '/' + st_file):
                os.rename(path + '/' + st_file, move_to)

    @api.model
    def cron_outgoing_file_cleanup(self):
        """
        Method that is used to delete already exported XML files
        :return: None
        """
        sd = get_swed_data(self.env)
        base_robo_path = sd.get('directory_path').replace('swedbank_internal', 'swedbank')
        paths = [(base_robo_path + '/sending', base_robo_path + '/sent'),
                 (sd.get('directory_path') + '/sending', sd.get('directory_path') + '/sent')]

        for path, path_to_move in paths:
            if not os.path.isdir(path_to_move):
                os.mkdir(path_to_move)
            os.chdir(path)
            files_to_move = []
            now_dt = datetime.utcnow()
            for r, d, f in os.walk(path):
                for st_file in f:
                    f_path = os.path.join(r, st_file)
                    c_time = os.path.getctime(f_path)
                    # Load unix timestamp to datetime, and calculate
                    # the difference between file create date, and now
                    c_time_dt = datetime.utcfromtimestamp(c_time)
                    diff = now_dt - c_time_dt
                    # If file is here for less than an hour, keep it
                    if diff.total_seconds() / 3600.0 < 1:
                        continue
                    files_to_move.append((st_file, c_time))
            files_to_move = sorted(files_to_move, key=lambda c: c[1])
            resorted = [x[0] for x in files_to_move]
            for st_file in resorted:
                os.rename(path + '/' + st_file, path_to_move + '/' + st_file)

        # After moving, delete all of the files that meet the criteria
        self.delete_historic_files()

    @api.model
    def delete_historic_files(self):
        """
        Method that deletes files from Swed-Bank
        directories that are either older than DAYS_TO_KEEP Months
        or contain SUBSTRING_TO_REMOVE substring in the file name
        :return: None
        """
        sd = get_swed_data(self.env)
        base_internal_path = sd.get('directory_path')
        base_robo_path = base_internal_path.replace('swedbank_internal', 'swedbank')
        parent_paths = [base_robo_path, base_internal_path]
        for fp in parent_paths:
            paths = [fp + '/sent', fp + '/processed']
            now_dt = datetime.utcnow()
            for path in paths:
                for r, d, f in os.walk(path):
                    for st_file in f:
                        f_path = os.path.join(r, st_file)
                        c_time = os.path.getctime(f_path)
                        # Load unix timestamp to datetime, and calculate
                        # the difference between file create date, and now
                        c_time_dt = datetime.utcfromtimestamp(c_time)
                        # If file is here for less than an hour, keep it
                        if (now_dt - c_time_dt).days >= DAYS_TO_KEEP or SUBSTRING_TO_REMOVE in st_file.lower():
                            os.remove(f_path)


SwedBankAPIExport()


class SwedbankMapper(models.Model):
    _name = 'swedbank.mapper'

    mapper_id = fields.Many2one('database.mapper', string='Database', required=True)
    bank_account = fields.Char(string='Bank Account', required=True)

    @api.constrains('bank_account')
    def constraint_bank_account(self):
        if self.search([('bank_account', '=', self.bank_account)], count=True) > 1:
            raise exceptions.ValidationError(_('Duplicate account number.'))

    @api.model
    def get_mapper(self, number):
        bank = self.search([('bank_account', '=', number)])
        if bank:
            return bank.mapper_id
        else:
            return self.env['database.mapper']

    @api.model
    def add_number(self, number, mapper):
        rec = self.search([('bank_account', '=', number)])
        if not rec:
            self.create({
                'bank_account': number,
                'mapper_id': mapper.id
            })
        elif rec and rec.mapper_id.id != mapper.id:
            self.env['script'].send_email(['support@robolabs.lt'],
                                          u'SWEDBANK API alert',
                                          u'Trying to add a bank account %s [%s], but it is already assigned to a '
                                          u'different client. New client %s.' % (number, rec.mapper_id.database, mapper.database))

    @api.model
    def cron_fetch_swedbank_accounts(self):
        if not self.env.user.has_group('base.group_user'):
            return False
        databases = self.env['database.mapper'].search([('accounting', '=', True)])
        for database in databases:
            with api.Environment.manage():
                cr = sql_db.db_connect(database.database_url, allow_uri=True).cursor()
                env = api.Environment(cr, SUPERUSER_ID, {'lang': 'lt_LT'})
                bank_id = env['res.bank'].search([('kodas', '=', '73000')], limit=1)
                if bank_id:
                    journals = env['account.journal'].search([('type', '=', 'bank'), ('bank_id', '=', bank_id.id),
                                                              ('bank_acc_number', '!=', False)])
                    if journals:
                        for number in journals.mapped('bank_acc_number'):
                            self.add_number(number, database)
                cr.commit()
                cr.close()


SwedbankMapper()


class DupplicateWizard(models.TransientModel):
    _inherit = 'duplicate.wizard'

    automated_payment = fields.Boolean('Automated payment', default=False)

    @api.multi
    def confirm(self):
        if not self.env.user.has_group('base.group_system'):
            return
        self.ensure_one()
        res = super(DupplicateWizard, self).confirm()
        mapper_obj = self.env['database.mapper']
        mapper_id = mapper_obj.search([('company_code', '=', self.company_code)], limit=1)
        if mapper_id:
            mapper_id.automated_payment = self.automated_payment
        return res


DupplicateWizard()


class RoboPlanInvoice(models.Model):
    _inherit = 'robo.plan.invoice'

    @api.model
    def cron_check_payment_status(self):
        if not self.env.user.has_group('base.group_system'):
            return
        res = super(RoboPlanInvoice, self).cron_check_payment_status()
        date_dt = datetime.utcnow()
        date_from = (date_dt - relativedelta(months=1, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = (date_dt - relativedelta(months=1, day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        invoice_numbers = []
        if date_dt.day <= 5:
            r_database = self.env['database.mapper'].search([('database', '=', 'r')], limit=1)
            try:
                cr = sql_db.db_connect(r_database.database_url, allow_uri=True).cursor()
                env = api.Environment(cr, SUPERUSER_ID, {'lang': 'lt_LT'})
                invoices = env['account.invoice'].search([('date_invoice', '>=', date_from),
                                                              ('date_invoice', '<=', date_to),
                                                              ('state', '=', 'open'),
                                                              ('type', '=', 'out_invoice'),
                                                              ('bank_export_state', 'in', ['accepted', 'processed'])])
                invoice_numbers += invoices.mapped('number')
                cr.rollback()
                cr.close()
            except Exception as exc:
                cr.rollback()
                cr.close()
                _logger.info('Traceback: %s' % traceback.format_exc())
                self.env['script'].send_email(['support@robolabs.lt'],
                                              u'SWEDBANK API alert',
                                              u'Could not load eInvoices from r database.')
        if invoice_numbers:
            failed_str = ''
            for mapper in self.env['database.mapper'].search([('domain', '!=', ''), ('database_url', '!=', '')]):
                try:
                    cr = sql_db.db_connect(mapper.database_url, allow_uri=True).cursor()
                    env = api.Environment(cr, SUPERUSER_ID, {'lang': 'lt_LT'})
                    invoice = env['account.invoice'].search([('date_invoice', '>=', date_from),
                                                              ('date_invoice', '<=', date_to),
                                                              ('state', '=', 'open'),
                                                              ('type', '=', 'in_invoice'),
                                                              ('partner_id.kodas', '=', '304222026'),
                                                              ('reference', 'in', invoice_numbers)], limit=1)
                    if invoice:
                        invoice.write({
                            'robo_unpaid_e_invoice': True
                        })
                        cr.commit()
                    cr.rollback()
                    cr.close()
                except Exception as exc:
                    cr.rollback()
                    cr.close()
                    failed_str += 'Exception: %s \n' % tools.ustr(exc)
                    _logger.info('Traceback: %s' % traceback.format_exc())
            if failed_str:
                self.env['script'].send_email(['support@robolabs.lt'],
                                              u'SWEDBANK API alert',
                                              u'Could not update RoboLabs eInvoice unpaid status.\n%s' % failed_str)
        return res


RoboPlanInvoice()
