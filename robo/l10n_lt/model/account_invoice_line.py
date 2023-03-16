# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, fields, tools, api, _, exceptions
from datetime import datetime
import odoo.addons.decimal_precision as dp


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    @api.model
    def _default_account(self):
        if self._context.get('type') in ('out_invoice', 'out_refund'):
            return self.env['account.account'].search([('code', '=', '5001')], limit=1).id
        return self.env['account.account'].search([('code', '=', '6001')], limit=1).id

    total_with_tax_amount = fields.Monetary(string='Užsienio valiuta su mokesčiais', compute='_total_tax_amount_computed',
                                            store=True, lt_string='Užsienio valiuta su mokesčiais')
    total_with_tax_amount_company = fields.Monetary(string='Suma su mokesčiais',
                                                    compute='_total_tax_amount_computed', store=True,
                                                    currency_field='company_currency_id', lt_string='Suma su mokesčiais')
    price_unit_tax_included = fields.Float(string='Vnt. kaina (su PVM)', compute='_total_tax_amount_computed',
                                           digits=dp.get_precision('Product Price'), lt_string='Vnt. kaina (su PVM)')
    price_unit_tax_excluded = fields.Float(string='Vnt. kaina (be PVM)', compute='_total_tax_amount_computed',
                                           digits=dp.get_precision('Product Price'), lt_string='Vnt. kaina (be PVM)')
    price_unit_tax_included_company = fields.Float(string='Vnt. kaina (su PVM, EUR)',
                                                   compute='_total_tax_amount_computed',
                                                   digits=dp.get_precision('Product Price'))
    price_unit_tax_excluded_company = fields.Float(string='Vnt. kaina (be PVM, EUR)',
                                                   compute='_total_tax_amount_computed',
                                                   digits=dp.get_precision('Product Price'))
    price_subtotal_make_force_step = fields.Boolean(string="Force step", default=False)
    price_subtotal_save_force_value = fields.Float(string="Force value", default=0.0)
    amount_depends = fields.Monetary(string='Suma', compute='_amount_depends', readonly=False)
    account_id = fields.Many2one(default=_default_account)
    print_qty = fields.Float(compute='_compute_print_fields')
    print_price_subtotal = fields.Monetary(compute='_compute_print_fields')
    print_total_with_tax_amount = fields.Monetary(compute='_compute_print_fields')
    print_discount_currency = fields.Monetary(compute='_compute_print_fields')
    print_price_subtotal_company = fields.Monetary(compute='_compute_print_fields',
                                                   currency_field='company_currency_id')
    print_total_with_tax_amount_company = fields.Monetary(compute='_compute_print_fields',
                                                          currency_field='company_currency_id')
    print_discount_company_currency = fields.Monetary(compute='_compute_print_fields',
                                                      currency_field='company_currency_id')
    analytic_tag_ids = fields.Many2many(string='Analitinė žyma')

    @api.one
    @api.depends('price_unit', 'discount', 'invoice_line_tax_ids', 'quantity',
                 'product_id', 'invoice_id.partner_id', 'invoice_id.currency_id', 'invoice_id.company_id',
                 'invoice_id.date_invoice', 'invoice_id.price_include_selection')
    def _compute_price(self):
        # Override base method
        currency = self.invoice_id and self.invoice_id.currency_id or None
        date = self.invoice_id.operacijos_data or self.invoice_id.date_invoice or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        if self.price_subtotal_make_force_step:
            # P3:DivOK -- quantity is float
            price = self.price_subtotal_save_force_value / self.quantity if self.quantity else 0.0
        else:
            # P3:DivOK
            price = self.price_unit * (1 - (self.discount or 0.0) / 100.0)
        taxes = False
        if self.invoice_line_tax_ids:
            if self.invoice_id.price_include_selection == 'inc':
                taxes = self.invoice_line_tax_ids.with_context(price_include=True).compute_all(
                    price, currency, self.quantity, product=self.product_id, partner=self.invoice_id.partner_id,
                    force_total_price=self.price_subtotal_make_force_step and self.price_subtotal_save_force_value or None
                )
            else:
                taxes = self.invoice_line_tax_ids.compute_all(
                    price, currency, self.quantity, product=self.product_id, partner=self.invoice_id.partner_id,
                    force_total_price=self.price_subtotal_make_force_step and self.price_subtotal_save_force_value or None
                )
        if self.price_subtotal_make_force_step:
            price_subtotal_signed = taxes['total_excluded'] if taxes else self.price_subtotal_save_force_value
        else:
            price_subtotal_signed = taxes['total_excluded'] if taxes else self.quantity * price
        self.price_subtotal = price_subtotal_signed
        if self.invoice_id.currency_id and self.invoice_id.currency_id != self.invoice_id.company_id.currency_id:
            price_subtotal_signed = self.invoice_id.currency_id.with_context(date=date).compute(price_subtotal_signed,
                                                                                                self.invoice_id.company_id.currency_id)
        sign = self.invoice_id.type in ['in_refund', 'out_refund'] and -1 or 1
        self.price_subtotal_signed = price_subtotal_signed * sign

    @api.one
    @api.depends('invoice_line_tax_ids', 'company_currency_id', 'price_unit', 'quantity',
                 'invoice_id.price_include_selection', 'currency_id', 'invoice_id.date_invoice')
    def _total_tax_amount_computed(self):
        currency = self.currency_id or None
        # P3:DivOK
        price = self.price_unit * (1 - (self.discount or 0.0) / 100.0)

        # Get decimal precision for price unit field. If there's no decimal precision, or decimal precision == 2
        # (default if not found), we do not force the precision to keep the previous behaviour
        forced_dp = self.env['decimal.precision'].precision_get('Product Price')
        if not forced_dp or forced_dp == 2:
            forced_dp = False
        if self.invoice_id.price_include_selection == 'inc':
            taxes = self.invoice_line_tax_ids.with_context(
                price_include=True, round=False, forced_dp=forced_dp).compute_all(
                price, currency, self.quantity, product=self.product_id, partner=self.invoice_id.partner_id,
                force_total_price=self.price_subtotal_make_force_step and self.price_subtotal_save_force_value or None
            )
        else:
            taxes = self.invoice_line_tax_ids.with_context(round=False, forced_dp=forced_dp).compute_all(
                price, currency, self.quantity, product=self.product_id, partner=self.invoice_id.partner_id,
                force_total_price=self.price_subtotal_make_force_step and self.price_subtotal_save_force_value or None
            )
        self.total_with_tax_amount = taxes['total_included']
        total_without_tax_amount = taxes['total_excluded']
        total_without_tax_amount_company = 0.0
        if currency:
            use_rounding = currency.apply_currency_rounding(self.total_with_tax_amount_company)
            date = self.invoice_id and self.invoice_id.date_invoice \
                   or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            self.total_with_tax_amount_company = currency.with_context(date=date).compute(
                self.total_with_tax_amount, self.company_currency_id, round=use_rounding)
            total_without_tax_amount_company = currency.with_context(date=date).compute(
                total_without_tax_amount, self.company_currency_id, round=use_rounding)
        else:
            self.total_with_tax_amount_company = self.total_with_tax_amount
        if self.quantity > 0:
            # P3:DivOK - quantity is float
            self.price_unit_tax_included = (taxes['total_included'] / self.quantity)
            if not tools.float_is_zero(self.discount - 100.0, precision_digits=2):
                # P3:DivOK
                self.price_unit_tax_excluded = (taxes['total_excluded'] / self.quantity)/(1-self.discount/100.0)
            else:
                self.price_unit_tax_excluded = self.price_unit
            if currency:
                # P3:DivOK - All following lines are ok, since at least one variable is float (quantity)
                self.price_unit_tax_included_company = self.total_with_tax_amount_company / self.quantity
                price_unit_tax_excluded_company = total_without_tax_amount_company / self.quantity
                if not tools.float_is_zero(self.discount - 100.0, precision_digits=2):
                    price_unit_tax_excluded_company /= 1 - self.discount / 100.0
                self.price_unit_tax_excluded_company = price_unit_tax_excluded_company
            else:
                self.price_unit_tax_included_company = self.price_unit_tax_included
                self.price_unit_tax_excluded_company = self.price_unit_tax_excluded

    @api.one
    @api.depends('invoice_id.price_include_selection', 'price_subtotal', 'price_unit', 'quantity',
                 'price_subtotal_make_force_step', 'price_subtotal_save_force_value', 'discount')
    def _amount_depends(self):
        if self.price_subtotal_make_force_step:
            self.amount_depends = self.price_subtotal_save_force_value
        else:
            # P3:DivOK
            self.amount_depends = tools.float_round(
                self.price_unit * self.quantity * (1 - ((self.discount / 100.0) or 0.0)), precision_digits=2)

    @api.model
    def is_company_taxfree_income_above_5percent(self, date=None):
        """
        Calculates if companies income taxed as PVM5 (tax-free income) is above 5% of
        companies total income or not
        :param date: datetime object
        :return: boolean
        """
        fiscal_year = self.env.user.company_id.compute_fiscalyear_dates(date)
        date_from_str = fiscal_year.get('date_from').strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_str = fiscal_year.get('date_to').strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        pvm5_income_query = """
            SELECT SUM(price_subtotal_signed) FROM account_invoice_line ail 
            JOIN account_invoice inv ON inv.id = ail.invoice_id 
            JOIN account_invoice_line_tax ailt ON ailt.invoice_line_id = ail.id 
            JOIN account_tax at2 ON at2.id = ailt.tax_id 
            WHERE inv."type" IN ('out_invoice', 'out_refund') AND
            at2.code = 'PVM5' AND
            inv.state IN ('paid', 'open') AND
            inv.date_invoice >= %s AND
            inv.date_invoice <= %s;"""
        self.env.cr.execute(pvm5_income_query, (date_from_str, date_to_str))
        pvm5_total_income = self.env.cr.fetchall()[0][0]

        total_income_query = """
            SELECT SUM(price_subtotal_signed) FROM account_invoice_line ail 
            JOIN account_invoice inv ON inv.id = ail.invoice_id 
            WHERE inv."type" IN ('out_invoice', 'out_refund') AND
            inv.state IN ('paid', 'open') AND
            inv.date_invoice >= %s AND
            inv.date_invoice <= %s;"""
        self.env.cr.execute(total_income_query, (date_from_str, date_to_str))
        total_income = self.env.cr.fetchall()[0][0]
        if not pvm5_total_income or not total_income:
            return False
        # P3: DivOK -- Both fields are either none or float
        pvm5_income_as_percentage = (pvm5_total_income / total_income) * 100
        return pvm5_income_as_percentage > 5

    @api.one
    @api.depends('invoice_id.type')
    def _compute_print_fields(self):
        sign = -1.0 if 'refund' in self.invoice_id.type else 1.0
        self.print_qty = sign * self.quantity
        self.print_price_subtotal = sign * self.price_subtotal
        self.print_total_with_tax_amount = sign * self.total_with_tax_amount
        discount = self.price_unit * self.quantity - self.price_subtotal
        self.print_discount_currency = sign * discount
        self.print_price_subtotal_company = self.price_subtotal_signed
        self.print_total_with_tax_amount_company = sign * self.total_with_tax_amount_company
        discount_company = self.price_unit * self.quantity - sign * self.price_subtotal_signed
        self.print_discount_company_currency = sign * discount

    @api.onchange('product_id')
    def _onchange_product_id(self):
        res = super(AccountInvoiceLine, self)._onchange_product_id()
        if self.product_id and self.invoice_id.partner_id \
                and self.env.user.company_id.sudo().use_last_unit_price_of_account_invoice_line:
            last_invoice = self.env['account.invoice'].search([('partner_id', '=', self.invoice_id.partner_id.id),
                                                               ('invoice_line_ids.product_id', '=', self.product_id.id),
                                                               ('state', 'in', ('open', 'paid')),
                                                               ], order='date_invoice DESC', limit=1)
            if last_invoice:
                lines = last_invoice.invoice_line_ids.filtered(lambda x:
                                                               self.product_id.id == x.product_id.id,
                                                               ).sorted(key=lambda x: x.write_date, reverse=True)
                last_line = lines and lines[0]
                if last_line:
                    self.price_unit = last_line.price_unit if last_line else 1.0

        if not self.product_id:
            if self.invoice_id.type in ('in_invoice', 'in_refund'):
                self.account_id = self.env['account.account'].search([('code', '=', '6001')], limit=1).id
            else:
                self.account_id = self.env['account.account'].search([('code', '=', '5001')], limit=1).id
        return res

    @api.constrains('invoice_line_tax_ids')
    def _check_invoice_line_tax_price_include(self):
        """ Enforce same price_include """
        for rec in self:
            price_include = rec.invoice_id.price_include
            if any(tax.price_include != price_include for tax in rec.invoice_line_tax_ids):
                raise exceptions.ValidationError(_('Wrong type of tax. ') + (
                    _('It should be included in price') if price_include else _('It should not be included in price')))

    @api.constrains('invoice_line_tax_ids')
    def _check_invoice_line_tax_codes(self):
        """ Enforce some rules regarding tax code combination """
        for line in self:
            if len(line.invoice_line_tax_ids) > 2:
                raise exceptions.ValidationError(
                    _('Vienai eilutei negali būti priskirti daugiau nei du mokesčių kodai'))
            codes = line.mapped('invoice_line_tax_ids.code')
            if len(line.invoice_line_tax_ids) == 2:
                if sum(code.startswith('S') or code.startswith('A') for code in codes) != 1:
                    raise exceptions.ValidationError(
                        _('Vienoje eilutėje gali būti du mokesčių kodai, jei vienas iš jų prasideda kodu A arba S'))
            if 'A21' in codes and 'PVM1' in codes:
                raise exceptions.ValidationError(_('Vienoje eilutėje negali būti mokesčių kodai A21 ir PVM1'))
            if codes == ['S21']:
                raise exceptions.ValidationError(_('Mokesčių kodas S21 privalo būti pateiktas su kitu PVM kodu'))

    @api.onchange('amount_depends')
    def onchange_amount_depends(self):
        curr = self.currency_id
        if not curr:
            curr = self.invoice_id.currency_id
        if not curr:
            curr = self.env.user.company_id.currency_id
        amount = curr.round(self.amount_depends)
        if self._context.get('direct_trigger_amount_depends', False):
            self.price_subtotal_make_force_step = True
            self.price_subtotal_save_force_value = amount
            # P3: DivOK -- For all the following lines
            if self.quantity and not tools.float_is_zero((1 - (self.discount or 0.0) / 100.0), precision_digits=4):
                self.price_unit = (amount / self.quantity) / (1 - (self.discount or 0.0) / 100.0)
                for tax in self.invoice_line_tax_ids:
                    if tax.price_include and not self.invoice_id.price_include:
                        self.price_unit *= 1 + tax.amount / 100.0

    @api.onchange('discount', 'invoice_line_tax_ids', 'quantity')
    def _onchange_discount(self):
        if not self._context.get('not_update_make_force_step'):
            self.price_subtotal_make_force_step = False

    @api.onchange('price_unit')
    def _onchange_human(self):
        if self._context.get('triggered_field') == 'price_unit':
            self.price_subtotal_make_force_step = False

    @api.multi
    def _switch_to_nondeductible_taxes(self):
        """ Tries to switch invoice lines to non-deductible if the tax is not already non-deductible and it finds a match """
        for line in self:
            changes = []
            for tax in line.invoice_line_tax_ids:
                if tax.nondeductible:
                    continue
                new_tax = tax.with_context(do_not_raise_if_not_found=True).find_matching_nondeductible()
                if new_tax:
                    changes.append((3, tax.id,))
                    changes.append((4, new_tax.id,))
            if changes:
                line.invoice_line_tax_ids = changes

    @api.multi
    def switch_to_deductible_taxes(self):
        """ Tries to switch invoice lines to deductible
        if the tax is not already deductible and it finds a match """
        for line in self:
            changes = []
            for tax in line.invoice_line_tax_ids:
                if not tax.nondeductible:
                    continue
                new_tax = tax.with_context(do_not_raise_if_not_found=True).find_matching_deductible()
                if new_tax:
                    changes.append((3, tax.id,))
                    changes.append((4, new_tax.id,))
            if changes:
                line.invoice_line_tax_ids = changes

    @api.multi
    def _switch_to_nondeductible_profit_taxes(self):
        """ Tries to switch invoice lines to non-deductible if the tax is not already non-deductible and it finds a match """
        for line in self:
            changes = []
            for tax in line.invoice_line_tax_ids:
                if tax.nondeductible_profit:
                    continue
                new_tax = tax.with_context(do_not_raise_if_not_found=True).find_matching_nondeductible_profit()
                if new_tax:
                    changes.append((3, tax.id,))
                    changes.append((4, new_tax.id,))
            if changes:
                line.invoice_line_tax_ids = changes

    @api.model
    def create(self, vals):
        if 'invoice_line_tax_ids' in vals:
            if len(vals['invoice_line_tax_ids']) > 0:
                tax_ids_set = set()
                for line in vals['invoice_line_tax_ids']:
                    if line[0] == 6:
                        tax_ids_set = set(self.env['account.tax'].browse(line[2]).mapped('id'))
                    elif line[0] == 4:
                        tax_ids_set.add(self.env['account.tax'].browse(line[1]).id)
                    else:
                        continue
                tax_ids_obj = self.env['account.tax'].browse(list(tax_ids_set))
                child_ids = tax_ids_obj.mapped('child_tax_ids.id')
                tax_ids = tax_ids_obj.mapped('id')
                all_ids = list(set(tax_ids + child_ids))
                new_vals = [(6, 0, all_ids)]
                vals['invoice_line_tax_ids'] = new_vals
        line_id = super(AccountInvoiceLine, self).create(vals=vals)
        if 'invoice_line_tax_ids' in vals:
            line_id.invoice_id.compute_taxes()
        return line_id

    @api.multi
    def write(self, vals):
        if 'invoice_line_tax_ids' in vals:
            if len(vals['invoice_line_tax_ids']) > 0:
                tax_ids_set = set()
                for line in vals['invoice_line_tax_ids']:
                    if line[0] == 6:
                        tax_ids_set = set(self.env['account.tax'].browse(line[2]).mapped('id'))
                    elif line[0] == 4:
                        tax_ids_set.add(self.env['account.tax'].browse(line[1]).id)
                    else:
                        continue
                tax_ids_obj = self.env['account.tax'].browse(list(tax_ids_set))
                child_ids = tax_ids_obj.mapped('child_tax_ids.id')
                tax_ids = tax_ids_obj.mapped('id')
                all_ids = list(set(tax_ids + child_ids))
                new_vals = [(6, 0, all_ids)]
                vals['invoice_line_tax_ids'] = new_vals
        res = super(AccountInvoiceLine, self).write(vals=vals)
        fields_trigger_taxes = ['invoice_line_tax_ids', 'quantity', 'price_unit', 'discount']
        if any(f in vals for f in fields_trigger_taxes):
            self.mapped('invoice_id').compute_taxes()
        return res

    @api.multi
    def unlink(self):
        invoices = self.mapped('invoice_id')
        res = super(AccountInvoiceLine, self).unlink()
        invoices.exists().compute_taxes()
        return res

    def _set_taxes(self):
        """ Used in on_change to set taxes and price."""
        if self.invoice_id.type in ('out_invoice', 'out_refund'):
            taxes = self.product_id.taxes_id or self.account_id.tax_ids
        else:
            taxes = self.product_id.supplier_taxes_id or self.account_id.tax_ids

        # Keep only taxes of the company
        company_id = self.company_id or self.env.user.company_id
        taxes = taxes.filtered(lambda r: r.company_id == company_id)

        self.invoice_line_tax_ids = fp_taxes = self.invoice_id.fiscal_position_id.with_context(
            product_type=self.product_id.acc_product_type).map_tax(taxes)
        for tax in self.invoice_line_tax_ids:
            if not self.env.user.sudo().company_id.with_context({'date': self.invoice_id.get_vat_payer_date()}).vat_payer:
                self.invoice_line_tax_ids = [(3, tax.id,)]
                # code = tax.code
                # type_tax_use = tax.type_tax_use
                # self._cr.execute('select id from account_tax where code = %s and nondeductible=true '
                #                  'and company_id = %s and type_tax_use = %s', (code, company_id.id, type_tax_use,))
                # tax_ids_list = self._cr.fetchall()
                # tax_ids_list = map(lambda r: r[0], tax_ids_list)
                # changed_tax = taxes_obj.browse(tax_ids_list)
                # if changed_tax:
                #     self.invoice_line_tax_ids -= tax
                #     self.invoice_line_tax_ids |= changed_tax[0]
        if not self.price_unit:
            fix_price = self.env['account.tax']._fix_tax_included_price
            if self.invoice_id.type in ('in_invoice', 'in_refund'):
                prec = self.env['decimal.precision'].precision_get('Product Price')
                if not self.price_unit or tools.float_compare(self.price_unit, self.product_id.standard_price,
                                                              precision_digits=prec) == 0:
                    self.price_unit = fix_price(self.product_id.standard_price, taxes, fp_taxes)
            else:
                self.price_unit = fix_price(self.product_id.lst_price, taxes, fp_taxes)
        self._change_taxes_price_included()


    @api.one
    def _change_taxes_price_included(self):
        price_include = self.invoice_id.price_include_selection == 'inc'
        tax_obj = self.env['account.tax']
        taxes = []
        for tax in self.invoice_line_tax_ids:
            if tax.price_include != price_include:
                taxes.append((3, tax.id))
                # FIXME: Should we keep that name check? Seems sketchy
                # if price_include and not tax.name.endswith(' su PVM'):
                #     new_name = tax.name + ' su PVM'
                # elif len(tax.name) > 7:
                #     new_name = tax.name[:-7]
                # else:
                #     raise exceptions.UserError(_('Netinkamas mokesčio pavadinimas %s') % tax.name)
                tax_id = tax_obj.search([('nondeductible', '=', tax.nondeductible),
                                         ('nondeductible_profit', '=', tax.nondeductible_profit),
                                         ('code', '=', tax.code),
                                         ('price_include', '=', price_include)],
                                        limit=1)
                if tax_id:
                    taxes.append((4, tax_id.id))
        if taxes:
            self.invoice_line_tax_ids = taxes

    @api.multi
    def get_invoice_line_account(self, type, product, fpos, company):
        if self._context.get('type') == 'out_refund':
            account_id = self.product_id.refund_expense_account_id or self.product_id.categ_id.refund_expense_account_id
            if account_id:
                return account_id
        if type == 'in_refund':
            account_id = product.refund_income_account_id or product.categ_id.refund_income_account_id
            if account_id:
                return account_id
        return super(AccountInvoiceLine, self).get_invoice_line_account(type, product, fpos, company)

    def get_rounded_price_unit(self, values):
        price_unit = values.get('price_unit', 0.0)
        quantity = values.get('quantity', 0.0)
        digits = self.env['decimal.precision'].precision_get('Product Price')

        if digits:
            price = tools.float_round(price_unit * quantity, precision_digits=digits)
        else:
            curr_id = values.get('currency_id', False)
            curr = self.env['res.currency'].browse(curr_id)

            if not curr:
                curr_id = values['invoice_id']['currency_id']
                curr = self.env['res.currency'].browse(curr_id)
            if not curr:
                curr = self.env.user.company_id.currency_id

            price = curr.round(price_unit * quantity)
        # P3: DivOK
        price_unit = price / quantity if quantity else price_unit

        return price_unit

    @staticmethod
    def _get_fields_trigger_force_price():
        return ['discount', 'quantity']

    @api.multi
    def onchange(self, values, field_name, field_onchange):
        price_unit_changed = False
        if (isinstance(field_name, basestring) and field_name == 'price_unit' or
                isinstance(field_name, list) and 'price_unit' in field_name):
            price_unit_changed = True
            self = self.with_context(triggered_field='price_unit')
            price_unit = self.get_rounded_price_unit(values)
            values.update({'price_unit': price_unit})
        fields_trigger_force_price = self._get_fields_trigger_force_price()
        if (isinstance(field_name, basestring) and field_name not in fields_trigger_force_price or
                isinstance(field_name, list) and len(field_name) == 1 and field_name not in fields_trigger_force_price):
            self = self.with_context(not_update_make_force_step=True)
        res = super(AccountInvoiceLine, self).onchange(values, field_name, field_onchange)
        if price_unit_changed:
            res['value'].setdefault('price_unit', price_unit)

        return res
