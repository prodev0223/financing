# -*- encoding: utf-8 -*-
from odoo import fields, models, _, api, exceptions, tools
from datetime import datetime
import pytz
import os
from lxml import etree, objectify
from lxml.etree import XMLSyntaxError
import logging
import base64
import psutil
import subprocess32 as subprocess

_logger = logging.getLogger(__name__)
swed_bic = '73000'
subprocess_timeout = 10  # 10 secs

# If this message was received in the response of the bank
# accountant should not be informed, since it's either duplicate
# payment or it was rejected in the bank itself
STATIC_RESPONSE_DRAFT_DISCARDED = 'Cancelled!'

# Indicates for how long swed-bank files should be kept
# until their deletion (in days)
DAYS_TO_KEEP = 90

# Indicates a substring - if found in a file name,
# file is deleted ignoring DAYS_TO_KEEP parameter
SUBSTRING_TO_REMOVE = '__bal__'


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

    res = reasons.get(fail_reason, False) if reasons.get(fail_reason, False) else \
        'Unexpected %s %s' % (reason_type, fail_reason)
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
    Map state string to specific parial state string
    :param state: state string
    :return: partial state string
    """
    partial_state_mapper = {'accepted': 'accepted_partial',
                            'rejected': 'rejected_partial',
                            'processed': 'processed_partial'}
    return partial_state_mapper.get(state)


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
                reg_num_node = agreement.find('RegistrationNumber')
                reg_num = reg_num_node.text if reg_num_node is not None else False
                data.append({
                    'agreement_id': agreement.get('id', False),
                    'company_code': reg_num
                })
            return data
    except Exception as exc:
        _logger.info('Agreement file checking exception: %s' % str(exc.args[0]))
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
        _logger.info('Skipped SwedBank file import, error message: %s' % str(exc.args[0]))
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

    swed_bank_agreement_id = fields.Integer(string='SwedBank Agreement ID')


DatabaseMapper()


class SwedBankAPIExport(models.TransientModel):
    _name = 'swed.bank.export.internal'
    _description = 'Transient model that is used for automatic bank ' \
                   'statement exports from SwedBank using API solutions. Located in internal.'

    @api.model
    def inform_findir(self, message, obj_id=None, inform_type='post'):
        if inform_type in ['post'] and obj_id is not None:
            obj_id.robo_message_post(subtype='mt_comment', body=message,
                                     partner_ids=self.env.user.company_id.findir.partner_id.ids,
                                     priority='low')
        # elif inform_type in ['email']:
        findir_email = self.sudo().env.user.company_id.findir.partner_id.email
        database = self._cr.dbname
        subject = '{} // [{}]'.format('Swedbank Import -- Atmestas mokėjimas', database)
        self.env['script'].send_email(emails_to=[findir_email],
                                      subject=subject,
                                      body=message)

    def update_object_status(self, obj_data, sepa_instruction_id, file_name):
        """
        Method that matches invoices or front bank statements by sepa instruction ID and updates their states
        based on received PAIN response file.
        :return: swed.bank.export.mapper records that were found
        """

        state = obj_data.get('state')
        error_message = obj_data.get('error_message')

        # If we get the static response non inform, we force the state to
        # no_action (so export is possible again) form separate body message and
        # DO NOT inform the findir. # TODO: Other code parts will be modified in internal repo itself
        if error_message == STATIC_RESPONSE_DRAFT_DISCARDED:
            state = 'no_action'
            body = 'Mokėjimo eksportavimas į Swedbank buvo priimtas, ' \
                   'tačiau ruošinys buvo atšauktas naudotojo pačiame banke, ' \
                   'arba ruošinys buvo atpažintas kaip duplikatas išorinės banko sistemos.'
        else:
            body = 'Mokėjimo eksportavimas į Swedbank buvo atmestas.\n' if state in ['rejected'] else \
                'Mokėjimo eksportavimas į Swedbank buvo priimtas.\n'
            if error_message:
                body += ' Klaidos pranešimas - {}'.format(error_message)
        main_acc_part_id = self.env.user.company_id.vadovas.user_id.partner_id.ids
        ceo_part_id = self.env.user.company_id.findir.partner_id.ids
        recs = self.env['bank.export.job'].search([('sepa_instruction_id', '=', sepa_instruction_id)])
        if not recs:
            body = 'Swedbank API Error: Got a sepa instruction ID that does not match ' \
                   'any entries in the system. File name - %s, Instruction ID - %s' % (file_name, sepa_instruction_id)
            self.send_bug(body=body, subject='Swedbank API - Instruction ID mismatch.')

            if state in ['rejected']:
                body = 'Atmestas mokėjimo siuntimas į Swedbank. Gavėjo sąskaita - %s, suma - %s %s, ' \
                       'mokėjimo data - %s' % (obj_data.get('receiver_iban'), obj_data.get('tr_amount'),
                                               obj_data.get('tr_currency'), obj_data.get('tr_date'))
                partner_ids = main_acc_part_id + ceo_part_id
                self.env.user.company_id.post_announcement(html=body, subject='Atmestas Swedbank mokėjimas',
                                                           partner_ids=partner_ids)
        for rec in recs:
            if rec.invoice_id:
                if rec.partial_invoice_payment:
                    state = get_partial_state(state)
                rec.invoice_id.write({'bank_export_state': state})
                self.inform_findir(message=body, obj_id=rec.invoice_id)
            elif rec.front_statement_line_id:
                rec.front_statement_line_id.write({'bank_export_state': state})
                body_line = body + ' Eilutė - {}'.format(rec.front_statement_line_id.display_name)
                self.inform_findir(message=body_line, obj_id=rec.front_statement_line_id.statement_id)
            else:
                if state in ['rejected']:
                    body = 'Atmestas mokėjimo siuntimas į Swedbank. Gavėjo sąskaita - %s, suma - %s %s, ' \
                           'mokėjimo data - %s' % (obj_data.get('receiver_iban'), obj_data.get('tr_amount'),
                                                   obj_data.get('tr_currency'), obj_data.get('tr_date'))
                    partner_ids = main_acc_part_id + ceo_part_id
                    self.env.user.company_id.post_announcement(html=body, subject='Atmestas Swedbank mokėjimas',
                                                               partner_ids=partner_ids)
        return recs

    def process_pain_response(self, xml_stream, file_name):
        """
        Method that checks whether passed file is pain response, and if it is,
        checks whether file is accepted or rejected and updates corresponding object states.
        :return: False if file is not PAIN, otherwise True
        """
        is_pain_file = xml_validator(xml_stream, xsd_file=os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', 'xsd_schemas')) + '/pain.001.001.03.xsd')
        if not is_pain_file:
            is_pain_file = xml_validator(xml_stream, xsd_file=os.path.abspath(
                os.path.join(os.path.dirname(__file__), '..', 'xsd_schemas')) + '/pain.002.001.03.xsd')
            if not is_pain_file:
                return False
        try:
            root = etree.fromstring(
                xml_stream, parser=etree.XMLParser(recover=True))
        except etree.XMLSyntaxError:
            return False
        try:
            ns = root.tag[1:root.tag.index("}")]
            path = str('{' + ns + '}')
        except Exception as exc:
            _logger.info('Skipped SwedBank file import, error message: %s' % str(exc.args[0]))
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
                export_objects = self.env['swed.bank.export.mapper']
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
                        'error_message': error_message
                    }
                    recs = self.update_object_status(obj_data=data, sepa_instruction_id=export_id, file_name=file_name)
                    export_objects |= recs
                export_objects.inform_ceo()
                return True
            else:
                body = 'Swedbank API Error: Bank returned corrupt PAIN file. File name - %s' % file_name
                self.env['script'].send_email(['support@robolabs.lt'],
                                              u'Swedbank API - Rejected PAIN file.',
                                              body)
                return False
        except Exception as exc:
            _logger.info('Pain file checking exception: %s' % str(exc.args[0]))
            return False

    def process_balance_response(self, data, file_name):
        if not xml_validator(data, xsd_file=os.path.abspath(
                os.path.join(os.path.dirname(__file__), '..', 'xsd_schemas')) + '/camt.052.001.02.xsd'):
            try:
                root = etree.fromstring(
                    data, parser=etree.XMLParser(recover=True))
            except etree.XMLSyntaxError:
                return False
            error_code = root.find('.//HGWError/Code')
            if error_code is not None:
                if 'AccountNotAllowed' in error_code.text:
                    body = 'Swedbank API Info: Bank refused to return balance due to access rights. File name - %s' % file_name
                    self.env['script'].send_email(['support@robolabs.lt'],
                                                  u'Swedbank API - Balance.', body)
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
            _logger.info('Skipped SwedBank file import, error message: %s' % str(exc.args[0]))
            return False

        rpt_vals = root.findall('.//' + path + 'BkToCstmrAcctRpt/' + path + 'Rpt')
        if rpt_vals is None:
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
                bal_amt = bal_val.find(path + 'Amt')
                balance = {
                    'bal_type': parse(bal_tp, str),
                    'bal_amount': parse(bal_amt, int),
                    'bal_currency': bal_amt.attrib.get('Ccy') if
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
            bank_iban = line.get('bank_iban')
            balance_data = filter(lambda x: x['bal_type'] == 'ITAV', line['balances'])
            if not balance_data:
                balance_data = filter(lambda x: x['bal_type'] == 'ITBD', line['balances'])
            balance_amount = float(balance_data[0].get('bal_amount', 0.0))
            # todo INTERNAL: find corresponding company by code, then find account journal by iban and write
            # todo INTERNAL: balance_date and balance_amount to swed_balance_update_date and swed_end_balance_real todo change
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
        if tag != 'FailedInvoice':
            return False
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
            self.send_bug(body=body, subject='Swedbank API - Corrupt eInvoice.')
            return False
        if not fail_reason:
            try:
                tot_count = int(root.find('.//Footer').attrib.get('totalNr'))
            except AttributeError:
                body = 'Swedbank API Error: Got a corrupt eInvoice. Cant fetch Total Failed Count. ' \
                       'File name - %s' % file_name
                self.send_bug(body=body, subject='Swedbank API - Corrupt eInvoice.')
                return False
            if tot_count:
                parent_status = 'failed_partial'
                invoices = root.findall('.//Invoice')
                for invoice in invoices:
                    unique_id = parse(invoice.find('.//InvoiceGlobUniqId'), str)
                    fail_reason_inv = parse(invoice.find('.//FailReason'), str)
                    reason = e_invoice_fail_reason_mapper(fail_reason_inv, 'FailReason')
                    failed_numbers.update({unique_id: reason})

            else:
                parent_status = 'success_all'
        else:
            reason = e_invoice_fail_reason_mapper(fail_reason, 'FileFailReason')
            body = 'Swedbank API Error: Got a failed eInvoice. error - %s ' \
                   'File name - %s' % (reason, file_name)
            parent_fail_message = reason
            self.send_bug(body=body, subject='Swedbank API - Corrupt eInvoice.')
            parent_status = 'failed_all'

        try:
            database_name = file_id.split('__')[1]
        except IndexError:
            body = 'Swedbank API Error: Got an eInvoice with corrupt FILE ID.' \
                   ' File name - %s, FILE ID - %s' % (file_name, file_id)
            self.send_bug(body=body, subject='Swedbank API - Instruction ID mismatch.')
            return

        # todo INTERNAL: We Have the DB name, browse the database and loop through recs

        recs = self.env['e.invoice.file.mapper'].search([('file_id', '=', file_id)])
        if recs:
            if parent_status in ['success_all']:
                recs.mapped('invoice_id').write({'e_invoice_export_state': 'accepted'})
                recs.mapped('invoice_id').message_post(body='eSąskaitos eksportavimas į Swedbank buvo priimtas.')
            elif parent_status in ['failed_all']:
                recs.mapped('invoice_id').write({'e_invoice_export_state': 'rejected'})
                recs.mapped('invoice_id').message_post(body='eSąskaitos eksportavimas į Swedbank buvo atmestas. '
                                                            'Klaidos pranešimas: %s' % parent_fail_message)
            else:
                for rec in recs:
                    if rec.global_unique_id in failed_numbers:
                        message = failed_numbers[rec.global_unique_id]
                        rec.invoice_id.write({'e_invoice_export_state': 'rejected'})
                        recs.mapped('invoice_id').message_post(
                            body='eSąskaitos eksportavimas į Swedbank buvo atmestas. Klaidos pranešimas: %s' % message)
                    else:
                        rec.invoice_id.write({'e_invoice_export_state': 'accepted'})
                        recs.mapped('invoice_id').message_post(
                            body='eSąskaitos eksportavimas į Swedbank buvo priimtas.')
        else:
            body = 'Swedbank API Error: Got an eInvoice FILE ID that does not match ' \
                   'any entries in the system. File name - %s, FILE ID - %s' % (file_name, file_id)
            self.send_bug(body=body, subject='Swedbank API - Instruction ID mismatch.')
        return True

    def process_e_invoice_application_response(self, data, file_name):
        try:
            root = etree.fromstring(
                data, parser=etree.XMLParser(recover=True))
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
                self.send_bug(body=body, subject='Swedbank API - Application fields.')
                continue

            application_data.append({
                'seller_company_code': seller_reg,
                'seller_contract_id': seller_contract_id,
                'action': parse(node.find('Action'), str),
                'service_id': parse(node.find('ServiceId'), int),
                'buyer_iban': buyer_iban,
                'buyer_presentment_type': parse(node.find('PresentmentType'), str),
                'buyer_company_code': parse(node.find('CustomerIdCode'), str),
                'buyer_name': parse(node.find('CustomerName'), str),
                'buyer_email': parse(node.find('CustomerEmail'), str),
                'application_date': parse(node.find('TimeStamp'), str, date=True),
            })

        for data in application_data:
            # TODO INTERNAL: Identify DB by seller company_code or seller_contract ID
            # TODO INTERNAL: Identify specific partner in that DB by buyer_iban or other buyer fields
            partner_id = self.env['res.partner']  # FOUND PARTNER
            if not partner_id:
                body = 'Swedbank API Error: Got Corrupt application file.' \
                       'Cant find partner in the system. File name - %s' % file_name
                self.send_bug(body=body, subject='Swedbank API - Application fields.')
                continue
            if data.get('action') in ['ADD']:
                bank_id = partner_id.bank_ids.filtered(lambda x: x.acc_number == data.get('buyer_iban'))
                if not bank_id:
                    bank_id = self.env['res.partner.bank'].create({'acc_number': data.get('buyer_iban'),
                                                                   'partner_id': partner_id.id})
                    bank_id.onchange_acc_number()
                partner_id.write({'send_e_invoices': True,
                                  'e_invoice_application_date': data.get('application_date'),
                                  'res_partner_bank_e_invoice_id': bank_id.id})

            elif data.get('action') in ['DEL']:
                partner_id.write({'send_e_invoices': False, 'e_invoice_application_date': False})
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
            self.send_bug(body=body, subject='Swedbank API - Corrupt AutoPayment response.')
            return False
        if not fail_reason:
            try:
                tot_count = int(root.find('.//Footer').attrib.get('totalNr'))
            except AttributeError:
                body = 'Swedbank API Error: Got a corrupt AutoPayment. Cant fetch Total Failed Count. ' \
                       'File name - %s' % file_name
                self.send_bug(body=body, subject='Swedbank API - Corrupt AutoPayment response.')
                return False
            if tot_count:
                parent_status = 'failed_partial'
                agreements = root.findall('.//Agreement')
                for agreement in agreements:
                    partner_id = parse(agreement.find('.//ServiceId'), str)
                    fail_reason_agr = parse(agreement.find('.//FailureCode'), str)
                    reason = automated_payment_fail_reason_mapper(fail_reason_agr, 'FailReason')
                    failed_numbers.update({partner_id: fail_reason_agr})
            else:
                parent_status = 'success_all'
        else:
            reason = automated_payment_fail_reason_mapper(fail_reason, 'FileFailReason')
            body = 'Swedbank API Error: Got a failed AutoPayment. error - %s ' \
                   'File name - %s' % (reason, file_name)
            parent_fail_message = reason
            self.send_bug(body=body, subject='Swedbank API - Failed AutoPayment response.')
            parent_status = 'failed_all'

        try:
            database_name = file_id.split('__')[1]
            # TODO INTERNAL: Identify DB by seller company_code or seller_contract ID
        except IndexError:
            body = 'Swedbank API Error: Got an AutoPayment with corrupt FILE ID.' \
                   ' File name - %s, FILE ID - %s' % (file_name, file_id)
            self.send_bug(body=body, subject='Swedbank API - Instruction ID mismatch.')
            return

        recs = self.env['e.invoice.file.mapper'].search([('file_id', '=', file_id)])
        if recs:
            if parent_status in ['success_all']:
                recs.mapped('partner_id').reverse_auto_payment_write()
                recs.mapped('partner_id').message_post(body='Automatinio mokėjimo sudarymas buvo priimtas.')
            elif parent_status in ['failed_all']:
                recs.mapped('partner_id').reverse_auto_payment_write(failed=True)
                recs.mapped('partner_id').message_post(body='Automatinio mokėjimo sudarymas buvo atmestas. '
                                                            'Klaidos pranešimas: %s' % parent_fail_message)
            else:
                for rec in recs:
                    if rec.global_unique_id in failed_numbers:
                        rec.partner_id.reverse_auto_payment_write(failed=True)
                        message = failed_numbers[rec.global_unique_id]
                        recs.mapped('partner_id').message_post(
                            body='Automatinio mokėjimo sudarymas buvo atmestas. Klaidos pranešimas: %s' % message)
                    else:
                        rec.partner_id.reverse_auto_payment_write()
                        recs.mapped('partner_id').message_post(
                            body='Automatinio mokėjimo sudarymas buvo priimtas.')
        else:
            body = 'Swedbank API Error: Got an AutoPayment response FILE ID that does not match ' \
                   'any entries in the system. File name - %s, FILE ID - %s' % (file_name, file_id)
            self.send_bug(body=body, subject='Swedbank API - Instruction ID mismatch.')
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
        sd = get_swed_data(self.env)
        path = sd.get('directory_path') + '/received'
        statement_file_paths = []
        for r, d, f in os.walk(path):
            for st_file in f:
                if '.xml' in st_file.lower():
                    f_path = os.path.join(r, st_file)
                    c_time = os.path.getctime(f_path)
                    statement_file_paths.append((f_path, st_file, c_time))

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
                company_code = client_data.get('iban_currency')
                iban_currency = client_data.get('company_code')
                if extracted_iban not in file_path:
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
                            if company_code and agreement_id:
                                db_id = self.env['database.mapper'].search([('company_code', '=', company_code)])
                                db_id.write({'swed_bank_agreement_id': agreement_id})
                    else:
                        files_to_keep.append(file_name)
        for file_data in valid_statement_list:
            # todo here do database mapping by xml_iban, new table should be created that has db name and iban
            # todo include second loop here that loops through databases and passes xml_b65 files to account.sepa.import
            wizard_id = self.env['account.sepa.import'].create({'coda_data': file_data.get('xml_b64')})
            try:
                wizard_id.coda_parsing()
            except Exception as exc:
                body = 'SwedBank -- Automatic CronJob fail: Fetching of files was ' \
                       'successful, but error occurred on coda parsing, exception message: %s' % exc.args[0]
                subject = 'SwedBank -- Automatic CronJob, file creation fail'
                self.send_bug(body=body, subject=subject)

                # If we fail to create the file, we keep the file
                files_to_keep.append(file_data.get('file_name'))
        self.incoming_file_cleanup(files_to_keep=files_to_keep)

    def incoming_file_cleanup(self, files_to_keep=None):
        """
        Method that is used to move already imported XML files
        :return: None
        """
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
                if '.xml' in st_file.lower():
                    f_path = os.path.join(r, st_file)
                    c_time = os.path.getctime(f_path)
                    potentially_movable.append((st_file, c_time))
        potentially_movable = sorted(potentially_movable, key=lambda c: c[1])
        resorted = [x[0] for x in potentially_movable]
        files_to_move = list(set(resorted) - set(files_to_keep))
        for st_file in files_to_move:
            os.rename(path + '/' + st_file, path_to_move + '/' + st_file)
        for st_file in files_to_keep:
            os.rename(path + '/' + st_file, error_path + '/' + st_file)

    @api.model
    def cron_outgoing_file_cleanup(self):
        """
        Method that is used to delete already exported XML files
        :return: None
        """
        sd = get_swed_data(self.env)
        path = sd.get('directory_path') + '/sending'
        path_to_move = sd.get('directory_path') + '/sent'
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
        fp = sd.get('directory_path')
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

    def send_bug(self, body, subject):
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'subject': subject + ' [%s]' % self._cr.dbname,
            'error_message': subject,
        })


SwedBankAPIExport()
