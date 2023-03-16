# -*- coding: utf-8 -*-


from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import _, api, exceptions, fields, models, tools

import odoorpc


class ResCompany(models.Model):
    _name = 'res.company'
    _inherit = ['res.company', 'mail.thread']

    analytic_account_id = fields.Many2one('account.analytic.account', string='Numatytoji analitinė sąskaita',
                                          required=False)
    robo_alias = fields.Char(string='Email Alias', compute='_robo_alias')
    politika_atostoginiai = fields.Selection([('su_du', 'Visada su darbo užmokesčiu'),
                                              ('rinktis', 'Leisti rinktis')],
                                             string='Atostoginių politika', default='su_du')
    module_work_schedule = fields.Boolean(string='Aktyvuoti darbo laiko apskaitos grafiką')
    module_work_schedule_analytics = fields.Boolean(string='Aktyvuoti analitiką pagal darbo laiko apskaitos grafikus')
    module_robo_analytic = fields.Boolean(string='Aktyvuoti analitiką')
    module_robo_api = fields.Boolean(string='Aktyvuoti ROBO API')
    politika_neatvykimai = fields.Selection(
        [('own', 'Darbuotojas mato tik savo neatvykimus'),
         ('department', 'Darbuotojas mato tik savo skyriaus darbuotojų neatvykimus'),
         ('all', 'Darbuotojas mato visų darbuotojų neatvykimus')],
        string='Neatvykimų politika', inverse='inv_politika_neatvykimai')
    accumulated_days_policy = fields.Selection(
        [('allow', 'Leisti'),
         ('deny', 'Drausti')], string='Atostogos su nepakankamu likučiu', default='deny')
    worker_policy = fields.Selection([
        ('enabled', 'Darbuotojas mato tik savo kortelę'),
        ('disabled', 'Darbuotojas mato visas darbuotojų korteles')],
        string='Darbuotojų kortelių politika', inverse='inverse_worker_policy')
    company_activity_form = fields.Selection(
        [('uab', 'Uždaroji akcinė bendrovė'),
         ('vsi', 'Viešoji įstaiga'),
         ('mb', 'Mažoji bendrija'),
         ('iv', 'Individuali veikla')], string='Įmonės veiklos forma', default='uab', required=True)
    automatic_salary_reconciliation = fields.Boolean(
        string='Automatiškai dengti atlyginimus',
        help='Išjungus šį pasirinkimą atlyginimų įrašai nebebus automatiškai dengimai', default=True)
    manager_lock_date_analytic = fields.Date(
        string='Analitikos užrakinimo data vadovams')
    user_lock_date_analytic = fields.Date(
        string='Analitikos užrakinimo data naudotojams')
    analytic_lock_type = fields.Selection(
        [('freeze', 'Užšaldyti analitiką'),
         ('block', 'Blokuoti analitiką')], default='block',
        string='Analitikos užrakinimo tipas'
    )
    uab_report_size = fields.Selection([('max', 'Išplėstinis balansas'),
                                        ('mid', 'Sutrumpintas balansas'),
                                        ('min', 'Trumpas balansas')],
                                       string='UAB balanso dydis', default='max')
    company_invoice_text = fields.Text(string='Tekstas spausdinamas sąskaitų faktūrų apačioje')
    additional_analytic_actions = fields.Boolean(string='Papildomi veiksmai keičiant analitiką sąskaitoje faktūroje')
    required_du_analytic = fields.Boolean(string='Priverstinė DU analitika')
    change_analytic_on_accountant_validated = fields.Boolean(
        string='Leisti keisti analitiką buhalterio patvirtintoms sąskaitoms')
    company_proforma_invoice_text_different_from_regular = fields.Boolean(
        string='Išankstinėse sąskaitose rodyti kitokį tekstą')
    company_invoice_proforma_text = fields.Text(string='Tekstas spausdinamas išankstinių sąskaitų faktūrų apačioje')
    politika_atostogu_suteikimas = fields.Selection([('ceo', 'Tvirtina vadovas'),
                                                     ('department', 'Padalinio vadovas')],
                                                    string='Atostogų tvirtinimas', default='ceo')
    holiday_policy_inform_manager = fields.Boolean(string='Siųsti laukiančių prašymų pranešimus padalinio vadovui')
    default_msg_receivers = fields.Many2many(
        'res.partner', 'res_company_res_partner_msg_receivers_rel', string='Papildomi žinučių gavėjai',
        help='Gavėjai, kai SF kūrėjas buhalteris.', groups="robo_basic.group_robo_premium_accountant")
    force_accounting_date = fields.Boolean(string='Default choice for force_accounting_date', default=False)
    longterm_assets_min_val = fields.Float(
        string='Mažiausia suma, nuo kurios išlaidos gali būti kapitalizuojamos (laikomos materialiuoju ilgalaikiu turtu)',
        lt_string='Mažiausia suma, nuo kurios išlaidos gali būti kapitalizuojamos (laikomos materialiuoju ilgalaikiu turtu)',
        default=300.0, required=True,
        groups='robo_basic.group_robo_premium_accountant')
    longterm_non_material_assets_min_val = fields.Float(
        string='Mažiausia suma, nuo kurios išlaidos gali būti kapitalizuojamos (laikomos nematerialiuoju ilgalaikiu '
               'turtu)',
        lt_string='Mažiausia suma, nuo kurios išlaidos gali būti kapitalizuojamos (laikomos nematerialiuoju ilgalaikiu '
                  'turtu)',
        default=300.0, required=True,
        groups='robo_basic.group_robo_premium_accountant')
    e_documents_allow_historic_signing = fields.Boolean(string='Leisti formuoti el. dokumentus praeities data',
                                                        default=False,
                                                        groups="robo_basic.group_robo_premium_accountant")
    print_invoice_presenter = fields.Boolean(string='Spausdinti sąskaitą išrašiusio asmens vardą sąskaitų apačioje')
    print_invoice_partner_balance = fields.Selection([
        ('disabled', 'Išjungta'),
        ('enabled_all', 'Taikoma visiems klientams'),
        ('enabled_partial', 'Taikoma pasirinktiems klientams')],
        string='Spausdinti partnerio skolą/permoką sąskaitoje faktūroje',
        help="Pasirinkus opciją 'Taikoma pasirinktiems klientams', opciją pažymėti galite kliento kortelėje")
    swed_bank_agreement_id = fields.Integer(string='SwedBank sutarties numeris', groups='base.group_system')
    force_need_action_repr = fields.Boolean(
        string='Užduoti reprezentacinių išlaidų tvirtinimo klausimus '
               'vadovui/atsakingam asmeniui kai sąskaitą įveda vartotojas')
    e_documents_allow_historic_signing_spec = fields.Boolean(
        string='Leisti formuoti darbo užmokesčio el. dokumentus praeities data',
        default=True,
        groups="robo_basic.group_robo_premium_accountant",
        help='Leidimas formuoti šiuos el. dokumentus praeities data:\n'
             'Įsakymas dėl atleidimo iš darbo \n '
             'Įsakymas dėl priėmimo į darbą \n '
             'Įsakymas dėl darbo užmokesčio pakeitimo')
    sumine_apskaita_period_amount = fields.Integer(string='Suminės darbo laiko apskaitos periodo mėnesių skaičius',
                                                   groups="robo_basic.group_robo_premium_accountant",
                                                   required=True,
                                                   default=3)
    sumine_apskaita_period_start = fields.Date(string='Suminės darbo laiko apskaitos periodo skaičiavimo pradžia',
                                               groups="robo_basic.group_robo_premium_accountant",
                                               required=True,
                                               default=datetime(2017, 1, 1))
    res_company_message_ids = fields.One2many('res.company.message', 'company_id')
    prevent_duplicate_product_code = fields.Boolean(string='Neleisti produkto kodų dublikatų', default=False)
    prevent_empty_product_code = fields.Boolean(string='Neleisti tuščių produkto kodų', default=False)
    allow_zero_allowance_business_trip = fields.Boolean(string='Leisti įvesti nulinius '
                                                               'dienpinigius komandiruočių el. dokumentuose')
    form_business_trip_payments_immediately_after_signing = fields.Boolean(string='Formuoti dienpinigių mokėjimo '
                                                                                  'pavedimus iš karto po komandiruotės '
                                                                                  'įsakymo pasirašymo',
                                                                           default=True)
    automatically_send_business_trip_allowance_payments_to_bank = fields.Boolean(
        string='Automatically send business trip allowance payments to bank',
        compute='_compute_automatically_send_business_trip_allowance_payments_to_bank',
        inverse='_set_automatically_send_business_trip_allowance_payments_to_bank',
        default=False,
    )
    form_gpm_line_with_holiday_payout = fields.Boolean(string='Formuoti GPM mokėjimą kartu su atostoginių išmokėjimu, '
                                                              'kai išmokama prieš atostogas', default=True)
    show_debt_banner = fields.Boolean(string='Rodyti neapmokėtų skolų juostelę')
    request_swed_bank_balance = fields.Boolean(string='Prašyti Swedbank likučio',
                                               groups='base.group_system', default=True)
    enable_product_uom = fields.Boolean(string='Įgalinti matavimo vienetus', inverse='_enable_product_uom')
    enable_periodic_invoices = fields.Boolean(string='Įgalinti periodines sąskaitas',
                                              inverse='_enable_periodic_invoices')
    enable_periodic_front_statements = fields.Boolean(string='Įgalinti periodinius mokėjimo ruošinius',
                                                      inverse='_enable_periodic_front_statements')
    enable_cash_registers = fields.Boolean(string='Įgalinti kasos aparatus', inverse='_enable_cash_registers')
    enable_invoice_journal_selection = fields.Boolean(string='Įgalinti skirtingas sąskaitų numeruotes',
                                                      inverse='_enable_invoice_journal_selection')
    enable_employment_requests_on_order_sign = fields.Boolean(string='Įgalinti automatinį prašymo dėl priėmimo '
                                                                     'į darbą kūrimą', default=True)
    invoice_print_only_foreign_currency = fields.Boolean(string='Sąskaitoje spausdinti tik užsienio valiuta')
    invoice_print_discount_type = fields.Selection([('perc', 'Procentais'), ('currency', 'Pinigine verte')],
                                                   string='Spausdinant sąskaitą rodyti nuolaidą', default='perc')
    # Paypal and Revolut integrations are turned on by default
    enable_paypal_integration = fields.Boolean(string='Įgalinti Paypal integraciją', default=True)
    enable_revolut_integration = fields.Boolean(string='Įgalinti Revolut integraciją', default=True)
    enable_paysera_integration = fields.Boolean(
        string='Įgalinti Paysera integraciją', default=True, inverse='_set_enable_paysera_integration')
    enable_seb_integration = fields.Boolean(
        string='Įgalinti SEB integraciją', default=True, inverse='_set_enable_seb_integration')
    e_documents_enable_advance_setup = fields.Boolean(
        string='Įgalinti avanso nustatymus el. dokumentuose', default=False)
    auto_form_employee_advance_balance_document = fields.Boolean(
        string='Automatiškai formuoti avansinės apyskaitos dokumentą')
    activate_threaded_front_reports = fields.Boolean(
        string='Eksportuoti ataskaitas kaip foninę užduotį', inverse='_set_activate_threaded_front_reports')
    embed_einvoice_xml = fields.Boolean(
        string='Įterpti e-sąskaitos duomenis sąskaitų PDF failuose',
        help='Įgalinus - sąskaitų PDF dokumentuose bus įterpiamos standartizuotos e-sąskaitos. Gavėjams e-sąskaitos'
             'suteikia galimybę sąskaitas apdoroti automatiškai, be papildomų žmogaus veiksmų.',
        default=True
    )
    show_machine_readable = fields.Boolean(
        string='Rodyti "Machine Readable" (e-sąskaitos) logotipą sąskaitos poraštėje',
        help='"Machine Readable" logotipas sąskaitų poraštėse parodo, kad sąskaita gali būti lengvai apdorota kitų '
             'sistemų, nes joje yra įkoduotas XML su visa reikalinga sąskaitos informacija.',
        default=True
    )
    custom_cash_receipt_header_enabled = fields.Boolean(string='Allow setting custom cash receipt headers',
                                                        compute='_compute_custom_cash_receipt_header_enabled',
                                                        inverse='_set_custom_cash_receipt_header_enabled')
    custom_invoice_color_text = fields.Char(string='Custom system invoice template text color',
                                            compute='_compute_custom_invoice_color_text',
                                            inverse='_set_custom_invoice_color_text')
    custom_invoice_color_details = fields.Char(string='Custom system invoice template detail color',
                                               compute='_compute_custom_invoice_color_details',
                                               inverse='_set_custom_invoice_color_details')
    custom_invoice_footer_enabled = fields.Boolean('Custom invoice footer')
    custom_invoice_footer = fields.Text('Footer to be shown on invoices')
    require_2fa = fields.Boolean(string='Require 2FA', help='When enabled, all users must use 2FA for connecting',
                                 inverse='_set_require_2fa')
    default_payment_term_id = fields.Many2one('account.payment.term', string='Numatytasis kliento mokėjimo terminas')
    default_supplier_payment_term_id = fields.Many2one('account.payment.term',
                                                       string='Numatytasis tiekėjo mokėjimo terminas')
    allow_use_ne_pvm_objektas = fields.Boolean(string='Let users set non-VAT objects')
    invoice_default_proforma_print = fields.Selection([('proforma', 'Išankstinė sąskaita'),
                                                       ('commercial_offer', 'Komercinis pasiūlymas')],
                                                      compute='_compute_invoice_default_proforma_print',
                                                      inverse='_set_invoice_default_proforma_print')
    invoice_decimal_precision = fields.Integer(compute='_compute_invoice_decimal_precision',
                                               inverse='_set_invoice_decimal_precision')
    enable_e_banking_integration = fields.Boolean(
        compute='_compute_enable_e_banking_integration',
        inverse='_set_enable_e_banking_integration',
    )

    enable_braintree_integration = fields.Boolean(
        compute='_compute_enable_braintree_integration',
        inverse='_set_enable_braintree_integration',
    )

    enable_invoice_reconciliation_on_private_consumption = fields.Boolean(
        string='Įgalinti automatinį sąskaitų sudengimą tenkinant privačius poreikius',
        compute='_compute_enable_invoice_reconciliation_on_private_consumption',
        inverse='_set_enable_invoice_reconciliation_on_private_consumption',
    )
    invoice_cc_emails = fields.Char(string='Invoice carbon copy (CC) receivers',
                                    compute='_compute_invoice_cc_emails', inverse='_set_invoice_cc_emails',)
    allow_accumulative_work_time_accounting_net_bonus_orders = fields.Boolean(
        string='Allow bonus orders with NET amounts specified for employees working by accumulative work time '
               'accounting',
        compute='_compute_allow_accumulative_work_time_accounting_net_bonus_orders',
        inverse='_set_allow_accumulative_work_time_accounting_net_bonus_orders',
    )
    use_latest_product_price = fields.Boolean(compute='_compute_use_latest_product_price', default=False,
                                              inverse='_set_use_latest_product_price')
    default_action_after_fixed_term_contract_end = fields.Selection([
        ('extend', 'Create document to extend fixed term contract'),
        ('change_type', 'Create document to change contract type to indefinite duration'),
        ('terminate', 'Create document to terminate the work relation'),
        ('nothing', 'Do not create any document'),
    ], default='change_type', compute='_compute_default_action_after_fixed_term_contract_end',
        inverse='_set_default_action_after_fixed_term_contract_end')
    fixed_term_contract_extension_by_months = fields.Integer(compute='_compute_fixed_term_contract_extension_by_months',
                                                             inverse='_set_fixed_term_contract_extension_by_months',
                                                             default=1, )
    use_children_records_for_parental_leave_documents = fields.Boolean(
        compute='_compute_use_children_records_for_parental_leave_documents',
        inverse='_set_use_children_records_for_parental_leave_documents',
        default=False)

    show_paid_invoice_state_on_printing = fields.Boolean(string='Show paid invoice state on printing',
                                                         compute='_compute_show_paid_invoice_state_on_printing',
                                                         inverse='_set_show_paid_invoice_state_on_printing')

    use_last_unit_price_of_account_invoice_line = fields.Boolean(
        compute='_compute_use_last_unit_price_of_account_invoice_line',
        inverse='_set_use_last_unit_price_of_account_invoice_line',
        default=False)

    @api.multi
    def _compute_use_children_records_for_parental_leave_documents(self):
        self.ensure_one()
        self.use_children_records_for_parental_leave_documents = self.env['ir.config_parameter'].sudo().get_param(
            'use_children_records_for_parental_leave_documents') == 'True'

    @api.multi
    def _set_use_children_records_for_parental_leave_documents(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param('use_children_records_for_parental_leave_documents',
                                                         str(self.use_children_records_for_parental_leave_documents))

    @api.multi
    def _compute_use_last_unit_price_of_account_invoice_line(self):
        self.ensure_one()
        self.use_last_unit_price_of_account_invoice_line = self.env['ir.config_parameter'].sudo().get_param(
            'use_last_unit_price_of_account_invoice_line') == 'True'

    @api.multi
    def _set_use_last_unit_price_of_account_invoice_line(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param('use_last_unit_price_of_account_invoice_line',
                                                         str(self.use_last_unit_price_of_account_invoice_line))

    @api.multi
    def _compute_allow_accumulative_work_time_accounting_net_bonus_orders(self):
        """Check if private consumption invoice reconciliation is enabled in the system"""
        self.ensure_one()
        allow_net_bonuses_for_accumulative_accounting = self.env['ir.config_parameter'].sudo().get_param(
            'allow_accumulative_work_time_accounting_net_bonus_orders') == 'True'
        self.allow_accumulative_work_time_accounting_net_bonus_orders = allow_net_bonuses_for_accumulative_accounting

    @api.multi
    def _set_allow_accumulative_work_time_accounting_net_bonus_orders(self):
        """Update config parameter based on company settings value"""
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param(
            'allow_accumulative_work_time_accounting_net_bonus_orders',
            str(self.allow_accumulative_work_time_accounting_net_bonus_orders),
        )

    @api.multi
    def _compute_automatically_send_business_trip_allowance_payments_to_bank(self):
        self.ensure_one()
        automatically_send_business_trip_allowance_payments_to_bank = self.env['ir.config_parameter'].sudo().get_param(
            'automatically_send_business_trip_allowance_payments_to_bank') == 'True'
        self.automatically_send_business_trip_allowance_payments_to_bank = automatically_send_business_trip_allowance_payments_to_bank

    @api.multi
    def _set_automatically_send_business_trip_allowance_payments_to_bank(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param('automatically_send_business_trip_allowance_payments_to_bank',
                                                         str(self.automatically_send_business_trip_allowance_payments_to_bank))

    @api.multi
    def _compute_show_paid_invoice_state_on_printing(self):
        self.ensure_one()
        show_paid_invoice_state_on_printing = self.env['ir.config_parameter'].sudo().get_param(
            'show_paid_invoice_state_on_printing') == 'True'
        self.show_paid_invoice_state_on_printing = show_paid_invoice_state_on_printing

    @api.multi
    def _set_show_paid_invoice_state_on_printing(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param('show_paid_invoice_state_on_printing',
                                                         str(self.show_paid_invoice_state_on_printing))

    @api.multi
    def _compute_default_action_after_fixed_term_contract_end(self):
        self.ensure_one()
        default_action_after_fixed_term_contract_end = self.env['ir.config_parameter'].sudo().get_param(
            'default_action_after_fixed_term_contract_end')
        self.default_action_after_fixed_term_contract_end = default_action_after_fixed_term_contract_end or 'change_type'

    @api.multi
    def _set_default_action_after_fixed_term_contract_end(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param('default_action_after_fixed_term_contract_end',
                                                         str(self.default_action_after_fixed_term_contract_end))

    @api.multi
    def _compute_use_latest_product_price(self):
        self.ensure_one()
        use_latest_product_price = self.env['ir.config_parameter'].sudo().get_param(
            'use_latest_product_price') == 'True'
        self.use_latest_product_price = use_latest_product_price or False

    @api.multi
    def _set_use_latest_product_price(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param('use_latest_product_price', str(self.use_latest_product_price))

    @api.multi
    def _compute_fixed_term_contract_extension_by_months(self):
        self.ensure_one()
        fixed_term_contract_extension_by_months = self.env['ir.config_parameter'].sudo().get_param(
            'fixed_term_contract_extension_by_months')
        self.fixed_term_contract_extension_by_months = fixed_term_contract_extension_by_months or 1

    @api.multi
    def _set_fixed_term_contract_extension_by_months(self):
        self.ensure_one()
        current_value = int(self.fixed_term_contract_extension_by_months)
        extension = current_value if current_value >= 1 else 1
        self.env['ir.config_parameter'].sudo().set_param('fixed_term_contract_extension_by_months', extension)

    @api.multi
    def _compute_custom_cash_receipt_header_enabled(self):
        self.ensure_one()
        custom_cash_receipt_header_enabled = self.env['ir.config_parameter'].sudo().get_param(
            'custom_cash_receipt_header_enabled') == 'True'
        self.custom_cash_receipt_header_enabled = custom_cash_receipt_header_enabled

    @api.multi
    def _set_custom_cash_receipt_header_enabled(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param('custom_cash_receipt_header_enabled',
                                                         str(self.custom_cash_receipt_header_enabled))

    @api.multi
    def _compute_custom_invoice_color_text(self):
        self.ensure_one()
        custom_invoice_color_text = self.env['ir.config_parameter'].sudo().get_param('custom_invoice_color_text')
        self.custom_invoice_color_text = custom_invoice_color_text or "rgba(52, 152, 219, 1)"

    @api.multi
    def _set_custom_invoice_color_text(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param('custom_invoice_color_text', self.custom_invoice_color_text)

    @api.multi
    def _compute_custom_invoice_color_details(self):
        self.ensure_one()
        custom_invoice_color_details = self.env['ir.config_parameter'].sudo().get_param('custom_invoice_color_details')
        self.custom_invoice_color_details = custom_invoice_color_details or "rgba(41, 128, 185, 1)"

    @api.multi
    def _set_custom_invoice_color_details(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param('custom_invoice_color_details',
                                                         self.custom_invoice_color_details)

    @api.multi
    def _compute_invoice_cc_emails(self):
        sys_param = self.env['ir.config_parameter'].sudo().get_param('invoice_cc_emails')
        self.invoice_cc_emails = sys_param or str()

    @api.multi
    def _set_invoice_cc_emails(self):
        self.env['ir.config_parameter'].sudo().set_param('invoice_cc_emails', self.invoice_cc_emails)

    @api.multi
    def _compute_enable_invoice_reconciliation_on_private_consumption(self):
        """Check if private consumption invoice reconciliation is enabled in the system"""
        self.ensure_one()
        enable_private_cons = self.env['ir.config_parameter'].sudo().get_param(
            'enable_invoice_reconciliation_on_private_consumption') == 'True'
        self.enable_invoice_reconciliation_on_private_consumption = enable_private_cons

    @api.multi
    def _set_enable_invoice_reconciliation_on_private_consumption(self):
        """Update config parameter based on company settings value"""
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param(
            'enable_invoice_reconciliation_on_private_consumption',
            str(self.enable_invoice_reconciliation_on_private_consumption),
        )

    @api.multi
    def _compute_enable_braintree_integration(self):
        """Check if Braintree integration is enabled in the system"""
        self.ensure_one()
        braintree_enabled = self.env['ir.config_parameter'].sudo().get_param(
            'enable_braintree_integration') == 'True'
        self.enable_braintree_integration = braintree_enabled

    @api.multi
    def _set_enable_braintree_integration(self):
        """Update config parameter based on company settings value"""
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param(
            'enable_braintree_integration', str(self.enable_braintree_integration)
        )
        # Disable all gateways and journals on deactivation
        if not self.enable_braintree_integration:
            braintree_gateways = self.env['braintree.gateway'].search([])
            braintree_gateways.write({'api_state': 'not_initiated', 'initially_authenticated': False})
            merchant_accounts = self.env['braintree.merchant.account'].search([])
            merchant_accounts.write({'status': 'suspended', 'last_fetch_date': False})
            # Recompute journal states
            merchant_accounts.mapped('journal_id')._compute_api_integrated_bank()

    @api.multi
    def _compute_enable_e_banking_integration(self):
        """Check if enable banking integration is enabled in the system"""
        self.ensure_one()
        e_banking_enabled = self.env['ir.config_parameter'].sudo().get_param(
            'enable_e_banking_integration') == 'True'
        self.enable_e_banking_integration = e_banking_enabled

    @api.multi
    def _set_enable_e_banking_integration(self):
        """Update config parameter based on company settings value"""
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param(
            'enable_e_banking_integration', str(self.enable_e_banking_integration)
        )
        # Either disable all of the connectors or recreate/enable them
        configuration = self.env['enable.banking.api.base'].get_configuration(fully_functional=False)
        if not self.enable_e_banking_integration:
            configuration.connector_ids.reset_connectors_sessions()
        else:
            # Check whether there's any inactive connectors that need configuration
            inactive_connectors = configuration.with_context(
                active_test=False).connector_ids.filtered(lambda x: not x.active)
            inactive_connectors.relate_to_corresponding_banks()

    @api.multi
    def _compute_invoice_default_proforma_print(self):
        sys_param = self.env['ir.config_parameter'].sudo().get_param('invoice_default_proforma_print', 'proforma')
        if sys_param not in [s[0] for s in self._fields['invoice_default_proforma_print'].selection]:
            sys_param = 'proforma'
        self.invoice_default_proforma_print = sys_param

    @api.multi
    def _set_invoice_default_proforma_print(self):
        if self.invoice_default_proforma_print:
            self.env['ir.config_parameter'].sudo().set_param('invoice_default_proforma_print', self.invoice_default_proforma_print)

    @api.multi
    def _set_invoice_decimal_precision(self):
        self.env['ir.config_parameter'].sudo().set_param('invoice_decimal_precision', self.invoice_decimal_precision)

    @api.multi
    def _compute_invoice_decimal_precision(self):
        sys_param = self.env['ir.config_parameter'].sudo().get_param('invoice_decimal_precision')
        if not sys_param:
            sys_param = self.env['decimal.precision'].precision_get('Product Price')
        self.invoice_decimal_precision = sys_param

    @api.model
    def _default_msg_receivers(self):
        manager_ids = self.sudo().env['hr.employee'].search(
            [('robo_access', '=', True), ('robo_group', '=', 'manager')])
        return manager_ids.mapped('address_home_id.id') or []

    @api.multi
    def compute_fiscalyear_dates(self, date=None):
        if date is None:
            date = datetime.now()
        return super(ResCompany, self).compute_fiscalyear_dates(date=date)

    @api.model
    def get_fiscal_year_params(self):
        company = self.env.user.sudo().company_id
        previous_year_period = company.compute_fiscalyear_dates(datetime.now() + relativedelta(years=-1))
        current_year_period = company.compute_fiscalyear_dates()
        return {
            'prev_from': previous_year_period['date_from'].strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'prev_to': previous_year_period['date_to'].strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'curr_from': current_year_period['date_from'].strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'curr_to': current_year_period['date_to'].strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
        }

    @api.multi
    def _set_enable_paysera_integration(self):
        """
        Inverse //
        If Paysera integration is disabled, set
        paysera configuration state as not_initiated
        :return: None
        """
        for rec in self:
            if not rec.enable_paysera_integration:
                configuration = self.env['paysera.api.base'].get_configuration(raise_exception=False)
                configuration.write({'api_state': 'not_initiated'})

    @api.multi
    def _set_enable_seb_integration(self):
        """
        Inverse //
        If SEB integration is disabled, set
        SEB configuration state as not_initiated
        :return: None
        """
        for rec in self:
            if not rec.enable_seb_integration:
                configuration = self.env['seb.api.base'].get_configuration(raise_exception=False)
                configuration.write({'api_state': 'not_initiated'})

    @api.multi
    def _set_activate_threaded_front_reports(self):
        """
        Inverse //
        Add or remove special threaded group that let's users see the menu if threaded reports are activated
        :return: None
        """
        threaded_group = self.env.ref('robo.group_robo_threaded_front_reports')
        reports_group = self.env.ref('robo.robo_reports')
        for rec in self:
            if rec.activate_threaded_front_reports:
                reports_group.sudo().write({
                    'implied_ids': [(4, threaded_group.id)]
                })
            else:
                reports_group.sudo().write({
                    'implied_ids': [(3, threaded_group.id)]
                })
                threaded_group.write({'users': [(5,)]})

    @api.model
    def get_record_url(self, record, view_type='form'):
        """
            Returns the URL by which a record can be accessible
        :param record: Record to link to
        :param view_type: What view type should the record be displayed in
        :return: URL to the form view of the record if a single record is given otherwise None
        """
        if len(record) != 1:
            return None
        if view_type == 'form':
            try:
                web_base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                return '%s/?db=%s#id=%s&model=%s&view_type=%s' % (
                    web_base_url,
                    self._cr.dbname,
                    record.id,
                    record._name,
                    view_type
                )
            except:
                return None
        else:
            return None

    @api.one
    def _enable_product_uom(self):
        group_uom = self.env.ref('product.group_uom')
        user_group = self.env.ref('base.group_user')
        if self.enable_product_uom:
            user_group.sudo().write({
                'implied_ids': [(4, group_uom.id)]
            })
        else:
            user_group.sudo().write({
                'implied_ids': [(3, group_uom.id)]
            })
            group_uom.write({'users': [(5,)]})

    @api.one
    def _enable_periodic_front_statements(self):
        periodic_group = self.env.ref('robo_basic.group_robo_periodic_front_statement')
        man_group = self.env.ref('robo_basic.group_robo_premium_manager')
        if self.enable_periodic_front_statements:
            man_group.sudo().write({
                'implied_ids': [(4, periodic_group.id)]
            })
        else:
            man_group.sudo().write({
                'implied_ids': [(3, periodic_group.id)]
            })
            periodic_group.write({'users': [(5,)]})

    @api.one
    def _enable_periodic_invoices(self):
        periodic_group = self.env.ref('robo_basic.group_robo_periodic')
        man_group = self.env.ref('robo_basic.group_robo_premium_manager')
        inc_group = self.env.ref('robo_basic.group_robo_see_income')
        all_group = self.env.ref('robo.group_menu_kita_analitika')
        if self.enable_periodic_invoices:
            man_group.sudo().write({
                'implied_ids': [(4, periodic_group.id)]
            })
            inc_group.sudo().write({
                'implied_ids': [(4, periodic_group.id)]
            })
            all_group.sudo().write({
                'implied_ids': [(4, periodic_group.id)]
            })
        else:
            man_group.sudo().write({
                'implied_ids': [(3, periodic_group.id)]
            })
            inc_group.sudo().write({
                'implied_ids': [(3, periodic_group.id)]
            })
            all_group.sudo().write({
                'implied_ids': [(3, periodic_group.id)]
            })
            periodic_group.write({'users': [(5,)]})

    @api.one
    def _enable_cash_registers(self):
        cash_register_group = self.env.ref('robo_basic.group_robo_kasos_aparatas')
        groups = self.env.ref('robo_basic.group_robo_premium_manager') + self.env.ref(
            'robo_basic.group_robo_premium_accountant')
        if self.enable_cash_registers:
            groups.sudo().write({'implied_ids': [(4, cash_register_group.id)]})
        else:
            groups.sudo().write({'implied_ids': [(3, cash_register_group.id)]})
            cash_register_group.write({'users': [(5,)]})

    @api.one
    def _enable_invoice_journal_selection(self):
        invoice_journal_selection_group = self.env.ref('robo_basic.group_robo_select_invoice_journal')
        groups = self.env.ref('robo_basic.group_robo_premium_manager') + self.env.ref(
            'robo_basic.group_robo_premium_accountant') \
                 + self.env.ref('robo_basic.group_robo_see_income') + self.env.ref('robo.group_menu_kita_analitika')
        if self.enable_invoice_journal_selection:
            groups.sudo().write({'implied_ids': [(4, invoice_journal_selection_group.id)]})
        else:
            groups.sudo().write({'implied_ids': [(3, invoice_journal_selection_group.id)]})
            invoice_journal_selection_group.write({'users': [(5,)]})

    @api.one
    def inverse_worker_policy(self):
        act = self.env.ref('robo.open_employees_action')
        if self.worker_policy == 'enabled':
            act.write({'domain': "[('main_accountant','=',False), ('id', '=', False)]"})
        else:
            act.write({'domain': "[('main_accountant','=',False)]"})

    @api.multi
    @api.constrains('sumine_apskaita_period_amount')
    def _check_sumine_apskaita_period_amount_is_correct(self):
        lower_bound = 1
        upper_bound = 4
        for rec in self:
            if not lower_bound <= rec.sumine_apskaita_period_amount <= upper_bound:
                raise exceptions.ValidationError(
                    _('Suminės apskaitos periodų skaičius privalo būti nuo %s iki %s')
                    % (str(lower_bound), str(upper_bound + 1))
                )

    @api.multi
    @api.constrains('fixed_term_contract_extension_by_months')
    def _check_fixed_term_contract_extension_by_months(self):
        for rec in self:
            if rec.default_action_after_fixed_term_contract_end == 'extend' and \
                    rec.fixed_term_contract_extension_by_months < 1:
                raise exceptions.ValidationError(
                    _('Number of months to extend ending fixed term contracts by must be higher than 0'))

    @api.multi
    @api.constrains('default_action_after_fixed_term_contract_end')
    def _check_default_action_after_fixed_term_contract_end(self):
        for rec in self:
            if not rec.default_action_after_fixed_term_contract_end:
                raise exceptions.ValidationError(
                    _('You need to choose what happens, after a fixed term contract comes to an end'))

    @api.one
    def inv_politika_neatvykimai(self):
        user_group = self.env.ref('base.group_user')

        own_hol_group = self.env.ref('robo_basic.group_holiday_policy_self')

        all_hol_group = self.env.ref('robo_basic.group_holiday_policy_all')

        dep_hol_group = self.env.ref('robo_basic.group_holiday_policy_department')

        if self.politika_neatvykimai == 'own':
            user_group.write({'implied_ids': [(4, own_hol_group.id), (3, dep_hol_group.id), (3, all_hol_group.id)]})
            all_hol_group.write({'users': [(5,)]})
            dep_hol_group.write({'users': [(5,)]})

        elif self.politika_neatvykimai == 'department':
            user_group.write({'implied_ids': [(4, dep_hol_group.id), (3, own_hol_group.id), (3, all_hol_group.id)]})
            all_hol_group.write({'users': [(5,)]})
            own_hol_group.write({'users': [(5,)]})

        elif self.politika_neatvykimai == 'all':
            user_group.write({'implied_ids': [(4, all_hol_group.id), (3, own_hol_group.id), (3, dep_hol_group.id)]})
            own_hol_group.write({'users': [(5,)]})
            dep_hol_group.write({'users': [(5,)]})

    @api.one
    def _set_require_2fa(self):
        """ Mark all users to use 2FA """
        if self.require_2fa:
            domain = [('enable_2fa', '=', False)]
        else:
            domain = [
                ('enable_2fa', '=', True),
                ('secret_code_2fa', '=', False),
                ('qr_image_2fa', '=', False),
            ]
        self.env['res.users'].sudo().search(domain).with_context(changing_global_2fa_policy=True).write({
            'enable_2fa': self.require_2fa,
        })

    @api.one
    def _set_vat(self):
        if self.vat:
            group_vat_id = self.env.ref('robo_basic.group_robo_vat')
            group1_id = self.env.ref('robo_basic.group_robo_free_employee')
            group2_id = self.env.ref('robo_basic.group_robo_premium_user')
            group1_id.write({
                'implied_ids': [(4, group_vat_id.id)]
            })
            group2_id.write({
                'implied_ids': [(4, group_vat_id.id)]
            })
        else:
            group_vat_id = self.env.ref('robo_basic.group_robo_vat')
            group1_id = self.env.ref('robo_basic.group_robo_free_employee')
            group2_id = self.env.ref('robo_basic.group_robo_premium_user')
            group1_id.write({
                'implied_ids': [(3, group_vat_id.id)]
            })
            group2_id.write({
                'implied_ids': [(3, group_vat_id.id)]
            })
            group_vat_id.write({'users': [(5,)]})

    @api.model
    def install_vat(self):
        self.env.user.company_id._set_vat()

    @api.multi
    def write(self, vals):
        res = super(ResCompany, self).write(vals)
        if 'vat' in vals:
            for rec in self:
                rec._set_vat()
        return res

    @api.one
    def _robo_alias(self):
        self.robo_alias = self.env.cr.dbname + u'@robolabs.lt'

    @api.model
    def robo_help(self, comp_id):

        # email = ''
        mobile = ''
        logo = ''
        name = ''
        substitute_accountant = False
        company_id = self.env['res.company'].browse(comp_id)

        if company_id:
            # email = company_id.robo_alias
            findir = company_id.sudo().findir
            if findir:
                mobile = findir.work_phone or ''
                name = findir.name or ''
                # email = findir.login or ''
                logo = findir.image_medium
                substitute_accountant = findir.substitute_accountant

        vals = {
            'email': 'accounting@robolabs.lt',
            'tech_email': 'support@robolabs.lt',
            'customer_support_email': 'customersupport@robolabs.lt',
            'mobile': mobile,
            'name': name,
            'logo': logo,
            'substitute_accountant': substitute_accountant
        }
        return vals

    @api.multi
    def post_announcement(self, html, subject='Naujienos', partner_ids=False, priority='medium'):
        self.ensure_one()
        if not partner_ids:
            partner_ids = self.env.user.company_id.default_msg_receivers.ids
        if not partner_ids:
            group_id1 = self.env.ref('robo_basic.group_robo_premium_manager').id
            group_id2 = self.env.ref('robo_basic.group_robo_premium_accountant').id
            user_ids = self.env['res.users'].search(
                [('groups_id', 'in', [group_id1]), ('groups_id', 'not in', [group_id2])])
            partner_ids = user_ids.mapped('partner_id.id')
        rec_id = self.env['res.company.message'].create({
            'body': html,
            'subject': subject,
            'company_id': self.id
        })
        msg = {
            'body': _(html),
            'subject': _(subject),
            'priority': priority,
            'front_message': True,
            'rec_model': 'res.company.message',
            'rec_id': rec_id,
            'partner_ids': partner_ids,
            'view_id': self.env.ref('robo.res_company_message_form').id,
        }
        rec_id.robo_message_post(**msg)

    @api.model
    def _get_odoorpc_object(self):
        """ Return an OdooRPC connect object """
        config_obj = self.sudo().env['ir.config_parameter']
        central_server_url = tools.config.get('central_server', False)
        central_server_database = tools.config.get('robo_server_database', False)
        robo_server_username = tools.config.get('robo_server_username', False)
        robo_server_password = tools.config.get('robo_server_password', False)
        if not central_server_url:
            raise exceptions.UserError(_('Central server URL not found.'))
        if not central_server_database:
            raise exceptions.UserError(_('Robo server database not found.'))
        if not robo_server_username:
            raise exceptions.UserError(_('Robo server username not found.'))
        if not robo_server_password:
            raise exceptions.UserError(_('Robo server password not found.'))
        central_server_url = central_server_url.replace('https://', '')
        url, db, username, password, port = central_server_url, central_server_database, robo_server_username, robo_server_password, 443
        rpcobj = odoorpc.ODOO(url, port=port, protocol='jsonrpc+ssl')
        try:
            rpcobj.login(db, username, password)
        except odoorpc.error.RPCError:
            # Fallback mode
            username = config_obj.get_param('robo.robo_server_username')
            password = config_obj.get_param('robo.robo_server_password')
            rpcobj.login(db, username, password)
        return rpcobj

    def get_manager_mail_channels(self):
        """ return default mail channel records for manager """
        channels = self.env['mail.channel']
        channel_eids = ['l10n_lt_payroll.end_of_child_care_leave_notification_mail_channel']
        for eid in channel_eids:
            channel = self.env.ref(eid, False)
            if channel:
                channels |= channel
        return channels
