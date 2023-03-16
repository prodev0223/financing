# -*- coding: utf-8 -*-
from odoo.addons.base_iban.models.res_partner_bank import validate_iban
from odoo.addons.sepa import api_bank_integrations as abi
from odoo import models, api, tools, exceptions, fields
from odoo.tools.translate import _
from datetime import datetime
from xml.etree.ElementTree import SubElement
from time import gmtime, strftime
from xml.dom.minidom import parseString
from lxml import etree, objectify
from lxml.etree import XMLSyntaxError
import base64
import os
import re
import logging

_logger = logging.getLogger(__name__)


def set_node_and_tag(p_node, c_tag, c_text, c_node, c_tag_key, decimal_precision=False):
    """
    Creates new etree node in passed parent node and sets the specified tag
    :param p_node: Parent node, etree object (in which the new node should be created)
    :param c_tag: to-be-created Child node tag value
    :param c_text: to-be-created Child node text
    :param c_node: to-be-created Child node name
    :param c_tag_key: to-be-created Child node tag key
    :param decimal_precision: Indicates whether to use .2 decimal precision for float/int values
    :return: None
    """
    el = etree.Element(c_node)
    if isinstance(c_text, (float, int)) and not isinstance(c_text, bool):
        c_text = '%.2f' % c_text if decimal_precision else str(c_text)
    if c_text:
        el.text = c_text
    else:
        el.text = ''
    if isinstance(c_tag, (float, int)) and not isinstance(c_tag, bool):
        c_tag = str(c_tag)
    el.attrib[c_tag_key] = c_tag
    p_node.append(el)


def set_node(node, key, value, skip_empty=False, decimal_precision=False):
    """
    Create a new node inside passed parent node and set its value
    :param node: Parent node, etree object (in which the new node should be created)
    :param key: Name of the node to-be-created
    :param value: Value of the node to-be-created
    :param skip_empty: Bool value indicates whether
           child node should not be created if passed value is empty
    :param decimal_precision: Indicates whether to use .2 decimal precision for float/int values
    :return: None
    """
    if skip_empty and not value:
        return
    if not skip_empty and not value and not isinstance(value, tuple([int, float, long])):
        pass
    el = etree.Element(key)
    if isinstance(value, tuple([int, float, long])) and not isinstance(value, bool):
        value = '%.2f' % value if decimal_precision else str(value)
    if value:
        el.text = value
    setattr(node, key, el)


def multiple_replace(text, **replacement_rules):
    """
    Replace symbols in text based on replacement rules
    :param text: text to be changed
    :param replacement_rules: dict of rules to use while replacing
    :return: sanitized text
    """
    if not text:
        text = ''
    elif len(replacement_rules) > 0:
        keys = sorted(replacement_rules, key=len, reverse=True)
        reg = re.compile("|".join(map(re.escape, map(unicode, keys))))
        text = reg.sub(lambda m: replacement_rules[m.group(0)], text)
    return text


def xml_validator(some_xml_string, xsd_file='/path/to/my_schema_file.xsd'):
    """
    Validate XML using xsd schema
    :param some_xml_string
    :param xsd_file: xsd file location
    :return: True if valid/raise otherwise
    """
    try:
        schema = etree.XMLSchema(file=xsd_file)
        parser = objectify.makeparser(schema=schema)
        objectify.fromstring(some_xml_string, parser)
        return True
    except XMLSyntaxError as exc:
        raise exceptions.UserError(_('Failed to generate SEPA file: %s') % exc.message)


def rm_spaces(s):
    """
    Remove all spaces from the passed string
    :param s: passed string
    :return: sanitized string
    """
    if not isinstance(s, (str, unicode)):
        raise exceptions.UserError(_('Nėra sąskaitos'))
    else:
        return s.strip().replace(' ', '')


