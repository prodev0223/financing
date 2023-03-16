# -*- encoding: utf-8 -*-
from __future__ import division
import pytz
import re
import logging
import traceback
from lxml import etree, objectify
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from odoo import models, fields, _, api, exceptions, tools
from odoo.tools import float_compare, float_is_zero, float_round
from ..tools.pdftools import add_xml_binary_pdf
from six import itervalues


STATIC_GPM_SPLIT_TAX_CODE = 'Ne PVM'
_logger = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    def _default_ap_employee_id(self):
        return self.env.user.employee_ids and self.env.user.employee_ids[0].id or False

    def _default_cash_account(self):
        return self.env.user.sudo().company_id.cash_advance_account_id.id

    def _default_payment_mode(self):
        return 'own_account' if self._context.get('with_cheque_picture') else 'company_account'

    def _default_account(self):
        if self._context.get('type') in ('out_invoice', 'out_refund'):
            return self.env['account.account'].search([('code', '=', '2410')], limit=1).id
        return self.env['account.account'].search([('code', '=', '4430')], limit=1).id

    invoice_type = fields.Selection([('invoice', 'Invoice'),
                                     ('imt', 'Asset self-production'),
                                     ('internal', 'Internal needs'),
                                     ], string='Invoice type', default='invoice',
                                    required=True)
    skip_isaf = fields.Boolean(string='Praleisti ISAF', groups="account.group_account_user", copy=False)
    proforma_paid = fields.Boolean(string='ProForma invoice paid', lt_string='Sąskaita apmokėta', sequence=100)
    distributed_payment = fields.Boolean(string='Išskaidyti mokėjimą', copy=False)
    distributed_payment_ids = fields.One2many('account.invoice.distributed.payment.line', 'invoice_id', sequence=100)
    distributed_move_id = fields.Many2one('account.move', string='Išskaidyto mokėjimo įrašas')
    distributed_account_id = fields.Many2one('account.account', string='Išskaidytų mokėjimų mokėtina sąskaita',
                                             domain="[('company_id', '=', company_id), ('deprecated', '=', False), ('reconcile', '=', True), '|', ('internal_type', '=', 'payable'), ('user_type_id', '=', 10)]",
                                             sequence=100,
                                             )
    distributed_total_amount = fields.Boolean(compute='_check_total_distributed_amount')
    imported_api = fields.Boolean(string='API', readonly=True, groups='base.group_system', copy=False)
    expense_split = fields.Boolean(string='Paslaugų sutartis (gyventojas)',
                                   states={'draft': [('readonly', False)]}, readonly=True, sequence=100)
    gpm_move = fields.Many2one('account.move', string='Žurnalo įrašas (GPM 15%)', readonly=True, sequence=100)
    partner_tag_ids = fields.Many2many(related='partner_id.category_id', string='Partnerio žymos', readonly=True,
                                       groups='robo_basic.group_robo_invoice_see_partner_tags')
    proforma_number = fields.Char(string='Išankstinės sąskaitos numeris', copy=False)
    show_signed = fields.Boolean(compute='_show_signed')
    amount_untaxed = fields.Monetary(string='Untaxed Amount', store=True, readonly=True, compute='_compute_amount',
                                     track_visibility='always', sequence=100)
    amount_untaxed_signed = fields.Monetary(string='Untaxed Amount', currency_field='company_currency_id',
                                            store=True, readonly=True, compute='_compute_amount', sequence=100)
    amount_tax = fields.Monetary(string='Tax', store=True, readonly=True, compute='_compute_amount')
    amount_total = fields.Monetary(string='Total', store=True, readonly=True, compute='_compute_amount')
    amount_total_signed = fields.Monetary(string='Total', currency_field='currency_id', store=True, readonly=True,
                                          compute='_compute_amount', help='', sequence=100)
    amount_total_company_signed = fields.Monetary(string='Total', currency_field='company_currency_id', store=True,
                                                  readonly=True, compute='_compute_amount',
                                                  help=('Total amount in the currency of the company, '
                                                        'negative for credit notes.'), sequence=100)
    amount_tax_signed = fields.Monetary(string='Tax Amount', compute='_amount_tax_signed', store=True,
                                        currency_field='company_currency_id', sequence=100)
    reporting_amount_untaxed = fields.Monetary(string='Suma be mokesčių', compute='_reporting_amounts')
    reporting_amount_tax = fields.Monetary(string='Mokesčiai', compute='_reporting_amounts')
    reporting_amount_total = fields.Monetary(string='Suma su mokesčiais', compute='_reporting_amounts')
    reporting_amount_untaxed2 = fields.Monetary(string='Suma be mokesčių', compute='_reporting_amounts')
    reporting_amount_tax2 = fields.Monetary(string='Mokesčiai', compute='_reporting_amounts')
    reporting_amount_total2 = fields.Monetary(string='Suma su mokesčiais', compute='_reporting_amounts')
    reporting_additional_tax = fields.Monetary(string='Papildomi mokesčiai', compute='_reporting_amounts')
    force_taxes = fields.Boolean(string='Priverstiniai mokesčiai', copy=False, track_visibility='onchange', sequence=100)
    print_amount_untaxed = fields.Monetary(string='Suma be mokesčių', compute='_compute_print_amounts')
    print_amount_tax = fields.Monetary(string='Mokesčiai', compute='_compute_print_amounts')
    print_amount_total = fields.Monetary(string='Suma su mokesčiais', compute='_compute_print_amounts')
    print_amount_total_signed = fields.Monetary(string='Suma su mokesčiais', compute='_compute_print_amounts')
    print_amount_untaxed_company = fields.Monetary(string='Suma be mokesčių', compute='_compute_print_amounts',
                                                   currency_field='company_currency_id')
    print_amount_tax_company = fields.Monetary(string='Mokesčiai', compute='_compute_print_amounts',
                                               currency_field='company_currency_id')
    print_amount_total_company = fields.Monetary(string='Suma su mokesčiais', compute='_compute_print_amounts',
                                                 currency_field='company_currency_id')
    date_due_report = fields.Date(string='Perderėtas apmokėjimo terminas')
    show_date_due_report = fields.Boolean(string='Rodyti ataskaitų apmokėjimo datą', compute='_show_date_due_report')
    date_due = fields.Date(help="", inverse='_set_date_due_report')
    virtual_payment_move_id = fields.Many2one('account.move', string='Virtual payment journal entry',
                                              copy=False, readonly=True, sequence=100,
                                              )
    picking_id_refund = fields.Many2one('stock.picking', string='Refund Picking', copy=False, sequence=100)
    picking_id = fields.Many2one('stock.picking', string='Picking', copy=False)
    show_create_picking = fields.Boolean(compute='_compute_show_create_picking')
    price_include_selection = fields.Selection([('exc', 'be PVM'), ('inc', 'su PVM')], string='Kainos',
                                               default='exc', inverse='inverse_price_selection')
    price_include = fields.Boolean(string='Kainos su PVM', compute='_price_include')
    expense_id = fields.Many2one('hr.expense.sheet', string='Čekis', readonly=True, copy=False, sequence=100)
    hr_expense_id = fields.Many2one('hr.expense', string='Čekis', readonly=True, copy=False, index=True, sequence=100)
    expense_move_id = fields.Many2one('account.move', string='Expense move', readonly=True, copy=False, sequence=100)
    advance_payment = fields.Boolean(string='Apmokėta (avansinė apyskaita)', default=False, copy=False)
    advance_payment_date = fields.Date(string='Avansinio mokėjimo data', copy=False, default=False, readonly=True,
                                       states={'draft': [('readonly', False)]}, sequence=100)
    advance_payment_amount = fields.Float(string='Avanso suma', copy=False, readonly=True,
                                          states={'draft': [('readonly', False)]}, sequence=100)
    ap_employee_id = fields.Many2one('hr.employee', string='Apmokėjęs darbuotojas', copy=False,
                                     default=_default_ap_employee_id, track_visibility='onchange', index=True)
    cash_advance_account_id = fields.Many2one('account.account', string='Atskaitingų asmenų sąskaita', copy=False,
                                              default=_default_cash_account, sequence=100)
    payment_mode = fields.Selection(
        [('own_account', 'Asmeninėmis lėšomis'),
         ('company_account', 'Kompanijos lėšomis')],
        string='Kaip apmokėjote?', default=_default_payment_mode, copy=False, track_visibility='onchange',
    )
    allow_change_ap_employee_id = fields.Boolean(compute='_allow_change_payment_details')
    has_fuel_lines = fields.Boolean(string='Sąskaitos eilutėse rasta produktų priklausančių kuro kategorijai',
                                    compute='_has_fuel_lines')
    fuel_expense_move_id = fields.Many2one('account.move', string='Kuro nurašymai', copy=False)
    show_payment_url = fields.Boolean(compute='_compute_show_payment_url')
    invoice_payment_url = fields.Char(compute='_compute_invoice_payment_url')
    account_id = fields.Many2one('account.account', default=_default_account)
    invoice_header = fields.Char(string='Invoice header', translate=True)

    @api.multi
    def _compute_show_payment_url(self):
        for rec in self:
            rec.show_payment_url = bool(rec.invoice_payment_url) if 'refund' not in rec.type else False

    @api.multi
    def _compute_invoice_payment_url(self):
        for rec in self:
            rec.invoice_payment_url = None

    @api.one
    @api.depends('distributed_payment_ids', 'distributed_payment')
    def _check_total_distributed_amount(self):
        if self.distributed_payment:
            amount = sum(self.mapped('distributed_payment_ids.amount'))
            self.distributed_total_amount = float_compare(self.amount_total, amount,
                                                          precision_rounding=self.currency_id.rounding) == 0

    @api.one
    @api.depends('currency_id')
    def _show_signed(self):
        if self.env.user.sudo().company_id.currency_id.id != self.currency_id.id:
            self.show_signed = True
        else:
            self.show_signed = False

    @api.depends('invoice_line_ids.price_subtotal', 'tax_line_ids.amount', 'currency_id', 'company_id', 'date_invoice',
                 'price_include_selection')
    def _compute_amount(self):
        for rec in self:
            rec.amount_untaxed = sum(line.price_subtotal for line in rec.invoice_line_ids)
            rec.amount_tax = sum(line.amount for line in rec.tax_line_ids)
            rec.amount_total = rec.amount_untaxed + rec.amount_tax
            amount_total_company_signed = rec.amount_total
            amount_untaxed_signed = rec.amount_untaxed
            if rec.currency_id and rec.currency_id != rec.company_id.currency_id:
                date = rec.operacijos_data or rec.date_invoice or datetime.utcnow()
                amount_total_company_signed = rec.currency_id.with_context( date=date).compute(
                    rec.amount_total, rec.company_id.currency_id)
                amount_untaxed_signed = rec.currency_id.with_context(date=date).compute(
                    rec.amount_untaxed, rec.company_id.currency_id)
            sign = rec.type in ['in_refund', 'out_refund'] and -1 or 1
            rec.amount_total_company_signed = amount_total_company_signed * sign
            rec.amount_total_signed = rec.amount_total * sign
            rec.amount_untaxed_signed = amount_untaxed_signed * sign

    @api.depends('amount_total_company_signed', 'amount_untaxed_signed')
    def _amount_tax_signed(self):
        for rec in self:
            if rec.amount_untaxed_signed and rec.amount_total_company_signed:
                rec.amount_tax_signed = rec.amount_total_company_signed - rec.amount_untaxed_signed
            else:
                rec.amount_tax_signed = 0.0

    @api.multi
    @api.depends('amount_untaxed', 'amount_tax', 'amount_total', 'tax_line_ids')
    def _reporting_amounts(self):
        for rec in self:
            amount_additional_taxes = sum(rec.tax_line_ids.filtered(
                lambda r: r.tax_id.code and 'S' in r.tax_id.code
            ).mapped('amount'))
            rec.reporting_additional_tax = amount_additional_taxes
            rec.reporting_amount_untaxed = rec.reporting_amount_untaxed2 = rec.amount_untaxed
            rec.reporting_amount_tax = rec.reporting_amount_tax2 = rec.amount_tax + amount_additional_taxes
            rec.reporting_amount_total = rec.reporting_amount_total2 = rec.amount_total + amount_additional_taxes

    @api.multi
    @api.depends('type', 'currency_id', 'date_invoice')
    def _compute_print_amounts(self):
        for rec in self:
            sign = -1.0 if 'refund' in rec.type else 1.0
            amount_additional_tax = sign * rec.reporting_additional_tax
            # Invoice currency
            rec.print_amount_untaxed = sign * rec.reporting_amount_untaxed
            rec.print_amount_tax = sign * rec.reporting_amount_tax
            rec.print_amount_total = sign * rec.reporting_amount_total
            rec.print_amount_total_signed = rec.amount_total_signed

            if rec.currency_id and rec.company_id and rec.currency_id != rec.company_id.currency_id:
                currency_from = rec.currency_id.with_context(date=rec.date_invoice)
                amount_additional_tax = currency_from.compute(amount_additional_tax, rec.company_id.currency_id)

            # Company currency
            rec.print_amount_total_company = rec.amount_total_company_signed + amount_additional_tax
            rec.print_amount_tax_company = rec.amount_tax_signed + amount_additional_tax
            rec.print_amount_untaxed_company = rec.amount_total_company_signed - rec.amount_tax_signed

    @api.multi
    def _show_date_due_report(self):
        edit_date_due = self.env.user.company_id.inv_due_date_edit
        for rec in self:
            if edit_date_due and (rec.move_name or rec.state in ('open', 'paid')):
                rec.show_date_due_report = True

    @api.multi
    def _compute_show_create_picking(self):
        """
        Check whether stock picking creation button
        should be shown to the current user
        :return: None
        """
        for rec in self.filtered(lambda x: x.state in ['open', 'paid', 'proforma', 'proforma2']):
            show_create_picking = False
            # Only execute further checks if invoice has any product line
            if any(ln.product_id.type == 'product' for ln in rec.invoice_line_ids):
                # If there's not direct picking and invoice contains no external sales
                # or purchases OR is of refund type, allow the picking creation
                if not rec.picking_id and (
                        not rec.sale_ids and not rec.invoice_line_ids.filtered(lambda r: r.purchase_id)
                        or rec.type in ['out_refund', 'in_refund']):
                    show_create_picking = True
                else:
                    # Only fetch related pickings here, to save resources
                    pickings = rec.get_related_pickings()
                    if pickings and all(x.state == 'cancel' for x in pickings):
                        show_create_picking = True
            rec.show_create_picking = show_create_picking

    @api.depends('price_include_selection')
    def _price_include(self):
        for rec in self:
            rec.price_include = rec.price_include_selection == 'inc'

    @api.depends('state', 'payment_mode')
    def _allow_change_payment_details(self):
        for rec in self:
            if rec.payment_mode == 'company_account':
                if rec.state == 'paid':
                    rec.allow_change_ap_employee_id = False
                else:
                    rec.allow_change_ap_employee_id = True
            else:
                rec.allow_change_ap_employee_id = True

    @api.depends('invoice_line_ids.product_id')
    def _has_fuel_lines(self):
        for rec in self:
            rec.has_fuel_lines = any(rec.invoice_line_ids.filtered(
                lambda r: r.product_id.categ_id.fuel and r.account_id.code.startswith('2')))

    @api.multi
    def _set_date_due_report(self):
        for rec in self:
            if rec.invoice_type in ('out_invoice', 'out_refund') or not rec.move_name or not rec.company_id.inv_due_date_edit:
                rec.date_due_report = rec.date_due

    @api.multi
    def inverse_price_selection(self):
        for rec in self:
            rec.change_taxes_price_included()

    @api.multi
    @api.constrains('reference')
    def _check_reference_no_space(self):
        for rec in self:
            if rec.type in ['in_invoice', 'in_refund'] and rec.reference and ' ' in rec.reference:
                raise exceptions.ValidationError(
                    _('Klaida, tiekėjo sąskaitos numeris negali turėti tarpų, patikrinkite ir bandykite dar kartą.'))

    @api.multi
    @api.constrains('gpm_move')
    def gpm_move_constrain(self):
        for rec in self:
            if rec.expense_split and rec.state in ['open', 'paid'] and not rec.gpm_move:
                raise exceptions.ValidationError(_('Klaida, nerastas GPM įrašas'))

    @api.multi
    @api.constrains('advance_payment_amount')
    def constraint_advance_payment_amount(self):
        for rec in self:
            if rec.advance_payment_amount < 0.0:
                raise exceptions.ValidationError(_('Avanso suma negali būti neigiama.'))

    @api.onchange('reference')
    def _onchange_reference(self):
        if self.reference and ' ' in self.reference:
            self.reference = self.reference.replace(' ', '')

    @api.onchange('distributed_payment')
    def onchange_distributed_payment(self):
        if not self.distributed_account_id:
            account_id = self.partner_id.property_account_payable_id
            self.distributed_account_id = account_id

    @api.onchange('invoice_type')
    def onchange_invoice_type(self):
        if self.invoice_type and self.type in ['out_invoice', 'out_refund']:
            if self.invoice_type in ['imt', 'internal']:
                return {'domain': {'account_id': [('deprecated', '=', False), ('company_id', '=', self.company_id.id)]}}
            else:
                if self.account_id.internal_type != 'receivable':
                    self.account_id = False
                return {'domain': {'account_id': [('deprecated', '=', False), ('company_id', '=', self.company_id.id), ('internal_type', '=', 'receivable')]}}

    @api.onchange('partner_id')
    def _onchange_partner_id_set_purchase_currency(self):
        if self.type in ('in_invoice', 'in_refund') and self.partner_id.property_purchase_currency_id:
            self.currency_id = self.partner_id.property_purchase_currency_id.id

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        if self.journal_id and not self._context.get('leave_currency', False):
            self.currency_id = self.journal_id.currency_id.id or self.journal_id.company_id.currency_id.id

    @api.onchange('payment_term_id', 'date_invoice')
    def _onchange_payment_term_date_invoice(self):
        date_invoice = self.date_invoice
        if not date_invoice:
            date_invoice = fields.Date.context_today(self)
        if not self.payment_term_id:
            # When no payment term defined
            self.date_due = self.date_due or self.date_invoice
        elif self.payment_term_id or (self.type == 'in_invoice'
                                    and self.partner_id and self.partner_id.property_supplier_payment_term_id):
            pterm = self.payment_term_id or self.partner_id.property_supplier_payment_term_id
            pterm_list = pterm.with_context(currency_id=self.currency_id.id).compute(value=1, date_ref=date_invoice)[0]
            self.date_due = max(line[0] for line in pterm_list)

    @api.onchange('price_include_selection')
    def onchange_price_include(self):
        self.change_taxes_price_included()

    @api.onchange('advance_payment', 'expense_split')
    def onchange_advance_payment(self):
        if self.advance_payment:
            amount = abs(self.amount_total_company_signed)
            if self.expense_split:
                # P3:DivOK -- gpm_du_unrelated is float, thus division always results in float
                gpm_proc = self.company_id.with_context(date=self.date_invoice).gpm_du_unrelated / 100
                amount = tools.float_round(amount * (1 - gpm_proc), precision_digits=2)
            self.advance_payment_amount = amount

    @api.onchange('advance_payment_amount')
    def onchange_advance_payment_amount(self):
        if self.advance_payment_amount < 0.0:
            self.advance_payment_amount = abs(self.advance_payment_amount)

    @api.multi
    def name_get(self):
        result = []
        res = super(AccountInvoice, self).name_get()
        for rec_id, rec_name in res:
            rec = self.env['account.invoice'].browse(rec_id)
            if rec.type in ['in_invoice', 'in_refund'] and rec.reference:
                reference = rec.reference
                internal_name = rec.number
                if reference and internal_name:
                    new_name = '%s (%s)' % (reference, internal_name)
                elif reference and not internal_name:
                    new_name = reference
                elif internal_name and not reference:
                    new_name = internal_name
                elif rec.name:
                    new_name = rec.name
                else:
                    new_name = ''
                result.append((rec_id, new_name))
            else:
                result.append((rec_id, rec_name))
        return result

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = args or []
        recs = self.search(['|', ('number', operator, name), ('reference', operator, name)] + args, limit=limit)
        return recs.name_get()

    @api.model
    def create(self, vals):
        res = super(AccountInvoice, self).create(vals)
        res.compute_taxes()
        return res

    @api.multi
    def write(self, vals):
        if not self.env.user.is_accountant() and 'force_taxes' in vals:
            vals.pop('force_taxes')
        if not self.env.user.is_accountant() and 'tax_line_ids' in vals:
            for rec in self:
                if rec.sudo().force_taxes:
                    raise exceptions.UserError(_('Šiai sąskaitai mokesčius sudėjo buhalteris, todėl jos negalima keisti'))
        if 'tax_line_ids' in vals and 'invoice_line_ids' in vals:
            if vals.get('force_taxes', self and self[0].sudo().force_taxes):
                vals.pop('invoice_line_ids')
            else:
                vals.pop('tax_line_ids')
        res = super(AccountInvoice, self).write(vals)
        if self._context.get('write_from_expense', False):
            return res
        for rec in self.filtered(lambda x: x.hr_expense_id):
            rec.hr_expense_id.with_context(write_from_invoice=True).write({
                'name': rec.origin,
                'partner_id': rec.partner_id.id,
                'reference': rec.reference,
            })
        return res

    @api.multi
    def copy(self, default=None):
        if not self.env.user.company_id.with_context(date=False).vat_payer and self.sudo().mapped('invoice_line_ids.invoice_line_tax_ids'):
            raise exceptions.UserError(_('Negalima kopijuoti šios sąskaitos'))
        return super(AccountInvoice, self).copy(default)

    @api.multi
    def unlink(self):
        is_accountant = self.env.user.is_accountant()
        for rec in self:
            if rec.type in ('in_invoice', 'in_refund') and rec.state == 'cancel' and rec.move_name:
                if not is_accountant and rec.sudo().create_uid.is_accountant():
                    raise exceptions.UserError(_('Tik buhalteris gali ištrinti šį įrašą.'))
                rec.move_name = False
        for rec in self:
            if rec.hr_expense_id and not self._context.get('deleting_cheque', False):
                rec.hr_expense_id.with_context({'deleting_invoice': True}).unlink()
        return super(AccountInvoice, self).unlink()

    @api.multi
    def action_invoice_open(self):
        # FIXME: most of the method can act on multi set, except the call to super because of a date passed as context
        self.ensure_one()
        for rec in self:
            rec.proforma_vat_visibility = 'default'
            if rec.type in ['out_invoice', 'out_refund']:
                if rec.price_include_selection == 'inc' and rec.invoice_line_ids.mapped(
                        'invoice_line_tax_ids').filtered(lambda r: not r.price_include):
                    raise exceptions.UserError(_('Neteisingai nurodyti mokesčiai. Pabandykite pakeisti kainų skaičivimą'
                                                 ' su PVM arba be PVM. Jei nepavyks - kreipkitės į buhalterį.'))
                elif rec.price_include_selection != 'inc' and rec.invoice_line_ids.mapped(
                        'invoice_line_tax_ids').filtered(lambda r: r.price_include):
                    raise exceptions.UserError(_('Neteisingai nurodyti mokesčiai. Pabandykite pakeisti kainų skaičivimą'
                                                 ' su PVM arba be PVM. Jei nepavyks - kreipkitės į buhalterį.'))
            if rec.type in ['in_invoice']:
                if not self.env.user.is_accountant() and any(l.asset_category_id for l in rec.sudo().invoice_line_ids):
                    raise exceptions.UserError(
                        _('Atsiprašome, jums neleidžiama patvirtinti šios sąskaitos. Kreipkitės į buhalterį'))
            if rec.state in ['proforma', 'proforma2'] and 'out_' in rec.type and rec.date_invoice < datetime.utcnow().strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT):
                rec.mark_invalidated()
                rec.date_invoice = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                if rec.date_due < rec.date_invoice:
                    rec.date_due = rec.date_invoice
        # Get the expense split account id
        expense_split_account_id = self.env['account.account'].search([('code', '=', '4486')]).id
        for inv in self:
            if float_compare(inv.amount_total, 0.0, precision_rounding=inv.currency_id.rounding) < 0:
                if not self.env.user.is_accountant():
                    raise exceptions.UserError(_('Tik buhalteris gali patvirtinti sąskaitą kurios suma yra neigiama'))
            if inv.distributed_payment:
                if not self.env.user.is_accountant():
                    raise exceptions.UserError(_('Tik buhalteris gali patvirtinti šią sąskaitą'))
                if not inv.distributed_total_amount:
                    raise exceptions.UserError(
                        _('Negalite patvirtinti sąskaitos, nes sąskaitos suma nesutampa su išskaidoma suma.'))
                if inv.account_id.id == inv.distributed_account_id.id:
                    raise exceptions.UserError(_('Negali sutapti sąskaitos ir išskaidymo DK sąskaitos.'))
                if not inv.distributed_account_id:
                    raise exceptions.UserError(_('Nenurodyta išskaidytų mokėjimų sąskaita'))
            if inv.expense_split:
                # Always skip iSAF and force specific account ID on expense split
                inv.sudo().write({'skip_isaf': True, 'account_id': expense_split_account_id})
                for line in inv.invoice_line_ids:
                    for tax in line.invoice_line_tax_ids:
                        if tax.code != STATIC_GPM_SPLIT_TAX_CODE:
                            raise exceptions.ValidationError(
                                _("Pasirinkus paslaugų opciją, eilučių PVM turi būti 'Ne PVM'")
                            )
        for rec in self:
            if rec.hr_expense_id:
                rec.hr_expense_id.state = 'reported'

        self.sudo().recompute_taxes_if_neccesary()
        self.assert_taxes_ok()
        self.check_invoice_tax_integrity()
        #FIXME: If we want to have this method be multi, we need a way around this context
        date = self.operacijos_data or self.date_invoice or datetime.utcnow()
        res = super(AccountInvoice, self.with_context(
            enable_invoice_line_edition=True, force_exact_currency_rate=True, date=date)).action_invoice_open()
        self.filtered(lambda inv: inv.has_fuel_lines and 'in_' in inv.type).create_fuel_expense_move()
        for inv in self.filtered('distributed_payment'):
            account_d = inv.account_id
            account_c = inv.distributed_account_id
            line_to_reconcile = self.move_id.line_ids.filtered(lambda l: l.account_id == account_d)
            if len(line_to_reconcile) != 1:
                raise exceptions.UserError(_('Nepavyko nustatyti kredito eilutės. Kreipkitės į buhalterį.'))
            company_currency = self.env.user.company_id.currency_id
            currency = inv.currency_id if inv.currency_id != company_currency else False
            line_debit_vals = {
                'partner_id': inv.partner_id.id,
                'date_maturity': line_to_reconcile.date_maturity,
                'ref': line_to_reconcile.ref,
                'name': '/',
                'debit': line_to_reconcile.credit,
                'account_id': account_d.id,
                'invoice_id': inv.id,
            }
            lines = [(0, 0, line_debit_vals)]
            credit_line_template = {
                    'partner_id': inv.partner_id.id,
                    'ref': inv.reference,
                    'name': '/',
                    'account_id': account_c.id,
                    'invoice_id': inv.id,
                }
            for line in inv.distributed_payment_ids:
                line_credit_vals = credit_line_template.copy()
                line_credit_vals.update({
                    'date_maturity': line.date,
                    'credit': line.amount,
                })
                if currency:
                    ctx = {'date': inv.date_invoice}
                    line_credit_vals.update({
                        'currency_id': line.currency_id.id,
                        'amount_currency': -line.amount,
                        'credit': line.currency_id.with_context(ctx).compute(line.amount, company_currency)
                    })
                lines.append((0, 0, line_credit_vals))
            if currency:
                line_debit_vals.update({'currency_id': line_to_reconcile.currency_id.id,
                                        'amount_currency': - line_to_reconcile.amount_currency,
                                        'debit': sum(l[2]['credit'] for l in lines[1:])})

            move_vals = {
                'name': inv.number + ' (Distr)',
                'journal_id': self.env['account.journal'].search([('code', '=', 'KITA')], limit=1).id,
                'date': inv.date_invoice,
                'currency_id': inv.currency_id.id,
                'line_ids': lines
            }
            move = self.env['account.move'].create(move_vals)
            inv.distributed_move_id = move.id
            move.post()
            debit_line = move.line_ids.filtered(lambda l: l.account_id == account_d)
            self.env['account.move.line'].browse([debit_line.id, line_to_reconcile.id]).auto_reconcile_lines()

        return res

    @api.multi
    def action_invoice_cancel(self):
        for rec in self:
            if rec.hr_expense_id:
                rec.hr_expense_id.state = 'refused'
            if rec.fuel_expense_move_id:
                try:
                    rec.fuel_expense_move_id.button_cancel()
                    rec.fuel_expense_move_id.line_ids.remove_move_reconcile()
                    rec.fuel_expense_move_id.unlink()
                except Exception as e:
                    _logger.info('Could not cancel invoice {} (Id: {}), because fuel expense record cannot be deleted.'
                                 '\nError: {} \nTraceback: {}'.format(rec.document_name, rec.id,
                                                                      tools.ustr(e), traceback.format_exc()))
                    raise exceptions.UserError(_('Negalite atšaukti sąskaitos faktūros, '
                                                 'nes kuro sąnaudų įrašas negali būti ištrintas.'))
            if rec.expense_move_id:
                try:
                    rec.expense_move_id.button_cancel()
                    rec.expense_move_id.line_ids.remove_move_reconcile()
                    rec.expense_move_id.unlink()
                except:
                    raise exceptions.UserError(_('Negalite atšaukti sąskaitos faktūros, '
                                                 'nes avansinės apyskaitos įrašas negali būti ištrintas.'))
        for rec in self:
            if rec.type in ['in_invoice']:
                if not self.env.user.is_accountant() and any(l.asset_category_id for l in rec.sudo().invoice_line_ids):
                    raise exceptions.UserError(
                        _('Atsiprašome, jums neleidžiama atšaukti šios sąskaitos. Kreipkitės į buhalterį'))
            if rec.virtual_payment_move_id:
                move = rec.virtual_payment_move_id
                move.line_ids.remove_move_reconcile()
                move.button_cancel()
                move.unlink()
            rec.mark_proforma_not_paid()
            if rec.distributed_move_id:
                if not self.env.user.is_accountant():
                    raise exceptions.UserError(
                        _('Kreipkitės į buhalterį, jei norite atšaukti šią sąskaitą.'))
                move = rec.distributed_move_id
                for line in move.line_ids:
                    if line.account_id == rec.account_id:
                        line.remove_move_reconcile()
                    if line.matched_debit_ids or line.matched_credit_ids or line.reconciled:
                        raise exceptions.UserError(_('Norėdami atšaukti šią sąskaitą, atidenkite mokėjimus.'))
                move.button_cancel()
                move.unlink()
            if rec.gpm_move:
                try:
                    rec.gpm_move.button_cancel()
                    rec.gpm_move.unlink()
                except Exception as e:
                    error_base = _('Negalite atšaukti sąskaitos faktūros, nes GPM įrašas negali būti ištrintas.')
                    if self.env.user.is_accountant():
                        error_base += _('\nKlaidos pranešimas - %s') % str(e.args[0])
                    else:
                        error_base += _('\nSusisiekite su buhalteriu.')
                    raise exceptions.UserError(error_base)
        return super(AccountInvoice, self).action_invoice_cancel()

    @api.multi
    def action_cancel_paid(self):
        for rec in self:
            if rec.state not in ['open', 'paid']:
                raise exceptions.UserError(_('Negalite atšaukti nepatvirtintos sąskaitos.'))
            if rec.move_id:
                rec.mapped('move_id.line_ids').filtered(lambda l: l.account_id == rec.account_id).remove_move_reconcile()
            rec.action_invoice_cancel()

    @api.multi
    def action_invoice_re_open(self):
        for rec in self:
            if rec.hr_expense_id:
                rec.hr_expense_id.state = 'reported'
        return super(AccountInvoice, self).action_invoice_re_open()

    @api.multi
    def action_invoice_paid(self):
        for rec in self:
            if rec.hr_expense_id:
                rec.hr_expense_id.state = 'done'
        return super(AccountInvoice, self).action_invoice_paid()

    @api.multi
    def action_invoice_draft(self):
        for rec in self:
            if rec.type in ['in_invoice', 'in_refund'] and rec.date_invoice:
                date_invoice_dt = datetime.strptime(rec.date_invoice, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_invoice_dt2 = date_invoice_dt - relativedelta(months=1, day=1)
                date_deadline_dt = datetime.utcnow() - relativedelta(months=1, day=1)
                isaf_day = rec.get_isaf_report_date(rec.date_invoice)
                isaf_submitted = rec.check_isaf_report_submitted(rec.date_invoice)
                if ((date_invoice_dt2 == date_deadline_dt
                     and datetime.utcnow().day > isaf_day) or date_invoice_dt2 < date_deadline_dt) and isaf_submitted:
                    rec.force_dates = True
            if rec.hr_expense_id:
                rec.hr_expense_id.state = 'draft'
        return super(AccountInvoice, self).action_invoice_draft()

    @api.multi
    def action_cancel(self):
        res = super(AccountInvoice, self).action_cancel()
        for rec in self:
            if rec.expense_move_id:
                rec.expense_move_id.state = 'draft'
                rec.expense_move_id.unlink()
            if rec.expense_id:
                rec.expense_id.state = 'approve'
        return res

    @api.multi
    def mark_proforma_paid(self):
        self.write({'proforma_paid': True})

    @api.multi
    def mark_proforma_not_paid(self):
        self.write({'proforma_paid': False})

    @api.multi
    def recalculate_taxes(self):
        for rec in self:
            rec._onchange_invoice_line_ids()

    @api.multi
    def _check_proforma2_constraints(self):
        for rec in self:
            if rec.state != 'draft':
                raise exceptions.UserError(
                    _('Norint sąskaitą padaryti išankstine, sąskaita privalo būti juodraščio būsenoje.')
                )
            if rec.move_name:
                raise exceptions.UserError(_('Sąskaitos, kuri jau buvo patvirtinta, negalima padaryti išankstine.'))

    @api.multi
    def action_invoice_proforma2(self):
        self._check_proforma2_constraints()
        for rec in self:
            if rec.hr_expense_id:
                rec.hr_expense_id.state = 'reported'
            if not rec.proforma_number:
                rec.proforma_number = self.env['ir.sequence'].sudo().next_by_code('account.invoice.proforma')
        return super(AccountInvoice, self).action_invoice_proforma2()

    @api.multi
    def assert_taxes_ok(self):
        for rec in self:
            if rec.sudo().force_taxes:
                continue
            computed_lines = rec.get_taxes_values()
            computed_taxes = {}
            for v in itervalues(computed_lines):
                key = (v['tax_id'], v['account_id'], v['account_analytic_id'])
                value = {'amount': v['amount'], 'base': v['base']}
                computed_taxes[key] = value
            company_currency = rec.company_id.currency_id
            tax_keys = []
            precision = self.env['decimal.precision'].precision_get('Account')
            for tax_line in rec.tax_line_ids:
                if tax_line.manual:
                    continue
                key = (tax_line.tax_id.id, tax_line.account_id.id, tax_line.account_analytic_id.id)
                tax_keys.append(key)
                if key not in computed_taxes:
                    raise exceptions.UserError(_('Reikia perskaičiuoti mokesčius'))
                base = computed_taxes[key]['base']
                amount = computed_taxes[key]['amount']
                if float_compare(abs(base - tax_line.base), company_currency.rounding * 2, precision_digits=precision) == 1:
                    raise exceptions.UserError(_('Reikia perskaičiuoti mokesčius'))
                if float_compare(abs(amount - tax_line.amount), company_currency.rounding * 2, precision_digits=precision) == 1:
                    raise exceptions.UserError(_('Reikia perskaičiuoti mokesčius'))
                computed_taxes[key]['base'] -= tax_line.base
                computed_taxes[key]['amount'] -= tax_line.amount
            for key in computed_taxes:
                if key not in tax_keys:
                    raise exceptions.UserError(_('Reikia perskaičiuoti mokesčius'))

    @api.multi
    def recompute_taxes_if_neccesary(self):
        invoices_to_recompute = self.env['account.invoice']
        for rec in self:
            if rec.force_taxes:
                continue
            try:
                rec.assert_taxes_ok()
            except:
                invoices_to_recompute |= rec
        if invoices_to_recompute:
            invoices_to_recompute.compute_taxes()

    def prep_vals(self, iml, inv):
        if inv.expense_split:
            try:
                debit_line = next(item for item in iml if item['price'] and item['price'] > 0)
                credit_line = next(item for item in iml if item['price'] and item['price'] < 0)
            except StopIteration:
                raise exceptions.Warning(_('Pasirinkus paslaugų sutarties opciją,'
                                           ' paslaugos kaina privalo būti didesnė už 0!'))
            # P3:DivOK -- gpm_du_unrelated is float, thus division always results in float
            gpm_proc = inv.company_id.with_context(date=inv.date_invoice).gpm_du_unrelated / 100
            a_class = self.env['a.klase.kodas'].search([('code', '=', '70')]).id
            price = credit_line['price']
            credit_gpm = credit_line.copy()
            debit_gpm = debit_line.copy()
            account = self.env['account.account'].search([('code', '=', '4486')]).id
            credit_line['account_id'] = account
            credit_line['price'] = float_round(price * (1 - gpm_proc), precision_digits=2)
            credit_line['a_klase_kodas_id'] = a_class
            debit_line['price'] = float_round(price * -1 * (1 - gpm_proc), precision_digits=2)
            account = self.env['account.account'].search([('code', '=', '4487')]).id
            credit_gpm['account_id'] = account
            credit_gpm['price'] = float_round(price * gpm_proc, precision_digits=2)
            credit_gpm['a_klase_kodas_id'] = a_class
            debit_gpm['price'] = float_round(price * -1 * gpm_proc, precision_digits=2)
            iml = [debit_line, credit_line]

            # Create GPM move
            gpm_lines = [debit_gpm, credit_gpm]
            part = self.env['res.partner']._find_accounting_partner(inv.partner_id)
            gpm_lines = [(0, 0, self.line_get_convert(l, part.id)) for l in gpm_lines]
            gpm_lines = inv.group_lines(iml, gpm_lines)
            ctx = dict(self._context, lang=inv.partner_id.lang)
            journal = inv.journal_id.with_context(ctx)
            move_vals = {
                'ref': inv.reference,
                'line_ids': gpm_lines,
                'journal_id': journal.id,
                'date': inv.date or inv.date_invoice,
                'narration': inv.comment,
            }
            gpm_move = self.env['account.move'].create(move_vals)
            gpm_move.post()
            inv.write({'gpm_move': gpm_move.id})
        return super(AccountInvoice, self).prep_vals(iml, inv)

    @api.model
    def line_get_convert(self, line, part):
        res = super(AccountInvoice, self).line_get_convert(line, part)
        if res['account_id'] == self.env['account.account'].search([('code', '=', '4487')]).id:
            vmi_partner = self.env['res.partner'].search([('kodas', '=', '188659752')], limit=1)
            res['partner_id'] = vmi_partner.id
        res['a_klase_kodas_id'] = line.get('a_klase_kodas_id', False)
        return res

    @api.multi
    def action_cancel_imt(self):
        self.ensure_one()
        if self.move_id:
            move_id = self.move_id
            move_id.button_cancel()
            self.move_id = False
            move_id.unlink()
            self.state = 'draft'
            # No workflow in v10
            # self.delete_workflow()
            # self.create_workflow()

    @api.multi
    def check_nonzero_amount(self):
        for rec in self.filtered(lambda i: i.type in ('out_invoice', 'out_refund')):
            rounding = rec.currency_id.rounding
            if any(float_is_zero(l.price_subtotal, precision_rounding=rounding) and float_compare(l.discount, 100, precision_rounding=0.01) != 0 and not float_is_zero(l.discount, precision_rounding=0.01) for l in rec.invoice_line_ids):
                raise exceptions.UserError(_('Kaina negali būti nulinė, jeigu nurodyta ne 100% nuolaida'))

    @api.multi
    def invoice_validate(self):
        self.check_nonzero_amount()
        res = super(AccountInvoice, self).invoice_validate()
        for invoice in self:
            if invoice.type in ['out_invoice', 'out_refund'] and invoice.invoice_type == 'invoice' and invoice.account_id.internal_type != 'receivable':
                raise exceptions.UserError(_('Pasirinkite gautinų sumų sąskaitą.'))
            if invoice.type in ['out_invoice', 'out_refund'] and invoice.invoice_type == 'imt':
                tags = invoice.mapped('tax_line_ids.tax_id.tag_ids.code')
                if '15' not in tags:
                    raise exceptions.UserError(_('Neteisingi mokesčiai, kreipkitės į buhalterį.'))
        for rec in self:
            if tools.float_is_zero(rec.amount_total, precision_digits=2) and not rec.invoice_line_ids:
                raise exceptions.UserError(_("Įveskite sąskaitos sumą."))

            # ROBO: remove if it is not important anymore
            if rec.expense_id.payment_mode == 'own_account':
                rec.expense_move_create()
                pay_line_id = rec.move_id.mapped('line_ids').filtered(lambda r: r.account_id.reconcile)
                if not pay_line_id or pay_line_id and len(pay_line_id) > 1:
                    raise exceptions.UserError(
                        _("Nepavyko patvirtinti sąskaitos, patikrinkite ar darbuotojo apskaitos informacija yra teisinga"))
                emp_line_id = rec.expense_move_id.mapped('line_ids').filtered(
                    lambda r: r.account_id.reconcile and r.account_id.id == pay_line_id.account_id.id)
                if not emp_line_id or emp_line_id and len(emp_line_id) > 1:
                    raise exceptions.UserError(
                        _("Nepavyko patvirtinti sąskaitos, patikrinkite ar darbuotojo apskaitos informacija yra teisinga"))
                self.env['account.move.line'].browse([pay_line_id.id, emp_line_id.id]).with_context(
                    force_reconcile=True).reconcile()
                rec.expense_id.state = 'post'
                rec.expense_id.account_move_id = rec.expense_id.invoice_id.expense_move_id.id
            elif rec.expense_id.payment_mode == 'company_account':
                rec.expense_id.paid_expense_sheets()
            elif rec.advance_payment:
                rec.expense_move_create_extra()
                pay_line_id = rec.move_id.mapped('line_ids').filtered(lambda r: r.account_id.reconcile and tools.float_compare(r.balance, 0, precision_digits=2) == (1 if rec.type == 'in_refund' else -1))
                if not pay_line_id or pay_line_id and len(pay_line_id) > 1:
                    raise exceptions.UserError(
                        _("Nepavyko patvirtinti sąskaitos, patikrinkite ar darbuotojo apskaitos informacija yra teisinga"))
                emp_line_id = rec.expense_move_id.mapped('line_ids').filtered(
                    lambda r: r.account_id.reconcile and r.account_id.id == pay_line_id.account_id.id)
                if not emp_line_id or emp_line_id and len(emp_line_id) > 1:
                    raise exceptions.UserError(
                        _("Nepavyko patvirtinti sąskaitos, patikrinkite ar darbuotojo apskaitos informacija yra teisinga"))
                self.env['account.move.line'].browse([pay_line_id.id, emp_line_id.id]).with_context(
                    force_reconcile=True).reconcile()
        return res

    @api.model
    def tax_line_move_line_get(self):
        # we need to round taxes that are roundable at invoice level, otherwise following situation might occur:
        #VAT 21%: 10.5 ct
        #VAT 9%: 10.5 ct
        # Total should be 21 ct, but we will get 22ct
        # #
        res = super(AccountInvoice, self).tax_line_move_line_get()
        # keep track of taxes already processed
        price_undone = 0
        line_to_change = {}
        currency = self.currency_id
        # loop the invoice.tax.line in reversal sequence
        for iml in res:
            tax_id = iml['tax_line_id']
            if not self.env['account.tax'].browse(tax_id).price_include:
                line_to_change = iml
                line_to_change['price'] += price_undone
                old_price = line_to_change['price']
                new_price = currency.round(old_price)
                price_undone = old_price - new_price
                line_to_change['price'] = new_price

        if line_to_change:
            line_to_change['price'] += price_undone
        return res

    @api.multi
    def call_distributed_line_wizard(self):
        ctx = self._context.copy()
        ctx.update({
            'invoice_id': self.id,
            'date': self.date_due,
            'amount': self.amount_total,
            'currency_id': self.currency_id.id
        })
        return {
            'context': ctx,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.invoice.distributed.payment.line.wizard',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.model
    def _prepare_refund(self, invoice, date_invoice=None, date=None, description=None, journal_id=None):
        res = super(AccountInvoice, self)._prepare_refund(invoice, date_invoice=date_invoice, date=date,
                                                          description=description, journal_id=journal_id)
        res['price_include_selection'] = invoice.price_include_selection
        res['user_id'] = self._context.get('user_id')
        return res

    @api.model
    def find_suspicious_operations(self):
        """
        Finds invoices considered suspicious - that are over 15k in value.
        :return dictionary: values are numbers of suspicious invoices:
         - 'not_in_eu_total_more_than_15k' : buyer is not from EU and out invoice value over 15k
         - 'total_more_than_15k_and_10_times_more_than_avg_sales' :
         out invoice value over 15k and over 10 times more than company yearly average.
         - 'total_more_than_15k_and_10_times_more_than_avg_purchases' :
         in invoice value over 15k and over 10 times more than company yearly average.
        """
        suspicious_ops = {
            'not_in_eu_total_more_than_15k': None,
            'total_more_than_15k_and_10_times_more_than_avg_sales': None,
            'total_more_than_15k_and_10_times_more_than_avg_purchases': None,
        }
        current_year_beginning = \
            (datetime.utcnow() - relativedelta(month=1, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        europe = self.env.ref('base.europe')
        not_in_eu_total_more_than_15k = self.env['account.invoice'].search([
            ('partner_country_id', 'not in', europe.country_ids.ids),
            '|', ('amount_total_company_signed', '>', 15000), ('amount_total_company_signed', '<', -15000),
            ('type', 'in', ['out_invoice', 'out_refund']),
            ('state', 'in', ['open', 'paid']),
            ('date_invoice', '>=', current_year_beginning),
        ])
        suspicious_ops['not_in_eu_total_more_than_15k'] = not_in_eu_total_more_than_15k.mapped('number')

        out_invoices = self.env['account.invoice'].search([
            ('type', 'in', ['out_invoice', 'out_refund']),
            ('state', 'in', ['open', 'paid']),
            ('date_invoice', '>=', current_year_beginning),
        ])
        out_invoices_over_15k = out_invoices.filtered(lambda i: abs(i.amount_total_company_signed) > 15000)
        if out_invoices_over_15k:
            # P3:DivOK -- amount_total_company_signed is float, thus division always results in float
            avg_out = sum(out_invoices.mapped(lambda i: abs(i.amount_total_company_signed))) / len(out_invoices)
            query_out = out_invoices_over_15k.filtered(lambda i: abs(i.amount_total_company_signed) > 10*avg_out)
            if query_out:
                suspicious_ops['total_more_than_15k_and_10_times_more_than_avg_sales'] = query_out.mapped('number')

        in_invoices = self.env['account.invoice'].search([
            ('type', 'in', ['in_invoice', 'in_refund']),
            ('state', 'in', ['open', 'paid']),
            ('date_invoice', '>=', current_year_beginning),
        ])
        in_invoices_over_15k = in_invoices.filtered(lambda i: abs(i.amount_total_company_signed) > 15000)
        if in_invoices_over_15k:
            # P3:DivOK -- amount_total_company_signed is float, thus division always results in float
            avg_in = sum(out_invoices.mapped(lambda i: abs(i.amount_total_company_signed))) / len(in_invoices)
            query_in = in_invoices_over_15k.filtered(lambda i: abs(i.amount_total_company_signed) > 10*avg_in)
            if query_in:
                suspicious_ops['total_more_than_15k_and_10_times_more_than_avg_purchases'] = query_in.mapped('number')

        return suspicious_ops

    @api.multi
    def _prepare_pdf_metadata(self):
        """
        Prepare the PDF meta data information
        :return: dict containing the metadata
        """
        self.ensure_one()
        company_name = self.company_id.name
        inv_type = self.type == 'out_refund' and _('Refund') or _('Invoice')
        pdf_metadata = {
            'author': company_name,
            'keywords': ', '.join([inv_type, _('eInvoice')]),
            'title': _('%s: Invoice %s dated %s') % (
                company_name,
                self.number or self.move_name or self.state,
                self.date_invoice or '(no date)'),
            'subject': 'eInvoice %s dated %s issued by %s' % (
                self.number or self.move_name or self.date,
                self.date_invoice or '(no date)',
                company_name),
        }
        return pdf_metadata

    @api.multi
    def insert_xml_content_into_pdf(self, pdf_content, xml_type='esaskaita'):
        """
        Insert XML invoice into PDF version of invoice
        :param pdf_content: content of PDF file as a str (as returned by get_pdf)
        :param xml_type: handles different format. Default to e-invoice
        :return: modified pdf_content as str
        """
        self.ensure_one()
        if not pdf_content:
            raise exceptions.UserError(_('Trūksta PDF turinio'))
        if xml_type != 'esaskaita':
            raise NotImplementedError(_('Šiuo metu palaikomas tik lietuviškos e-sąskaitos formatas'))
        if self.type not in ('out_invoice', 'out_refund'):
            raise exceptions.UserError(
                _('Tik kliento sąskaitos (pardavimai, grąžinimai) gali būti eksportuojamos kaip e-sąskaita'))
        einvoice_xml_str = self.generate_einvoice_xml()
        pdf_metadata = self._prepare_pdf_metadata()
        # Generate a new PDF with XML file as attachment
        pdf_content = add_xml_binary_pdf(pdf_content, einvoice_xml_str, check_xsd=False, pdf_metadata=pdf_metadata)
        return pdf_content

    @api.multi
    def generate_einvoice_xml(self):
        """
        Generate XML for eInvoice format
        :return: Invoice XML as a string
        """
        self.ensure_one()

        def sanitize_str_for_xml(s):
            # https://stackoverflow.com/a/25920392
            return re.sub(u'[^\u0020-\uD7FF\u0009\u000A\u000D\uE000-\uFFFD\U00010000-\U0010FFFF]+', '', s)

        def set_node(node, key, value, skip_empty=False):
            if skip_empty and not value:
                return
            if not skip_empty and not value and not isinstance(value, tuple([int, float, long])):
                raise exceptions.UserError('Tuščia reikšmė privalomam elementui %s' % key)
            el = etree.Element(key)
            if isinstance(value, tuple([int, float, long])) and not isinstance(value, bool):
                value = str(value)
            elif isinstance(value, basestring):
                value = sanitize_str_for_xml(value)
            if value:
                el.text = value
            setattr(node, key, el)

        def set_tag(node, tag, value):
            if isinstance(value, (float, int)) and not isinstance(value, bool):
                value = str(value)
            node.attrib[tag] = value

        if self.state not in ['open', 'paid']:
            raise exceptions.UserError(_('Negalima įkelti juodraštinių sąskaitų'))

        company_id = self.env.user.sudo().company_id

        e_xml_template = '''<?xml version="1.0" encoding="UTF-8"?>
            <E_Invoice xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            </E_Invoice>'''
        e_root = objectify.fromstring(e_xml_template)
        e_head = objectify.Element('Header')
        e_root.append(e_head)
        db_name = self.env.cr.dbname
        file_id = self.env['ir.sequence'].next_by_code('swed.bank.e.invoice.seq') + '__' + db_name  # maybe commit
        date = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        set_node(e_head, 'Date', date)
        set_node(e_head, 'FileId', file_id)
        set_node(e_head, 'AppId', 'EINVOICE')
        set_node(e_head, 'Version', '1.1')

        total_inv_number = 0
        total_amount = 0.0
        if self.state not in ['open', 'paid']:
            raise exceptions.Warning('Negalima įkelti juodraštinių sąskaitų')
        e_invoice = objectify.Element('Invoice')
        global_code = str(self.id) + '__' + db_name
        number = self.number or self.move_name
        set_tag(e_invoice, 'invoiceId', number)
        set_tag(e_invoice, 'serviceId', self.partner_id.sudo().e_invoice_service_id or self.partner_id.id)
        set_tag(e_invoice, 'regNumber', self.partner_id.kodas or '0')
        set_tag(e_invoice, 'channelId', '0')  #TODO:maybe we can include it?
        set_tag(e_invoice, 'channelAddress', '0')  #TODO:maybe we can include it?
        set_tag(e_invoice, 'presentment', 'YES')
        set_tag(e_invoice, 'invoiceGlobUniqId', global_code or '0')
        set_tag(e_invoice, 'globalSellerContractId', '0')  #TODO: don't think it makes sense to have something here ?
        set_tag(e_invoice, 'sellerRegNumber', company_id.company_registry)

        # -Invoice parties
        ei_parties = objectify.Element('InvoiceParties')
        s_party = objectify.Element('SellerParty')
        b_party = objectify.Element('BuyerParty')

        ei_parties.append(s_party)
        ei_parties.append(b_party)

        total_inv_number += 1
        total_amount += self.amount_total

        # --Seller party
        set_node(s_party, 'Name', company_id.name)
        set_node(s_party, 'RegNumber', company_id.company_registry)
        set_node(s_party, 'VATRegNumber', company_id.vat, skip_empty=True)
        for journal in self.env['account.journal'].search([('display_on_footer', '=', True)]):
            s_party_ai = objectify.Element('AccountInfo')
            set_node(s_party_ai, 'IBAN', journal.bank_acc_number)
            set_node(s_party_ai, 'BIC', journal.bank_id.bic)
            set_node(s_party_ai, 'BankName', journal.bank_id.name)
            s_party.append(s_party_ai)

        # --Buyer party
        set_node(b_party, 'Name', self.partner_id.name)
        set_node(b_party, 'RegNumber', self.partner_id.kodas, skip_empty=True)
        set_node(b_party, 'VATRegNumber', self.partner_id.vat, skip_empty=True)
        e_invoice.append(ei_parties)

        # -Invoice information
        ei_info = objectify.Element('InvoiceInformation')
        ei_type = objectify.Element('Type')
        set_tag(ei_type, 'type', 'CRE' if 'refund' in self.type else 'DEB')
        #TODO: if CRE, we can refer to the original. Should we ?
        ei_info.append(ei_type)
        set_node(ei_info, 'DocumentName', 'E-Invoice') #TODO: Should we have as printed on invoice (PVM saskaita faktura, etc) ?
        set_node(ei_info, 'InvoiceNumber', number)
        set_node(ei_info, 'InvoiceDate', self.date_invoice)
        set_node(ei_info, 'DueDate', self.date_due)
        e_invoice.append(ei_info)

        # -Invoice sum group
        ei_sum = objectify.Element('InvoiceSumGroup')
        set_node(ei_sum, 'InvoiceSum', self.amount_untaxed)
        set_node(ei_sum, 'TotalVATSum', self.amount_tax)
        set_node(ei_sum, 'TotalSum', self.amount_total)
        set_node(ei_sum, 'Currency', self.currency_id.name)
        e_invoice.append(ei_sum)

        # -Invoice invoice item
        ei_item = objectify.Element('InvoiceItem')
        for en, line in enumerate(self.invoice_line_ids, 1):
            ei_group = objectify.Element('InvoiceItemGroup')
            ei_item.append(ei_group)
            set_tag(ei_group, 'groupId', line.id)

            ei_entry = objectify.Element('ItemEntry')
            ei_group.append(ei_entry)

            set_node(ei_entry, 'RowNo', en)
            set_node(ei_entry, 'SerialNumber', line.product_id.default_code, skip_empty=True)
            set_node(ei_entry, 'SellerProductId', line.product_id.id, skip_empty=True)
            set_node(ei_entry, 'Description', line.name)
            set_node(ei_entry, 'EAN', line.product_id.barcode, skip_empty=True)

            product_type_info = objectify.Element('ItemReserve')
            set_node(product_type_info, 'InformationName', 'ProductType')
            set_node(product_type_info, 'InformationContent', line.product_id.acc_product_type)
            ei_entry.append(product_type_info)
            det_info = objectify.Element('ItemDetailInfo')

            if not tools.float_is_zero(line.quantity, precision_digits=2):
                # P3:DivOK -- both field types are float
                item_price = tools.float_round(line.price_subtotal / line.quantity, precision_digits=2)
            else:
                item_price = line.price_subtotal

            set_node(det_info, 'ItemAmount', line.quantity)
            set_node(det_info, 'ItemPrice', item_price)
            ei_entry.append(det_info)
            set_node(ei_entry, 'ItemSum', line.price_subtotal)

            vat_payer = self.env.user.company_id.sudo().with_context(date=self.get_vat_payer_date()).vat_payer
            for tax in line.invoice_line_tax_ids:
                code = tax.code or ''
                if code.startswith('A') or code.startswith('S'):
                    continue
                vat_info = objectify.Element('VAT')
                set_node(vat_info, 'VATRate', tax.amount)
                if not vat_payer:
                    set_tag(vat_info, 'vatId', 'NOTTAX')
                elif tools.float_is_zero(tax.amount, precision_digits=2):
                    set_tag(vat_info, 'vatId', 'TAXEX')
                else:
                    set_tag(vat_info, 'vatId', 'TAX')

                code_info = objectify.Element('Reference')
                set_node(code_info, 'InformationName', 'Code')
                set_node(code_info, 'InformationContent', code)
                vat_info.append(code_info)
                ei_entry.append(vat_info)

            set_node(ei_entry, 'ItemTotal', line.total_with_tax_amount)
            ei_g_entry = objectify.Element('GroupEntry')
            ei_group.append(ei_g_entry)
            set_node(ei_g_entry, 'GroupAmount', line.quantity)
            set_node(ei_g_entry, 'GroupSum', line.price_subtotal)

        ei_group_tot = objectify.Element('InvoiceItemTotalGroup')
        ei_item.append(ei_group_tot)
        e_invoice.append(ei_item)
        set_node(ei_group_tot, 'InvoiceItemTotalSum', self.amount_untaxed)

        set_node(ei_sum, 'InvoiceSum', self.amount_untaxed)
        set_node(ei_sum, 'TotalVATSum', self.amount_tax)
        set_node(ei_sum, 'TotalSum', self.amount_total)
        e_root.append(e_invoice)

        e_foot = objectify.Element('Footer')
        e_root.append(e_foot)
        set_node(e_foot, 'TotalNumberInvoices', 1)
        set_node(e_foot, 'TotalAmount', self.amount_total)

        objectify.deannotate(e_root)
        etree.cleanup_namespaces(e_root)
        string_repr = etree.tostring(e_root, xml_declaration=True, encoding='utf-8')

        return string_repr

    @api.multi
    def finalize_invoice_move_lines(self, move_lines):
        super(AccountInvoice, self).finalize_invoice_move_lines(move_lines)
        invoice_id = False
        for line in move_lines:
            if line[0] == 0:
                invoice_id = self.browse(line[2]['invoice_id'])
                break
        if invoice_id and invoice_id.currency_id.id != invoice_id.company_id.currency_id.id and invoice_id.company_id.rounding_expense and invoice_id.company_id.rounding_income:
            for line in move_lines:
                if not tools.float_compare(abs(line[2]['amount_currency']), invoice_id.amount_total,
                                           precision_digits=2):
                    debit = line[2]['debit']
                    credit = line[2]['credit']
                    amount = debit if debit > 0.0 else credit
                    amount2 = invoice_id.amount_total_company_signed
                    if tools.float_compare(amount, amount2, precision_digits=2):
                        if debit:
                            line[2]['debit'] = amount2
                            sign = -1
                        else:
                            sign = 1
                            line[2]['credit'] = amount2
                        diff = tools.float_round(sign * (amount2 - amount), precision_digits=2)
                        vals = line[2].copy()
                        vals['amount_currency'] = 0.0
                        vals['currency_id'] = False
                        if diff >= 0.0:
                            vals['debit'] = abs(diff)
                            vals['credit'] = 0.0
                            vals['account_id'] = invoice_id.company_id.rounding_income.id
                        else:
                            vals['debit'] = 0.0
                            vals['credit'] = abs(diff)
                            vals['account_id'] = invoice_id.company_id.rounding_expense.id
                        move_lines.append((0, 0, vals))

        return move_lines

    @api.multi
    def compute_taxes(self):
        inv_to_compute = self.filtered(lambda i: not i.force_taxes)
        if inv_to_compute:
            super(AccountInvoice, inv_to_compute).compute_taxes()
        return self.filtered('force_taxes').write({'invoice_line_ids': []})

    @api.multi
    def get_taxes_values(self):
        tax_grouped = {}
        for line in self.invoice_line_ids:
            # P3:DivOK -- discount is float field, thus division results in float
            price_unit = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            if self.price_include_selection == 'inc':
                taxes = \
                    line.invoice_line_tax_ids.with_context(price_include=True).compute_all(price_unit, self.currency_id,
                                                                                           line.quantity,
                                                                                           line.product_id,
                                                                                           self.partner_id,
                                                                                           force_total_price=line.price_subtotal_make_force_step and line.price_subtotal_save_force_value or None)[
                        'taxes']
            else:
                taxes = \
                    line.invoice_line_tax_ids.compute_all(price_unit, self.currency_id, line.quantity, line.product_id,
                                                          self.partner_id,
                                                          force_total_price=line.price_subtotal_make_force_step and line.price_subtotal_save_force_value or None)[
                        'taxes']
            for tax in taxes:
                val = self._prepare_tax_line_vals(line, tax)
                key = self.env['account.tax'].browse(tax['id']).get_grouping_key(val)

                if key not in tax_grouped:
                    tax_grouped[key] = val
                else:
                    tax_grouped[key]['amount'] += val['amount']
                    tax_grouped[key]['base'] += val['base']
        for tax in tax_grouped:
            tax_grouped[tax]['amount'] = self.currency_id.round(tax_grouped[tax]['amount'])
        return tax_grouped

    @api.multi
    def change_taxes_price_included(self):
        self.ensure_one()
        self.invoice_line_ids._change_taxes_price_included()

    @api.multi
    def check_invoice_tax_integrity(self):
        """
        When invoice is confirmed and it has forced taxes,
        check if tax_line_ids in the invoice match
        grouped invoice_line_tax_ids for each line.
        :return: None
        """
        for rec in self.filtered(lambda x: x.force_taxes):
            invoice_taxes = rec.tax_line_ids.mapped('tax_id')
            lines_taxes = rec.invoice_line_ids.mapped('invoice_line_tax_ids')
            # Compare two sets -- Main invoice taxes can have more records,
            # but they must include every tax that is contained in the invoice lines
            for lines_tax in lines_taxes:
                if lines_tax not in invoice_taxes:
                    error = _('Negalite patvirtinti sąskaitos, sąskaitos eilučių mokesčiai nesutampa su bendrais '
                              'mokesčiais. Mokestis "{}" neegzistuoja bendrų mokesčių lentelėje.').format(
                        lines_tax.display_name)
                    raise exceptions.ValidationError(error)

    @api.multi
    def send_acc_invoice(self):
        self.ensure_one()

        try:
            template_id = self.env.ref('saskaitos.email_template_acc_invoice')
        except ValueError:
            template_id = False
        try:
            compose_form_id = self.env.ref('mail.email_compose_message_wizard_form')
        except ValueError:
            compose_form_id = False

        ctx = dict(self.env.context or {})
        id = self._ids[0]
        ctx.update({
            'default_model': 'account.invoice',
            'default_res_id': id,
            'default_use_template': bool(template_id),
            'default_template_id': template_id.id,
            'default_composition_mode': 'comment',
        })
        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form_id.id, 'form')],
            'view_id': compose_form_id.id,
            'target': 'new',
            'context': ctx,
        }

    @api.multi
    def create_picking(self):
        return {
            'context': self._context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'invoice.delivery.wizard',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.multi
    def action_move_create(self):
        for rec in self:
            if rec.currency_id != self.env.user.company_id.currency_id and rec.date_invoice > datetime.now().strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT):
                raise exceptions.UserError(
                    _('Negalima patvirtinti ateities sąskaitų užsienio valiuta, nes nežinomas valiutų kursas.'))
            rec.tax_line_ids._signed()
            rec.invoice_line_ids._compute_price()
        if self.check_access_rights('create', raise_exception=False):
            company = self.env.user.company_id
            lock_date = company.get_user_accounting_lock_date()
            for rec in self:
                inv_date = rec.date or rec.date_invoice
                if inv_date <= lock_date:
                    raise exceptions.UserError(company.accounting_lock_error_message(lock_date))
            self = self.sudo()
        return super(AccountInvoice, self).action_move_create()

    @api.multi
    def action_invoice_create_virtual_payment(self):
        # Access to method removed from views on accountant's request
        for rec in self:
            if rec.type != 'in_invoice':
                raise exceptions.UserError(_('Operacija gali būti taikoma tik pirkimams'))
            if rec.payment_move_line_ids:
                raise exceptions.UserError(_('Sąskaita jau turi susijusių mokėjimų'))
            aml = rec.move_id.line_ids.filtered(lambda l: l.account_id == rec.account_id)
            if len(aml) != 1:
                raise exceptions.UserError(_('Nepavyko rasti susijusių žurnalo įrašų'))
            amount_currency = aml.amount_residual_currency if aml.currency_id else False

            line_debit_vals = {
                'account_id': aml.account_id.id,
                'partner_id': aml.partner_id.id,
                'currency_id': aml.currency_id.id,
                'date_maturity': rec.date_due,
                'ref': rec.reference,
                'name': aml.name
            }
            line_credit_vals = line_debit_vals.copy()
            line_debit_vals.update({'debit': aml.credit})
            line_credit_vals.update({'credit': aml.credit})
            if amount_currency:
                line_debit_vals.update({'amount_currency': -amount_currency})
                line_credit_vals.update({'amount_currency': amount_currency})
            move_vals = {
                'name': rec.number + ' (VM)',
                'journal_id': self.env['account.journal'].search([('code', '=', 'KITA')], limit=1).id,
                'date': rec.date,
                'currency_id': aml.currency_id.id,
                'line_ids': [(0, 0, line_debit_vals), (0, 0, line_credit_vals)]
            }
            move = self.env['account.move'].create(move_vals)
            move.post()
            rec.virtual_payment_move_id = move.id
            line_to_reconcile = sorted(move.line_ids, key=lambda l: l.debit)[1]
            self.env['account.move.line'].browse([aml.id, line_to_reconcile.id]).auto_reconcile_lines()

    @api.multi
    def _get_origin_picking_ids(self):
        res = []
        for rec in self:
            if not rec.origin:
                continue
            origin = self.env['account.invoice'].search([('number', '=', rec.origin)], limit=1)
            if origin:
                if origin.picking_id:
                    res += [origin.picking_id.id]
                else:
                    picking_ids = origin.mapped('sale_ids.picking_ids').filtered(
                        lambda p: p.location_id.usage == 'internal' and
                                  p.location_dest_id.usage == 'customer' and
                                  p.state == 'done' and
                                  p.mapped('move_lines.non_error_quant_ids')
                    )
                    if picking_ids:
                        res += picking_ids.mapped('id')
        return res

    @api.multi
    def change_payment_details(self):
        self.ensure_one()
        now = datetime.utcnow().date()
        year = now.year
        invoice_year = datetime.strptime(self.date_invoice, tools.DEFAULT_SERVER_DATE_FORMAT).year
        if not self.env.user.is_accountant():
            if self.accountant_validated:
                raise exceptions.UserError(_('Negalima keisti sąskaitos kuri patvirtinta buhalterio!'))
            if year != invoice_year and now + relativedelta(month=4, day=1) < now or invoice_year < year - 1: #TODO: what happens when invoice_date is in future ?
                raise exceptions.UserError(_('Finansiniai metai jau uždaryti. Jeigu reikia ką nors tikslinti, parašykite '
                                             'komentarą buhalterijai lango apačioje.'))
            elif self.payment_mode == 'own_account' and self.expense_move_id:
                already_paid = True
                line_ids = self.expense_move_id.line_ids.filtered(lambda r: r.partner_id.id == self.ap_employee_id.address_home_id.id and r.account_id.id == self.cash_advance_account_id.id)
                if line_ids and len(line_ids) == 1 and not line_ids[0].matched_debit_ids:
                    already_paid = False
                if already_paid:
                    raise exceptions.UserError(
                        _('Nurodytam darbuotojui jau kompensuotos išlaidos pagal šią sąskaitą. Jeigu reikia ką nors '
                          'tikslinti, parašykite komentarą buhalterijai lango apačioje.'))
        ctx = {
            'active_id': self.id
        }
        return {
            'name': _('Keisti apmokėjimo informaciją'),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': False,
            'res_model': 'expenses.wizard',
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': ctx,
        }

    @api.multi
    def update_payment_details(self, payment_mode, new_emp):
        self.ensure_one()
        self = self.with_context(skip_accountant_validated_check=True)
        if not self.allow_change_ap_employee_id:
            raise exceptions.UserError(_('Negalite pakeisti apmokėjimo informacijos, nes sąskaita jau patvirtinta arba'
                                         ' darbuotojui jau sumokėta.'))
        elif self.ap_employee_id == new_emp and payment_mode == 'own_account' and payment_mode == self.payment_mode:
            if self._context.get('apmoketa_direktoriaus', False):
                raise exceptions.UserError(_('Jau nustatyta, kad įmonės vadovas apmokėjo šią sąskaitą.'))
            else:
                raise exceptions.UserError(_('Pasirinktas darbuotojas atitinka atskaitingą asmenį.'))
        elif not new_emp and payment_mode == 'own_account':
            raise exceptions.UserError(_('Nepasirinktas darbuotojas.'))
        else:
            if self.payment_mode == 'company_account' and payment_mode == 'company_account':
                return
            elif self.payment_mode == 'own_account' and payment_mode == 'own_account' and new_emp != self.ap_employee_id:
                for line in self.expense_move_id.line_ids:
                    if line.partner_id == self.ap_employee_id.address_home_id and float_compare(line.credit, self.advance_payment_amount, precision_digits=2) >= 0 and self.cash_advance_account_id == line.account_id:
                        line.partner_id = new_emp.address_home_id
                        break
                self.ap_employee_id = new_emp
                if self.hr_expense_id.id:
                    self.hr_expense_id.employee_id = new_emp
            elif self.payment_mode == 'own_account' and payment_mode == 'company_account':
                for move_line in self.payment_move_line_ids:
                    move_line.sudo().delete_move_reconcile()
                for rec in self:
                    if rec.hr_expense_id and not self._context.get('deleting_cheque', False):
                        rec.hr_expense_id.with_context({'deleting_invoice': True}).unlink()
                    if rec.expense_move_id:
                        rec.expense_move_id.write({'state': 'draft'})
                        rec.expense_move_id.unlink()
                if self.hr_expense_id.id:
                    self.hr_expense_id.payment_mode = 'company_account'
                    self.hr_expense_id.employee_id = None
                self.payment_mode = 'company_account'
                self.ap_employee_id = None
            else:
                if self.hr_expense_id.id:
                    self.hr_expense_id.payment_mode = 'own_account'
                    self.hr_expense_id.employee_id = new_emp
                self.payment_mode = 'own_account'
                self.ap_employee_id = new_emp
                self.sudo().expense_move_create_extra()
                pay_line_id = self.move_id.mapped('line_ids').filtered(lambda r: r.account_id.reconcile)
                if not pay_line_id or pay_line_id and len(pay_line_id) > 1:
                    raise exceptions.UserError(
                        _("Negalima patvirtinti sąskaitos, prašome kreiptis į buhalterį."))
                emp_line_id = self.expense_move_id.mapped('line_ids').filtered(
                    lambda r: r.account_id.reconcile and r.account_id.id == pay_line_id.account_id.id)
                if not emp_line_id or emp_line_id and len(emp_line_id) > 1:
                    raise exceptions.UserError(
                        _("Negalima patvirtinti sąskaitos, prašome kreiptis į buhalterį."))
                self.env['account.move.line'].sudo().browse([pay_line_id.id, emp_line_id.id]).with_context(
                    force_reconcile=True).reconcile()
            self.move_id._check_lock_date()

    @api.multi
    def create_fuel_expense_move(self):
        invoices = self.filtered(lambda inv: inv.type in ['in_invoice', 'in_refund'] and inv.has_fuel_lines)
        if not invoices:
            return
        journal = self.env['account.journal'].search([('code', '=', 'KURAS')], limit=1)
        if not journal:
            raise exceptions.UserError(_('Kuro nurašymų žurnalas nerastas. Kreipkitės į buhalterį.'))
        journal_debit_account = journal.default_debit_account_id
        journal_credit_account = journal.default_credit_account_id

        if not journal_debit_account or not journal_credit_account:
            raise exceptions.UserError(_('Nenustatyti kuro nurašymo nustatymai. Kreipkitės į buhalterį.'))
        for invoice in invoices:
            lines = []
            date = datetime.strptime(invoice.date_invoice, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(day=31)
            common_line_vals = {
                'name': _('Kuro nurašymas: ') + (invoice.reference or ''),
                'origin': invoice.name,
                'invoice_id': invoice.id,
                'date': date,
                'partner_id': invoice.partner_id.id
            }
            if invoice.b_klase_kodas_id:
                common_line_vals['b_klase_kodas_id'] = invoice.b_klase_kodas_id.id
            if invoice.type == 'in_invoice':
                debit_account, credit_account = journal_debit_account, journal_credit_account
            else:
                credit_account, debit_account = journal_debit_account, journal_credit_account

            for line in invoice.mapped('invoice_line_ids'):
                if not line.product_id.categ_id.fuel:
                    continue
                analytic_account_id = line.account_analytic_id
                common_line_vals.update({
                    'price_unit': line.price_unit,
                    'quantity': line.quantity,
                    'uom_id': line.uom_id.id,
                    'product_id': line.product_id.id or False,
                })
                amount = abs(line.price_subtotal_signed)
                credit_line_vals = {
                    'account_id': credit_account.id,
                    'credit': amount
                }
                debit_line_vals = {
                    'account_id': debit_account.id,
                    'debit': amount
                }
                debit_line_vals.update(common_line_vals)
                credit_line_vals.update(common_line_vals)
                if analytic_account_id:
                    if credit_account.code[0] in ['5', '6']:
                        credit_line_vals['analytic_account_id'] = analytic_account_id.id
                    if debit_account.code[0] in ['5', '6']:
                        debit_line_vals['analytic_account_id'] = analytic_account_id.id

                lines.append(debit_line_vals)
                lines.append(credit_line_vals)

            if lines:
                move_vals = {
                    'ref': _('Kuro nurašymas: ') + (invoice.reference or ''),
                    'line_ids': [(0, 0, line_vals) for line_vals in lines],
                    'journal_id': journal.id,
                    'date': date,
                    'narration': invoice.comment,
                }
                move = self.env['account.move'].with_context(enable_invoice_line_edition=True).create(move_vals)
                move.post()
                invoice.fuel_expense_move_id = move

    @api.multi
    def show_related_fuel_accounting_entries(self):
        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move.line',
            'name': _('Kuro nurašymai'),
            'view_id': False,
            'domain': [('move_id', 'in', self.mapped('fuel_expense_move_id.id') )],
        }

    @api.multi
    def expense_move_create(self):
        """ Creates invoice related analytics and financial move lines """
        raise exceptions.UserError(_('Ši funkcija negalima, susisiekite su sistemos administratoriumi'))
        self.ensure_one()
        account_move = self.env['account.move']
        if not self.journal_id.sequence_id:
            raise exceptions.UserError(_('Prašome apibrėžti seką žurnale, susijusiame su šia sąskaita faktūra.'))
        if not self.invoice_line_ids:
            raise exceptions.UserError(_('Sukurkite bent vieną sąskaitos eilutę'))
        if not self.expense_id:
            return
        if self.expense_move_id:
            return
        if not self.date_invoice:
            self.write({'date_invoice': fields.Date.context_today(self)})
        date_invoice = self.date_invoice
        company_currency = self.company_id.currency_id
        diff_currency = self.currency_id != company_currency
        move_line_partner = {
            'partner_id': self.partner_id.id,
            'name': 'Pagal avansinę apyskaitą: %s' % self.partner_ref,
            'debit': self.amount_total_signed,
            'credit': 0,
            'account_id': self.account_id.id,
            'amount_currency': self.amount_total if diff_currency else 0.0,
            'currency_id': self.currency_id.id if diff_currency else False,
            'quantity': 1.00,
            'invoice_id': self.id
        }
        if self.expense_id.employee_id.address_home_id:
            employee_partner = self.expense_id.employee_id.address_home_id
        elif self.expense_id.employee_id.user_id and self.expense_id.employee_id.user_id.partner_id:
            employee_partner = self.expense_id.employee_id.user_id.partner_id
        else:
            raise exceptions.UserError(_('Nenustatytas darbuotojo gyvenamosios vietos adresas'))
        if employee_partner.sudo().company_id.cash_advance_account_id:
            cash_account_id = employee_partner.sudo().company_id.cash_advance_account_id.id
        else:
            cash_account_id = employee_partner.property_account_payable_id.id
        move_line_employee = {
            'partner_id': employee_partner.id,
            'name': self.expense_id.name or '/',
            'debit': 0,
            'credit': self.amount_total_signed,
            'account_id': cash_account_id,
            'amount_currency': - self.amount_total if diff_currency else 0.0,
            'currency_id': self.currency_id.id if diff_currency else False,
            'quantity': 1.00,
            'invoice_id': self.id
        }

        lines = [(0, 0, move_line_partner), (0, 0, move_line_employee)]

        date = self.date or date_invoice
        move_vals = {
            'ref': self.reference,
            'line_ids': lines,
            'journal_id': self.journal_id.id,
            'date': date,
            'narration': self.comment,
        }
        expense_move = account_move.create(move_vals)
        expense_move.post()
        # make the invoice point to that move
        vals = {
            'expense_move_id': expense_move.id
        }
        self.write(vals)

    @api.multi
    def expense_move_create_extra(self):
        """ Creates invoice related analytics and financial move lines """
        self.ensure_one()
        account_move = self.env['account.move']
        if not self.journal_id.sequence_id:
            raise exceptions.UserError(_('Prašome apibrėžti seką žurnale, susijusiame su šia sąskaita faktūra.'))
        if not self.invoice_line_ids:
            raise exceptions.UserError(_('Sukurkite bent vieną sąskaitos eilutę'))
        if not self.date_invoice:
            self.write({'date_invoice': fields.Date.context_today(self)})
        date_invoice = self.date_invoice
        company_currency = self.company_id.currency_id
        diff_currency = self.currency_id != company_currency
        expense_move_name = 'Pagal avansinę apyskaitą: %s' % self.reference
        if self.advance_payment_amount and not tools.float_is_zero(self.advance_payment_amount, precision_digits=2):
            amount = abs(self.advance_payment_amount)
        else:
            amount = abs(self.amount_total_company_signed)
            if self.expense_split:
                # P3:DivOK -- gpm_du_unrelated is float thus division results in float
                gpm_proc = self.company_id.with_context(date=self.date_invoice).gpm_du_unrelated / 100
                amount = tools.float_round(amount * (1 - gpm_proc), precision_digits=2)

        move_line_partner = {
            'partner_id': self.partner_id.id,
            'name': expense_move_name,
            'debit': amount,
            'credit': 0,
            'account_id': self.account_id.id,
            'amount_currency': self.amount_total if diff_currency else 0.0,
            'currency_id': self.currency_id.id if diff_currency else False,
            'quantity': 1.00,
            'invoice_id': self.id
        }
        if self.amount_total_company_signed < 0.0:
            move_line_partner['credit'] = amount
            move_line_partner['debit'] = 0.0
        if self.ap_employee_id.advance_accountancy_partner_id:
            employee_partner = self.ap_employee_id.advance_accountancy_partner_id
        elif self.ap_employee_id.address_home_id:
            employee_partner = self.ap_employee_id.address_home_id
        elif self.ap_employee_id.user_id and self.ap_employee_id.user_id.partner_id:
            employee_partner = self.ap_employee_id.user_id.partner_id
        else:
            raise exceptions.UserError(_('Nenurodytas atskaitingas asmuo.'))
        if self.cash_advance_account_id:
            cash_account_id = self.cash_advance_account_id.id
        elif employee_partner.sudo().company_id.cash_advance_account_id:
            cash_account_id = employee_partner.sudo().company_id.cash_advance_account_id.id
        else:
            cash_account_id = employee_partner.property_account_payable_id.id
        move_line_employee = {
            'partner_id': employee_partner.id,
            'name': expense_move_name,
            'debit': 0,
            'credit': amount,
            'account_id': cash_account_id,
            'amount_currency': - self.amount_total if diff_currency else 0.0,
            'currency_id': self.currency_id.id if diff_currency else False,
            'quantity': 1.00,
            'invoice_id': self.id
        }
        if self.amount_total_company_signed < 0.0:
            move_line_employee['debit'] = amount
            move_line_employee['credit'] = 0.0

        lines = [(0, 0, move_line_partner), (0, 0, move_line_employee)]

        if self.advance_payment_date:
            date = self.advance_payment_date
        else:
            date = self.date or date_invoice
        move_vals = {
            'ref': expense_move_name,
            'line_ids': lines,
            'journal_id': self.journal_id.id,
            'date': date,
            'narration': self.comment,
        }
        expense_move = account_move.create(move_vals)
        expense_move.post()
        # make the invoice point to that move
        vals = {
            'expense_move_id': expense_move.id
        }
        self.write(vals)

    @api.multi
    def invoice_print(self):
        if self.check_access_rights('read', raise_exception=False):
            self = self.sudo()
        return super(AccountInvoice, self).invoice_print()
