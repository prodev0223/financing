# -*- coding: utf-8 -*-
from __future__ import division
import odoo.addons.decimal_precision as dp

from odoo import _, api, exceptions, fields, models, tools
from odoo.tools import float_compare


class InvoiceChangeLineWizard(models.TransientModel):
    _name = 'invoice.change.line.wizard'

    @api.multi
    def tax_line_ids_domain(self):
        if self._context.get('inv_type', False) == 'out':
            return [('type_tax_use', '=', 'sale')]
        else:
            return [('type_tax_use', '=', 'purchase')]

    invoice_line_id = fields.Many2one('account.invoice.line')
    product_id = fields.Many2one('product.product', string='Produktas')
    account_id = fields.Many2one('account.account', string='Sąskaita')
    name = fields.Char(string='Aprašymas')
    quantity = fields.Float(string='Kiekis', digits=dp.get_precision('Product Unit of Measure'))
    currency_id = fields.Many2one('res.currency', string='Valiuta')
    price_unit = fields.Float(string='Vnt. kaina', digits=dp.get_precision('Product Price'))
    deferred = fields.Boolean(string='Išskaidyti')
    invoice_line_tax_ids = fields.Many2many('account.tax',
                                            string='Mokesčiai', domain=tax_line_ids_domain)
    uom_id = fields.Many2one('product.uom')
    price_subtotal_make_force_step = fields.Boolean(string="Force step", default=False)
    price_subtotal_save_force_value = fields.Float(string="Force value", default=0.0)
    amount_depends = fields.Monetary(string='Suma', compute='_amount_depends', readonly=False)
    discount = fields.Float(string='Discount (%)', digits=dp.get_precision('Discount'),
                            default=0.0)
    has_picking = fields.Boolean(compute='_compute_has_picking')
    parent_force_taxes = fields.Boolean(compute='_parent_force_taxes')
    price_include = fields.Boolean(compute='_compute_price_include')
    type_tax_use = fields.Selection([('sale', 'Sales'), ('purchase', 'Purchases')], compute='_compute_type_tax_use')

    @api.one
    @api.depends('invoice_line_id')
    def _parent_force_taxes(self):
        if self.invoice_line_id.invoice_id.force_taxes:
            self.parent_force_taxes = True

    @api.multi
    @api.depends('invoice_line_id')
    def _compute_has_picking(self):
        """Checks whether related invoice has pickings"""
        for rec in self.filtered(lambda i: i.invoice_line_id):
            pickings = rec.invoice_line_id.invoice_id.get_related_pickings()
            if pickings:
                rec.has_picking = True

    @api.depends('invoice_line_id')
    def _compute_price_include(self):
        self.price_include = self.invoice_line_id.invoice_id.price_include

    @api.depends('invoice_line_id')
    def _compute_type_tax_use(self):
        self.type_tax_use = 'sale' if self.invoice_line_id.invoice_id.type in ['out_invoice', 'out_refund'] else 'purchase'

    @api.onchange('product_id')
    def _onchange_product_id(self):
        AccountAccount = self.env['account.account']

        rec = self._origin  # some record fields are empty only in an onchange method.. using _origin instead
        part = rec.invoice_line_id.invoice_id.partner_id
        company = rec.invoice_line_id.invoice_id.company_id
        currency = rec.invoice_line_id.invoice_id.currency_id
        invoice_type = rec.invoice_line_id.invoice_id.type

        if self.product_id:
            product = self.product_id.with_context(lang=part.lang or self.env.user.lang)
            line_name = product.partner_ref

            if invoice_type in ['out_invoice', 'out_refund']:
                product_account = product.get_product_income_account(return_default=True)
                if product.description_sale:
                    line_name += '\n' + product.description_sale
            else:
                product_account = product.get_product_expense_account(return_default=True)
                if product.description_purchase:
                    line_name += '\n' + product.description_purchase

            # Assign the values
            self.name = line_name
            self.account_id = product_account

            if not self.parent_force_taxes:
                # Do not change taxes if parent invoice has forced taxes
                invoice = rec.invoice_line_id.invoice_id
                if invoice.company_id.with_context({'date': invoice.get_vat_payer_date()}).vat_payer:
                    if rec.invoice_line_id.invoice_id.type in ('out_invoice', 'out_refund'):
                        taxes = self.product_id.taxes_id or self.account_id.tax_ids
                    else:
                        taxes = self.product_id.supplier_taxes_id or self.account_id.tax_ids

                    company_id = rec.invoice_line_id.company_id or self.env.user.company_id
                    taxes = taxes.filtered(lambda r: r.company_id == company_id)
                    fp_taxes = self.invoice_line_tax_ids
                    fix_price = self.env['account.tax']._fix_tax_included_price
                    if rec.invoice_line_id.invoice_id.type in ('in_invoice', 'in_refund'):
                        prec = self.env['decimal.precision'].precision_get('Product Price')
                        if not self.price_unit or float_compare(self.price_unit, self.product_id.standard_price,
                                                                precision_digits=prec) == 0:
                            self.price_unit = fix_price(self.product_id.standard_price, taxes, fp_taxes)
                    else:
                        self.price_unit = fix_price(self.product_id.lst_price, taxes, fp_taxes)
                else:
                    self.invoice_line_tax_ids = [(6, 0, [])]

            if not rec.uom_id or product.uom_id.category_id.id != rec.uom_id.category_id.id:
                self.uom_id = product.uom_id.id

            if company and currency:
                if rec.uom_id and rec.uom_id.id != product.uom_id.id:
                    self.price_unit = product.uom_id._compute_price(rec.price_unit, rec.uom_id)

    @api.multi
    def change_vals(self):
        self.ensure_one()
        is_accountant = self.env.user.is_accountant()
        skip_picking_creation = self._context.get('skip_stock') and is_accountant
        invoice = self.invoice_line_id.invoice_id
        if invoice.accountant_validated and not is_accountant:
            raise exceptions.UserError(_('Negalima keisti sąskaitos kuri patvirtinta buhalterio!'))
        if invoice.state in ['paid', 'open']:
            if self.product_id.type in ['service']:
                invoice = invoice.with_context(skip_stock=True)
            res = invoice.action_invoice_cancel_draft_and_remove_outstanding()

            # Get amount depends based on force fields
            amount_depends = self.price_subtotal_save_force_value if \
                self.price_subtotal_make_force_step else self.amount_depends
            # If taxes are not changed, and possible amounts are not changed -- skip ISAF redeclaration ticket sending
            if self.invoice_line_id.invoice_line_tax_ids == self.invoice_line_tax_ids and not \
                    tools.float_compare(self.invoice_line_id.price_unit, self.price_unit, precision_digits=2) and not \
                    tools.float_compare(self.invoice_line_id.quantity, self.quantity, precision_digits=2) and not \
                    tools.float_compare(amount_depends, self.invoice_line_id.amount_depends, precision_digits=2):
                invoice = invoice.with_context(skip_isaf_redeclaration=True)
            self.write_vals()
            invoice.with_context(skip_picking_creation=skip_picking_creation).action_invoice_open()
            invoice.action_re_assign_outstanding(res, raise_exception=False)

        return {'type': 'ir.actions.act_close_wizard_and_reload_view'}

    @api.onchange('amount_depends')
    def onchange_amount_depends(self):
        curr = self.currency_id or self.invoice_line_id.invoice_id.currency_id or self.env.user.company_id.currency_id
        amount = curr.round(self.amount_depends)
        original_id = self._origin.id
        if self._context.get('direct_trigger_amount_depends', False):
            self.price_subtotal_make_force_step = True
            self.price_subtotal_save_force_value = amount
            self.env.cr.execute('''
            UPDATE invoice_change_line_wizard 
            SET price_subtotal_make_force_step = true, 
            price_subtotal_save_force_value = %s 
            WHERE id = %s''', (amount, original_id,))
            # P3:DivOK -- All cases
            if self.quantity and not tools.float_is_zero((1 - (self.discount or 0.0) / 100.0), precision_digits=4):
                price_unit = (amount / self.quantity) / (1 - (self.discount or 0.0) / 100.0)
                for tax in self.invoice_line_tax_ids:
                    if tax.price_include and not self.invoice_line_id.invoice_id.price_include:
                        price_unit *= 1 + tax.amount / 100.0
                self.price_unit = price_unit
                self.env.cr.execute('''
                UPDATE invoice_change_line_wizard 
                SET price_unit = %s
                WHERE id = %s''', (price_unit, original_id,))
            self.env.cr.commit()
        else:
            self.price_subtotal_make_force_step = False
            self.env.cr.execute('''
            UPDATE invoice_change_line_wizard 
            SET price_subtotal_make_force_step = false
            WHERE id = %s''', (original_id,))

    @api.one
    @api.depends('price_unit', 'quantity',
                 'price_subtotal_make_force_step', 'price_subtotal_save_force_value', 'discount')
    def _amount_depends(self):
        if self.price_subtotal_make_force_step:
            self.amount_depends = self.price_subtotal_save_force_value
        else:
            self.amount_depends = tools.float_round(
                self.price_unit * self.quantity * (1 - ((self.discount / 100.0) or 0.0)), precision_digits=2)

    @api.one
    def write_vals(self):
        final_amount_to_use = self.price_subtotal_save_force_value if \
            self.price_subtotal_make_force_step else self.amount_depends
        vals = {
            'product_id': self.product_id.id,
            'account_id': self.account_id.id,
            'name': self.name,
            'quantity': self.quantity,
            'currency_id': self.currency_id.id,
            'price_unit': self.price_unit,
            'deferred': self.deferred,
            'amount_depends': final_amount_to_use,
            'price_subtotal_make_force_step': self.price_subtotal_make_force_step,
            'price_subtotal_save_force_value': final_amount_to_use,
        }
        if not self.invoice_line_id.invoice_id.force_taxes:
            vals['invoice_line_tax_ids'] = [(6, 0, self.invoice_line_tax_ids.ids)]
        self.invoice_line_id.write(vals)
        self.invoice_line_id._amount_depends()