class BankExportBase(models.AbstractModel):

    """
    Base model that is inherited by debt reconciliation report multi and
    debt reconciliation report multi minimal
    """

    _name = 'bank.export.base'

    # Field that is shared between all the models that inherit this one
    journal_id = fields.Many2one('account.journal', string='Žurnalas')
    international_priority = fields.Selection([
        ('SDVA', 'Šiandieninis'), ('URGP', 'Skubus'), ('NURG', 'Neskubus')],
        string='Tarptautinių mokėjimų prioritetas', default='NURG'
    )

    # -----------------------------------------------------------------------------------------------------------------
    # Getters // ------------------------------------------------------------------------------------------------------

    @api.model
    def get_structured_reference_partner_codes(self):
        # Partner codes that usually should have structured reference, and, in case of non structured reference,
        # must display a warning when bank statement is being exported as PAIN XML file
        STATIC_STRUCTURED_REF_PARTNER_CODES = ['188659752', '191630223']
        return STATIC_STRUCTURED_REF_PARTNER_CODES

    @api.model
    def get_msg_id(self):
        return self.env['ir.sequence'].next_by_code('MsgId')

    @api.model
    def get_pmt_inf_id(self):
        return self.env['ir.sequence'].next_by_code('PMTINFID')

    @api.multi
    def get_sanitize_rules(self, line_id=None):
        """
        Get sanitize rules for specific bank. If no rule code is specified,
        global rules are used, otherwise specific rules are applied
        :param line_id: account.bank.statement.line record or None
        :return: sanitize rules (dict)
        """
        self.ensure_one()
        rules = {unicode(u'„'): "'",
                 unicode(u'“'): "'",
                 unicode(u'"'): "'",
                 unicode(u'\t'): ' ',
                 unicode(u'\n'): ' ',
                 }

        if line_id:
            bank = line_id.bank_account_id.bank_id

            #  Global sanitize rules for all of the banks
            if not bank.sudo().sepa_export_rules_code:
                allowed_to_other_lithuania = unicode(
                    u'abcdefghijklmnopqrstuvwxyząęėįšųūžABCDEFGHIJKLMNOPQRSTUVWXYZĄĘĖĮŠŲŪŽ0123456789/-?:().,\'+')
                rules.update({
                    unicode(u'!'): '.',
                    unicode(u'$'): '.',
                    unicode(u'%'): '.',
                    unicode(u'*'): '.',
                    unicode(u'#'): '.',
                    unicode(u';'): '.',
                    unicode(u'@'): '.',
                    unicode(u'['): '(',
                    unicode(u']'): ')',
                    unicode(u'_'): '-',
                    unicode(u'`'): '\'',
                    unicode(u'|'): '\\',
                    unicode(u'='): '.',
                    unicode(u'Õ'): 'O',
                    unicode(u'õ'): 'o',
                    unicode(u'Ä'): 'A',
                    unicode(u'ä'): 'a',
                    unicode(u'Ö'): 'O',
                    unicode(u'ö'): 'o',
                    unicode(u'Ü'): 'U',
                    unicode(u'ü'): 'u',
                    unicode(u'Ā'): 'A',
                    unicode(u'ā'): 'a',
                    unicode(u'Ē'): 'E',
                    unicode(u'ē'): 'e',
                    unicode(u'Ģ'): 'G',
                    unicode(u'ģ'): 'g',
                    unicode(u'Ī'): 'I',
                    unicode(u'ī'): 'i',
                    unicode(u'Ķ'): 'K',
                    unicode(u'ķ'): 'k',
                    unicode(u'Ļ'): 'L',
                    unicode(u'ļ'): 'l',
                    unicode(u'Ņ'): 'N',
                    unicode(u'ņ'): 'n',
                })
                for i in allowed_to_other_lithuania:
                    if i in rules:
                        rules.pop(i)

            # Use other rules // This part of the code can be updated based on the bank
            elif bank.sudo().sepa_export_rules_code == 'CITADELE':
                rules.update({
                    unicode('_'): "-",
                    unicode('{'): "(",
                    unicode('}'): ")",
                    unicode('['): "(",
                    unicode(']'): ")",
                    unicode('*'): ".",
                    unicode('|'): ".",
                    unicode('\\'): ".",
                    unicode('"'): "'",
                    unicode('`'): "'",
                    unicode(';'): ":",
                    unicode('!'): ".",
                    unicode('?'): ".",
                    unicode('#'): ".",
                    unicode('$'): ".",
                    unicode('%'): ".",
                    unicode('^'): ".",
                    unicode('&'): ".",
                })
        return rules

    @api.model
    def get_integration_types(self, api_bank_type):
        return abi.INTEGRATION_TYPES.get(api_bank_type)

    # -----------------------------------------------------------------------------------------------------------------
    # Download methods // ---------------------------------------------------------------------------------------------

    @api.multi
    def export_sepa_attachment(self):
        """
        Generate bank statement SEPA PAIN xml file and return attachment
        :return: ir.attachment object
        """
        self.ensure_one()
        return self.action_generate_sepa_xml(return_mode='attachment')

    @api.multi
    def export_sepa_attachment_download(self, data):
        """
        Generate bank statement SEPA PAIN xml file and return downloadable link
        :return: download link (dict)
        """
        self.ensure_one()
        # Always a file download here
        data.update({'xml_file_download': True})
        # Get the sepa export prep data
        prep_data = self.prepare_sepa_xml_bank_export(data)
        if prep_data:
            # Get origin model and resource ID for attachment download
            f_origin = prep_data.get('forced_origin') or data.get('origin')
            f_res_id = prep_data.get('forced_res_id') or data.get('res_id')
            return {
                'type': 'ir.actions.act_url',
                'url': '/web/binary/download?res_model=%s&res_id=%s&attach_id=%s' % (
                    f_origin, f_res_id, prep_data['attachment'].id),
                'target': 'self',
            }

    @api.model
    def action_generate_sepa_xml(self, return_mode=None):
        """
        Action to generate SEPA PAIN XML, called from the code.
        Following methods can be called externally to generate the file
        :param return_mode: indicates the return mode None/attachment/script_attachment
        :return: ir.attachment / None
        """

        # Extra data signifies used objects. Here self acts as account.bank.statement record
        # Passed as a dictionary so following methods are not wizard-bound
        extra_data = {
            'journal': self.journal_id,
            'currency': self.currency_id,
            'charge_info': self.kas_sumoka,
            'statement_name': self.name,
            'statement_date': self.date
        }

        # Flags signify used context.
        # Context passed as a parameter so following methods are not wizard/prev-context bound
        flags = {
            'group_transfer': self._context.get('group_transfer'),
            'ultimate_debtor_export': self._context.get('ultimate_debtor_export'),
            'international_priority': self.international_priority or 'NURG',
        }
        statement_lines = self.line_ids
        if self._context.get('send_to_bank'):
            # If send to bank flag is passed, be sure to filter out lines that are not yet exported
            statement_lines = statement_lines.filtered(lambda x: x.bank_export_state in ['waiting'])

        pain_xml_data = self.prepare_pain_data(statement_lines, extra_data, flags)
        return self.generate_sepa_pain_xml(pain_xml_data, return_mode=return_mode)

    # -----------------------------------------------------------------------------------------------------------------
    # Send to bank methods // -----------------------------------------------------------------------------------------

    @api.multi
    def get_bank_export_data(self, export_lines):
        """Returns extra data for bank exports"""
        self.ensure_one()
        return {
            'origin': self._name,
            'res_id': self.id,
            'export_lines': export_lines,
        }

    @api.multi
    def send_to_bank(self):
        """
        Method that is used as an intermediate method in the
        models that inherits bank exporting functionality.
        Must be overridden in the used model
        :return: result of send_to_bank_base
        """
        self.ensure_one()
        return self.send_to_bank_base(data={})

    @api.multi
    def send_to_bank_base(self, data):
        """
        Method that is used to send front bank statement data to bank.
        Validates the data-to-be send, determines what integration is used
        (SEPA or API, only those two at the moment), groups data
        accordingly, calls the method that is the initiator of
        bank statement export for specific journal.
        :return: result of export method for specific journal
        """
        self.ensure_one()
        # Validate base constraints
        # Ensure that send_to_bank method is overridden in every inherited module
        if not data:
            raise exceptions.ValidationError(_('Klaida eksportuojant mokėjimą, trūksta duomenų!'))
        _logger.info('User %s sent statement to bank ID: %s model: %s', self.env.user.name, self.id, self._name)
        self.send_to_bank_validator()

        # Determine bank integration type based on the journal,
        # fetch method and model names of the specific bank
        integration_type = abi.INTEGRATION_TYPES.get(self.journal_id.api_bank_type)
        model_name, method_name = self.env['api.bank.integrations'].get_bank_method(
            self.journal_id, m_type='push_transactions')
        method_instance = getattr(self.env[model_name], method_name)

        # Thus far only these two types are present
        if integration_type == 'api':
            data = self.prepare_api_data_bank_export(data)
            # API integration type methods are expected to take in grouped wizard data as argument
            return method_instance(data)
        elif integration_type == 'sepa_xml':
            # SEPA XML integration type methods are expected to take in
            # grouped data dict - XML stream and bank export jobs
            prep_data = self.prepare_sepa_xml_bank_export(data)
            return method_instance(prep_data)

        # Else - integration type is unrecognized, raise an error
        raise exceptions.ValidationError(
            _('Sending to bank error: Unrecognized bank integration type [%s] for journal [%s]') % (
                integration_type, self.journal_id.name)
        )

    @api.multi
    def prepare_sepa_xml_bank_export(self, data):
        """
        Creates export jobs for the data that is
        being exported, creates artificial bank statement
        and generates attachment - data structure that is
        acceptable for bank integrations of SEPA type.
        :return: generated attachment data b64 (str)
        """
        self.ensure_one()
        # Get needed extra data for bank export creation
        line_records = data.get('export_lines')
        origin = data.get('origin')
        xml_file_download = data.get('xml_file_download')
        priority = data.get('international_priority') or 'NURG'
        # Generate the attachment
        attachment = self.with_context(international_priority=priority).export_sepa_attachment()
        # Create the exports
        bank_exports = self.env['bank.export.job'].create_bank_export_jobs(data={
            'parent_lines': line_records,
            'export_type': 'sepa_xml',
            'journal': self.journal_id,
            'origin': origin,
            'xml_file_download': xml_file_download,
            'xml_file_data': attachment.datas,
        })
        # Gather exported data
        xml_stream = base64.b64decode(attachment.datas)
        data = {
            'bank_exports': bank_exports,
            'attachment': attachment,
            'xml_stream': xml_stream,
        }
        return data

    @api.multi
    def prepare_api_data_bank_export(self, data):
        """
        Creates export jobs for the data that is
        being exported, and groups data into a structure
        that is acceptable for bank integrations of API type.
        !BASE METHOD THAT IS USED FOR BANK STATEMENT (front/back)
        EXPORTS MEANT TO BE OVERRIDDEN FOR OTHER MODELS!
        :return: API suited data-set (dict)
        """
        self.ensure_one()
        # Get needed extra data for bank export creation
        line_records = data.get('export_lines')
        international_priority = data.get('international_priority')
        origin = data.get('origin')
        # Create bank export jobs
        batch_exports = self.env['bank.export.job'].create_bank_export_jobs(data={
            'parent_lines': line_records,
            'export_type': 'api',
            'journal': self.journal_id,
            'origin': origin,
        })
        return {
            'journal_id': self.journal_id,
            'international_priority': international_priority,
            'batch_exports': batch_exports,
        }

    @api.multi
    def send_to_bank_validator(self):
        """
        Validate the data before sending
        it to bank. Method is meant to be overridden
        :return: None
        """
        self.ensure_one()
        # Do not allow the operation if bank is not API integrated
        if not self.journal_id.sudo().api_integrated_journal:
            raise exceptions.ValidationError(_('Operacija galima tik šių bankų išrašams:\n{}'.format(
                '\n'.join(abi.INTEGRATED_BANKS_DISPLAY_NAMES)))
            )

    # -----------------------------------------------------------------------------------------------------------------
    # PAIN XML Generation methods // ----------------------------------------------------------------------------------

    @api.model
    def generate_sepa_pain_xml(self, data, return_mode=None):
        """
        Generate SEPA PAIN 001.03 XML using passed data
        and convert it to encoded string format
        :param data: Data used in XML forming (dict)
        :param return_mode: Indicates whether method should return ir.attachment record
        :return: None / ir.attachment record, based on method parameter
        """

        # PAIN ISO 001.001.03 Header template
        xml_template = '''<?xml version="1.0" encoding="UTF-8"?>
                          <Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"></Document>'''

        sepa_name = data.get('sepa_name') or _('Mokėjimas %s') % data.get('statement_date')

        base = objectify.fromstring(xml_template)
        e_root = SubElement(base, 'CstmrCdtTrfInitn')
        comp_info = data.get('company_info')
        payer_info = data.get('base_payer_info')

        # Generate group header
        gh_data = data.get('group_header')
        group_header = SubElement(e_root, 'GrpHdr')
        set_node(group_header, 'MsgId', gh_data.get('msg_id'))
        set_node(group_header, 'CreDtTm', gh_data.get('dt_tm'))
        set_node(group_header, 'NbOfTxs', gh_data.get('txs_num'))
        set_node(group_header, 'CtrlSum', gh_data.get('ctrl_sum'), decimal_precision=True)

        payer_party = SubElement(group_header, 'InitgPty')
        self.set_party_info_node_block(payer_party, comp_info, private=False)

        # Generate Payment information
        payment_blocks = data.get('pmt_blocks')
        for payment_block in payment_blocks:
            pmt_inf = SubElement(e_root, 'PmtInf')

            # Determine batch type
            batch_type = payment_block.get('batch_type')

            # Set base values (control sum, IDs, date, etc.)
            set_node(pmt_inf, 'PmtInfId', payment_block.get('pmt_inf_id'))
            set_node(pmt_inf, 'PmtMtd', 'TRF')
            set_node(pmt_inf, 'BtchBookg', batch_type)
            set_node(pmt_inf, 'NbOfTxs', payment_block.get('block_tx_number'))
            set_node(pmt_inf, 'CtrlSum', payment_block.get('block_control_sum'), decimal_precision=True)

            pmt_type_inf = SubElement(pmt_inf, 'PmtTpInf')
            svc_lvl = SubElement(pmt_type_inf, 'SvcLvl')
            set_node(svc_lvl, 'Cd', payment_block.get('pmt_type'))
            if batch_type == '1':
                set_node(SubElement(pmt_type_inf, 'CtgyPurp'), 'Cd', 'SALA')
            set_node(pmt_inf, 'ReqdExctnDt', payment_block.get('exec_date'))

            # Set Debtor information
            debtor_party = SubElement(pmt_inf, 'Dbtr')
            self.set_party_info_node_block(debtor_party, comp_info, private=False)

            # Set Debtor account information
            debtor_account = SubElement(pmt_inf, 'DbtrAcct')
            self.set_iban_node_block(debtor_account, payer_info.get('payer_iban'))
            set_node(debtor_account, 'Ccy', payer_info.get('payer_currency'))

            # Set Debtor bank information
            debtor_agt = SubElement(pmt_inf, 'DbtrAgt')
            self.set_bic_node_block(debtor_agt, payer_info.get('payer_bic'))

            # Set Ultimate Debtor information if it exists
            ultimate_debtor_info = payment_block.get('ultimate_debtor_info')
            if ultimate_debtor_info:
                ultimate_debtor = SubElement(pmt_inf, 'UltmtDbtr')
                self.set_party_info_node_block(ultimate_debtor, ultimate_debtor_info)

            # Set Charges information
            set_node(pmt_inf, 'ChrgBr', payment_block.get('charges'))

            # Set transaction info
            transactions = payment_block.get('transactions', [])
            for transaction in transactions:
                non_local = transaction.get('non_local')
                credit_transaction = SubElement(pmt_inf, 'CdtTrfTxInf')

                # Set payment IDs
                payment_id = SubElement(credit_transaction, 'PmtId')
                set_node(payment_id, 'InstrId', transaction.get('instruction_id'))
                set_node(payment_id, 'EndToEndId', transaction.get('end_to_end_id'))

                # Set amount
                amount = SubElement(credit_transaction, 'Amt')
                set_node_and_tag(p_node=amount, c_node='InstdAmt',
                                 c_text=transaction.get('transfer_amount'),
                                 c_tag_key='Ccy', c_tag=transaction.get('transfer_currency'),
                                 decimal_precision=True)

                # Set creditor bic
                creditor_agt = SubElement(credit_transaction, 'CdtrAgt')
                self.set_bic_node_block(creditor_agt, transaction.get('creditor_bic'))

                # Set creditor info
                creditor_party = SubElement(credit_transaction, 'Cdtr')
                self.set_party_info_node_block(creditor_party, transaction.get('creditor_info'), non_local=non_local)

                # Set creditor IBAN
                creditor_account = SubElement(credit_transaction, 'CdtrAcct')
                if transaction.get('iban_format'):
                    self.set_iban_node_block(creditor_account, transaction.get('creditor_iban'))
                else:
                    # If creditor country is not EU, use different IBAN node structure
                    other_node = SubElement(SubElement(creditor_account, 'Id'), 'Othr')
                    set_node(other_node, 'Id', transaction.get('creditor_iban'))

                # Set References
                reference_info_node = SubElement(credit_transaction, 'RmtInf')
                reference_data = transaction.get('reference_info')

                if reference_data.get('type') == 'unstructured':
                    # Set unstructured reference info
                    set_node(reference_info_node, 'Ustrd', reference_data.get('ref'))
                else:
                    # Set structured reference info
                    if reference_data.get('extra_rules') == 'CITADELE':
                        set_node(reference_info_node, 'Ustrd', reference_data.get('ref'))
                    credit_ref_info = SubElement(SubElement(reference_info_node, 'Strd'), 'CdtrRefInf')
                    cd_pr = SubElement(SubElement(credit_ref_info, 'Tp'), 'CdOrPrtry')
                    set_node(cd_pr, 'Cd', 'SCOR')
                    set_node(credit_ref_info, 'Ref', reference_data.get('ref'))

        objectify.deannotate(base)
        etree.cleanup_namespaces(base)
        generated_xml = etree.tostring(base, xml_declaration=True, encoding='utf-8')
        final_xml = parseString(generated_xml).toprettyxml(encoding='UTF-8')
        xsd_file = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', 'xsd_schemas')) + '/pain.001.001.03.xsd'

        if not xml_validator(final_xml, xsd_file=xsd_file):
            raise exceptions.UserError(_('Failo sugeneruoti nepavyko'))

        attach_vals = {
            'res_model': 'res.company' if return_mode == 'script_attachment' else self._name,
            'name': sepa_name + '.xml',
            'datas_fname': sepa_name + '.xml',
            'res_id': self.env.user.company_id.id if return_mode == 'script_attachment' else self.id,
            'type': 'binary',
            'db_datas': final_xml.encode('base64'),
        }
        res = self.env['ir.attachment'].sudo().create(attach_vals)
        if return_mode and return_mode in ['attachment', 'script_attachment']:
            return res

    @api.model
    def set_party_info_node_block(self, root, party_info, private=True, non_local=False):
        """
        Sub intermediate elements and party info (creditor/debtor/ultimate debtor)
        :param root: root node in which the new node should be created
        :param party_info: passed party information -- code, name, type (dict)
        :param private: Indicates what intermediate node should be used
        :param non_local: Indicates whether partner is of different country
        :return: None
        """
        set_node(root, 'Nm', party_info.get('name'))
        party_code = party_info.get('code')
        # if transfer is non-local set the address field
        if non_local:
            address_root = SubElement(root, 'PstlAdr')
            set_node(address_root, 'Ctry', party_info.get('country_code'))
            set_node(address_root, 'AdrLine', party_info.get('address'))
        if party_code:
            party_type = party_info.get('type')
            id_root = SubElement(root, 'Id')
            intermediate = \
                SubElement(id_root, 'PrvtId') if private and party_type == 'NIDN' else SubElement(id_root, 'OrgId')
            other_info = SubElement(intermediate, 'Othr')
            set_node(other_info, 'Id', party_code)
            scheme_name = SubElement(other_info, 'SchmeNm')
            set_node(scheme_name, 'Cd', party_type)

    @api.model
    def set_bic_node_block(self, root, bic):
        """
        Sub intermediate element and set bic node on passed root element
        :param root: root node in which the new node should be created
        :param bic: passed bic code
        :return: None
        """
        institution_id = SubElement(root, 'FinInstnId')
        set_node(institution_id, 'BIC', bic)

    @api.model
    def set_iban_node_block(self, root, iban):
        """
        Sub intermediate element and set IBAN node on passed root element
        :param root: root node in which the new node should be created
        :param iban: passed IBAN
        :return: None
        """
        party_id = SubElement(root, 'Id')
        set_node(party_id, 'IBAN', iban)

    # -----------------------------------------------------------------------------------------------------------------
    # PAIN XML data preparing methods // ------------------------------------------------------------------------------

    @api.model
    def prepare_pain_data(self, statement_lines, extra_data, flags):
        """
        Prepare data for PAIN XML export. Method can be called from a script, because
        it's not wizard bound.
        :param statement_lines: account.bank.statement.lines that are meant to be exported
        :param extra_data: (dict) of extra data to be used.
            -account.journal record of type bank that represents the company account from
            which the payment is going to be done
        :param flags: (dict) of parameters shaping the behaviour
            -group_transfer flag -- indicates whether export is SALA or not
            -ultimate_debtor_export -- indicates whether ultimate debtor node block should be included
            -international_priority -- Used only if some lines contain international transfers,
            can signify the priority of the transfer. Use static values expected by bank
            NURG - Not urgent, URGP - Urgent, SDVA - Most urgent
        :return: (dict) data structure that is used for pain export, compatible with generate_sepa_pain_xml method
        """
        self.validate_base_data(extra_data)

        # Sort passed statement lines and prepare PmtInf blocks
        payment_block_data = self.lines_sorting(statement_lines, extra_data, flags)

        # Arrange data in expected structure and return it
        journal = extra_data.get('journal')
        company = self.sudo().env.user.company_id
        return {
            'group_header': {
                'msg_id': self.get_msg_id(),
                'dt_tm': str(strftime("%Y-%m-%dT%H:%M:%S", gmtime())),
                'txs_num': sum(x.get('block_tx_number', 0) for x in payment_block_data),
                'ctrl_sum': sum(x.get('block_control_sum', 0) for x in payment_block_data)
            },
            'company_info': {
                'name': company.name,
                'code': company.company_registry or company.vat,
                'type': 'COID' if company.company_registry else 'TXID'
            },
            'base_payer_info': {
                'payer_iban': rm_spaces(journal.bank_acc_number),
                'payer_bic': rm_spaces(journal.bank_id.bic),
                'payer_currency': journal.currency_id.name or self.env.user.company_id.currency_id.name,
            },
            'sepa_name': extra_data.get('statement_name', str()),
            'statement_date': extra_data.get('statement_date', str()),
            'pmt_blocks': payment_block_data
        }

    @api.model
    def lines_sorting(self, statement_lines, extra_data, flags):
        """
        Sort bank statement lines by PmtInf blocks so it fits PAIN XML format.
        Blocks are sorted by date, transaction country and ultimate debtor parameters.
        :param statement_lines: account.bank.statement records
        :param extra_data: extra relational field data (currency, journal, etc.)
        :param flags: extra context (international_priority, etc.)
        :return: data sorted for PmtInf formatting - [{}, {}...]
        """
        payment_info_blocks = []

        utc_today = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        international_map = set(statement_lines.mapped('is_international'))
        for is_international in international_map:
            lines_inter = statement_lines.filtered(lambda x: x.is_international is is_international)
            dates_map = set(d if d >= utc_today else utc_today for d in lines_inter.mapped('date'))
            for date in dates_map:
                lines_date = lines_inter.filtered(
                    lambda x: x.date == date or date == utc_today and x.date < date)
                flags.update({'forced_date': date})
                if flags.get('ultimate_debtor_export'):
                    ud_lines = lines_date.filtered(lambda x: x.ultimate_debtor_id)
                    non_ud_lines = lines_date.filtered(lambda x: not x.ultimate_debtor_id)
                    for ud in ud_lines.mapped('ultimate_debtor_id'):
                        lines_partner = lines_date.filtered(lambda x: x.ultimate_debtor_id == ud)
                        payment_info_blocks.append(self.prepare_payment_block(lines_partner, extra_data, flags))
                    if non_ud_lines:
                        payment_info_blocks.append(self.prepare_payment_block(non_ud_lines, extra_data, flags))
                else:
                    payment_info_blocks.append(self.prepare_payment_block(lines_date, extra_data, flags))
        if not payment_info_blocks:
            raise exceptions.UserError(_('Nėra mokėtinų įrašų'))
        return payment_info_blocks

    @api.model
    def prepare_payment_block(self, statement_lines, extra_data, flags):
        """
        Prepare and format data for PmtInfo block
        :param statement_lines: account.bank.statement.line records
        :param extra_data: used relational fields
        :param flags: used context
        :return: payment_info data (dict)
        """
        company_country_code = self.env.user.company_id.country_id.code or 'LT'

        # Set flags
        group_transfer = flags.get('group_transfer')
        inter_priority = flags.get('international_priority')
        forced_date = flags.get('forced_date')

        # Set passed params
        journal = extra_data.get('journal')
        currency = extra_data.get('currency')
        charge_info = extra_data.get('charge_info')

        block_tx_number = 0
        block_control_sum = 0.0
        base_object = statement_lines[0]
        transactions = []

        # Get global sanitize rules
        global_sanitize_rules = self.get_sanitize_rules()

        # Get negative amount lines
        filtered_lines = statement_lines.filtered(
            lambda x: tools.float_compare(0.0, x.amount, precision_digits=2) > 0)

        if not filtered_lines:
            raise exceptions.UserError(_('Nėra mokėtinų įrašų'))
        self.validate_statement_lines(filtered_lines, journal, group_transfer=group_transfer)

        for line in filtered_lines:
            # Get line sanitize rules
            line_sanitize_rules = self.get_sanitize_rules(line_id=line)
            # Get bank account
            bank_account_id = line.bank_account_id or line.partner_id.get_preferred_bank(journal)

            # Get IBAN (we can safely access first two characters, since IBAN is already validated)
            creditor_iban = rm_spaces(bank_account_id.acc_number)
            non_local = creditor_iban[:2] != company_country_code
            try:
                validate_iban(creditor_iban)
                iban_format = True
            except exceptions.ValidationError:
                iban_format = False
            # Get and sanitize creditor info
            creditor_info = self.get_partner_data(line.partner_id, line_sanitize_rules)
            # Get and sanitize creditor bic
            creditor_bic = rm_spaces(line.bank_account_id.bank_bic)
            # Get ant sanitize transfer amount/currency and reference
            transfer_amount = abs(line.amount_currency) if line.currency_id else abs(line.amount)
            transfer_currency = line.currency_id and line.currency_id.name or currency.name
            payment_reference = multiple_replace(line.name, **line_sanitize_rules)

            if len(payment_reference) > 140:
                payment_reference = payment_reference[:140]

            # Prepare transaction information used in PAIN XML formatting
            transaction = {
                'instruction_id': self.env['bank.export.job'].calculate_composite_instruction_id(line),
                'end_to_end_id': str(line.invoice_id) if line.invoice_id else 'NOTPROVIDED',
                'transfer_amount': transfer_amount,
                'transfer_currency': transfer_currency,
                'creditor_bic': creditor_bic,
                'creditor_iban': creditor_iban,
                'transaction_date': line.date,
                'creditor_info': creditor_info,
                'non_local': non_local,
                'iban_format': iban_format,
                'reference_info': {
                    'type': line.info_type,
                    'ref': payment_reference,
                    'extra_rules': journal.bank_id.sudo().sepa_export_rules_code
                }
            }
            # Increment control numbers
            block_tx_number += 1
            block_control_sum += transfer_amount

            transactions.append(transaction)
        payment_block = {
            'pmt_inf_id': str(self.get_pmt_inf_id()),
            'exec_date': forced_date or base_object.date,
            'block_control_sum': block_control_sum,
            'block_tx_number': block_tx_number,
            'batch_type': '1' if group_transfer else '0',
            'pmt_type': inter_priority if base_object.is_international else 'SEPA',
            'transactions': transactions,
            'charges': charge_info or 'SHAR' if base_object.is_international else 'SLEV'
        }
        # Update block with ultimate debtor info
        if base_object.ultimate_debtor_id:
            ultimate_debtor_info = self.get_partner_data(base_object.ultimate_debtor_id, global_sanitize_rules)
            payment_block.update({'ultimate_debtor_info': ultimate_debtor_info})

        return payment_block

    @api.model
    def get_partner_data(self, partner_id, line_sanitize_rules):
        """
        Gets and formats partner data for PmtInf block
        (Used twice thus separate method)
        :param partner_id: res.partner record
        :param line_sanitize_rules: account.bank.statement.line sanitize rules
        :return: structured partner info (dict)
        """
        partner_name = multiple_replace(partner_id.get_bank_export_name(), **line_sanitize_rules)
        partner_address = multiple_replace(partner_id.get_bank_export_address(), **line_sanitize_rules)

        partner_code = partner_id.kodas or ''
        if not partner_code and self.env.user.is_accountant():
            employees = partner_id.with_context(active_test=False).employee_ids
            if employees:
                partner_code = employees[0].identification_id or ''
        if len(partner_name) > 70:
            partner_name = partner_name[:70]
        return {
            'name': partner_name,
            'code': partner_code,
            'type': 'COID' if partner_id.is_company else 'NIDN',
            'country_code': partner_id.country_id.code or 'LT',
            'address': partner_address,
        }

    # -----------------------------------------------------------------------------------------------------------------
    # PAIN XML data validation methods // -----------------------------------------------------------------------------

    @api.model
    def validate_base_data(self, extra_data):
        """
        Validate constraints for base data before using it in SEPA XML export.
        :param extra_data: account.bank.statement data or data passed to script
        :return: None
        """
        body = str()
        journal = extra_data.get('journal')
        currency = extra_data.get('currency')
        company = self.sudo().env.user.company_id

        if not isinstance(journal, type(self.env['account.journal'])) or not isinstance(
                currency, type(self.env['res.currency'])):
            body += _('Paduoti neteisingi papildomi parametrai Valiuta/Žurnalas\n')
        if not company.company_registry and not company.vat:
            body += _('Nenurodytas nei kompanijos kodas nei PVM mokėtojo numeris')
        if not journal or not journal.bank_id or not journal.bank_id.bic or not journal.bank_acc_number:
            body += _('Nepaduotas arba nesukonfigūruotas (bankas, banko kodas, IBAN) pagrindinis žurnalas\n')
        if journal.bank_acc_number and (len(journal.bank_acc_number) > 35 or len(journal.bank_acc_number) < 2):
            body += _('Neteisinga mokėtojo IBAN sąskaita\n')
        if body:
            body = _('SEPA Eksportavimas nepavyko, klaidos pranešimas: \n\n' + body)
            raise exceptions.ValidationError(body)

    @api.model
    def validate_statement_lines(self, statement_lines, journal, group_transfer=False):
        """
         Validate constraints for account.bank.statement.lines before using them in SEPA XML export.
        :param statement_lines: account.bank.statement lines to-be-validated
        :param journal: related statement account.journal or passed account.journal
        :param group_transfer: indicates whether to-be-created XML file is group transfer
        :return: None
        """
        body = str()
        for line in statement_lines:
            # Check whether partner exists
            if not line.partner_id:
                body += _('Eilutė %s neturi priskirto partnerio.\n') % line.name
            # Check whether bank account exists
            bank_account_id = line.bank_account_id
            if line.partner_id and not bank_account_id:
                bank_account_id = line.partner_id.get_preferred_bank(journal)
                line.bank_account_id = bank_account_id
            if not bank_account_id:
                body += _('Eilutė %s neturi priskirtos banko sąskaitos.\n') % line.name
            # if bank account exists check if it passes all the constraints
            if bank_account_id:
                iban_code = rm_spaces(bank_account_id.acc_number)
                if not iban_code or len(iban_code) > 35 or len(iban_code) < 2:
                    body += _('Eilutė %s, neteisinga gavėjo IBAN sąskaita.\n') % line.name
                if iban_code and group_transfer and iban_code[:2] != 'LT':
                    body += _('Eilutė %s, negalima suformuoti grupinio '
                              'mokėjimo tarptautiniam pavedimui.\n') % line.name
            # Check if BIC exists
            if bank_account_id and not bank_account_id.bank_bic:
                body += _('Eilutė %s, neteisingas gavėjo banko BIC kodas.\n') % line.name
            # Check if structured payment reference is not too long
            if line.info_type == 'structured' and len(line.name) > 35:
                body += _('Eilutė %s, struktūruota mokėjimo '
                          'paskirtis gali būti nedaugiau 35 simbolių!.\n') % line.name
            # Check if amount is not too big
            transfer_amount = abs(line.amount_currency) if line.currency_id else abs(line.amount)
            if len(str(round(transfer_amount * 100, 0))) > 14:
                body += _('Eilutė %s, per didelė suma. \n') % line.name

        if body:
            body = _('SEPA Eksportavimas nepavyko, klaidos pranešimas: \n\n' + body)
            raise exceptions.ValidationError(body)
