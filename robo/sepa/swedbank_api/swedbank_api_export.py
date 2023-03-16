# -*- encoding: utf-8 -*-
from odoo import fields, models, _, api, exceptions, tools
from datetime import datetime
import pytz
import os
import subprocess32 as subprocess
from lxml import etree, objectify
from odoo.addons.base_iban.models.res_partner_bank import validate_iban
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta
from odoo.addons.sepa import api_bank_integrations as abi
import swedbank_tools as st


def get_date_from_now(week=True):
    """
    Get the date that was a week/month ago from now.
    returns the week ago by default, if week=False is specified, gets the date a month ago
    :param week: Indicates whether the period is week (could be expanded)
    :return: date (str)
    """
    args = {'days': 7} if week else {'months': 1}
    offset = int(datetime.now(pytz.timezone('Europe/Vilnius')).strftime('%z')[1:3])
    date_from = datetime.utcnow() - relativedelta(**args) - relativedelta(
        days=1, hour=0, minute=0, second=0, hours=offset)
    return date_from


class SwedBankAPIExport(models.TransientModel):
    _name = 'swed.bank.api.export'
    _description = 'Transient model that is used for bank statement export requests from SwedBank using API solutions'

    @api.model
    def _default_date_to(self):
        offset = int(datetime.now(pytz.timezone('Europe/Vilnius')).strftime('%z')[1:3])
        return datetime.utcnow() - relativedelta(days=1, hour=23, minute=59, second=59) - relativedelta(hours=offset)

    @api.model
    def _default_date_from(self):
        offset = int(datetime.now(pytz.timezone('Europe/Vilnius')).strftime('%z')[1:3])
        return datetime.utcnow() - relativedelta(days=1) - relativedelta(day=1, hour=0, minute=0,
                                                                         second=0) - relativedelta(hours=offset)

    journal_id = fields.Many2one('account.journal', string='Žurnalas')
    date_from = fields.Datetime(string='Data nuo', default=_default_date_from)
    date_to = fields.Datetime(string='Data iki', default=_default_date_to)

    @api.model
    def get_related_journals(self):
        """returns configured/active swed-bank journal record-set"""
        journals = self.env['account.journal'].with_context(active_test=True).search(
            [('show_on_dashboard', '=', True), ('api_integrated_bank', '=', True),
             ('api_bank_type', '=', 'swed_bank'), ('gateway_deactivated', '=', False)])
        return journals

    @api.model
    def cron_query_daily_statements(self):
        """
        Loop through Swed-bank journals, check whether bank statement
        for yesterday exists - if it does not, query XML's
        for corresponding journal for a week period of time
        :return: None
        """

        # Get the needed dates
        day_to_check = (datetime.utcnow() - relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_from = get_date_from_now()

        # Search for Swed journals
        journals = self.get_related_journals()
        for journal in journals:
            # Check for previous day statement for current journal
            day_before_statement = self.env['account.bank.statement'].search(
                [('journal_id', '=', journal.id),
                 ('date', '=', day_to_check),
                 ('sepa_imported', '=', True)], limit=1)

            # If statement from day before does not exist, or does not have any lines - query the bank
            if not day_before_statement.line_ids:
                wiz_id = self.create({'journal_id': journal.id, 'date_from': date_from})
                wiz_id.query_statements()

    @api.model
    def cron_query_monthly_statements(self):
        """
        Query XML's for every corresponding journal for a month period of time
        DB's that have huge transaction streams can have this cron disabled
        :return: None
        """
        date_from = get_date_from_now(week=False)
        self.cron_query_period_statements(date_from)

    @api.model
    def cron_query_weekly_statements(self):
        """
        Query XML's for every corresponding journal for a week period of time
        :return: None
        """
        date_from = get_date_from_now()
        self.cron_query_period_statements(date_from)

    @api.model
    def cron_query_period_statements(self, date_from):
        """
        Query XML's for every corresponding journal for a passed period of time
        :return: None
        """
        journals = self.get_related_journals()
        for journal in journals:
            date_to_use = date_from
            statement = self.env['account.bank.statement'].search(
                [('journal_id', '=', journal.id), ('state', '=', 'confirm')], order='date asc', limit=1)
            if statement:
                date_st = datetime.strptime(statement.date, tools.DEFAULT_SERVER_DATE_FORMAT)
                if date_st > date_to_use:
                    date_to_use = date_st
            date_to_use = date_to_use.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            wiz_id = self.create({'journal_id': journal.id, 'date_from': date_to_use})
            wiz_id.query_statements()

    @api.multi
    def format_statement_request_xml(self):
        """
        Method that is used to format ISO20022 CAMT.060.001.03 xml file, to request statements for specific client
        :return: Request XML in str format
        """
        self.ensure_one()

        def set_node(node, key, value):
            el = etree.Element(key)
            if isinstance(value, (float, int)) and not isinstance(value, bool):
                value = str(value)
            if value:
                el.text = value
            setattr(node, key, el)

        def format_datetime(value=False, nullable=False):
            if nullable and not value:
                return False
            value = datetime.now(pytz.timezone('Europe/Vilnius')).strftime(
                tools.DEFAULT_SERVER_DATETIME_FORMAT) if not value else value
            return value.replace(' ', 'T')

        if self.journal_id.api_bank_type != 'swed_bank':
            raise exceptions.ValidationError(_('Operacija galima tik Swedbank išrašams!'))
        try:
            validate_iban(self.journal_id.bank_acc_number)
        except ValidationError:
            raise exceptions.ValidationError(_('Klaidingas banko IBAN numeris!'))

        # Get the currency of the current journal
        currency = self.journal_id.currency_id or self.env.user.company_id.currency_id
        xml_template = '''<?xml version="1.0" encoding="UTF-8"?>
                            <Document xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
                            xmlns="urn:iso:std:iso:20022:tech:xsd:camt.060.001.03">
                            </Document>
                            '''
        root = objectify.fromstring(xml_template)
        acct_req = objectify.Element('AcctRptgReq')
        root.append(acct_req)
        group_header = objectify.Element('GrpHdr')
        set_node(group_header, 'MsgId', 'camt060_balance')
        set_node(group_header, 'CreDtTm', format_datetime())
        acct_req.append(group_header)

        seq_number = self.env['ir.sequence'].next_by_code('swed.bank.import.seq')
        r_req = objectify.Element('RptgReq')
        set_node(r_req, 'Id', seq_number)
        set_node(r_req, 'ReqdMsgNmId', 'camt.053.001.02')
        acct = objectify.Element('Acct')
        acct_id = objectify.Element('Id')
        set_node(acct_id, 'IBAN', self.journal_id.bank_acc_number)
        acct.append(acct_id)
        # Set the currency of balance request
        set_node(acct, 'Ccy', currency.name)

        acct_owner = objectify.Element('AcctOwnr')
        set_node(acct_owner, 'Pty', False)
        r_prd = objectify.Element('RptgPrd')

        from_to_dt = objectify.Element('FrToDt')
        set_node(from_to_dt, 'FrDt', self.date_from[:10])
        set_node(from_to_dt, 'ToDt', self.date_to[:10])

        from_to_tm = objectify.Element('FrToTm')
        set_node(from_to_tm, 'FrTm', self.date_from[11:] + 'Z')
        set_node(from_to_tm, 'ToTm', self.date_to[11:] + 'Z')

        r_prd.append(from_to_dt)
        r_prd.append(from_to_tm)
        set_node(r_prd, 'Tp', 'ALLL')

        r_req.append(acct)
        r_req.append(acct_owner)
        r_req.append(r_prd)
        acct_req.append(r_req)

        filename = self.env.cr.dbname + '__' + datetime.utcnow().strftime('%m-%d-%Y_%H%M%S') + '.xml'
        objectify.deannotate(root)
        etree.cleanup_namespaces(root)
        string_repr = etree.tostring(root, xml_declaration=True, encoding='utf-8')
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'xsd_schemas')) + '/camt.060.001.03.xsd'
        validated, error = abi.xml_validator(string_repr, path)
        if validated:
            return string_repr, filename
        else:
            body = 'SwedBank -- Automatic CronJob fail: Failed to validate ' \
                   'XML XSD schema, error message: %s' % error
            self.send_bug(body=body, subject='SwedBank -- Failed to validate XSD')
            return False, False

    @api.multi
    def format_account_balance_request_xml(self):
        """
        Method that is used to format ISO20022 CAMT.060.001.03 xml file, to request statements for specific client
        :return: Request XML in str format
        """

        def set_node(node, key, value):
            el = etree.Element(key)
            if isinstance(value, (float, int)) and not isinstance(value, bool):
                value = str(value)
            if value:
                el.text = value
            setattr(node, key, el)

        def format_datetime(value=False, nullable=False):
            if nullable and not value:
                return False
            value = datetime.now(pytz.timezone('Europe/Vilnius')).strftime(
                tools.DEFAULT_SERVER_DATETIME_FORMAT) if not value else value
            return value.replace(' ', 'T')

        journal_ids = self.env['account.journal'].search([])

        xml_template = '''<?xml version="1.0" encoding="UTF-8"?>
                            <Document xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
                            xmlns="urn:iso:std:iso:20022:tech:xsd:camt.060.001.03">
                            </Document>
                            '''
        swed_journals = journal_ids.filtered(
            lambda x: x.api_integrated_bank and x.api_bank_type == 'swed_bank' and not x.gateway_deactivated)
        if not swed_journals:
            return False, False
        root = objectify.fromstring(xml_template)
        acct_req = objectify.Element('AcctRptgReq')
        root.append(acct_req)
        group_header = objectify.Element('GrpHdr')
        set_node(group_header, 'MsgId', 'camt060_balance')
        set_node(group_header, 'CreDtTm', format_datetime())
        acct_req.append(group_header)

        cr_time = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

        # Get the company currency code
        company_currency = self.env.user.company_id.currency_id
        for journal_id in swed_journals:
            try:
                validate_iban(journal_id.bank_acc_number)
            except ValidationError:
                raise exceptions.Warning(_('Klaidingas banko IBAN numeris!'))

            # Get the currency for the journal
            j_currency = journal_id.currency_id or company_currency
            r_req = objectify.Element('RptgReq')

            set_node(r_req, 'ReqdMsgNmId', 'camt.052.001.02')
            acct = objectify.Element('Acct')
            acct_id = objectify.Element('Id')
            set_node(acct_id, 'IBAN', journal_id.bank_acc_number)
            acct.append(acct_id)
            # Set the currency of balance request
            set_node(acct, 'Ccy', j_currency.name)

            acct_owner = objectify.Element('AcctOwnr')
            set_node(acct_owner, 'Pty', False)
            r_prd = objectify.Element('RptgPrd')

            req_tp = objectify.Element('ReqdBalTp')
            cd_prt = objectify.Element('CdOrPrtry')
            set_node(cd_prt, 'Prtry', 'ONLYBALANCE')
            req_tp.append(cd_prt)

            from_to_dt = objectify.Element('FrToDt')
            set_node(from_to_dt, 'FrDt', cr_time[:10])
            set_node(from_to_dt, 'ToDt', cr_time[:10])

            from_to_tm = objectify.Element('FrToTm')
            set_node(from_to_tm, 'FrTm', cr_time[11:] + 'Z')
            set_node(from_to_tm, 'ToTm', cr_time[11:] + 'Z')

            r_prd.append(from_to_dt)
            r_prd.append(from_to_tm)
            set_node(r_prd, 'Tp', 'ALLL')

            r_req.append(acct)
            r_req.append(acct_owner)
            r_req.append(r_prd)
            r_req.append(req_tp)
            acct_req.append(r_req)

        filename = self.env.cr.dbname + '__BAL__' + datetime.utcnow().strftime('%m-%d-%Y_%H%M%S') + '.xml'
        objectify.deannotate(root)
        etree.cleanup_namespaces(root)
        string_repr = etree.tostring(root, xml_declaration=True, encoding='utf-8')
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'xsd_schemas')) + '/camt.060.001.03.xsd'

        validated, error = abi.xml_validator(string_repr, path)
        if validated:
            return string_repr, filename
        else:
            body = 'SwedBank -- Automatic CronJob fail: Failed to validate ' \
                   'XML XSD schema, error: %s' % error
            self.send_bug(body=body, subject='SwedBank -- Failed to validate XSD')
            return False, False

    @api.model
    def query_account_balance(self):
        """
        Method that is used to query account balance for specific IBAN from SwedBank.
        Query XML is formed and is passed to SwedBank API.
        :return: None
        """
        if not self.sudo().env.user.company_id.request_swed_bank_balance:
            return
        agr_id = self.env.user.sudo().company_id.swed_bank_agreement_id
        if not agr_id:
            return
        statement_xml, filename = self.format_account_balance_request_xml()
        if not statement_xml:
            return
        sd = st.get_swed_data(self.env)
        abs_path = sd.get('directory_path') + '/sending/' + filename
        sending_path = sd.get('directory_path') + '/sending'
        if not os.path.isdir(sending_path):
            os.mkdir(sending_path)
        with open(abs_path, 'w+') as fh:
            fh.write(statement_xml)
        os.chdir(sd.get('directory_path'))
        command = './send.sh url=%s agreementId=%s file=sending/%s erpCert=certs/%s transportCert=certs/%s ' \
                  'dir=received' % (sd.get('main_url'), str(agr_id), filename,
                                    sd.get('cert_path'), sd.get('cert_path'))
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=None, executable='/bin/bash', shell=True)
        st.handle_timeout(process)

    @api.multi
    def query_statements(self):
        """
        Method that is used to query statements from SwedBank. Query XML is formed and is passed to SwedBank API.
        :return: None
        """
        agr_id = self.env.user.sudo().company_id.swed_bank_agreement_id
        if not agr_id:
            return
        statement_xml, filename = self.format_statement_request_xml()
        if not statement_xml:
            raise exceptions.Warning(_('Klaidingai suformatuotas failas! Susisiekite su administratoriais.'))
        sd = st.get_swed_data(self.env)
        abs_path = sd.get('directory_path') + '/sending/' + filename
        sending_path = sd.get('directory_path') + '/sending'
        if not os.path.isdir(sending_path):
            os.mkdir(sending_path)
        with open(abs_path, 'w+') as fh:
            fh.write(statement_xml)
        os.chdir(sd.get('directory_path'))
        command = './send.sh url=%s agreementId=%s file=sending/%s erpCert=certs/%s transportCert=certs/%s ' \
                  'dir=received' % (sd.get('main_url'), str(agr_id), filename,
                                    sd.get('cert_path'), sd.get('cert_path'))
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=None, executable='/bin/bash', shell=True)
        st.handle_timeout(process)

    @api.model
    def query_statements_prep(self, journal, date_from, date_to, *_):
        """
        Method that prepares current wizard for bank statement
        query - accepts values as parameters, creates the record
        and executes statement querying method.
        :param journal: account.journal record
        :param date_from: date_from (str)
        :param date_to: date_to (str)
        :return: result of query_statements()
        """
        # Last parameter is statement fetch job record, it's not used in Swed's case,
        # since data querying is done between DB and Internal. However, variable
        # is in method definition to maintain the structure of bank export methods

        wizard = self.create({'journal_id': journal.id, 'date_from': date_from, 'date_to': date_to})
        return wizard.query_statements()

    @api.model
    def send_bug(self, body, subject):
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'subject': subject + ' [%s]' % self._cr.dbname,
            'error_message': body,
        })


SwedBankAPIExport()
