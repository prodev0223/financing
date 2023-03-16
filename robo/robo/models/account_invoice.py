# -*- coding: utf-8 -*-
from __future__ import division
import json
import uuid
from datetime import datetime
from odoo.addons.queue_job.job import job, identity_exact
from dateutil.relativedelta import relativedelta

from six import iteritems
from odoo import _, api, exceptions, fields, models, tools
from odoo.tools import float_compare, float_is_zero


@api.model
def _lang_get(self):
    return self.env['res.lang'].get_installed()


class AccountInvoice(models.Model):
    _name = 'account.invoice'
    _inherit = ['account.invoice', 'ir.needaction_mixin']
    _order = "date_invoice desc, number desc, id desc"

    def _default_payment_mode(self):
        if self._context.get('with_cheque_picture', False):
            return 'own_account'
        else:
            return 'company_account'

    def default_lang(self):
        return self.env.user.lang

    def random_unique_code(self):
        return uuid.uuid4()

    @api.model
    def _default_journal(self):
        if self._context.get('front_invoice_creation') and self.env.user.company_id.enable_invoice_journal_selection and \
                self.env['account.journal'].search_count([('type', '=', 'sale')]) > 1:
            return self.env['account.journal']
        else:
            return super(AccountInvoice, self)._default_journal()

    def _search_tax_ids(self, operator, value):
        if isinstance(value, basestring):
            value = value.upper()
        if operator in ['like', 'ilike']:
            operator = '='
        return [('tax_line_ids.tax_id.code', operator, value)]

    # This field must be set on this condition
    # if invoice_id.swed_bank_export_state == 'accepted' and not \
    # invoice_id.partner_id.automated_e_invoice_payment_state == 'automated'
    # IMPORTANT: bool must be unset when invoice_id.swed_bank_export_state changes to 'processed'
    robo_unpaid_e_invoice = fields.Boolean(string='Nesumokėta eSąskaita robo', sequence=100)
    # --

    unique_wizard_id = fields.Text(default=random_unique_code, store=False, sequence=100)
    attachment_drop_lock = fields.Boolean(compute='_compute_attachment_drop_lock')
    attachment = fields.Binary(string='Išlaidos', attachment=True, copy=False)
    name_attachment = fields.Char(string='Failo pavadinimas', copy=False, sequence=100)
    mime_attachment = fields.Char(string='Failo tipas', copy=False, sequence=100)
    user_attachment_ids = fields.Many2many('ir.attachment', compute='_compute_all_attachments', string='Prisegtukai',
                                           readonly=False, sequence=100,
                                           )
    # renew_user_attachments_ids = fields.Boolean(default=False, store=False)
    nbr_of_attachments = fields.Integer(compute='_compute_nbr_of_attachments', sequence=100)
    computed_attachment = fields.Binary(string='Išlaidos', compute='_find_attachment', sequence=100)
    computed_name_attachment = fields.Char(string='Failo pavadinimas', compute='_find_attachment', sequence=100)
    computed_mime_attachment = fields.Char(string='Failo tipas', compute='_find_attachment', sequence=100)

    # ROBO: IOS attachment fields
    app_attachment = fields.Binary(string='Išlaidos', compute='_app_attachment')
    app_name_attachment = fields.Char(string='Failo pavadinimas', compute='_app_attachment')
    app_mime_attachment = fields.Char(string='Failo tipas', compute='_app_attachment')
    computed_number = fields.Char(string='Numeris', compute='_get_invoice_number', store=True)
    with_cheque_picture = fields.Boolean(default=False, sequence=100)
    with_cheque_form = fields.Boolean(default=False, sequence=100)
    payment_mode = fields.Selection(
        [('own_account', 'Asmeninėmis lėšomis'), ('company_account', 'Kompanijos lėšomis')],
        string='Kaip apmokėjote?', default=_default_payment_mode, copy=False)
    state = fields.Selection([('draft', 'Juodraštis'),
                              ('proforma', 'Išankstinė'),
                              ('proforma2', 'Išankstinė'),
                              ('open', 'Laukiama mokėjimo'),
                              ('paid', 'Apmokėta'),
                              ('cancel', 'Atšaukta')], help='', inverse='_set_state',
                             )
    partner_vat = fields.Char(string='PVM kodas', inverse='_set_partner_data_vat', readonly=True,
                              states={'draft': [('readonly', False)]}, copy=False, sequence=100)
    partner_kodas = fields.Char(string='Kodas', inverse='_set_partner_data_kodas', readonly=True,
                                states={'draft': [('readonly', False)]}, copy=False)
    partner_company_type = fields.Selection(string='Juridinis/Fizinis asmuo',
                                            selection=[('person', 'Fizinis'), ('company', 'Juridinis')],
                                            inverse='_set_partner_data_type', readonly=True,
                                            states={'draft': [('readonly', False)]}, copy=False)
    partner_parent_id = fields.Many2one('res.partner', string='Susijusi kompanija', ondelete='restrict',
                                        readonly=True, states={'draft': [('readonly', False)]}, copy=False,
                                        sequence=100,
                                        )
    partner_street = fields.Char(string='Gatvė', inverse='_set_partner_data_street', readonly=True,
                                 states={'draft': [('readonly', False)]}, copy=False, sequence=100)
    partner_zip = fields.Char(string='Pašto kodas', inverse='_set_partner_data_zip', readonly=True,
                              states={'draft': [('readonly', False)]}, copy=False, sequence=100)
    partner_city = fields.Char(string='Miestas', inverse='_set_partner_data_city', readonly=True,
                               states={'draft': [('readonly', False)]}, copy=False, sequence=100)
    partner_country_id = fields.Many2one('res.country', string='Šalis (Partnerio)', ondelete='restrict',
                                         inverse='_set_partner_data_country_id', track_visibility='onchange',
                                         default=lambda self: self.env.ref('base.lt').id, readonly=True,
                                         states={'draft': [('readonly', False)]}, copy=False)
    partner_phone = fields.Char(string='Telefonas', inverse='_set_partner_data_phone', readonly=True,
                                states={'draft': [('readonly', False)]}, copy=False, sequence=100)
    partner_email = fields.Char(string='E. paštas', inverse='_set_partner_data_email', readonly=True,
                                states={'draft': [('readonly', False)]}, copy=False, sequence=100)
    partner_category_id = fields.Many2many('res.partner.category', column1='partner_id', column2='category_id',
                                           string='Kategorija', inverse='_set_partner_data_category_id',
                                           readonly=True, states={'draft': [('readonly', False)]}, copy=False,
                                           sequence=100,
                                           )
    partner_fax = fields.Char(string='Faksas', inverse='_set_partner_data_fax', readonly=True,
                              states={'draft': [('readonly', False)]}, copy=False, sequence=100)
    partner_mobile = fields.Char(string='Mobilus telefonas', inverse='_set_partner_data_mobile', readonly=True,
                                 states={'draft': [('readonly', False)]}, copy=False, sequence=100)
    partner_website = fields.Char(string='Tinklapis', inverse='_set_partner_data_website', readonly=True,
                                  states={'draft': [('readonly', False)]}, copy=False, sequence=100,
                                  )
    partner_lang = fields.Selection(_lang_get, default=default_lang, readonly=False, sequence=100)

    # default = " " to generate not empty field for visual effect
    my_company_name = fields.Char(string='Pavadinimas', default="", sequence=100)
    my_company_street = fields.Char(string='Gatvė', default="", sequence=100)
    my_company_zip = fields.Char(string='Pašto kodas', default="", sequence=100)
    my_company_city = fields.Char(string='Miestas', default="", sequence=100)
    my_company_country_id = fields.Many2one('res.country', string='Šalis', ondelete='restrict', sequence=100)
    my_company_phone = fields.Char(string='Telefonas', default="", sequence=100)
    my_company_email = fields.Char(string='E. paštas', default="", sequence=100)
    my_company_vat = fields.Char(string='PVM kodas', default="", sequence=100)
    my_company_kodas = fields.Char(string='Kodas', default="", sequence=100)
    my_company_bank_account = fields.Char(string='Banko sąskaita', default="", sequence=100)
    my_company_bank_name = fields.Char(string='Bankas', default="", sequence=100)
    my_company_bank_BIC = fields.Char(string='BIC kodas', default="", sequence=100)
    intrastat_country_id = fields.Many2one(compute='_compute_intrastat_country_id',
                                           store=True,
                                           )  # redefine field to make it computed
    empty_field = fields.Char(string=' ', default="", readonly=True, sequence=100)
    date_invoice = fields.Date(default=fields.Date.today, inverse='_inverse_date_invoice',
                               track_visibility='onchange')  # inverse method is also called elsewhere
    date_due = fields.Date(track_visibility='onchange')
    operacijos_data = fields.Date(track_visibility='onchange')
    # Domain is taken from the add-ons. exclude_from_invoices added to it (can't override otherwise)
    journal_id = fields.Many2one(
        track_visibility='onchange', default=_default_journal,
        domain="[('exclude_from_invoices', '=', False), "
               "('type', 'in', {'out_invoice': ['sale'], 'out_refund': ['sale'], 'in_refund': ['purchase'], "
               "'in_invoice': ['purchase']}.get(type, [])), ('company_id', '=', company_id)]",
    )
    document_name = fields.Text(String='Dokumento pavadinimas', compute='_document_name', default='Sąskaita faktūra')
    company_id = fields.Many2one(inverse='_set_company_id')
    expense_state = fields.Selection([('draft', 'Juodraštis'),
                                      ('proforma', 'Išankstinė'),
                                      ('proforma2', 'Išankstinė'),
                                      ('open', 'Laukiama mokėjimo'),
                                      ('paid', 'Apmokėta'),
                                      ('cancel', 'Atšaukta'),
                                      ('imported', 'Laukia papildymo'),
                                      ('awaiting', 'Laukia atsakymo')], string='Būsena',
                                     compute='_expense_status', store=True, sequence=100,
                                     )

    # onchange name please search inside robo_tree.js ColumnExpenseType object to change field name string
    is_cash_advance_repaid = fields.Boolean(string='Ar grąžinta darbuotojui', compute='_compute_cash_advance_repaid',
                                            store=True, sequence=100,
                                            )
    cash_advance_left_to_repay = fields.Monetary(string='Liko grąžinti darbuotojui',
                                                 compute='_compute_cash_advance_repaid',
                                                 store=True, sequence=100,
                                                 )
    robo_accounting_usage = fields.One2many('robo.usage', 'invoice_id', string='Apskaitos statistika', readonly=True,
                                            sequence=100,
                                            )
    payments_widget = fields.Text(compute='_get_payment_info_JSON')
    show_vat = fields.Boolean(compute='_show_vat')
    advance_payment = fields.Boolean(string='Apmokėta (avansinė apyskaita)', compute='_compute_advance_payment',
                                     store=True)
    imported_pic = fields.Boolean(string='Importuotas dokumentas su nuotrauka', default=False, copy=False, sequence=100)
    imported_need_action = fields.Boolean(string='Reikia papildomų duomenų', default=False, copy=False, sequence=100)
    need_action_repr = fields.Boolean(string='Reikia papildomų duomenų (Repr)', sequence=100)
    need_action_info = fields.Boolean(string='Reikia papildomų duomenų (Info)', sequence=100)
    need_action_text = fields.Text(string='Vadovo pagrindimas', readonly=True, sequence=100)
    need_action_text_accountant = fields.Text(string='Buhalterio pagrindimas', readonly=True, sequence=100)
    informed_accountant_repr = fields.Boolean(string='Buhalteris informuotas', readonly=True,
                                              groups='base.group_system', copy=False, sequence=100)
    need_action = fields.Boolean(string='Reikia papildomų duomenų', compute='_expense_status', store=False,
                                 sequence=100,
                                 )
    global_state = fields.Selection([('settled_draft', 'settled_draft'),
                                     ('settled_open', 'settled_open'),
                                     ('awaiting_consensus', 'awaiting_consensus')], default='awaiting_consensus',
                                    copy=False)
    ceo_state = fields.Selection([('agree', 'Taip'),
                                  ('disagree', 'Ne'),
                                  ('no_action', 'Jokio veiksmo')], default='no_action', string='Vadovo atsakymas',
                                 copy=False, sequence=100, track_visibility='onchange'
                                 )
    accountant_state = fields.Selection([('agree', 'Taip'),
                                         ('disagree', 'Ne'),
                                         ('no_action', 'Jokio veiksmo')], default='no_action', track_visibility='onchange',
                                        string='Buhalterio atsakymas', copy=False, sequence=100)
    action_shift = fields.Selection([('ceo', 'ceo'),
                                     ('accountant', 'accountant')], default='ceo', copy=False, sequence=100)
    recently_updated = fields.Datetime(string='Statuso pasikeitimo data', compute='_compute_recently_updated',
                                       store=True, sequence=100,
                                       )
    move_name = fields.Char(help="", sequence=100)
    attachment_ids = fields.One2many('ir.attachment', 'res_id', domain=[('res_model', '=', 'account.invoice')],
                                     string='Prisegtukai', sequence=100,
                                     )
    submitted_email = fields.Char(string='Pateikė (el. paštas)', readonly=True, groups='base.group_system',
                                  copy=False, sequence=100,
                                  )
    submitted_employee_id = fields.Many2one('hr.employee', string='Pateikęs darbuotojas', readonly=True,
                                            groups='base.group_system', copy=False,
                                            inverse='_add_submitter_to_followers', index=True, sequence=100,
                                            )
    submitted = fields.Char(string='Pateikė', compute='_submitted', store=True)
    amount_is_zero = fields.Boolean(compute='_amount_is_zero', string='Amount is zero')
    banking_export_status = fields.Selection([('asked', 'Reikia suformuoti'), ('asked_swed', 'Reikia suformuoti Swedbank'), ('asked_paysera', 'Reikia suformuoti Paysera'), ('informed', 'Informuota')],
                                             string='Suformuoti mokėjimo ruošinį', groups='base.group_system',
                                             copy=False, sequence=100, track_visibility='onchange',
                                             )
    number = fields.Char(track_visibility='onchange', sequence=100)
    reference = fields.Char(track_visibility='onchange', copy=False, help="", sequence=100)
    external_invoice = fields.Boolean(string='Išorinė sąskaita', groups='base.group_system', default=False, copy=False)
    is_ceo = fields.Boolean(compute='get_ceo')
    show_export_to_other_EU_member_state_warning = fields.Boolean(
        compute='_compute_show_export_to_other_EU_member_state_warning')
    user_id = fields.Many2one('res.users', copy=False, index=True)
    has_outstanding = fields.Boolean(search='_search_has_outstanding', sequence=100)
    show_representation_action = fields.Boolean(compute='_show_representation_action')
    visible_employee_analytic = fields.Boolean(compute='_visible_employee_analytic', store=True, sequence=100)
    offsetting_data = fields.Text(compute='_get_offsetting_info_json')
    has_potential_offsetting = fields.Boolean(compute='_get_offsetting_info_json',
                                              search='_search_potential_offsetting',
                                              sequence=100,
                                              )
    bank_statement_data = fields.Text(compute='_get_bank_statement_info_json')
    has_potential_bank_statement = fields.Boolean(compute='_get_bank_statement_info_json',
                                                  search='_search_potential_bank_statement',
                                                  sequence=100,
                                                  )
    has_not_been_validated_by_accountant_warning = fields.Html(
        compute='_compute_has_not_been_validated_by_accountant_warning')
    tag_ids = fields.Many2many('account.invoice.tags', string='Žymos',
                               groups='robo_basic.group_robo_premium_accountant', copy=False)
    tag_ids_text = fields.Html(string='Žymos', compute='_compute_tag_ids_text', store=True, copy=False, sequence=100)
    tag_ids_tree_text = fields.Html(string='Žymos', compute='_compute_tag_ids_tree_text', store=True, copy=False,
                                    sequence=100,
                                    )
    tag_detail_ids = fields.One2many('account.invoice.tags.details', 'invoice_id', string='Žymų aprašymas',
                                     groups='robo_basic.group_robo_premium_accountant', copy=False, sequence=100,
                                     )
    invoice_analytic_codes = fields.Char(
        string='Analitinių sąskaitų kodai',
        compute='_compute_invoice_analytic_codes', store=True, sequence=100,
    )
    internal_reported_vat = fields.Boolean(string='Išsiųsta ataskaita apie užsienio PVM', copy=False, sequence=100)
    main_analytic_id = fields.Many2one('account.analytic.account', string='Pagrindinė analitinė sąskaita',
                                       compute='_compute_main_analytic_id', store=True,
                                       )
    imported = fields.Boolean(string='Importuota', default=False, readonly=True, copy=False, sequence=100)
    periodic_ids = fields.One2many('periodic.invoice', 'invoice_id',
                                   groups='robo_basic.group_robo_periodic', copy=False, sequence=100)
    periodic_id = fields.Many2one('periodic.invoice', string='Periodinis įrašas', readonly=True,
                                  groups='robo_basic.group_robo_periodic', ondelete='set null', copy=False,
                                  sequence=100,
                                  )
    has_running_periodic = fields.Boolean(compute='_compute_has_running_periodic')
    tax_ids = fields.Many2many('account.tax', string='Tax Codes', store=False, search='_search_tax_ids')
    account_code = fields.Char(string="Account code", compute='_compute_account_code', store=True)

    @api.depends('invoice_line_ids.account_id')
    def _compute_account_code(self):
        for rec in self:
            account = rec.invoice_line_ids.mapped('account_id')
            rec.account_code = None if len(account) != 1 else account.code

    fuel_expense_move_id = fields.Many2one(sequence=100)
    comment = fields.Text(sequence=100)
    account_id = fields.Many2one(sequence=100)
    invoice_line_ids = fields.One2many(sequence=100)
    company_currency_id = fields.Many2one(sequence=100)
    fiscal_position_id = fields.Many2one(sequence=100)
    commercial_partner_id = fields.Many2one(sequence=100)
    message_is_follower = fields.Boolean(sequence=100)
    message_last_post = fields.Datetime(sequence=100)
    message_needaction = fields.Boolean(sequence=100)
    message_needaction_counter = fields.Integer(sequence=100)
    message_follower_ids = fields.One2many(sequence=100)
    message_partner_ids = fields.Many2many(sequence=100)
    message_channel_ids = fields.Many2many(sequence=100)
    move_id = fields.Many2one(sequence=100)
    name = fields.Char(sequence=100)
    payment_ids = fields.Many2many(sequence=100)
    payment_move_line_ids = fields.Many2many(sequence=100)
    purchase_id = fields.Many2one(sequence=100)
    reference_type = fields.Selection(sequence=100)
    refund_invoice_id = fields.Many2one(sequence=100)
    residual_signed = fields.Monetary(sequence=100)
    tax_line_ids = fields.One2many(sequence=100)
    team_id = fields.Many2one(sequence=100)
    origin = fields.Char(sequence=100)
    partner_shipping_id = fields.Many2one(sequence=100)
    campaign_id = fields.Many2one(sequence=100)
    source_id = fields.Many2one(sequence=100)
    medium_id = fields.Many2one(sequence=100)
    currency_id = fields.Many2one(sequence=100)
    payment_term_id = fields.Many2one(sequence=100)
    residual_company_signed = fields.Monetary(sequence=100)

    # Consumption of goods for private needs fields
    private_product_consumption = fields.Boolean(
        string='Product consumption for private needs'
    )
    private_product_consumption_move_id = fields.Many2one(
        'account.move', string='Product consumption for private needs account move'
    )

    @api.depends('periodic_id', 'periodic_ids.date_stop')
    def _compute_has_running_periodic(self):
        if self.env.user.has_group('robo_basic.group_robo_periodic'):
            for rec in self:
                rec.has_running_periodic = any(p.running for p in rec.periodic_ids) or rec.periodic_id and rec.periodic_id.running

    @api.depends('state', 'payment_mode')
    def _allow_change_payment_details(self):
        allowed_groups = [
            'robo_basic.group_robo_premium_manager',
            'robo.group_menu_kita_analitika',
            'robo.group_robo_see_all_expenses',
        ]
        allowed_user = any(self.env.user.has_group(g) for g in allowed_groups)
        for rec in self:
            if rec.accountant_validated:
                continue
            can_change = allowed_user or self.env.user == rec.user_id or self.env.user == rec.sudo().submitted_employee_id.user_id
            if not can_change:
                continue
            if rec.payment_mode == 'company_account':
                if rec.state == 'paid':
                    rec.allow_change_ap_employee_id = False
                else:
                    rec.allow_change_ap_employee_id = can_change
            else:
                rec.allow_change_ap_employee_id = not rec.is_cash_advance_repaid and can_change

    @api.multi
    def make_periodic(self):
        self.ensure_one()
        if not self.env.user.has_group('robo_basic.group_robo_periodic'):
            raise exceptions.UserError('You cannot do that')
        if self.type != 'out_invoice':
            raise exceptions.UserError(_('Tik kliento sąskaitos gali būti periodinės'))
        if self.has_running_periodic:
            raise exceptions.UserError('This invoice is already linked to an ongoing periodic invoice.')
        date = self.date_invoice
        date_invoice = datetime.strptime(self.date_invoice, tools.DEFAULT_SERVER_DATE_FORMAT)
        cdate = datetime(datetime.utcnow().year, datetime.utcnow().month, datetime.utcnow().day)
        if (date_invoice + relativedelta(months=1)) <= cdate:
            date = datetime(cdate.year, cdate.month, date_invoice.day).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_due = datetime.strptime(self.date_due, tools.DEFAULT_SERVER_DATE_FORMAT)
        term_days = (date_due - date_invoice).days
        periodic_id = self.env['periodic.invoice'].create({
            'invoice_id': self.id,
            'date': date,
            'payment_term_days': term_days,
        })
        periodic_id.set_next_date()

    @api.multi
    def stop_periodic(self):
        self.ensure_one()
        (self.periodic_ids + self.periodic_id).filtered('running').stop()

    @api.multi
    @api.depends('invoice_line_ids.account_analytic_id')
    def _compute_main_analytic_id(self):
        """
        Compute main analytic account according to the biggest amount in invoice lines
        :return: None
        """
        for rec in self:
            analytic_amounts = {}
            for line in rec.invoice_line_ids.filtered(lambda a: a.account_analytic_id):
                if line.account_analytic_id.id not in analytic_amounts:
                    analytic_amounts[line.account_analytic_id.id] = line.amount_depends
                else:
                    analytic_amounts[line.account_analytic_id.id] += line.amount_depends

            rec.main_analytic_id = max(analytic_amounts, key=analytic_amounts.get) if analytic_amounts else False

    # Mass Mailing wizard action --------------------------------------------------------------------------------------
    @api.model
    def invoice_mass_mailing_wizard_action_func(self):
        """Function to create mass invoice mailing action"""
        action = self.env.ref('robo.invoice_mass_mailing_wizard_action')
        if action:
            action.create_action()

    @api.model
    def get_account_invoice_mail_template(self):
        """
        Gets the mail template for account invoice based on forced template through context or based on the language
        Args:
            language (string): (optional) language ISO code to get the template based on language

        Returns:
            Mail template to use for sending the invoice
        """
        template = self._context.get('force_template')  # Get forced template
        if not template:
            if self._context.get('force_use_old_invoice_mail_template'):
                # Force use default (old) template. Useful for client modules that have changes to this template.
                template = self.env.ref('account.email_template_edi_invoice', False)
            else:
                template = self.env.ref('l10n_lt.account_invoice_main_mail_template', False)

        if not template:
            # Use old default invoice template which has both LT and EN languages inside
            template = self.env.ref('account.email_template_edi_invoice', False)

        return template

    @api.multi
    def invoice_mass_mailing_wizard_action_open(self):
        """
        Action that creates mass mailing wizard object and returns the form view
        :return: mass invoice mailing wizard action (dict)
        """
        # Ensure that all invoices are of out type
        if any(x.type in ['in_invoice', 'in_refund'] for x in self):
            raise exceptions.UserError(_('Tiekėjų sąskaitos negali būti siunčiamos paštu!'))

        # Ensure that invoices ready-to-send are of the same language
        partner_lang = list(set(self.mapped('partner_lang')))
        if len(partner_lang) > 1:
            raise exceptions.UserError(_('Masinis sąskaitų siuntimas galimas tik sąskaitoms su ta pačia kalba'))
        partner_lang = partner_lang and partner_lang[0]

        template = self.with_context(lang=partner_lang).get_account_invoice_mail_template()

        ctx = dict(
            default_use_template=bool(template),
            default_template_id=template.id,
            default_model='account.invoice',
            default_composition_mode='mass_mail',
            force_send_message=True,
            mark_invoice_as_sent=True,
            custom_layout="account.mail_template_data_notification_email_account_invoice",
            front_message=True,
        )
        ctx.update(self._context.copy())
        wizard_obj = self.env['invoice.mass.mailing.wizard']
        action = self.env.ref('robo.action_open_invoice_mass_mailing_wizard').read()[0]
        wiz_id = wizard_obj.with_context(ctx).create({})
        wiz_id.onchange_template_id_wrapper()

        action.update({
            'res_id': wiz_id.id,
            'context': ctx
        })
        return action

    # Tax change wizard action ----------------------------------------------------------------------------------------

    @api.multi
    def action_invoice_open_tax_change_wizard(self):
        self.ensure_one()
        wiz_id = self.env['account.invoice.tax.change.wizard'].create({'invoice_id': self.id})
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.invoice.tax.change.wizard',
            'res_id': wiz_id.id,
            'view_id': self.env.ref('robo.form_account_invoice_tax_change_wizard').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': {'inv_type': 'out' if self.type in ['out_invoice', 'out_refund'] else 'in',
                        'price_include_selection': 'inc' if self.price_include_selection in ['inc'] else 'exc'}
        }

    # Partner change wizard action ------------------------------------------------------------------------------------

    @api.multi
    def action_invoice_open_partner_change_wizard(self):
        self.ensure_one()
        wiz_id = self.env['account.invoice.partner.change.wizard'].create({'invoice_id': self.id})
        ctx = self._context.copy()
        ctx.update({'inv_type': 'out' if self.type in ['out_invoice', 'out_refund'] else 'in'})
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.invoice.partner.change.wizard',
            'res_id': wiz_id.id,
            'view_id': self.env.ref('robo.form_account_invoice_partner_change_wizard').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': ctx
        }

    # Analytic change (single invoice) wizard action ------------------------------------------------------------------

    @api.multi
    def action_invoice_change_analytics_all(self):
        self.ensure_one()
        wizard_obj = self.env['invoice.analytic.wizard.all']
        wiz_id = wizard_obj.create({'invoice_id': self.id}).id
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'invoice.analytic.wizard.all',
            'res_id': wiz_id,
            'view_id': self.env.ref('robo.line_analytic_wizard_all_form').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    # Analytic change (multi invoice) wizard action -------------------------------------------------------------------

    @api.model
    def multi_analytic_change_invoice_action(self):
        action = self.env.ref('robo.multi_analytic_change_invoice_action_rec')
        if action:
            action.create_action()

    @api.multi
    def action_open_multi_analytic_wizard(self):
        wizard_obj = self.env['invoice.analytic.wizard.all']
        wiz_id = wizard_obj.create({'invoice_ids': [(4, inv) for inv in self.ids]}).id
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'invoice.analytic.wizard.all',
            'res_id': wiz_id,
            'view_id': self.env.ref('robo.line_analytic_wizard_all_multi_form').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }
    # Financial account change wizard action --------------------------------------------------------------------------

    @api.multi
    def action_open_invoice_financial_account_change_wizard(self):
        """
        Returns the action to open invoice
        financial account change wizard
        :return: JS action (dict)
        """
        # Create the wizard
        res_model = 'invoice.financial.account.change.wizard'
        wizard = self.env[res_model].create({'invoice_ids': [(6, 0, self.ids)]})
        view = self.env.ref('robo.from_invoice_financial_account_change_wizard')
        context = self._context.copy()

        # Return the action
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': res_model,
            'res_id': wizard.id,
            'view_id': view.id,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': context,
            'view_ids': [(5, 0, 0), (0, 0, {'view_mode': 'form', 'view_id': view.id})]
        }

    @api.multi
    def action_open_account_invoice_vat_change_wizard(self):
        """
        Returns the action to open invoice line
        VAT change wizard
        :return: JS action (dict)
        """
        self.ensure_one()
        # Create the wizard
        res_model = 'account.invoice.vat.change.wizard'
        wizard = self.env[res_model].create({
            'invoice_id': self.id,
        })
        # Return the action
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': res_model,
            'res_id': wizard.id,
            'view_id': self.env.ref('robo.form_account_invoice_vat_change_wizard').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }


    @api.multi
    def action_open_invoice_date_change_wizard(self):
        """
        Returns the action to open invoice date change wizard
        :return: JS action (dict)
        """
        self.ensure_one()

        # Create the wizard
        res_model = 'invoice.date.change.wizard'
        wizard = self.env[res_model].create({'invoice_id': self.id})
        # Return the action
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': res_model,
            'res_id': wizard.id,
            'view_id': self.env.ref('robo.invoice_date_change_wizard_view_form').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.model
    def create_action_invoice_open_multi_income(self):
        """Create server action for mass invoice opening in income tree"""
        action = self.env.ref('robo.action_invoice_open_multi_income')
        if action:
            action.create_action()

    @api.multi
    def action_invoice_open_multi_preprocess(self):
        """Method that is used to create queue jobs for mass invoice opening"""
        invoices = self.filtered(
            lambda x: x.state in ['draft', 'proforma2']
            and x.type in ['out_invoice', 'out_refund']
        )
        for invoice in invoices:
            invoice.with_delay(
                channel='root.invoice', identity_key=identity_exact,
            ).action_invoice_open_multi_process()

    @job
    @api.multi
    def action_invoice_open_multi_process(self):
        """
        Job method that calls account_invoice_open.
        Used as an intermediary method to avoid decoration
        inconsistencies on account_invoice_open.
        """
        self.ensure_one()
        try:
            self.action_invoice_open()
        except Exception as exc:
            self.env.cr.rollback()
            body = _('Background invoice confirmation failed. Error message - %s') % str(exc.args[0])
        else:
            body = _('Invoice successfully confirmed in the background')

        # Post the message to invoice after successful or failed confirmation
        self.robo_message_post(
            subtype='mt_comment', body=body, priority='low')

    @api.multi
    def report_invoice_processing_issue(self):
        self.ensure_one()
        action = self.env.ref('robo.report_invoice_processing_issue_action').read()[0]
        action['context'] = {'active_id': self.id}
        return action

    @api.multi
    def _set_state(self):
        """
        Force bank_export_state to accepted if invoice becomes paid in the system.
        Used to prevent incorrect states when bank response is lost on the way
        back to the system
        :return: None
        """
        for rec in self:
            if rec.expense_state and rec.expense_state in ['paid'] and \
                    rec.bank_export_state in ['waiting', 'rejected', 'rejected_partial']:
                rec.bank_export_state = 'accepted'

    @api.multi
    def set_state_global(self):
        """
        Inverse state, use this if called from other model
        :return: None
        """
        self._set_state()

    @api.depends('partner_vat', 'partner_country_id')
    def _compute_intrastat_country_id(self):
        """ Compute Intrastat country based on partner VAT code or partner country """
        for inv in self:
            country = False
            partner_vat = inv.partner_vat
            if partner_vat:
                country = self.env['res.country'].search([('code', '=', partner_vat[:2])], limit=1)
            inv.intrastat_country_id = country or inv.partner_country_id

    @api.multi
    @api.depends('invoice_line_ids.account_analytic_id')
    def _compute_invoice_analytic_codes(self):
        """
        Compute string representation of account.analytic.account codes that belong to
        account.invoice via account.invoice.line
        :return: None
        """
        for rec in self:
            code_repr = str()
            for line in rec.sudo().mapped('invoice_line_ids.account_analytic_id'):
                if code_repr:
                    code_repr += '| '
                code_repr += '[{}]'.format(line.code) or str()
            rec.invoice_analytic_codes = code_repr

    @api.multi
    @api.constrains('move_name', 'reference')
    def _check_invoice_numbers(self):
        """
        Constraints //
        Ensure that invoice reference and move_name
        are unique based on following criteria
        :return: None
        """
        for invoice in self:
            base_domain = [('id', '!=', invoice.id),
                           ('type', '=', invoice.type),
                           ('company_id', '=', invoice.company_id.id)]

            if invoice.type in ['out_invoice', 'out_refund'] and invoice.move_name:
                type_domain = base_domain + [('move_name', '=', invoice.move_name)]
                if self.env['account.invoice'].search_count(type_domain):
                    raise exceptions.ValidationError(
                        _('Klaida, sąskaita su šiuo sisteminiu numeriu jau egzistuoja sistemoje!'))
            if invoice.type in ['in_invoice', 'in_refund'] and invoice.reference:
                type_domain = base_domain + [('reference', '=', invoice.reference),
                                             ('state', '!=', 'cancel'),
                                             ('commercial_partner_id', '=', invoice.commercial_partner_id.id)]
                if self.env['account.invoice'].search_count(type_domain):
                    raise exceptions.ValidationError(
                        _('Klaida, sąskaita su šiuo tiekėjo numeriu jau egzistuoja sistemoje!'))

    @api.multi
    def mark_sepa_non_exported(self):
        """
        If invoice is marked as 'exported_sepa' and does not have
        bank export jobs, allow to un-mark it.
        :return: None
        """
        if self.env.user.is_accountant():
            for rec in self.filtered(lambda x: x.exported_sepa):
                if not rec.bank_export_job_ids.filtered(lambda x: not x.xml_file_download):
                    rec.write({'exported_sepa': False, 'exported_sepa_date': False})
                else:
                    raise exceptions.UserError(
                        _('Negalite pažymėti sąskaitos kaip neeksportuotos, nes ji turi susijusių banko eksportų.'))

    @api.multi
    def create_private_consumption_move(self):
        """
        Creates private consumption move for account invoice if it
        has private product consumption bool set. Consumption move
        is reconciled with invoice move.
        :return: None
        """

        def get_reverse_amount_kw(move_line):
            """Return reverse move line amount value and keyword"""
            if tools.float_is_zero(move_line.debit, precision_digits=2):
                return 'debit', move_line.credit
            return 'credit', move_line.debit

        # Get tax accounts
        tax_accounts = self.env['account.tax'].search([('code', '=', 'PVM6')]).mapped('account_id')
        if not tax_accounts:
            tax_accounts = self.env['account.account'].search([('code', '=', '44921')])

        con_tax_account = self.env['account.account'].search([('code', '=', '652')], limit=1)

        # Check whether global private consumption is activated and filter the set otherwise
        private_cons = self.env.user.company_id.enable_invoice_reconciliation_on_private_consumption
        invoices = self if private_cons else self.filtered(lambda x: x.private_product_consumption)

        for rec in invoices:
            # Get tax line from invoice move, and skip the creation of the move if it does not exist
            tax_line = rec.move_id.line_ids.filtered(lambda x: x.account_id.id in tax_accounts.ids)
            if not tax_line or len(tax_line) > 1:
                continue
            move_lines = []
            # Prepare move lines - tax line has specific account, all other lines are just flipped
            extra_private_consumption_tax_line_values = rec.get_extra_private_consumption_values()
            for line in rec.move_id.line_ids:
                is_tax_line = line.id == tax_line.id
                amount_kw, amount = get_reverse_amount_kw(line)
                # Get the account based on the line
                account = con_tax_account if is_tax_line else line.account_id
                con_tax_line = {
                    'name': _('{} Sunaudojimas savoms reikmėms').format(tax_line.name),
                    'date': tax_line.date,
                    'partner_id': tax_line.partner_id.id,
                    'account_id': account.id,
                    amount_kw: amount,
                }
                if is_tax_line:
                    con_tax_line.update(extra_private_consumption_tax_line_values)

                move_lines.append((0, 0, con_tax_line))
            # Prepare move values
            move_vals = {
                'line_ids': move_lines,
                'journal_id': rec.move_id.journal_id.id,
                'date': rec.move_id.date,
            }
            # Create and post private consumption account move
            account_move = self.env['account.move'].sudo().create(move_vals)
            account_move.post()
            rec.write({'private_product_consumption_move_id': account_move.id})
            # Reconcile consumption move and the invoice move
            move_lines = account_move.line_ids.filtered(
                lambda r: r.account_id.id == rec.account_id.id)
            move_lines |= rec.move_id.line_ids.filtered(
                lambda r: r.account_id.id == rec.account_id.id)
            move_lines = move_lines.filtered(lambda x: not x.reconciled)
            if len(move_lines) > 1:
                move_lines.with_context(reconcile_v2=True).reconcile()

    @api.multi
    def unlink_private_consumption_move(self):
        """
        Un-reconciles and unlinks private consumption move from the invoice.
        Method is called on invoice cancellation.
        :return: None
        """
        for rec in self.filtered(lambda x: x.private_product_consumption_move_id):
            rec.private_product_consumption_move_id.line_ids.remove_move_reconcile()
            rec.private_product_consumption_move_id.button_cancel()
            rec.private_product_consumption_move_id.unlink()

    @api.multi
    def remove_outstanding_payments(self):
        """
        If invoice is in paid or open state, remove related assigned payments.
        Assigned payments may include:
            -Standard invoice payments
            -Expense move payments
            -GPM move payments
        :return: related unassigned payments (dict)
        """

        def full_unreconcile_line(exp_line):
            move_payment_lines = self.env['account.move.line']
            partial_reconciliation_ids = exp_line.matched_debit_ids + exp_line.matched_credit_ids
            full_reconcile_id = exp_line.full_reconcile_id
            if partial_reconciliation_ids:
                total_aml = partial_reconciliation_ids.mapped(
                    'credit_move_id') + partial_reconciliation_ids.mapped('debit_move_id')
                total_aml.remove_move_reconcile()
                move_payment_lines = total_aml.filtered(lambda x: x.id != exp_line.id)
            elif full_reconcile_id:
                lines = full_reconcile_id.reconciled_line_ids
                lines.remove_move_reconcile()
                move_payment_lines = full_reconcile_id.reconciled_line_ids.filtered(
                    lambda x: x.id != exp_line.id)
            return move_payment_lines

        self.ensure_one()
        AccountMoveLine = self.env['account.move.line']
        expense_payment_lines = AccountMoveLine
        payment_lines = AccountMoveLine
        gpm_payment_lines = AccountMoveLine

        if self.state in ['paid', 'open']:

            # Unreconcile and save GPM move payments
            payment_lines = self.payment_move_line_ids
            if payment_lines:
                for line in self.mapped('move_id.line_ids'):
                    if line.account_id == self.account_id:
                        line.remove_move_reconcile()

            # Unreconcile and save expense move payments
            reconciled_expense_lines = self.expense_move_id.line_ids.filtered(lambda x: x.reconciled)
            for line in reconciled_expense_lines:
                expense_payment_lines |= full_unreconcile_line(line)

            # Unreconcile and save GPM move payments
            reconciled_gpm_lines = self.gpm_move.line_ids.filtered(lambda x: x.reconciled)
            for line in reconciled_gpm_lines:
                gpm_payment_lines |= full_unreconcile_line(line)

        return {
            'expense_payment_lines': expense_payment_lines,
            'payment_lines': payment_lines,
            'gpm_payment_lines': gpm_payment_lines
        }

    @api.multi
    def get_extra_private_consumption_values(self):
        """
        Intended to be overridden
        :return: Empty dict
        """
        return {}

    @api.multi
    def action_invoice_cancel_draft_and_remove_outstanding(self):
        """
        If invoice is in paid or open state, cancel the invoice and remove related assigned payments.
        :return: related unassigned payments (dict)
        """

        self.ensure_one()

        AccountMoveLine = self.env['account.move.line']
        res = {
            'expense_payment_lines': AccountMoveLine,
            'payment_lines': AccountMoveLine,
            'gpm_payment_lines': AccountMoveLine
        }

        if self.state in ['paid', 'open']:

            res = self.remove_outstanding_payments()

            if any(x.product_id.type in ['service'] for x in self.invoice_line_ids):
                self.with_context(skip_stock=True).action_invoice_cancel_draft()
            else:
                self.action_invoice_cancel_draft()
        return res

    @api.multi
    def action_re_assign_outstanding(self, payment_dict, raise_exception=True, forced_partner=None):
        """
        Reassign outstanding payments to account.invoice record.
        Method is compatible with 'action_invoice_cancel_draft_and_remove_outstanding'
        Expected payment dict is of format returned by mentioned method
        :param payment_dict: Dictionary of related outstanding payments (dict)
        :param raise_exception: Indicates whether exception should be raised if re-assigning fails (bool)
        :param forced_partner: Partner that should be forced to related payments (res.partner/None)
        :return: None
        """
        self.ensure_one()
        fail_template = 'Sąskaitos {} duomenų keitimas nepavyko, klaidos pranešimas: '.format(self.number)

        payment_lines = payment_dict.get('payment_lines')
        gpm_payment_lines = payment_dict.get('gpm_payment_lines')
        expense_payment_lines = payment_dict.get('expense_payment_lines')

        # Gather all payment lines
        all_payment_lines = payment_lines | gpm_payment_lines | expense_payment_lines
        if all_payment_lines:
            if forced_partner:
                all_payment_lines.write({'partner_id': forced_partner})
                all_payment_lines.mapped('move_id').write({'partner_id': forced_partner})

            # Reassign outstanding to standard invoice move
            for line in payment_lines:
                try:
                    self.assign_outstanding_credit(line.id)
                except Exception as exc:
                    if raise_exception:
                        raise exceptions.UserError(fail_template + str(exc.args[0]))

            # Reassign outstanding to expense invoice move
            try:
                for line in expense_payment_lines:
                    corresponding = self.expense_move_id.line_ids.filtered(
                        lambda x: x.account_id.id == line.account_id.id)
                    corresponding |= line
                    if len(corresponding) > 1:
                        corresponding.reconcile()
            except Exception as exc:
                if raise_exception:
                    raise exceptions.UserError(fail_template + str(exc.args[0]))

            # Reassign outstanding to gpm invoice move
            try:
                for line in gpm_payment_lines:
                    corresponding = self.gpm_move.line_ids.filtered(
                        lambda x: x.account_id.id == line.account_id.id)
                    corresponding |= line
                    if len(corresponding) > 1:
                        corresponding.reconcile()
            except Exception as exc:
                if raise_exception:
                    raise exceptions.UserError(fail_template + str(exc.args[0]))

    @api.one
    @api.depends('tag_ids', 'tag_ids.color', 'tag_ids.name', 'tag_ids.description', 'tag_detail_ids.details')
    def _compute_tag_ids_text(self):
        text = ''
        for tag in self.sudo().tag_ids:
            details_id = self.sudo().tag_detail_ids.filtered(lambda r: r.tag_id.id == tag.id)
            details_tag = ''
            if details_id.details:
                details_tag = '''<br/><br/>{0}'''.format(details_id.details)
            description_tag = ''
            if tag.description:
                description_tag = '''<span class='invoice_tag_description'>{0}{1}</span>'''.format(tag.description,
                                                                                                   details_tag)
            text += '''<div class='invoice_tag' style="background-color: {0};">
                    <span>{1}</span>
                    {2}
                </div>'''.format(tag.color, tag.name, description_tag)
        self.tag_ids_text = text

    @api.one
    @api.depends('accountant_validated', 'tag_ids', 'tag_ids.color', 'tag_ids.name')
    def _compute_tag_ids_tree_text(self):
        if self.accountant_validated:
            self.tag_ids_tree_text = '<span style="color: green; font-weight: bold">Patvirtinta Buhalterio</span>'
        else:
            text = ''
            for tag in self.sudo().tag_ids:
                text += '''<span class="badge" style="background-color: {0};"><span class="o_badge_text">{1}</span></span>'''.format(
                    tag.color, tag.name)
            self.tag_ids_tree_text = text

    @api.one
    @api.depends('accountant_validated', 'state')
    def _compute_has_not_been_validated_by_accountant_warning(self):
        text = ''
        if not self.accountant_validated and self.state not in ['proforma', 'proforma2']:
            tag_help = _('Šios sąskaitos dar neperžiūrėjo buhalteris, todėl galimi netikslumai. Visi netikslumai bus '
                         'pataisyti peržiūrėjus dokumentus. Dokumentai yra peržiūrimi periodiškai.')
            text = '''<div class="is_not_validated_by_accountant_invoice_warning">
                <i class="fa fa-warning"/>
                <span class="invoice_tag_help_text">
                    {0}
                </span>
            </div>'''.format(tag_help)
        self.has_not_been_validated_by_accountant_warning = text

    @api.one
    def _get_offsetting_info_json(self):
        self.offsetting_data = json.dumps(False)
        account_mapper = {'2410': '4430', '4430': '2410'}
        if self.state in ['open', 'proforma', 'proforma2']:
            account_id = self.env['account.account'].search(
                [('code', '=', account_mapper.get(self.account_id.code, False))])
            if not account_id:
                return
            domain = [('account_id', '=', account_id.id),
                      ('partner_id', '=', self.env['res.partner']._find_accounting_partner(self.partner_id).id),
                      ('reconciled', '=', False), ('amount_residual', '!=', 0.0)]
            if self.type in ('out_invoice', 'in_refund'):
                domain.extend([('credit', '>', 0), ('debit', '=', 0)])
                type_payment = _('Outstanding credits')
            else:
                domain.extend([('credit', '=', 0), ('debit', '>', 0)])
                type_payment = _('Outstanding debits')
            info = {'title': '', 'offsetting': True, 'content': [], 'invoice_id': self.id}
            lines = self.env['account.move.line'].sudo().search(domain)
            currency_id = self.currency_id
            if len(lines) != 0:
                for line in lines:
                    if line.currency_id and line.currency_id == self.currency_id:
                        amount_to_show = abs(line.amount_residual_currency)
                    else:
                        amount_to_show = line.company_id.currency_id.with_context(
                            date=line.date).compute(abs(line.amount_residual), self.currency_id)
                    if float_is_zero(amount_to_show, precision_rounding=self.currency_id.rounding) or float_compare(
                            amount_to_show, self.residual_signed, precision_rounding=self.currency_id.rounding) != 0:
                        continue
                    if line.sudo().invoice_id and line.sudo().invoice_id.type in ('out_invoice', 'out_refund'):
                        journal_name = line.move_id.name or ''
                    else:
                        journal_name = line.name
                    if line.ref:
                        journal_name += ' (%s)' % line.ref
                    info['content'].append({
                        'journal_name': journal_name,
                        'date': line.date,
                        'amount': amount_to_show,
                        'currency': currency_id.symbol,
                        'id': line.id,
                        'position': currency_id.position,
                        'digits': [69, self.currency_id.decimal_places],
                        'state': self.state,
                    })
                if info['content']:
                    info['title'] = type_payment
                    self.offsetting_data = json.dumps(info)
                    self.has_potential_offsetting = True

    def _search_potential_offsetting(self, operator, value):
        if operator == '=' and value is True:
            offsetting_ids = self.env['account.invoice'].search([
                ('state', 'in', ['open', 'proforma', 'proforma2'])
            ]).filtered('has_potential_offsetting').mapped('id')
            return [('id', 'in', offsetting_ids)]
        return [('has_potential_offsetting', operator, value)]

    @api.multi
    def _get_bank_statement_info_json(self):
        AccountBankStatementLine = self.env['account.bank.statement.line']
        Partner = self.env['res.partner']
        if self.env.user.has_group('robo.group_menu_kita_analitika') or self.env.user.is_manager():
            for rec in self:
                rec.bank_statement_data = json.dumps(False)
                if rec.state == 'open' or (rec.state in ['proforma', 'proforma2'] and not rec.proforma_paid) \
                        or (rec.state == 'draft' and rec.type in ['in_invoice', 'in_refund']
                            and rec.expense_state == 'imported' and rec.need_action_info and not rec.need_action_repr):
                    domain = [('partner_id', '=', Partner._find_accounting_partner(rec.partner_id).id),
                              ('journal_entry_ids', '=', False), ('statement_id.sepa_imported', '=', True),
                              ('sepa_duplicate', '=', False)]
                    if rec.type in ('out_invoice', 'in_refund'):
                        domain.extend([('amount', '>', 0)])
                        type_bank_statement = _('Outstanding debits')
                    else:
                        domain.extend([('amount', '<', 0)])
                        type_bank_statement = _('Outstanding credits')
                    info = {'title': '', 'outstanding_statements': True, 'content': [], 'invoice_id': rec.id}
                    lines = AccountBankStatementLine.sudo().search(domain)
                    invoice_currency = rec.currency_id
                    for line in lines:
                        statement_currency = line.statement_id.currency_id
                        line_currency = line.currency_id
                        if line_currency and line_currency == invoice_currency:
                            # If line currency matches invoice currency show line amount_currency
                            amount_to_show = abs(line.amount_currency)
                        else:
                            # Convert from line currency to invoice currency
                            convert_from_currency = line_currency or statement_currency or line.company_id.currency_id
                            amount_to_show = convert_from_currency.with_context(date=line.date).compute(
                                abs(line.amount), invoice_currency
                            )
                        if float_is_zero(amount_to_show, precision_rounding=invoice_currency.rounding):
                            continue
                        if line.sudo().invoice_id and line.sudo().invoice_id.type in ('out_invoice', 'out_refund'):
                            journal_name = line.move_id.name or ''
                        else:
                            journal_name = line.name
                        if line.ref:
                            journal_name += ' (%s)' % line.ref
                        info['content'].append({
                            'journal_name': journal_name,
                            'date': line.date,
                            'amount': amount_to_show,
                            'currency': invoice_currency.symbol,
                            'id': line.id,
                            'position': invoice_currency.position,
                            'digits': [69, invoice_currency.decimal_places],
                            'state': rec.state,
                        })
                    if info['content']:
                        info['title'] = type_bank_statement
                        rec.bank_statement_data = json.dumps(info)
                        rec.has_potential_bank_statement = True

    def _search_potential_bank_statement(self, operator, value):
        if operator == '=' and value is True:
            invoice_ids = self.env['account.invoice'].search([
                ('state', 'in', ['draft', 'open', 'proforma', 'proforma2'])
            ]).filtered('has_potential_bank_statement').mapped('id')
            return [('id', 'in', invoice_ids)]
        return [('has_potential_bank_statement', operator, value)]

    @api.one
    @api.depends('invoice_line_ids.account_analytic_id.privacy_visibility')
    def _visible_employee_analytic(self):
        self.visible_employee_analytic = any(x.account_analytic_id and x.account_analytic_id.sudo().privacy_visibility
                                             in ['employee'] for x in self.invoice_line_ids)

    @api.model
    def create_action_e_invoice_export_wizard_multi(self):
        action = self.env.ref('robo.action_e_invoice_export_wizard_multi_ir')
        if action:
            action.create_action()

    @api.one
    @api.depends('invoice_line_ids.product_id', 'type', 'imported_need_action')
    def _show_representation_action(self):
        has_representation_product = any(x.product_id.default_code in ['R25', 'R75'] for x in self.invoice_line_ids)
        if has_representation_product and not self.imported_need_action and \
                self.env.user.company_id.vadovas.user_id.id != self.env.user.id and \
                self.env.ref('robo.group_robo_need_action').id not in self.env.user.groups_id.ids and \
                self.env.ref('robo_basic.group_robo_premium_accountant').id not in self.env.user.groups_id.ids and \
                self.env.user.company_id.force_need_action_repr and self.type in ['in_invoice', 'in_refund']:
            self.show_representation_action = True

    @api.multi
    def submit_ceo_action(self):
        self.ensure_one()
        if self.show_representation_action:
            self.write({
                'imported_need_action': True,
                'need_action_repr': True
            })

    def _search_has_outstanding(self, operator, value):
        if operator == '=' and value is True:
            outstanding_ids = self.env['account.invoice'].search([
                ('state', 'in', ['open', 'proforma', 'proforma2'])
            ]).filtered('has_outstanding').mapped('id')
            return [('id', 'in', outstanding_ids)]
        return [('has_outstanding', operator, value)]

    @api.one
    @api.depends('invoice_line_ids', 'invoice_line_ids.invoice_line_tax_ids')
    def _compute_show_export_to_other_EU_member_state_warning(self):
        eu_export_tax_rates = ['PVM12', 'PVM13']
        contains_eu_export_taxes = any(
            tax_id in eu_export_tax_rates for tax_id in self.invoice_line_ids.mapped('invoice_line_tax_ids.code')
        )
        validated = self.state in ['open', 'paid']
        out_invoice = self.type == 'out_invoice'
        self.show_export_to_other_EU_member_state_warning = True if contains_eu_export_taxes and validated and out_invoice else False

    @api.multi
    def js_unreconcile_payment(self, move_line_id):
        """
        Un-reconciles passed payment (Aml ID) from current
        account invoice record if user has sufficient rights.
        Called from the JS widget (account.invoice form).
        :return: None
        """
        self.ensure_one()
        # Check for the rights
        if self.accountant_validated and not self.env.user.is_manager():
            raise exceptions.UserError(_('Negalite pašalinti mokėjimų sąskaitai, kurią patvirtino buhalteris!'))
        move_line = self.env['account.move.line'].browse(move_line_id).exists()
        if not self.env.user.has_group('base.group_system'):
            use_sudo = self.env.user.has_group('robo.group_menu_kita_analitika') or self.env.user.is_manager()
            use_sudo = use_sudo or self.type in ['out_invoice', 'out_refund'] and self.env.user.has_group(
                'robo.group_robo_see_all_incomes')
            use_sudo = use_sudo or self.type in ['in_invoice', 'in_refund'] and self.env.user.has_group(
                'robo.group_robo_see_all_expenses')
            if not use_sudo:
                try:
                    self.check_access_rights('write')
                    self.check_access_rule('write')
                    use_sudo = True
                except (exceptions.UserError, exceptions.AccessError):
                    pass
            if use_sudo:
                self.message_post('Removing payment')
                move_line = move_line.sudo()
        move_line.remove_move_reconcile()

    @api.multi
    def set_need_action_fields(self, cancel=False):
        """
        Sets/resets need action fields based on the
        action - either it's invoice cancelling or confirmation
        :param cancel: True/False
        :return: None
        """
        # Set representation fields
        global_state = 'settled_draft' if cancel else 'settled_open'
        self.set_representation_fields(global_state)

        self.write({
            'imported_need_action': False,
            'need_action_repr': False,
            'need_action_info': False
        })

    @api.multi
    def switch_to_representation_expenses(self):
        """
        Switches all of account invoice lines to representation
        expenses - splits one line into two parts R75 and R25.
        Amount checks are done afterwards to ensure that
        final sum is not changed
        :return: None
        """
        for rec in self:
            # If there's no representation product, change all of the lines
            r75_data = self.env['hr.expense'].get_representation_product('R75')
            r25_data = self.env['hr.expense'].get_representation_product('R25')

            # Prepare set of lines to be unlinked, also save amount before split
            old_lines = self.env['account.invoice.line']
            old_amt = rec.amount_untaxed_signed if \
                rec.price_include_selection == 'exc' else rec.amount_total_signed
            amount_field = 'price_subtotal' if rec.price_include_selection == 'exc' else 'total_with_tax_amount'

            for line in rec.invoice_line_ids:
                # Check whether price is an even number, if it's not
                # subtract one cent difference from one of the lines
                odd_amount = int(round(tools.float_round(line[amount_field], precision_digits=2) * 100)) % 2
                # Save halved total of the line
                halved_price = tools.float_round(line[amount_field] * 0.5, precision_digits=2)
                for code, data in [('R75', r75_data), ('R25', r25_data)]:
                    # If amount is odd, subtract one cent difference
                    # from the second line.
                    if odd_amount and code == 'R25':
                        halved_price -= 0.01
                    # Create two invoice lines
                    new_line = old_lines.create({
                        'product_id': data['product'].id,
                        'name': data['product'].name,
                        'quantity': 1.0,
                        'price_unit': halved_price,
                        'account_id': data['account'].id,
                        'invoice_line_tax_ids': [(4, tax.id) for tax in line.invoice_line_tax_ids],
                        'account_analytic_id': line.account_analytic_id.id,
                        'invoice_id': rec.id,
                    })
                    # Ensure that R25 is nondeductible profit, and R75 is deductible
                    if code == 'R25':
                        new_line.with_context(ignore_exceptions=True)._switch_to_nondeductible_profit_taxes()
                    else:
                        new_line.with_context(ignore_exceptions=True).switch_to_deductible_taxes()
                old_lines |= line
            # Unlink old lines
            old_lines.unlink()

            # Get the new amount
            new_amt = rec.amount_untaxed_signed if \
                rec.price_include_selection == 'exc' else rec.amount_total_signed

            # Compare the amounts, raise the error if they do not match
            if tools.float_compare(old_amt, new_amt, precision_digits=2):
                raise exceptions.ValidationError(
                    _('Nepavyko korektiškai padalinti eilutės į reprezentacines sąnaudas. '
                      'Susiekite su administratoriais')
                )

    @api.multi
    def re_force_tax_amounts(self, all_line_split=False):
        """
        If invoice has forced taxes and it's lines were changed
        save the amounts from tax_line_ids, recompute taxes,
        and try to re-force the amounts. Parameter all_line_split
        indicates whether all of the invoice lines were split
        into representation expenses (one line is divided into two).
        Tax re-forcing is different on each case
        :return: None
        """

        sum_loss_warning = _(
            'Sąskaita turi priverstinius mokesčius - reprezentacijos, neleidžiamų atskaitymų '
            'ar neapibrėžtų išlaidų priskyrimo metu mokesčiai yra potencialiai keičiami, '
            'tad priverstinės sumos gali pasimesti, patikrinkite sąskaitos mokesčių eilutes.'
        )

        for rec in self:
            if not rec.force_taxes or not rec.tax_line_ids:
                continue
            # If invoice has forced taxes, save it's initial values
            forced_values = {}
            total_forced_amount = 0.0
            for t_line in rec.tax_line_ids:
                forced_values[t_line.tax_id] = t_line.amount
                total_forced_amount += t_line.amount

            rec.force_taxes = False
            rec.recompute_taxes_if_neccesary()

            if all_line_split:
                rec.tax_line_ids.write({'amount': 0.0})
                for tax, forced_amount in iteritems(forced_values):
                    # Search for the same tax line
                    invoice_tax_line = rec.tax_line_ids.filtered(lambda x: x.tax_id.id == tax.id)
                    # Find the reverse tax
                    if tax.nondeductible:
                        reverse_tax = tax.with_context(
                            do_not_raise_if_not_found=True,
                            ignore_exceptions=True).find_matching_deductible()
                    else:
                        reverse_tax = tax.with_context(
                            do_not_raise_if_not_found=True,
                            ignore_exceptions=True).find_matching_nondeductible_profit()
                    reverse_invoice_tax_line = rec.tax_line_ids.filtered(
                        lambda x: x.tax_id.id == reverse_tax.id)

                    odd_amount = forced_amount * 100.0 % 2
                    # Force the halved amount on current tax and it's reverse
                    # if both of them are found, otherwise force on the found one
                    if invoice_tax_line and reverse_invoice_tax_line:
                        # P3:DivOK
                        amount = round(forced_amount / 2, 2)
                        invoice_tax_line.write({'amount': amount})
                        reverse_invoice_tax_line.write({'amount': amount - 0.01 if odd_amount else amount})
                    else:
                        found_line = invoice_tax_line | reverse_invoice_tax_line
                        found_line.write({'amount': forced_amount})
            else:
                # if there's a mix -- Non representation lines
                # and representation lines, balance forced taxes on
                # nondeductible profit tax, or the first tax record.
                balancing_tax_line = rec.tax_line_ids[0]
                total_amount = 0.0
                for tax_line in rec.tax_line_ids:
                    if tax_line.tax_id.nondeductible_profit:
                        balancing_tax_line = tax_line
                    total_amount += tax_line.amount
                difference = round(total_forced_amount - total_amount, 2)
                balancing_tax_line.write({'amount': balancing_tax_line.amount + difference})

            # Re-force taxes afterwards and post the message
            rec.force_taxes = True
            rec.message_post(body=sum_loss_warning)

    @api.multi
    def action_agree(self):
        """
        Method used in invoice representation pseudo-wizard,
        to answer questions between accountant and CEO.
        Action type (ceo/accountant) is determined via context.
        Method either confirms the invoice or returns a wizard
        that asks for a justification for specific action
        :return: Action of the wizard (dict)/None
        """

        # Get values passed in the context and init variables
        accountant_action = self._context.get('accountant')
        non_deductible_action = self._context.get('non_deductible')
        force_confirm = self._context.get('force_confirm')
        non_deductible_prod = undefined_expense_prod = self.env['product.product']
        non_deductible_acc = undefined_expense_acc = self.env['account.account']

        if non_deductible_action:
            # Search for base non deductible values
            non_ded_domain = [('name', '=', 'Neleidžiami atskaitymai')]
            non_deductible_prod = self.env['product.product'].search(non_ded_domain, limit=1)
            non_deductible_acc = self.env['account.account'].search([('code', '=', '652')], limit=1)
            if not non_deductible_acc:
                non_deductible_acc = self.env['account.account'].search(non_ded_domain, limit=1)
        if force_confirm:
            # Hardcoded names and accounts (No better option at the moment)
            undefined_expense_prod = self.env['product.product'].search([('name', '=', 'Neapibrėžta')], limit=1)
            undefined_expense_acc = self.env['account.account'].search([('code', '=', '631298')], limit=1)

        # Base values that determine final behaviour
        wizard_ctx = confirm_action = False

        # Loop through the records, if wizard open action is to be
        # returned, raise an error on multi-set
        for rec in self:
            # If invoice has forced taxes and all of it's lines are switched
            # to representation expenses, we halve all of the taxes afterwards
            # all_line_split is set to True if that is the case, otherwise False.
            all_line_split = False
            no_further_questions = not self._context.get('ask_again')
            # Check whether the action is initiated from accountant user
            if accountant_action:
                vals = {}
                if no_further_questions:
                    vals['accountant_state'] = 'agree'
                # Check for lines with representation product

                lines_to_change = rec.invoice_line_ids.filtered(
                    lambda x: x.product_id.default_code in ['R75', 'R25'])
                if not lines_to_change:
                    all_line_split = True
                    rec.switch_to_representation_expenses()
                    lines_to_change = rec.invoice_line_ids

                if rec.ceo_state == 'agree' or non_deductible_action or force_confirm:
                    # Extra text that is posted
                    extra_text = str()
                    if non_deductible_action:
                        # Try to convert line values to non-deductible
                        for line in lines_to_change:
                            line.with_context(ignore_exceptions=True)._switch_to_nondeductible_profit_taxes()
                        lines_to_change.write({'product_id': non_deductible_prod.id,
                                               'account_id': non_deductible_acc.id,
                                               'name': non_deductible_prod.name})
                        extra_text = _('Priskirta neleidžiamiems atskaitymams.')
                    elif force_confirm:
                        # Try to convert line values to deductible
                        for line in lines_to_change:
                            line.with_context(ignore_exceptions=True).switch_to_deductible_taxes()
                        lines_to_change.write({'product_id': undefined_expense_prod.id,
                                               'account_id': undefined_expense_acc.id,
                                               'name': undefined_expense_prod.name})
                        extra_text = _('Priskirta neapibrėžtoms išlaidoms.')
                    # Post message to account invoice based on the action
                    msg = _("""<p>Patvirtinta buhalterio. %s<br/>
                    Ar šios sąnaudos yra laikomos įmonės reprezentacinėmis sąnaudomis? <br/> 
                    Vadovo komentaras: %s</p>""") % (extra_text, rec.need_action_text)
                    rec.message_post(body=msg)

                    # Update the values to-write and mark invoice as to-be confirmed
                    vals.update({'need_action_repr': False})
                    confirm_action = True
                else:
                    wizard_ctx = {'invoice_id': rec.id, 'accountant': True, 'agree': no_further_questions}
                rec.write(vals)
            else:
                # Otherwise, action is initiated from CEO
                if rec.accountant_state == 'agree':
                    # If accountant already agrees, mark the invoice as to-be confirmed
                    msg = _('''<p>Patvirtinta vadovo su buhalterio sutikimu. <br/> Ar šios sąnaudos yra laikomos įmonės 
                    reprezentacinėmis sąnaudomis? <br/> Buhalterio komentaras: %s</p>''') % \
                          rec.need_action_text_accountant or str()
                    rec.message_post(body=msg)
                    confirm_action = True
                else:
                    wizard_ctx = {'invoice_id': rec.id, 'ceo': True, 'agree': no_further_questions}

            # If confirm action is True, confirm invoice, or shift the action
            if confirm_action:
                # Get the lock date
                lock_date = self.env.user.company_id.get_user_accounting_lock_date()
                # Lock date is specified, check the invoice date against it,
                # and if needed, change invoice date to earliest non locked tate
                if lock_date and rec.date_invoice < lock_date:
                    date_invoice = (datetime.strptime(
                        lock_date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)).strftime(
                        tools.DEFAULT_SERVER_DATE_FORMAT
                    )
                    rec.date_invoice = date_invoice
                rec.need_action_repr = False
                if not rec.need_action_info:
                    rec.re_force_tax_amounts(all_line_split)
                    # Based on payment mode execute following actions
                    if rec.payment_mode == 'company_account':
                        rec.app_inv_company(mark_paid=False)
                    elif rec.payment_mode == 'own_account':
                        rec.app_inv_own()
                    else:
                        vals = {
                            'imported_need_action': False,
                        }
                        if not rec.move_name:
                            vals['registration_date'] = datetime.now()
                        rec.write(vals)
                        rec.set_representation_fields()
                        rec.action_invoice_open()

            # If wizard context exists - return an action
            if wizard_ctx:
                # Can't return wizard on multi-set
                if len(self) > 1:
                    raise exceptions.ValidationError(_('Operacija negalima keliems įrašams vienu metu'))

                # Create the wizard and return it's form
                model = 'needaction.accountant.wizard' if accountant_action else 'needaction.ceo.wizard'
                view = 'needaction_accountant_wizard_view' if accountant_action else 'needaction_ceo_wizard_view'

                # Different behaviour depending on action type
                if not accountant_action:
                    wizard = self.env[model].with_context(**wizard_ctx).create({})
                    wizard.get_answer()
                else:
                    wizard = self.env[model]
                return {
                    'name': _('Komentaras'),
                    'view_type': 'form',
                    'view_mode': 'form',
                    'view_id': self.env.ref('robo.' + view).id,
                    'res_model': model,
                    'type': 'ir.actions.act_window',
                    'target': 'new',
                    'context': wizard_ctx,
                    'res_id': wizard.id
                }

    @api.multi
    def action_disagree(self):
        self.ensure_one()
        ctx = {'invoice_id': self.id, 'ceo': True, 'agree': False}
        wizard = self.env['needaction.ceo.wizard'].with_context(**ctx).create({})
        wizard.get_answer()
        return {
            'name': _('Komentaras'),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': self.env.ref('robo.needaction_ceo_wizard_view').id,
            'res_model': 'needaction.ceo.wizard',
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': ctx,
            'res_id': wizard.id
        }

    @api.one
    def get_ceo(self):
        if self.env.user.company_id.vadovas.user_id.id == self.env.user.id or \
                self.env.user.has_group('robo.group_robo_need_action'):
            self.is_ceo = True
        else:
            self.is_ceo = False

    @api.one
    @api.depends('amount_total')
    def _amount_is_zero(self):
        self.amount_is_zero = tools.float_is_zero(self.amount_total, precision_rounding=self.currency_id.rounding)

    @api.multi
    def _inverse_date_invoice(self):
        super(AccountInvoice, self)._inverse_date_invoice()
        for rec in self:
            company = rec.company_id
            if company:
                if company.with_context({'date': rec.get_vat_payer_date()}).vat_payer:
                    rec.my_company_vat = company.vat
                else:
                    rec.my_company_vat = ''

    @api.multi
    def _add_submitter_to_followers(self):
        for rec in self:
            if rec.submitted_employee_id and rec.submitted_employee_id.address_home_id:
                rec.sudo().message_subscribe(partner_ids=rec.mapped('submitted_employee_id.address_home_id.id'))

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        if self.journal_id:
            if not self.currency_id:
                self.currency_id = self.journal_id.currency_id.id or self.journal_id.company_id.currency_id.id

    @api.depends('submitted_email', 'submitted_employee_id', 'user_id')
    def _submitted(self):
        for rec in self:
            if rec.sudo().submitted_employee_id:
                rec.submitted = rec.sudo().submitted_employee_id.name
            elif rec.sudo().submitted_email and rec.sudo().submitted_email.strip().endswith('robolabs.lt'):
                rec.submitted = 'ROBO'
            elif rec.sudo().submitted_email and len(rec.sudo().submitted_email) > 30:
                rec.submitted = rec.sudo().submitted_email[:27] + '...'
            elif rec.sudo().submitted_email:
                rec.submitted = rec.sudo().submitted_email
            else:
                rec.submitted = rec.sudo().user_id.name

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        if self._context.get('force_order') and self._context.get('is_force_order_time'):
            order = self._context.get('force_order')
        return super(AccountInvoice, self).search(args, offset=offset, limit=limit, order=order, count=count)

    @api.depends('state')
    def _compute_recently_updated(self):
        now = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        for rec in self:
            rec.recently_updated = now

    @api.one
    @api.depends('accountant_validated', 'with_cheque_picture', 'state', 'imported_pic', 'need_action')
    def _compute_attachment_drop_lock(self):
        self.attachment_drop_lock = False
        if self.accountant_validated or (
                self.with_cheque_picture and self.state == 'paid') or self.imported_pic or self.need_action:
            self.attachment_drop_lock = True

    @api.one
    @api.depends('hr_expense_id')
    def _compute_all_attachments(self):
        ids = self.env['ir.attachment'].search(
            [('res_model', '=', 'account.invoice'), ('res_id', '=', self.id), ('res_field', '=', False)]).ids

        # old structure support: showing attachments with res_field not empty (added previously through model field)
        # maybe we should clean db by removing ir.attachment res_field for res_model = account.invoice or hr.expense
        # also we should move some ir.attachment documents from hr.expense to account.invoice if hr.expense state = reported
        # also review robo app attachment import
        ids_fields_inv = self.env['ir.attachment'].search(
            [('res_model', '=', 'account.invoice'), ('res_id', '=', self.id), ('res_field', '!=', False)]).ids
        ids_fields_exp = []
        if self.hr_expense_id:
            ids_fields_exp = self.env['ir.attachment'].search(
                [('res_model', '=', 'hr.expense'), ('res_id', '=', self.hr_expense_id.id),
                 ('res_field', '!=', False)]).ids
        ids = set(ids + ids_fields_inv + ids_fields_exp)
        #
        self.user_attachment_ids = [(4, doc_id) for doc_id in ids]

    @api.one
    def _compute_nbr_of_attachments(self):
        self.nbr_of_attachments = len(self.user_attachment_ids.ids)

    @api.onchange('payment_mode', 'ap_employee_id')
    def onchange_payment_mode(self):
        if self.type in ['in_invoice', 'in_refund']:
            if self.payment_mode == 'company_account':
                return {'domain': {'partner_id': [('is_employee', '=', False)]}}
            elif self.payment_mode == 'own_account':
                partneris = False
                if self.ap_employee_id and self.ap_employee_id.sudo().advance_accountancy_partner_id:
                    partneris = self.ap_employee_id.sudo().advance_accountancy_partner_id
                return {'domain': {'partner_id': [
                    '|',
                    ('id', '=', partneris and partneris.id or False),
                    ('is_employee', '=', False)
                ]}}

    @api.multi
    def app_inv_company(self, mark_paid=True):
        self.ensure_one()
        self.payment_mode = 'company_account'
        self.need_action_info = False
        if mark_paid:
            self.exported_sepa = True
        if not self.need_action_repr:
            self.imported_need_action = False
            upload_id = self.sudo().env['robo.upload'].search(
                [('res_model', '=', 'account.invoice'), ('res_id', '=', self.id), ('state', '=', 'need_action')])
            if not upload_id and self.hr_expense_id:
                upload_id = self.sudo().env['robo.upload'].search(
                    [('res_model', '=', 'hr.expense'), ('res_id', '=', self.hr_expense_id.id),
                     ('state', '=', 'need_action')])
            if upload_id:
                upload_id.write({'state': 'done'})
            if not self.move_name:
                self.write({
                    'registration_date': datetime.now(),
                })
            if self.type in ['in_invoice'] and not self.env.user.is_accountant() and any(
                    l.asset_category_id for l in self.sudo().invoice_line_ids):
                self.message_post('Setting as paid by company funds')
                self.sudo().action_invoice_open()
            elif self.env.user == self.user_id or self.env.user == self.sudo().submitted_employee_id.user_id:
                self.message_post('Setting as paid by company funds')
                self.sudo().action_invoice_open()
            else:
                self.action_invoice_open()
            self.set_representation_fields()
            return True

    @api.multi
    def app_inv_own_select(self):
        wizard_obj = self.env['ap.employee.select.wizard']
        vals = {
            'invoice_id': self.id,
            'ap_employee_id': self.env.user.employee_ids[0].id if self.env.user.employee_ids else False
        }
        wiz_id = wizard_obj.create(vals).id
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'ap.employee.select.wizard',
            'res_id': wiz_id,
            'view_id': self.env.ref('robo.ap_employee_select_wizard').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.multi
    def app_inv_own(self):
        self.ensure_one()
        self.payment_mode = 'own_account'
        self.need_action_info = False
        if not self.need_action_repr:
            self.imported_need_action = False
            upload_id = self.sudo().env['robo.upload'].search(
                [('res_model', '=', 'account.invoice'), ('res_id', '=', self.id), ('state', '=', 'need_action')])
            if not upload_id and self.hr_expense_id:
                upload_id = self.sudo().env['robo.upload'].search(
                    [('res_model', '=', 'hr.expense'), ('res_id', '=', self.hr_expense_id.id),
                     ('state', '=', 'need_action')])
            if upload_id:
                upload_id.write({'state': 'done'})
            if not self.move_name:
                self.write({
                    'registration_date': datetime.now(),
                })
            if self.type in ['in_invoice'] and not self.env.user.is_accountant() and any(
                    l.asset_category_id for l in self.sudo().invoice_line_ids):
                self.sudo().action_invoice_open()
            elif self.env.user == self.user_id or self.env.user == self.sudo().submitted_employee_id.user_id:
                self.sudo().action_invoice_open()
            else:
                # If current user is simple employee and process is done on other employee user --
                # force use sudo, too much system places where partner ID access is blocked.
                # TODO: Even though the traceability is kept (several messages are posted w/o sudo),
                # TODO: discuss for a better alternative - this is more of a quick fix
                user = self.env.user
                can_manage_partners = user.is_manager() or user.is_hr_manager() or user.has_group(
                    'robo_basic.group_robo_manage_all_partners')
                if user.employee_ids and user.employee_ids[0] != self.ap_employee_id and not can_manage_partners:
                    self = self.sudo()
                self.action_invoice_open()
            self.set_representation_fields()
            return True

    @api.multi
    def action_invoice_sent(self):
        """ Open a window to compose an email, with the edi invoice template
            message loaded by default
        """
        self.ensure_one()
        language = self.partner_lang or 'lt_LT'
        template = self.with_context(lang=language).get_account_invoice_mail_template()
        compose_form = self.env.ref('mail.email_compose_message_wizard_form', False)
        ctx = dict(
            default_model='account.invoice',
            default_res_id=self.id,
            default_use_template=bool(template),
            default_template_id=template.id,
            default_composition_mode='comment',
            mark_invoice_as_sent=True,
            custom_layout="account.mail_template_data_notification_email_account_invoice",
            force_send_message=True,
            front_message=True,
        )
        if self._context.get('uid'):
            ctx['uid'] = self._context.get('uid')
        if self._context.get('force_email_sender_mail', False):
            ctx['force_email_sender_mail'] = self._context.get('force_email_sender_mail')
        if self._context.get('force_email_sender_name', False):
            ctx['force_email_sender_name'] = self._context.get('force_email_sender_name')
        res_id = self.env['mail.compose.message'].with_context(ctx).create({})
        res_id.onchange_template_id_wrapper()
        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'res_id': res_id.id,
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form.id, 'form')],
            'view_id': compose_form.id,
            'target': 'new',
            'context': ctx,
        }

    @api.multi
    def action_invoice_change_number(self):
        self.ensure_one()
        ctx = dict(self._context)
        ctx['active_id'] = self.id
        action = self.env.ref('robo.change_invoice_number_wizard').read()[0]
        action['context'] = ctx
        return action

    @api.multi
    def action_invoice_open_type_change_wizard(self):
        self.ensure_one()
        if not self.env.user.is_accountant():
            raise exceptions.UserError(_('Tik buhalteriai gali atlikti šią operaciją'))
        ctx = dict(self._context)
        ctx['active_id'] = self.id
        action = self.env.ref('robo.account_invoice_type_change_wizard').read()[0]
        action['context'] = ctx
        return action

    @api.multi
    def action_invoice_cancel(self):
        for rec in self:
            if rec.imported:
                raise exceptions.UserError(_('Importuotos sąskaitos atšaukti negalima. '
                                             'Jei importavote neteisingas reikšmes, spauskite ištrinti šią sąskaitą ir '
                                             'importuokite iš naujo.'))
        for rec in self:
            if rec.global_state != 'awaiting_consensus':
                rec.global_state = 'settled_draft'
        rec_proforma = self.filtered(lambda inv: inv.state in ['proforma'])
        self.set_need_action_fields(cancel=True)
        if rec_proforma:
            rec_not_proforma = self.filtered(lambda inv: inv.state not in ['proforma'])
            res = rec_proforma.action_cancel()
            res_another = True
            if rec_not_proforma:
                res_another = super(AccountInvoice, rec_not_proforma).action_invoice_cancel()
            return res and res_another

        # Deletes private consumption moves for the invoices
        self.unlink_private_consumption_move()
        return super(AccountInvoice, self.with_context(ensure_analytic_batch_integrity=True)).action_invoice_cancel()

    @api.one
    @api.depends('name', 'company_id', 'date_invoice')
    def _show_vat(self):
        self.show_vat = self.company_id.sudo().with_context({'date': self.get_vat_payer_date()}).vat_payer

    @api.onchange('my_company_vat')
    def set_reset_tax_line_ids(self):
        if self.env.context.get('creation_from_purchase_order'):
            return
        for line in self.invoice_line_ids:
            line._set_taxes()

    @api.multi
    def cancel_invoice_created_from_cheque_with_action(self):
        self.cancel_invoice_created_from_cheque()

        action = self.env.ref('robo.new_cheque_action')
        cekis = self.hr_expense_id
        if cekis:
            vals = action.read()[0]
            vals['res_id'] = cekis.id
            # special function to move attactments from invoice to cheque
            self.env['hr.expense'].move_attachments(new_src=cekis, old_src=self, old_model='account.invoice',
                                                    new_model='hr.expense', err_msg=_('Nepavyko atšaukti sąskaitos.'))
            return vals

    @api.multi
    def cancel_invoice_created_from_cheque(self):
        self.ensure_one()
        for move_line in self.payment_move_line_ids:
            move_line.delete_move_reconcile()
        self.action_invoice_cancel()
        self.action_invoice_draft()

    @api.multi
    def action_invoice_order(self):
        self.ensure_one()
        view_id = self.env.ref('robo.account_payment_form').id
        context = dict(self._context)
        context['default_payment_type'] = 'inbound' if self.type in ['out_invoice', 'in_refund'] else 'outbound'
        context['default_partner_type'] = 'customer' if self.type in ['out_invoice', 'in_refund'] else 'supplier'
        context['default_partner_id'] = self.partner_id.id
        context['default_cashier_id'] = self.env.user.employee_ids and self.env.user.employee_ids[0].id or False
        context['default_amount'] = abs(self.residual)
        context['default_currency_id'] = self.currency_id.id
        context['default_communication'] = self.reference or self.number
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_type': 'form',
            'view_mode': 'form',
            'views': [(view_id, 'form')],
            'target': 'current',
            'context': context,
        }

    @api.depends('number', 'move_name', 'state')
    def _get_invoice_number(self):
        for rec in self:
            if rec.state in ['proforma', 'proforma2']:
                rec.computed_number = rec.sudo().proforma_number or rec.sudo().id
            elif rec.number:
                rec.computed_number = rec.sudo().number
            elif rec.move_name:
                rec.computed_number = rec.sudo().move_name
            else:
                rec.computed_number = False

    @api.one
    @api.depends('payment_move_line_ids.amount_residual')
    def _get_payment_info_JSON(self):
        self.payments_widget = json.dumps(False)
        if self.sudo().payment_move_line_ids:
            info = {'title': _('Less Payment'), 'outstanding': False, 'content': []}
            currency_id = self.currency_id
            for payment in self.sudo().payment_move_line_ids[:30]:
                payment_currency_id = False
                amount_currency = 0
                amount = 0
                if self.type in ('out_invoice', 'in_refund'):
                    amount = sum(p.amount for p in payment.matched_debit_ids
                                 if p.debit_move_id in self.sudo().move_id.line_ids)
                    amount_currency = sum(p.amount_currency for p in payment.matched_debit_ids
                                          if p.debit_move_id in self.sudo().move_id.line_ids)
                    if payment.matched_debit_ids:
                        payment_currency_id = all(p.currency_id == payment.matched_debit_ids[0].currency_id for p in
                                                  payment.matched_debit_ids) and payment.matched_debit_ids[
                                                  0].currency_id or False
                elif self.type in ('in_invoice', 'out_refund'):
                    amount = sum(
                        [p.amount for p in payment.matched_credit_ids if
                         p.credit_move_id in self.sudo().move_id.line_ids])
                    amount_currency = sum(p.amount_currency for p in payment.matched_credit_ids
                                          if p.credit_move_id in self.sudo().move_id.line_ids)
                    if payment.matched_credit_ids:
                        payment_currency_id = all(p.currency_id == payment.matched_credit_ids[0].currency_id for p in
                                                  payment.matched_credit_ids) and payment.matched_credit_ids[
                                                  0].currency_id or False
                # get the payment value in invoice currency
                if payment_currency_id and payment_currency_id == self.currency_id:
                    amount_to_show = amount_currency
                else:
                    amount_to_show = payment.company_id.currency_id.with_context(date=payment.date).compute(amount,
                                                                                                            self.currency_id)
                if tools.float_is_zero(amount_to_show, precision_rounding=self.currency_id.rounding):
                    continue
                payment_ref = payment.move_id.name
                if payment.create_uid.is_accountant() and not self.env.user.is_accountant():
                    show = False
                else:
                    show = True
                if payment.move_id.ref:
                    payment_ref += ' (' + payment.move_id.ref + ')'
                info['content'].append({
                    'name': payment.name,
                    'journal_name': payment.journal_id.name,
                    'amount': amount_to_show,
                    'currency': currency_id.symbol,
                    'digits': [69, currency_id.decimal_places],
                    'position': currency_id.position,
                    'date': payment.date,
                    'payment_id': payment.id,
                    'move_id': payment.move_id.id,
                    'ref': payment_ref,
                    'show': show,
                    'offsetting_front_move': payment.move_id.offsetting_front_move,
                    'accountant': self.env.user.is_accountant()
                })
            self.payments_widget = json.dumps(info)

    @api.model
    def _needaction_domain_get(self):
        if self.env.ref('robo_basic.group_robo_premium_accountant').id in self.env.user.groups_id.ids:
            return ['|', ('expense_state', '=', 'awaiting'), '&', ('expense_state', '=', 'imported'), '|',
                    ('submitted_employee_id.user_id', '=', self.env.user.id),
                    ('user_id', '=', self.env.user.id)]
        elif self.env.user.company_id.vadovas.user_id.id == self.env.user.id or \
                self.env.user.has_group('robo.group_robo_need_action'):
            return [('expense_state', '=', 'imported')]
        else:
            return [('expense_state', '=', 'imported'), '|', ('submitted_employee_id.user_id', '=', self.env.user.id),
                    ('user_id', '=', self.env.user.id)]
        # return [('need_action', '=', True)]

    @api.model
    def open_expense_badge_action(self):
        """
        Returns expense tree action with modified domain
        based on need-action settings, and current users
        configuration
        :return: JS action (dict)
        """
        action = self.env.ref('robo.robo_expenses_action').read()[0]
        domain = self._needaction_domain_get()
        action['domain'] = domain + [('type', 'in', ['in_invoice', 'in_refund'])]
        return action

    # computes *****************************

    @api.one
    @api.depends('attachment', 'mime_attachment', 'name_attachment', 'hr_expense_id.attachment',
                 'hr_expense_id.name_attachment', 'hr_expense_id.mime_attachment')
    def _app_attachment(self):
        if self.attachment:
            self.app_attachment = self.attachment
            self.app_mime_attachment = self.mime_attachment
            self.app_name_attachment = self.name_attachment or 'cekis.jpg'
        elif self.hr_expense_id and self.hr_expense_id.attachment:
            self.app_attachment = self.hr_expense_id.attachment
            self.app_name_attachment = self.hr_expense_id.name_attachment or 'cekis.jpg'
            self.app_mime_attachment = self.hr_expense_id.mime_attachment

    @api.one
    @api.depends('hr_expense_id.attachment', 'hr_expense_id.mime_attachment', 'hr_expense_id.name_attachment')
    def _find_attachment(self):
        if not self.attachment and self.hr_expense_id and self.hr_expense_id.attachment:
            self.computed_attachment = self.hr_expense_id.attachment
            if self.hr_expense_id.mime_attachment:
                self.computed_mime_attachment = self.hr_expense_id.mime_attachment
            if self.hr_expense_id.name_attachment:
                self.computed_name_attachment = self.hr_expense_id.name_attachment

    @api.depends('expense_move_id.line_ids.reconciled', 'expense_move_id.line_ids.amount_residual')
    def _compute_cash_advance_repaid(self):
        for rec in self:
            rec.is_cash_advance_repaid = False
            rec.cash_advance_left_to_repay = 0
            cash_advance_account_id = rec.company_id.cash_advance_account_id.id
            if rec.expense_move_id:
                rec.is_cash_advance_repaid = all(
                    rec.expense_move_id.line_ids.filtered(lambda r: r.account_id.id == cash_advance_account_id).mapped(
                        'reconciled'))
            if not rec.is_cash_advance_repaid:
                rec.cash_advance_left_to_repay = sum(
                    rec.expense_move_id.line_ids.filtered(lambda r: r.account_id.id == cash_advance_account_id).mapped(
                        'amount_residual'))

    @api.one
    @api.depends('state', 'hr_expense_id.state', 'imported_need_action', 'global_state', 'action_shift')
    def _expense_status(self):
        if self.hr_expense_id.state == 'imported':
            self.expense_state = 'imported'
            self.need_action = True
        elif self.state != 'draft':
            self.need_action = False
            self.expense_state = self.state
        else:
            if self.imported_need_action and self.action_shift == 'ceo':
                self.need_action = True
                self.expense_state = 'imported'
            elif self.imported_need_action and self.action_shift == 'accountant':
                self.expense_state = 'awaiting'
                self.need_action = True
            elif self.global_state == 'settled_draft':
                self.expense_state = 'draft'
                self.need_action = False
            elif self.global_state == 'settled_open':
                self.expense_state = 'open'
                self.need_action = False
            else:
                self.expense_state = 'draft'

    @api.depends('payment_mode', 'type')
    def _compute_advance_payment(self):
        for rec in self:
            rec.advance_payment = rec.type in ['in_invoice', 'in_refund'] and rec.payment_mode == 'own_account'

    @api.onchange('date_due')
    def onchange_date_due_payment_term(self):
        if self.payment_term_id and self._context.get('robo', False):
            pterm = self.payment_term_id
            date_ref = self.operacijos_data or self.date_invoice or datetime.utcnow().strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT)
            pterm_list = pterm.with_context(currency_id=self.currency_id.id).compute(value=1, date_ref=date_ref)[0]
            date_due = max(line[0] for line in pterm_list)
            if date_due != self.date_due:
                self.payment_term_id = False

    @api.one
    @api.depends('my_company_vat', 'partner_vat', 'state', 'number', 'type')
    def _document_name(self):
        doc_type = self.type or (self._context and self._context['default_type'])
        document_name = self.invoice_header or _('Sąskaita faktūra')
        if not self.invoice_header and doc_type:
            if 'refund' in doc_type:
                document_name = _('Kreditinė sąskaita faktūra')

            if 'out' in doc_type and self.my_company_vat:
                if 'refund' in doc_type:
                    if not self.my_company_vat.strip():
                        document_name = _('Kreditinė sąskaita faktūra')
                    else:
                        document_name = _('Kreditinė PVM sąskaita faktūra')
                else:
                    if not self.my_company_vat.strip():
                        document_name = _('Sąskaita faktūra')
                    else:
                        document_name = _('PVM sąskaita faktūra')
            elif 'in_' in doc_type and self.partner_vat:
                if 'refund' in doc_type:
                    if not self.partner_vat.strip():
                        document_name = _('Kreditinė sąskaita faktūra')
                    else:
                        document_name = _('Kreditinė PVM sąskaita faktūra')
                else:
                    if not self.partner_vat.strip():
                        document_name = _('Sąskaita faktūra')
                    else:
                        document_name = _('PVM sąskaita faktūra')

        if self.number or self.move_name:
            document_name += ' ' + self.number if self.number else ' ' + self.move_name
        if self.state in ['proforma', 'proforma2']:
            document_name = _('Išankstinė ') + document_name
            document_name = document_name.replace(' PVM', '').replace(' faktūra', '')
            if self.proforma_number:
                document_name += ' ' + self.proforma_number
        self.document_name = document_name

    @api.onchange('date_invoice')
    def onchange_date_invoice(self):
        if self.date_invoice and not self.date_due:
            self.date_due = self.date_invoice
        elif self.date_invoice and self.payment_term_id:
            self._onchange_payment_term_date_invoice()

    @api.onchange('company_id', 'date_invoice')
    def _my_company_data(self):
        company = self.company_id
        journal_id = False

        self.my_company_name = False
        self.my_company_street = False
        self.my_company_zip = False
        self.my_company_city = False
        self.my_company_country_id = False
        self.my_company_phone = False
        self.my_company_email = False
        self.my_company_vat = False
        self.my_company_kodas = False
        self.my_company_bank_name = False
        self.my_company_bank_BIC = False
        self.my_company_bank_account = False

        if company:
            if company.name:
                self.my_company_name = company.name
            if company.street:
                self.my_company_street = company.street
            if company.zip:
                self.my_company_zip = company.zip
            if company.city:
                self.my_company_city = company.city
            if company.country_id:
                self.my_company_country_id = company.country_id
            if company.phone:
                self.my_company_phone = company.phone
            if company.email:
                self.my_company_email = company.email
            if company.with_context({'date': self.get_vat_payer_date()}).vat_payer:
                self.my_company_vat = company.vat
            if company.partner_id and company.partner_id.kodas:
                self.my_company_kodas = company.partner_id.kodas
                # Since we have limit=1 we also check that bank_id is not empty,
                # Because all of the displays are done if the bank is there anyway
                journal_id = self.sudo().env['account.journal'].search(
                    [('type', '=', 'bank'), ('display_on_footer', '=', True), ('bank_id', '!=', False)], limit=1)
            if journal_id:
                bank_id = journal_id.bank_id
                if bank_id.name:
                    self.my_company_bank_name = bank_id.name
                if bank_id.bic:
                    self.my_company_bank_BIC = bank_id.bic
                if journal_id.bank_acc_number:
                    self.my_company_bank_account = journal_id.bank_acc_number

    @api.one
    def _set_company_id(self):
        company = self.company_id
        vals = {}
        if company:
            if company.name:
                vals['my_company_name'] = company.name
            if company.street:
                vals['my_company_street'] = company.street
            if company.zip:
                vals['my_company_zip'] = company.zip
            if company.city:
                vals['my_company_city'] = company.city
            if company.country_id:
                vals['my_company_country_id'] = company.country_id.id
            if company.phone:
                vals['my_company_phone'] = company.phone
            if company.email:
                vals['my_company_email'] = company.email
            if company.with_context({'date': self.get_vat_payer_date()}).vat_payer:
                vals['my_company_vat'] = company.vat
            if company.partner_id and company.partner_id.kodas:
                vals['my_company_kodas'] = company.partner_id.kodas
            journal_id = self.sudo().env['account.journal'].search(
                [('type', '=', 'bank'), ('display_on_footer', '=', True)], limit=1)
            if journal_id:
                bank_id = journal_id.bank_id
                if bank_id.name:
                    vals['my_company_bank_name'] = bank_id.name
                if bank_id.bic:
                    vals['my_company_bank_BIC'] = bank_id.bic
                if journal_id.bank_acc_number:
                    vals['my_company_bank_account'] = journal_id.bank_acc_number
            self.write(vals)

    @api.onchange('partner_id')
    def _partner_data(self):
        partner = self.partner_id

        self.partner_vat = False
        self.partner_kodas = False
        self.partner_company_type = False
        self.partner_parent_id = False
        self.partner_street = False
        self.partner_zip = False
        self.partner_city = False
        self.partner_country_id = False
        self.partner_phone = False
        self.partner_email = False

        if partner:
            if partner.vat:
                self.partner_vat = partner.vat
            if partner.kodas:
                self.partner_kodas = partner.kodas
            if partner.company_type:
                self.partner_company_type = partner.company_type
            if partner.parent_id:
                self.partner_parent_id = partner.parent_id.id
            if partner.street:
                self.partner_street = partner.street
            if partner.zip:
                self.partner_zip = partner.zip
            if partner.city:
                self.partner_city = partner.city
            if partner.country_id:
                self.partner_country_id = partner.country_id.id
            if partner.phone:
                self.partner_phone = partner.phone
            if partner.email:
                self.partner_email = partner.email
            if partner.lang:
                self.partner_lang = partner.lang

    @api.multi
    def partner_data_force(self):
        self.ensure_one()
        partner = self.partner_id
        vals = {}
        if partner:
            if partner.vat:
                vals['partner_vat'] = partner.vat
            if partner.kodas:
                vals['partner_kodas'] = partner.kodas
            if partner.company_type:
                vals['partner_company_type'] = partner.company_type
            if partner.parent_id:
                vals['partner_parent_id'] = partner.parent_id.id
            if partner.street:
                vals['partner_street'] = partner.street
            if partner.zip:
                vals['partner_zip'] = partner.zip
            if partner.city:
                vals['partner_city'] = partner.city
            if partner.country_id:
                vals['partner_country_id'] = partner.country_id.id
            if partner.phone:
                vals['partner_phone'] = partner.phone
            if partner.email:
                vals['partner_email'] = partner.email
        company = self.company_id
        if company:
            if company.name:
                vals['my_company_name'] = company.name
            if company.street:
                vals['my_company_street'] = company.street
            if company.zip:
                vals['my_company_zip'] = company.zip
            if company.city:
                vals['my_company_city'] = company.city
            if company.country_id:
                vals['my_company_country_id'] = company.country_id.id
            if company.phone:
                vals['my_company_phone'] = company.phone
            if company.email:
                vals['my_company_email'] = company.email
            if company.vat:
                vals['my_company_vat'] = company.vat
            if company.partner_id and company.partner_id.kodas:
                vals['my_company_kodas'] = company.partner_id.kodas
            journal_id = self.sudo().env['account.journal'].search(
                [('type', '=', 'bank'), ('display_on_footer', '=', True)], limit=1)
            if journal_id:
                bank_id = journal_id.bank_id
                if bank_id.name:
                    vals['my_company_bank_name'] = bank_id.name
                if bank_id.bic:
                    vals['my_company_bank_BIC'] = bank_id.bic
                if journal_id.bank_acc_number:
                    vals['my_company_bank_account'] = journal_id.bank_acc_number
        self.write(vals)

    @api.constrains('type')
    def _check_type(self):
        user_can_see_income = self.env.user.has_group('robo_basic.group_robo_see_income')
        for rec in self:
            if not user_can_see_income and rec.type and rec.type not in ['in_invoice', 'in_refund']:
                raise exceptions.ValidationError(_('Neturite teisių kurti sąskaitas faktūras.'))

    @api.model
    def create(self, vals):
        if 'partner_country_id' not in vals:
            partner_id = vals.get('partner_id', False)
            country_id = self.env['res.partner'].browse(partner_id).country_id.id
            if country_id:
                vals['partner_country_id'] = country_id
        invoice = super(AccountInvoice, self).create(vals)
        invoice._show_representation_action()
        wizard_id = vals.pop('unique_wizard_id', False)
        if wizard_id and invoice and not invoice.hr_expense_id:
            wizards_records = self.env['ir.attachment.wizard'].search(
                [('res_model', '=', 'account.invoice'), ('wizard_id', '=', wizard_id)])
            if wizards_records:
                for rec in wizards_records:
                    new_vals = {
                        'name': rec['name'],
                        'datas': rec['datas'],
                        'datas_fname': rec['datas_fname'],
                        'res_model': 'account.invoice',
                        'res_id': invoice.id,
                        'type': rec['type'],
                        # sometimes type by default (if not provided) is taken from invoice (='in_invoice')
                    }
                    self.env['ir.attachment'].create(new_vals)
                # invoice.renew_user_attachments_ids = True
        return invoice

    @api.multi
    def copy(self, default=None):
        self.ensure_one()
        if self.with_cheque_form:
            raise exceptions.UserError(_('Negalima dublikuoti sąskaitos faktūros sugeneruotos iš čekio.'))
        elif self.expense_state == 'imported':
            raise exceptions.UserError(_('Negalima dublikuoti sąskaitos faktūros susietos dokumentu.'))
        new = super(AccountInvoice, self).copy(default=default)
        new.partner_data_force()
        new._onchange_payment_term_date_invoice()
        return new

    @api.one
    def _set_partner_data_vat(self):
        if self.partner_vat and self.partner_vat != self.sudo().partner_id.vat:
            self.sudo().partner_id.vat = self.partner_vat

    @api.one
    def _set_partner_data_kodas(self):
        if self.partner_kodas and self.partner_kodas != self.sudo().partner_id.kodas:
            self.sudo().partner_id.kodas = self.partner_kodas

    @api.one
    def _set_partner_data_street(self):
        if self.partner_street and self.partner_street != self.sudo().partner_id.street:
            self.sudo().partner_id.street = self.partner_street

    @api.one
    def _set_partner_data_zip(self):
        if self.partner_zip and self.partner_zip != self.sudo().partner_id.zip:
            self.sudo().partner_id.zip = self.partner_zip

    @api.one
    def _set_partner_data_city(self):
        if self.partner_city and self.partner_city != self.sudo().partner_id.city:
            self.sudo().partner_id.city = self.partner_city

    @api.one
    def _set_partner_data_country_id(self):
        if self.partner_country_id and self.partner_country_id != self.sudo().partner_id.country_id:
            self.sudo().partner_id.country_id = self.partner_country_id
        # todo: think whether force recalculation is needed
        # for line in self.invoice_line_ids:
        #     line._set_taxes()

    @api.one
    def _set_partner_data_phone(self):
        if self.partner_phone and self.partner_phone != self.sudo().partner_id.phone:
            self.sudo().partner_id.phone = self.partner_phone

    @api.one
    def _set_partner_data_email(self):
        if self.partner_email and self.partner_email != self.sudo().partner_id.email:
            self.sudo().partner_id.email = self.partner_email

    @api.one
    def _set_partner_data_category_id(self):
        if self.partner_category_id and self.partner_category_id != self.sudo().partner_id.category_id:
            self.sudo().partner_id.category_id = self.partner_category_id

    @api.one
    def _set_partner_data_fax(self):
        if self.partner_fax and self.partner_fax != self.sudo().partner_id.fax:
            self.sudo().partner_id.fax = self.partner_fax

    @api.one
    def _set_partner_data_mobile(self):
        if self.partner_mobile and self.partner_mobile != self.sudo().partner_id.mobile:
            self.sudo().partner_id.mobile = self.partner_mobile

    @api.one
    def _set_partner_data_website(self):
        if self.partner_website and self.partner_website != self.sudo().partner_id.website:
            self.sudo().partner_id.website = self.partner_website

    @api.one
    def _set_partner_data_type(self):
        is_company = self.partner_company_type == 'company'
        if self.partner_company_type and is_company != self.sudo().partner_id.is_company:
            # self.sudo().partner_id.company_type = self.partner_company_type
            self.sudo().partner_id.is_company = is_company

    # **************************************
    # default form to open from another form

    @api.multi
    def get_formview_id(self):
        """ Return an view id to open the document ``self`` with. This method is
            meant to be overridden in addons that want to give specific view ids
            for example.
        """
        view_ref = self._context.get('form_view_ref', False)
        if view_ref:
            view_id = self.env.ref(view_ref, raise_if_not_found=False)
            if not view_id:
                view_id = self.env.ref(self._module + '.' + view_ref, raise_if_not_found=False)
            if view_id:
                return view_id.id
        if self.type in ['in_invoice', 'in_refund']:
            view_id = self.env.ref('robo.robo_expenses_form').id
        else:
            view_id = self.env.ref('robo.pajamos_form').id
        return view_id

    @api.multi
    def get_formview_action(self):
        """ Return an action to open the document ``self``. This method is meant
            to be overridden in addons that want to give specific view ids for
            example.
        """
        view_id = self.get_formview_id()
        view_type = 'form'  # self._context.get('form_view_type', 'form')
        view_mode = self._context.get('form_view_mode', 'form')

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_type': view_type,
            'view_mode': view_mode,
            'views': [(view_id, view_type)],
            'target': 'current',
            'res_id': self.id,
            'context': dict(self._context),
        }

    @api.multi
    def representation_check(self):
        self.ensure_one()
        if any(x.product_id.default_code in ['R25', 'R75'] for x in self.invoice_line_ids) and \
                not self.env.user.is_accountant():
            self.write({
                'imported_need_action': True,
                'need_action_repr': True
            })
        else:
            self.action_invoice_open()

    @api.multi
    def check_taxes(self):
        for rec in self:
            if rec.type in ['in_invoice', 'in_refund']:
                type_tax_use = 'purchase'
            else:
                type_tax_use = 'sale'
            for line in rec.invoice_line_ids:
                if not all(x.type_tax_use == type_tax_use for x in line.invoice_line_tax_ids):
                    new_tax_lines = self.env['account.tax']
                    for tax_line in line.invoice_line_tax_ids:
                        if tax_line.type_tax_use != type_tax_use:
                            reverse_tax = self.env['account.tax'].search([
                                ('price_include', '=', tax_line.price_include),
                                ('code', '=', tax_line.code),
                                ('type_tax_use', '=', type_tax_use),
                                ('nondeductible', '=', False),
                                ('nondeductible_profit', '=', False),
                            ])
                            if len(reverse_tax) != 1:
                                raise exceptions.Warning(
                                    _('Patikrinkite sąskaitos mokesčius, rasta eilučiu su klaidingu PVM!'))
                            else:
                                new_tax_lines += reverse_tax
                        else:
                            new_tax_lines += tax_line
                    line.invoice_line_tax_ids = [(6, 0, new_tax_lines.ids)]

    @api.multi
    def _check_invoice_open_constraints(self):
        company = self.env.user.sudo().company_id
        for rec in self:
            if rec.show_representation_action:
                raise exceptions.ValidationError(_(
                    "Sąskaita turi reprezentacinių produktų, išsaugokite sąskaitą spustelkite naujai atsiradusį mygtuką 'Pateikti vadovui'"))
            if (rec.with_cheque_picture or (rec.type in ['in_invoice', 'in_refund'])) and (
                    rec.nbr_of_attachments == 0 and (
                    not rec.hr_expense_id or rec.hr_expense_id.nbr_of_attachments == 0)) and not self._context.get(
                    'skip_attachments', False):
                raise exceptions.ValidationError(_('Prisekite bent vieną dokumentą!'))
            if company.with_context({'date': rec.get_vat_payer_date()}).vat_payer:
                if not all(line.invoice_line_tax_ids for line in rec.invoice_line_ids):
                    raise exceptions.UserError(_('Prieš patvirtindami sąskaitą privalote nurodyti taikomus mokesčius.'))

    @api.multi
    def action_invoice_proforma2(self):
        self.mapped('invoice_line_ids').apply_default_analytics()
        return super(AccountInvoice, self).action_invoice_proforma2()

    @api.multi
    def action_invoice_open(self):
        self.check_taxes()
        # Apply analytics to invoice lines
        self.mapped('invoice_line_ids').apply_default_analytics()
        self._check_invoice_open_constraints()
        for rec in self.filtered(lambda r: r.type == 'out_invoice' and r.state in ['proforma', 'proforma2']):
            rec.date_invoice = datetime.utcnow()
            rec.onchange_date_invoice()
            if rec.date_due < rec.date_invoice:
                rec.date_due = rec.date_invoice
        self.set_need_action_fields()
        # ROBO: should be possible only for accountant?
        self.write({'imported_need_action': False})

        res = super(AccountInvoice, self).action_invoice_open()

        #TODO: when  robo dependency on l10n_lt is removed, move this loop to module that depends on both robo and l10n_lt
        for inv in self:
            upload_id = self.sudo().env['robo.upload']
            if inv.hr_expense_id:
                upload_id = self.sudo().env['robo.upload'].search([('res_model', '=', 'hr.expense'),
                                                                   ('res_id', '=', inv.hr_expense_id.id),
                                                                   ('state', '=', 'need_action')])
            upload_id |= self.sudo().env['robo.upload'].search([('res_model', '=', 'account.invoice'),
                                                                ('res_id', '=', inv.id),
                                                                ('state', '=', 'need_action')])
            if upload_id:
                upload_id.write({'state': 'done'})

        # Creates private consumption moves for the invoices
        self.create_private_consumption_move()
        return res

    @api.multi
    def unlink(self):
        allow = self.env.user.is_manager()
        for invoice in self:
            if invoice.imported and allow:
                invoice.move_id.write({'state': 'draft'})
                invoice.write({'state': 'draft', 'imported': False, 'move_name': False})
                invoice.action_invoice_cancel()
            if invoice.state not in ('draft', 'cancel'):
                raise exceptions.UserError(_('Negalite ištrinti patvirtintos sąskaitos.'))
            # elif invoice.expense_state in ('imported'):
            #     raise exceptions.UserError(_('Negalite ištrinti sąskaitos su statusu importuota.'))
            elif invoice.move_name:
                raise exceptions.UserError(_(
                    'Negalite ištrinti sąskaitos, kuriai jau buvo suteiktas unikalus numeris. '
                    'Galite grąžinti į juodraščio būseną, redaguoti ir iš naujo patvirtinti.'))
        robo_upload_data = [{'res_id': invoice.id, 'hr_expense_id': invoice.hr_expense_id.id} for invoice in self]
        res = super(AccountInvoice, self).unlink()
        for robo_upload in robo_upload_data:
            upload_id = self.sudo().env['robo.upload'].search(
                [('res_model', '=', 'account.invoice'), ('res_id', '=', robo_upload.get('res_id'))])
            if not upload_id and robo_upload.get('hr_expense_id'):
                upload_id = self.sudo().env['robo.upload'].search(
                    [('res_model', '=', 'hr.expense'), ('res_id', '=', robo_upload.get('hr_expense_id'))])
            if upload_id:
                upload_id.write({'active': False})
        return res

    @api.multi
    def download_sepa(self):
        return self.with_context(download=True).call_multiple_invoice_export_wizard()

    @api.model
    def create_acc_invoice_SEPA_download_action(self):
        action = self.env.ref('robo.invoice_bank_SEPA_download_action')
        if action:
            action.create_action()

    @api.model
    def create_action_export_refund_invoices_to_bank(self):
        """Create the action for refund invoices that allows to export them to bank"""
        action = self.env.ref('robo.action_export_refund_invoices_to_bank')
        if action:
            action.create_action()

    @api.model
    def create_multi_invoice_print_action(self):
        action = self.env.ref('robo.multi_invoice_print_action')
        if action:
            action.create_action()

    @api.model
    def create_action_invoice_financial_account_change_wizard(self):
        action = self.env.ref('robo.action_invoice_financial_account_change_wizard')
        if action:
            action.create_action()

    @api.model
    def message_get_reply_to(self, res_ids, default=None):
        invoices = self.browse(res_ids)
        return dict((invoice.id, self.env.user.email or default) for invoice in invoices)

    @api.multi
    @job
    def action_invoice_cancel_draft(self):
        self.action_invoice_cancel()
        self.action_invoice_draft()

    @api.multi
    @job
    def action_invoice_cancel_unlink(self, unlink_payments=False):
        if unlink_payments:
            res = self.action_invoice_cancel_draft_and_remove_outstanding()

            payments = res.get('payment_lines').mapped('move_id')
            payments |= res.get('expense_payment_lines').mapped('move_id')
            payments |= res.get('gpm_payment_lines').mapped('move_id')

            # Unlink only those related payment moves which do not contain any reconciled lines
            for payment in payments.filtered(lambda pmt: all(not x.reconciled and x.account_id.reconcile
                                                             for x in pmt.line_ids)):
                payment.button_cancel()
                payment.unlink()
        else:
            self.action_invoice_cancel_draft()
        self.write({
            'move_name': False,
            'number': False,
            'reference': False,
        })
        self.unlink()

    @api.multi
    def ask_payment(self):
        self.ensure_one()
        if self.env.user.is_accountant() and self.expense_state == 'open':
            self.action_invoice_cancel()
            self.action_invoice_draft()
            self.imported_need_action = True
            self.need_action_info = True
            if self.hr_expense_id:
                self.hr_expense_id.state = 'imported'
        elif self.env.user.is_accountant() and self.expense_state not in ['open', 'paid']:
            self.imported_need_action = True
            self.need_action_info = True

    @api.multi
    def ask_representation(self):
        self.ensure_one()
        if self.env.user.is_accountant():
            if self.expense_state == 'paid':
                raise exceptions.ValidationError(
                    _('Negalite klausti reprezentacinių išlaidų klausimo jei sąskaita jau apmokėta'))
            if self.expense_state == 'cancel':
                raise exceptions.ValidationError(
                    _('Negalite klausti reprezentacinių išlaidų klausimo jei sąskaita yra atšaukta. '
                      'Atstatykite sąskaitą į juodraštį.'))
            if self.expense_state == 'open':
                self.action_invoice_cancel()
                self.action_invoice_draft()
                if self.hr_expense_id:
                    self.hr_expense_id.state = 'imported'

            # Reset the fields that are needed for representation confirmation
            self.write({
                'accountant_validated': False,
                'imported_need_action': True,
                'need_action_repr': True,
            })
            self.set_representation_fields(global_state='awaiting_consensus')

    @api.multi
    def set_representation_fields(self, global_state='settled_open'):
        """
        Sets invoice representation fields to their initial states.
        global state is passed to the method.
        :param global_state: global state, must match the selection field (str)
        :return: None
        """
        self.write({
            'need_action_text_accountant': False,
            'need_action_text': False,
            'action_shift': 'ceo',
            'accountant_state': 'no_action',
            'ceo_state': 'no_action',
            'global_state': global_state
        })

    @api.multi
    def open_backend(self):
        self.ensure_one()
        if self.env.user.is_accountant():
            if self.type in ['in_invoice', 'in_refund']:
                view_id = self.env.ref('account.invoice_supplier_form').id
                force_back_menu_id = self.env.ref('account.menu_action_invoice_tree2').id
                action = self.env.ref('account.action_invoice_tree2')
            else:
                view_id = self.env.ref('account.invoice_form').id
                force_back_menu_id = self.env.ref('account.menu_action_invoice_tree1').id
                action = self.env.ref('account.action_invoice_tree1')
            return {
                'id': action.id,
                'name': _('Sąskaita'),
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'account.invoice',
                'type': 'ir.actions.act_window',
                'target': 'self',
                'view_id': view_id,
                'res_id': self.id,
                'context': {
                    'force_back_menu_id': force_back_menu_id
                }
            }

    @api.multi
    def open_frontend(self):
        self.ensure_one()
        if self.type in ['in_invoice', 'in_refund']:
            view_id = self.env.ref('robo.robo_expenses_form').id
            force_back_menu_id = self.env.ref('robo.menu_islaidos').id
            action = self.env.ref('robo.robo_expenses_action')
        else:
            view_id = self.env.ref('robo.pajamos_form').id
            force_back_menu_id = self.env.ref('robo.menu_pajamos').id
            action = self.env.ref('robo.open_client_invoice')

        return {
            'id': action.id,
            'name': _('Sąskaita'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.invoice',
            'type': 'ir.actions.act_window',
            'view_id': view_id,
            'res_id': self.id,
            'context': {
                'robo_menu_name': force_back_menu_id,
                'force_back_menu_id': force_back_menu_id,
                'robo_header': {},
                'robo_front': True
            },
            'header': action.read()[0]['header'],
        }

    @api.multi
    def assign_outstanding_credit(self, credit_aml_id):
        self.ensure_one()
        use_sudo = self.env.user.has_group('robo.group_menu_kita_analitika') or self.env.user.is_manager()
        use_sudo = use_sudo or self.type in ['out_invoice', 'out_refund'] and self.env.user.has_group('robo.group_robo_see_all_incomes')
        use_sudo = use_sudo or self.type in ['in_invoice', 'in_refund'] and self.env.user.has_group('robo.group_robo_see_all_expenses')
        if not use_sudo:
            try:
                self.check_access_rights('write')
                self.check_access_rule('write')
                use_sudo = True
            except (exceptions.UserError, exceptions.AccessError):
                pass
        if use_sudo and not self.env.user.has_group('base.group_system'):
            self.env['account.move.line'].check_global_readonly_access()
            self.message_post('Adding payment')
            return super(AccountInvoice, self.sudo()).assign_outstanding_credit(credit_aml_id=credit_aml_id)
        else:
            return super(AccountInvoice, self).assign_outstanding_credit(credit_aml_id=credit_aml_id)

    @api.multi
    def send_invoice_to_client(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            return
        user = self.env['res.users'].search([('login', '=', 'daivaras.anuzis@robolabs.lt')], limit=1)
        if not user:
            user = self.env.user
        action = self.action_invoice_sent()
        wizard_id = self.env['mail.compose.message'].sudo(user=user).with_context(action.get('context', {}),
                                                                                  lang='lt_LT').create({
            'email_from': 'hello@robolabs.lt'
        })
        wizard_id.onchange_template_id_wrapper()
        wizard_id.send_mail_action()

    @api.model
    def get_invoice_front_action(self, cat_id=None, date_str=None):
        if date_str:
            dates = date_str.split(' - ')
            if len(dates) != 2:
                raise exceptions.UserError(_('Klaidingos datos!'))
            date_from = dates[0]
            date_to = dates[1]
        else:
            raise exceptions.UserError(_('Nepaduotos datos!'))
        cat_ids = cat_id.split(',') if cat_id and ',' in cat_id else []
        cat_ids = [int(x) for x in cat_ids] if cat_ids else []
        if cat_id and cat_id not in ['DU', 'Kita', 'DEPR'] or cat_ids:
            cat_id = int(cat_id) if not cat_ids else False
            inv_domain = [('invoice_id.type', 'in', ['in_invoice', 'in_refund']),
                          ('invoice_id.state', 'in', ['open', 'paid']),
                          ('invoice_id.date_invoice', '>=', date_from),
                          ('invoice_id.date_invoice', '<=', date_to)]
            if cat_ids:
                inv_domain.append(('product_id.categ_id.ultimate_id', 'in', cat_ids))
            else:
                inv_domain.append(('product_id.categ_id.ultimate_id', '=', cat_id))
            domain = [('id', 'in', self.env['account.invoice.line'].search(inv_domain).mapped('invoice_id').ids)]
            ctx = {
                'activeBoxDomain': "[('state','!=','cancel')]",
                'default_type': "in_invoice",
                'force_order': "recently_updated DESC NULLS LAST",
                'journal_type': "purchase",
                'lang': "lt_LT",
                'limitActive': 0,
                'params': {'action': self.env.ref('robo.robo_expenses_action').id},
                'robo_create_new': self.env.ref('robo.new_supplier_invoice').id,
                'robo_menu_name': self.env.ref('robo.menu_islaidos').id,
                'robo_subtype': "expenses",
                'robo_template': "RecentInvoices",
                'search_add_custom': False,
                'type': "in_invoice",
                'robo_header': {},
            }
            return {
                'context': ctx,
                'display_name': _('Išlaidos'),
                'domain': domain,
                'name': _('Išlaidos'),
                'res_model': 'account.invoice',
                'target': 'current',
                'type': 'ir.actions.act_window',
                'header': self.env.ref('robo.robo_button_islaidos').id,
                'view_id': self.env.ref('robo.robo_expenses_tree').id,
                'view_mode': 'tree_expenses_robo,form,kanban',
                'views': [[self.env.ref('robo.robo_expenses_tree').id, 'tree_expenses_robo'],
                          [self.env.ref('robo.robo_expenses_form').id, 'form'],
                          [self.env.ref('robo.robo_expenses_kanban').id, 'kanban']],
                'with_settings': True,
            }

        elif cat_id in ['DU']:
            close_journal_id = self.env.user.sudo().company_id.period_close_journal_id.id or 0
            company_id = self.env.user.sudo().company_id
            du = company_id._get_payroll_expense_account_ids()
            du = tuple(du)
            domain = [('account_id', 'in', du),
                      ('date', '>=', date_from),
                      ('move_id.journal_id', '!=', close_journal_id),
                      ('move_id.state', '=', 'posted'),
                      ('date', '<=', date_to)]
            ctx = {'col_group_by': ['date:month'], 'group_by': ['account_id', 'partner_id']}
            return {
                'context': ctx,
                'name': _('Apskaitos Analizė'),
                'res_model': 'account.move.line',
                'target': 'current',
                'domain': domain,
                'type': 'ir.actions.act_window',
                'view_id': self.env.ref('robo.account_move_line_pivot_view').id,
                'views': [[self.env.ref('robo.account_move_line_pivot_view').id, 'pivot']],
                'view_mode': 'pivot',
            }
        elif cat_id in ['DEPR']:
            close_journal_id = self.env.user.sudo().company_id.period_close_journal_id.id or 0
            depreciation_account_ids = self.sudo().env['account.account'].search(
                [('user_type_id', '=', self.sudo().env.ref('account.data_account_type_depreciation').id)]).ids
            depreciation_account_ids = tuple(depreciation_account_ids)
            domain = [('account_id', 'in', depreciation_account_ids),
                      ('date', '>=', date_from),
                      ('move_id.journal_id', '!=', close_journal_id),
                      ('move_id.state', '=', 'posted'),
                      ('date', '<=', date_to)]
            ctx = {'col_group_by': ['date:month'], 'group_by': ['account_id']}
            return {
                'context': ctx,
                'name': _('Apskaitos Analizė'),
                'res_model': 'account.move.line',
                'target': 'current',
                'domain': domain,
                'type': 'ir.actions.act_window',
                'view_id': self.env.ref('robo.account_move_line_pivot_view').id,
                'views': [[self.env.ref('robo.account_move_line_pivot_view').id, 'pivot']],
                'view_mode': 'pivot',
            }
        elif cat_id in ['Kita']:
            close_journal_id = self.env.user.sudo().company_id.period_close_journal_id.id or 0
            company_id = self.env.user.sudo().company_id
            du = company_id._get_payroll_expense_account_ids()
            depreciation_account_ids = self.sudo().env['account.account'].search(
                [('user_type_id', '=', self.sudo().env.ref('account.data_account_type_depreciation').id)]).ids
            du = tuple(du + depreciation_account_ids)
            domain = [('account_id', 'not in', du),
                      ('account_id.code', '=like', '6%'),
                      ('move_id.journal_id', '!=', close_journal_id),
                      ('move_id.state', '=', 'posted'),
                      ('product_id', '=', False),
                      ('date', '>=', date_from),
                      ('date', '<=', date_to)]
            ctx = {'col_group_by': ['date:month'], 'group_by': ['account_id']}
            return {
                'context': ctx,
                'name': _('Apskaitos Analizė'),
                'res_model': 'account.move.line',
                'target': 'current',
                'domain': domain,
                'type': 'ir.actions.act_window',
                'view_id': self.env.ref('robo.account_move_line_pivot_view').id,
                'views': [[self.env.ref('robo.account_move_line_pivot_view').id, 'pivot']],
                'view_mode': 'pivot',
            }

    @api.multi
    def register_standard_cash_payment_and_download_pdf(self):
        self.ensure_one()
        if not self.env.user.employee_ids:
            raise exceptions.ValidationError(_('Jūs nesate darbuotojas'))
        cashier = self.env.user.company_id.cashier_id.id
        if not cashier and self.env.user.employee_ids:
            cashier = self.env.user.employee_ids[0].id
        if not cashier:
            raise exceptions.ValidationError(_(
                'Nenustatytas įmonės pagrindinis kasininkas, prašome jį nustatyti pasirašant įsakymą dėl kasos darbo organizavimo'))
        cash_journal = self.env['account.journal'].search([
            ('code', '=', 'CSH1')
        ], limit=1)
        if not cash_journal:
            raise exceptions.ValidationError(_('Nerastas grynųjų žurnalas'))
        payment_register_model = self.env['register.payment'].with_context(invoice_id=self.id).create({
            'cashier_id': cashier,
            'journal_id': cash_journal.id,
            'amount': self.residual,
            'currency_id': self.currency_id.id,
        })
        data = payment_register_model.post()
        res_id = data['res_id']
        res_model = data['res_model']
        if res_model != 'account.payment':
            raise exceptions.UserError(_('Nenumatyta sistemos klaida, susiekite su sistemos administratoriumi'))
        payment = self.env[res_model].browse(res_id)
        print_order = payment.print_order()
        print_order['report_type'] = 'qweb-pdf'
        return print_order

    @api.multi
    @api.returns('self')
    def refund(self, date_invoice=None, date=None, description=None, journal_id=None):
        if any(rec.type not in ['in_invoice', 'out_invoice'] for rec in self):
            raise exceptions.UserError(_('You cannot refund refund invoices'))
        new_invoices = super(AccountInvoice, self).refund(date_invoice=date_invoice, date=date, description=description,
                                                          journal_id=journal_id)
        for inv in new_invoices:
            inv._partner_data()
        return new_invoices
