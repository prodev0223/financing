# -*- encoding: utf-8 -*-
from odoo import models, _, api, exceptions
from lxml import etree, objectify

# FILE USED TO STORE GLOBAL DATA/METHODS REGARDING
# API BANK INTEGRATIONS AS WELL AS A SEPARATE ABSTRACT MODEL
# FOLLOWING LISTS/DICTS SHOULD BE FILLED WHEN NEW BANK INTEGRATION IS ADDED

# 1. INTEGRATED BANK BIC CODES
PAYSERA = 'EVIULT2VXXX'
SWED_BANK = 'HABALT22'
SEB_BANK = 'CBVILT2X'

# Continuation -- Enable banking
ENABLE_BANKING_BIC_CODES = [
    SWED_BANK, SEB_BANK, 'INDULT2X', 'CBSBLT26XXX', 'AGBLLT2X', 'CBSBLT26'
]

INTEGRATED_BANK_BIC_CODES = [PAYSERA, SWED_BANK, SEB_BANK]

# 2. LIST FOR ACCOUNT JOURNAL SELECTION FIELD TO DETERMINE INTEGRATED BANK TYPE
INTEGRATED_BANKS = [('swed_bank', 'Swedbank'),
                    ('paysera', 'Paysera'),
                    ('seb_bank', 'SEB'),
                    ('enable_banking', 'Enable Banking'),
                    ('braintree', 'Braintree'),
                    ('non_integrated', 'Not-integrated')]

# Data is not exchanged via SEPA files, which has strict date rules
INTEGRATED_NON_SEPA_BANKS = ['paysera', 'enable_banking', 'braintree']

# 3. INTEGRATED BANK DISPLAY NAMES
INTEGRATED_BANKS_DISPLAY_NAMES = [_('"Paysera" Bank'), _('"Swedbank" Bank'), _('"SEB" Bank')]

# 5. List of possible bank export states, based on Swed-Bank export
# some of these states are used only on specific banks
BANK_EXPORT_STATES = [('rejected', 'Payment rejected'),
                      ('accepted', 'Payment accepted'),
                      ('processed', 'Payment processed'),
                      ('revoked', 'Payment canceled by user'),
                      ('rejected_sign', 'Failed to sign the transaction'),
                      ('rejected_partial', 'Partial payment rejected'),
                      ('accepted_partial', 'Partial payment accepted'),
                      ('revoked_partial', 'Partial payment canceled by user'),
                      ('processed_partial', 'Partial payment processed'),
                      ('waiting', 'Waiting'),
                      ('no_action', 'Not exported'),
                      ('file_export', 'Exported as a file')]

BANK_EXPORT_TYPES = [
    ('move_lines', 'Žurnalo elementai'),
    ('invoices', 'Sąskaitos faktūros'),
    ('e_invoice', 'eSąskaitos'),
    ('automatic_e_invoice_payment', 'Automatiniai eSąskaitų mokėjimai'),
    ('front_statement', 'Mokėjimo ruošinys'),
    ('bank_statement', 'Banko išrašas'),
    ('non_exported', 'Neeksportuota'),
]

# 6. EXPORTABLE/ACCEPTED/REJECTED STATES (IF OBJECT IS IN OTHER STATE, DENY THE EXPORT TO BANK)
EXPORTABLE_STATES = ['rejected', 'no_action', 'rejected_partial', 'file_export',
                     'accepted_partial', 'processed_partial', False, 'revoked', 'revoked_partial']
ACCEPTED_STATES = ['accepted', 'processed', 'accepted_partial', 'processed_partial']
NON_SIGNED_ACCEPTED_STATES = ['accepted', 'accepted_partial']
POSITIVE_STATES = ['waiting', 'revoked', 'revoked_partial'] + ACCEPTED_STATES
REJECTED_STATES = ['rejected', 'rejected_partial']
REVOKED_STATES = ['revoked', 'revoked_partial']
EXTERNAL_SEPA_PROCESSED_STATES = ['ACCP', 'ACSP', 'ACWC', 'ACSC']
EXTERNAL_SEPA_REJECTED_STATES = ['RJCT']
EXTERNAL_SEPA_ACCEPTED_STATES = ['PDNG']

# 7. INTEGRATION TYPES (FOR NOW EITHER sepa_xml OR api)
INTEGRATION_TYPES = {
    'swed_bank': 'sepa_xml',
    'seb_bank': 'sepa_xml',
    'paysera': 'api',
}

# 8. eINVOICES, bank BICs that are allowed to receive eINVOICES.
E_INVOICE_ALLOWED_BANKS = ['INDULT2X', 'CBVILT2X', 'AGBLLT2X', 'NDEALT2X', 'CBSBLT26XXX', 'HABALT22', 'MDBALT22']

# 9. eINVOICES, bank BICs that are allowed to receive automatic payments.
E_INVOICE_AUTOMATIC_PAYMENT_BANKS = ['HABALT22']

# 10. Partner codes that must have structured payment reference when exporting to bank
ST_REF_PARTNER_CODES = ['191630223', '188659752']


INFORM_EXPORT_DATA_TYPES = ['invoices', 'e_invoice', 'move_lines', 'front_statement']


def xml_validator(some_xml_string, xsd_file='/path/to/my_schema_file.xsd'):
    """Validates various bank XML files (CAMT/PAIN/E-INVOICE/etc...)"""
    try:
        schema = etree.XMLSchema(file=xsd_file)
        parser = objectify.makeparser(schema=schema)
        objectify.fromstring(some_xml_string, parser)
        return True, str()
    except Exception as exc:
        return False, exc.args[0]


class APIBankIntegrations(models.AbstractModel):
    _name = 'api.bank.integrations'

    @api.model
    def check_api_configuration(self, journal):
        """
        Checks whether passed journal belongs to currently
        integrated banks, and check whether it's configured.
        Several checks are being executed:
        'integrated bank' Check -
            Checks if journal belongs to bank which is integrated.
        'integrated journal' Check -
            Checks if journal belongs to bank which is integrated,
            and journal itself is not externally disabled (for example related wallet)
        'full integration' Check -
            Checks if journal belongs to bank which is integrated,
            and if it's partially or fully integrated - if data is only fetched
            from the bank (statements, balance), and full - if data
            can also be sent to the bank (registering transfers)
        :param journal: account.journal record (optional)
        :return: True if configured otherwise False
        """

        int_bank = int_journal = full_int = False
        api_bank_type = 'non_integrated'
        # Check PAYSERA configuration
        if journal.bank_id.bic == PAYSERA:
            # Check whether Paysera is configured (In this case we don't check for TOKENS),
            # whether specific wallet for the journal is configured and working and if
            # API integration is full or partial
            configuration = self.env['paysera.api.base'].get_configuration()

            int_bank = self.env['paysera.api.base'].check_configuration()
            int_journal = int_bank and self.env['paysera.wallet'].get_related_wallet(
                journal, raise_exception=False)
            full_int = int_bank and configuration.api_mode == 'full_integration'
            api_bank_type = 'paysera'

        # Check SWED-BANK configuration
        if journal.bank_id.bic == SWED_BANK:
            company = self.env.user.sudo().company_id
            swed_bank_agr_id = company.swed_bank_agreement_id
            if swed_bank_agr_id:
                # In Swed bank case, only full integration is possible
                # and we do not need to confirm access for each specific
                # IBAN, thus all journals are always integrated.
                int_bank = int_journal = full_int = True
                api_bank_type = 'swed_bank'

        # Check SEB-BANK configuration
        if journal.bank_id.bic == SEB_BANK:
            configuration = self.env['seb.api.base'].get_configuration(raise_exception=False)
            if configuration:
                int_bank = configuration.check_configuration()
                full_int = int_bank and configuration.payment_init_endpoint
                int_journal = int_bank and self.env['seb.api.journal'].search_count(
                    [('journal_id', '=', journal.id), ('state', '=', 'working')]
                )
                api_bank_type = 'seb_bank'

        # Check for Braintree journal
        if not journal.bank_id.id and journal.import_file_type == 'braintree_api':
            # Check whether configured merchant account exists for this journal
            if self.env['braintree.merchant.account'].get_configured_accounts(journal=journal):
                int_bank = int_journal = True
                api_bank_type = 'braintree'

        # Priority is given to stand-alone integrations before enable banking
        if not int_bank and journal.bank_id.bic in ENABLE_BANKING_BIC_CODES:
            # Enable banking does not provide payment initiation, thus
            # integration is never marked as full
            integrated_bic_codes = self.env['enable.banking.connector'].sudo().get_integrated_bic_codes()
            if journal.bank_id.bic in integrated_bic_codes:
                int_bank = int_journal = True
                api_bank_type = 'enable_banking'

        return {
            'int_bank': int_bank,
            'int_journal': int_journal,
            'full_int': full_int,
            'api_bank_type': api_bank_type,
        }

    @api.model
    def get_bank_method(self, journal, m_type='push_transactions'):
        """
        Method that maps passed action/journal to specific bank integration
        model and function.
        :param journal: account.journal record
        :param m_type: method type (only 'push_transactions' for now)
        :return: model, method
        """

        # METHODS OF SWED-BANK
        if journal.api_bank_type == 'swed_bank':
            if m_type == 'push_transactions':
                return 'swed.bank.api.import', 'push_bank_statements'
            elif m_type in ['query_transactions', 'query_transactions_non_threaded']:
                return 'swed.bank.api.export', 'query_statements_prep'

        # METHODS OF SEB-BANK
        if journal.api_bank_type == 'seb_bank':
            if m_type == 'push_transactions':
                return 'seb.api.base', 'api_push_bank_statements'
            elif m_type == 'query_transactions':
                return 'seb.api.base', 'api_fetch_transactions_prep'
            elif m_type == 'query_transactions_non_threaded':
                return 'seb.api.base', 'api_fetch_transactions'

        # METHODS OF PAYSERA
        elif journal.api_bank_type == 'paysera':
            if m_type == 'push_transactions':
                return 'paysera.api.base', 'api_push_bank_statements'
            elif m_type == 'sign_transaction':
                return 'paysera.api.base', 'api_sign_bank_statement'
            elif m_type == 'query_transactions':
                return 'paysera.api.base', 'api_fetch_transactions_prep'
            elif m_type == 'query_transactions_non_threaded':
                return 'paysera.api.base', 'api_fetch_transactions'
            elif m_type == 'check_live_tr_state':
                return 'paysera.api.base', 'api_check_live_transaction_state'

        # METHOD(S) OF ENABLE BANKING
        elif journal.api_bank_type == 'enable_banking' \
                and m_type in ['query_transactions_non_threaded', 'query_transactions']:
            return 'enable.banking.api.base', 'api_get_bank_transactions'

        # METHOD(S) OF BRAINTREE
        elif journal.api_bank_type == 'braintree' \
                and m_type in ['query_transactions_non_threaded', 'query_transactions']:
            return 'braintree.merchant.account', 'api_fetch_transactions'

        raise exceptions.ValidationError(
            _('Bank integration or method was not found! Journal name - "{}"').format(journal.name))

    @api.model
    def allow_transaction_signing(self, journal):
        """
        Check whether transaction signing is available for specific bank
        based on passed account.journal, return True if its available
        otherwise return False
        :param journal: account.journal record
        :return: True/False
        """
        allow_signing = False
        if journal.api_bank_type == 'paysera':
            configuration = self.env['paysera.api.base'].get_configuration()
            allow_signing = configuration.sudo().allow_external_signing
        return allow_signing

    @api.model
    def allow_live_export_state_checking(self, journal):
        """
        Check whether external live transaction state checking is available
        based on passed account.journal, return True if its available
        otherwise return False
        :param journal: account.journal record
        :return: True/False
        """
        allow_checking = False
        if journal.api_bank_type == 'paysera':
            allow_checking = True
        return allow_checking

    @api.model
    def configure_related_bank_journals(self, bank_bic):
        """
        Recompute/Reconfigure account.journal records in the system based on
        passed bank bic code.
        :param bank_bic: bank bic code (str)
        :return: None
        """
        if bank_bic not in INTEGRATED_BANK_BIC_CODES:
            raise exceptions.ValidationError(
                _('Integration for passed bank was not found! Bank BIC - {}').fortmat(bank_bic))
        elif bank_bic == PAYSERA:
            journals = self.env['account.journal'].search([('bank_id.bic', '=', PAYSERA)])
            journals._compute_api_integrated_bank()

    @api.model
    def convert_to_partial_state(self, export_state):
        """
        Converts standard export state to partial
        :param export_state: bank export state (str)
        :return: converted bank export state (str)
        """
        if export_state in ['rejected', 'accepted', 'processed']:
            export_state += '_partial'
        return export_state

    @api.model
    def get_bank_export_state_html_data(self, model, state, extra_data=None):
        """
        Return formed badge in HTML string format for bank export
        state representation. Badge is formed based on bank export
        state, model of the record and some extra data if it's provided
        :param model: model of the record (str)
        :param state: state of bank export (str)
        :param extra_data: extra data (dict)
        :return: formed HTML badge (str)
        """
        partial_template = _('Partial bank payment export was ')
        full_template = _('Bank payment export was ')
        extra_data = {} if extra_data is None else extra_data

        style = str()
        # Check whether state is REJECTED (Did not reach the bank, or was rejected)
        if state == 'rejected':
            # Get the title based on some extra data and model
            if extra_data.get('inv_type') == 'out_invoice' and model == 'account.invoice':
                title = _('eInvoice export was rejected')
            else:
                title = full_template + _('rejected')
            i_class = 'fa-exclamation-triangle'
            button_class = 'text-danger'
        # Check whether state is ACCEPTED (Reached the bank with draft state)
        elif state == 'accepted':
            if extra_data.get('inv_type') == 'out_invoice' and model == 'account.invoice':
                title = _('eInvoice export was accepted')
            else:
                title = full_template + _('accepted')
            i_class = 'fa-check-circle'
            button_class = 'text-info'
        # Check whether state is REVOKED (Cancelled by the client in the bank)
        elif state == 'revoked':
            title = full_template + _('revoked by the user')
            i_class = 'fa-check-circle'
            button_class = 'text-warning'
        # Check whether state is PROCESSED (Was either signed in the bank, or the payment already reached
        # the desired recipient)
        elif state == 'processed':
            if extra_data.get('inv_type') == 'out_invoice' and model == 'account.invoice':
                title = _('eInvoice was accepted and paid')
            else:
                title = full_template + _('accepted and processed')
            i_class = 'fa-check-circle'
            button_class = 'text-success'
        # Check whether state is REJECTED PARTIAL (Only applies to account invoice export wizard, where
        # not all of the sum can be exported)
        elif state == 'rejected_partial':
            title = partial_template + _('rejected')
            i_class = 'fa-exclamation-triangle'
            button_class = 'text-danger'
        # Check whether state is ACCEPTED PARTIAL (Only applies to account invoice export wizard, where
        # not all of the sum can be exported)
        elif state == 'accepted_partial':
            title = partial_template + _('accepted')
            i_class = 'fa-check-circle'
            button_class = 'text-info'
        # Check whether state is REVOKED (Cancelled by the client in the bank)
        elif state == 'revoked_partial':
            title = partial_template + _('revoked by the user')
            i_class = 'fa-check-circle'
            button_class = 'text-warning'
        # Check whether state is PROCESSED PARTIAL (Only applies to account invoice export wizard, where
        # not all of the sum can be exported)
        elif state == 'processed_partial':
            title = partial_template + _('accepted and processed')
            i_class = 'fa-check-circle'
            button_class = 'text-success'
        # Check whether state is WAITING (No answer was yet received from the bank)
        elif state == 'waiting':
            if extra_data.get('inv_type') == 'out_invoice' and model == 'account.invoice':
                title = _('eInvoice was successfully exported.')
            else:
                title = _('Payment was successfully exported.')
            title += _(' Waiting for a response from the bank.')
            i_class = 'fa-refresh'
            button_class = 'text-info'
        # If model is account invoice and exported_sepa bool is checked it acts as exported record
        elif extra_data.get('exported_sepa'):
            title = _('Exported payment')
            i_class = 'fa-check-circle'
            button_class = 'text-info'
            if extra_data.get('expense_state') == 'paid':
                style = 'color: #468847'
        # neopay
        elif extra_data.get('paid_using_online_payment_collection_system'):
            title = _('Paid using online payment collection system')
            i_class = 'fa-check-circle'
            button_class = 'text-info'
            if extra_data.get('expense_state') == 'paid':
                style = 'color: #468847'
        else:
            title = i_class = button_class = False
        style = '''style="{0}"'''.format(style)

        # Return composed badge HTML
        if title and i_class and button_class:
            return '''<button type="button" title="{0}" class="o_icon_button 
            {1}"><i title="{0}" class="fa {2}" {3}></i></button>'''.format(title, button_class, i_class, style)
        else:
            return str()

    @api.model
    def get_bank_export_state_alert_html_data(self, state, model=None, extra_data=None):
        """
        Return formed alert in HTML string format for bank export
        state representation. Badge is formed based on bank export
        state, model of the record and some extra data if it's provided
        :param state: state of bank export (str)
        :param model: model of the record (str)
        :param extra_data: extra data (dict)
        :return: formed HTML alert (str)
        """

        extra_data = {} if extra_data is None else extra_data
        date = extra_data.get('exported_sepa_date') or str()
        exported_sepa = extra_data.get('exported_sepa')
        e_invoice = extra_data.get('inv_type') == 'out_invoice' and model == 'account.invoice'
        export_partner = extra_data.get('last_export_partner_name')
        message = alert_type = str()

        # Determine info type and message content
        if state in ['no_action', 'file_export'] and exported_sepa:
            message = _('Payment was exported{}').format(_(' on - %s') % date if date else str())
            if export_partner:
                message += _('. Exported by - {}').format(export_partner)
            alert_type = 'info'
        elif state == 'waiting':
            if e_invoice:
                message = _('eInvoice was successfully exported.')
            else:
                message = _('Payment was exported{}. Waiting for a response from the bank.').format(
                    _(' on - %s') % date if date else str())
            alert_type = 'info'
        elif state == 'rejected':
            if e_invoice:
                message = _('eInvoice export was rejected')
            else:
                message = _('Last bank payment export was rejected.')
            alert_type = 'danger'
        elif state == 'rejected_partial':
            message = _('Last partial bank payment export was rejected.')
            alert_type = 'danger'
        elif state == 'rejected_sign':
            message = _('Last signing of the payment export was rejected.')
            alert_type = 'danger'
        elif state == 'accepted':
            if e_invoice:
                message = _('eInvoice export was accepted')
            else:
                message = _('Last bank payment export was accepted.')
            alert_type = 'success'
        elif state == 'accepted_partial':
            message = _('Last partial bank payment export was accepted.')
            alert_type = 'success'
        elif state == 'revoked':
            message = _('Last bank payment export was revoked by the user.')
            alert_type = 'warning'
        elif state == 'revoked_partial':
            message = _('Last partial bank payment export was revoked by the user.')
            alert_type = 'warning'
        elif state == 'processed':
            if e_invoice:
                message = _('eInvoice was accepted and paid')
            else:
                message = _('Last bank payment export was accepted and processed.')
            alert_type = 'success'
        elif state == 'processed_partial':
            message = _('Last partial bank payment export was accepted and processed.')
            alert_type = 'success'

        # Assign HTML to the field
        base_html = '''<div class="alert alert-{0}" role="alert" 
                        style="margin-bottom:0px;">{1}</div>'''.format(alert_type, message)
        return base_html if message and alert_type else str()

    @api.model
    def check_for_integrations_to_activate(self):
        """
        Check whether there are any activate-able bank integrations.
        If we have the bank journal bu integration is not configured
        format the label for the user.
        :return: report of banks to integrate (str)
        """

        bank_links = []
        # IMPORTANT: Made report field 'disabled' and not an empty string, because
        # it causes error on HTML field - when it's empty and the record is being saved
        # system throws 'your changes will be lost, do you wish to continue?' warning, which
        # does not make sense. This is temp fix, investigation of the problem needs to be done
        report = 'disabled'
        domain = [('type', '=', 'bank'), ('active', '=', True)]

        # Check whether there are any Paysera journals
        paysera_journal = self.env['account.journal'].search(
            [('bank_id.bic', '=', PAYSERA)] + domain, limit=1)
        paysera_conf_data = self.check_api_configuration(paysera_journal)
        if paysera_journal and not paysera_conf_data.get('int_bank'):
            bank_links.append('''<a href="https://pagalba.robolabs.lt/lt/integracijos#paysera-integracija" 
            target="_blank">Paysera</a>''')

        # Check whether there are any Swed-bank journals
        swed_journal = self.env['account.journal'].search(
            [('bank_id.bic', '=', SWED_BANK)] + domain, limit=1)
        swed_conf_data = self.check_api_configuration(swed_journal)
        swed_integrated = swed_conf_data.get('int_bank')
        if swed_journal and not swed_integrated:
            bank_links.append('''<a href="https://pagalba.robolabs.lt/lt/integracijos#swedbank-gateway-integracija" 
                        target="_blank">Swedbank</a>''')

        # Check whether there are any SEB journals
        seb_journal = self.env['account.journal'].search(
            [('bank_id.bic', '=', SEB_BANK)] + domain, limit=1)
        seb_conf_data = self.check_api_configuration(seb_journal)
        seb_integrated = seb_conf_data.get('int_bank')
        if seb_journal and not seb_integrated:
            bank_links.append('''<a href="https://pagalba.robolabs.lt/lt/integracijos#seb-baltic-gateway-integracija"
                        target="_blank">SEB</a>''')

        # Check for semi-integrated banks as well
        revolut_journal = self.env['account.journal'].search(
            [('import_file_type', '=', 'revolut')] + domain, limit=1)
        revolut_configured = self.env['revolut.api'].search_count([])
        if revolut_journal and not revolut_configured:
            bank_links.append(
                '''<a href="https://pagalba.robolabs.lt/lt/integracijos#revolut-integracija" 
                target="_blank">Revolut</a>'''
            )
        paypal_journal = self.env['account.journal'].search(
            [('import_file_type', '=', 'paypal')] + domain, limit=1)
        paypal_configured = self.env['paypal.api'].search_count([])
        if paypal_journal and not paypal_configured:
            bank_links.append(
                '''<a href="https://pagalba.robolabs.lt/lt/integracijos#paypal-integracija" 
                target="_blank">Paypal</a>'''
            )

        # Build extra domain for enable banking if standalone integrations are activated
        extra_e_banking_domain = []
        if swed_integrated or swed_journal and not swed_integrated:
            extra_e_banking_domain += [('bank_id.bic', '!=', SWED_BANK)]
        if seb_integrated or seb_journal and not seb_integrated:
            extra_e_banking_domain += [('bank_id.bic', '!=', SEB_BANK)]
        # Check for Enable banking connectors (skip standalone integrations if any)
        connectors = self.env['enable.banking.connector'].search(
            [('api_state', '!=', 'working')] + extra_e_banking_domain
        )
        # Loop through connectors and search for journals
        for connector in connectors:
            e_bank_journal = self.env['account.journal'].search_count(
                [('bank_id.bic', '=', connector.bank_id.bic)] + domain)
            if e_bank_journal:
                bank_links.append(
                    '''<a href="https://pagalba.robolabs.lt/lt/integracijos#bankinės-ir-mokėjimo-įstaigų-integracijos" 
                    target="_blank">{}</a>'''.format(connector.name)
                )

        # If we have some activate-able integrations, compose a message
        if bank_links:
            help_href = _('''<a href="https://pagalba.robolabs.lt/lt/islaidos#bankiniai-israsai" 
            target="_blank">Robolabs pagalba</a>''')
            report = _('''Sistemoje rastos aktyvios sąskaitos šiems bankams: {}. 
            Šie bankai yra integruoti su Robolabs sistema. <br/>Rekomenduojame įgalinti šias integracijas, 
            konfigūravimo žingsnius galite rasti paspaudę šią nuorodą 
            {} ir pasirinkę skiltį "Integracijos".''').format(', '.join(bank_links), help_href)

        return report

    # Cron-jobs //

    @api.model
    def cron_fetch_statements_daily(self):
        """
        Cron that fetches daily bank statements for all possible integrated banks.
        :return: None
        """
        # Reduces concurrency when client has several integrations activated,
        # and maximizes utilization period (without random-guessed time gaps between cron-jobs)
        # Swed-bank behaves differently thus it's not included. All of the individual cron-jobs
        # are set to active=False, and are meant to be turned on manually if it's actually needed.

        # Constraint checks are done inside the methods
        self.env['seb.api.base'].cron_fetch_statements_daily()
        self.env.cr.commit()
        self.env['paysera.api.base'].cron_fetch_statements_daily()
        self.env.cr.commit()
        # Always fetch enable banking statements last, since this
        # action takes up most of the time (several aggregated integrations)
        self.env['enable.banking.api.base'].fetch_statements_daily()

    @api.model
    def cron_fetch_statements_weekly(self):
        """
        Cron that fetches weekly bank statements for all possible integrated banks.
        :return: None
        """
        self.env['seb.api.base'].cron_fetch_statements_weekly()
        self.env.cr.commit()
        self.env['paysera.api.base'].cron_fetch_statements_weekly()
        self.env.cr.commit()
        # Always fetch enable banking statements last, since this
        # action takes up most of the time (several aggregated integrations)
        self.env['enable.banking.api.base'].fetch_statements_weekly()

    @api.model
    def cron_fetch_statements_monthly(self):
        """
        Cron that fetches monthly bank statements for all possible integrated banks.
        :return: None
        """
        self.env['seb.api.base'].cron_fetch_statements_monthly()
        self.env.cr.commit()
        self.env['paysera.api.base'].cron_fetch_statements_monthly()
