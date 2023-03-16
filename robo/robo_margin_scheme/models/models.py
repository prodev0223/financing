# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, exceptions, tools


class ProductCategory(models.Model):
    _inherit = 'product.category'

    use_margin_scheme = fields.Boolean(string='Taikyti maržos schemą', default=False)


ProductCategory()


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    margin_scheme_used = fields.Boolean(compute='_compute_margin_scheme_used')

    @api.one
    @api.depends('invoice_line_ids.product_id', 'type')
    def _compute_margin_scheme_used(self):
        if self.type not in ['out_invoice', 'out_refund']:
            self.margin_scheme_used = False
        else:
            self.margin_scheme_used = any(
                self.invoice_line_ids.filtered(lambda r: r.product_id.categ_id.use_margin_scheme))


    # TODO: If current version is not user friendly for accountants (i.e. if they report something)
    # TODO: Uncomment and improve this onchange
    # @api.onchange('tax_line_ids')
    # def apply_simulated_margin_scheme(self):
    #     for rec in self:
    #         for tax_line in rec.tax_line_ids:
    #             total_line_margin_value = 0.0
    #             ail = rec.invoice_line_ids.filtered(lambda x: tax_line.tax_id.code in
    #                                                 x.invoice_line_tax_ids.mapped('code') and not
    #                                                 any(f.margin_invoice_line_id for f in x.invoice_line_tax_ids))
    #             if ail:
    #                 for line in ail:
    #                     quant = self.env['stock.quant'].search([('product_id', '=', line.product_id.id),
    #                                                             ('location_id.usage', '=', 'internal')],
    #                                                            order='in_date asc', limit=1)
    #                     if quant:
    #                         purchase_value = quant.inventory_value
    #                         sale_value = line.price_unit
    #                         margin_value = round(float(sale_value - purchase_value) * 21 / 121, 2)
    #                         margin_value = 0 if margin_value < 0 else margin_value
    #                         total_line_margin_value += margin_value
    #                 tax_line.amount = total_line_margin_value

    @api.multi
    def action_invoice_open(self):
        for inv in self.filtered(lambda x: x.type in ['in_invoice']):
            for rec in inv.invoice_line_ids:
                if rec.product_id.categ_id.use_margin_scheme:
                    inv_line = self.env['account.invoice.line'].search([('product_id', '=', rec.product_id.id),
                                                                        ('invoice_id.type', '=', 'in_invoice'),
                                                                        ('id', '!=', rec.id)])
                    if inv_line:
                        refund_line = self.env['account.invoice.line'].search([('product_id', '=', rec.product_id.id),
                                                                               ('invoice_id.type', '=', 'in_refund')])
                        if not refund_line:
                            body = 'Produktas {} jau yra įsigytas su sąskaita {}'.format(
                                rec.product_id.display_name or '', inv_line.invoice_id.reference or '')
                            raise exceptions.ValidationError(body)
        return super(AccountInvoice, self).action_invoice_open()

    @api.onchange('price_include_selection')
    def onchange_price_include(self):
        for rec in self:
            if rec.invoice_line_ids and any(line.product_id.categ_id.use_margin_scheme for line in
                                            rec.invoice_line_ids) and not self._context.get('prevent_loop', False):
                rec.price_include_selection = 'inc'
                super(AccountInvoice, rec.with_context(prevent_loop=True)).onchange_price_include()
            else:
                super(AccountInvoice, rec).onchange_price_include()

    @api.multi
    def write(self, vals):
        res = super(AccountInvoice, self).write(vals)
        for rec in self:
            for line in rec.invoice_line_ids:
                if line.invoice_id.type in ['out_invoice', 'out_refund'] and \
                        line.product_id.categ_id.use_margin_scheme and not \
                        self._context.get('skip_margin_computations', False):
                    margin_amount = 0.0
                    quant = self.env['stock.quant'].search([('product_id', '=', line.product_id.id),
                                                            ('location_id.usage', '=', 'internal')],
                                                           order='in_date asc', limit=1)
                    if quant:
                        purchase_value = quant.inventory_value
                        sale_value = line.price_unit
                        margin_value = tools.float_round(
                            float(sale_value - purchase_value) * 21 / 121, precision_digits=2)
                        margin_amount = 0 if margin_value < 0 else margin_value
                    else:
                        inv_line = self.env['account.invoice.line'].search([('product_id', '=', line.product_id.id),
                                                                            ('invoice_id.type', '=', 'in_invoice')],
                                                                           order='create_date desc', limit=1)
                        if inv_line:
                            purchase_value = inv_line.price_unit_tax_included
                            sale_value = line.price_unit
                            margin_value = tools.float_round(
                                float(sale_value - purchase_value) * 21 / 121, precision_digits=2)
                            margin_amount = 0 if margin_value < 0 else margin_value

                    self.env.cr.execute('''
                    SELECT ID FROM account_tax WHERE margin_invoice_line_id = %s''', (line.id,))
                    res_id = self.env.cr.fetchone()
                    res_id = res_id[0] if res_id and res_id[0] is not None else 0
                    margin_tax = self.env['account.tax'].browse(res_id) if res_id else False
                    if margin_tax:
                        margin_tax.amount = margin_amount
                    else:
                        account_id = self.env['account.account'].search([('code', '=', '44921')])
                        tag_ids = self.env['account.account.tag'].search([('code', 'in', ['16', '35'])])
                        margin_tax = self.env['account.tax'].create({
                            'name': 'Marža (0%) - #{}'.format(str(line.id)),
                            'code': 'PVM32',
                            'amount': margin_amount,
                            'amount_type': 'fixed',
                            'type_tax_use': 'purchase',
                            'account_id': account_id.id,
                            'refund_account_id': account_id.id,
                            'description': '0% - Su PVM',
                            'active': True,
                            'margin_invoice_line_id': line.id,
                            'tag_ids': [(6, 0, tag_ids.ids)],
                            'price_include': True,
                            'long_description': _('Atvejai, kai sandoriams taikoma speciali apmokestinimo schema (marža) (PVMĮ 106-110 str.)'),
                            'show_description': True,
                        })
                    line.with_context(skip_margin_computations=True
                                      ).invoice_line_tax_ids = [(6, 0, margin_tax.ids)]
                    if line.invoice_id.price_include_selection in ['exc']:
                        vals['price_include_selection'] = 'inc'
        return res


AccountInvoice()


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    margin_line = fields.Boolean(compute='_margin_line')

    @api.multi
    @api.depends('product_id')
    def _margin_line(self):
        for rec in self:
            if rec.product_id.categ_id.use_margin_scheme:
                rec.margin_line = True
            else:
                rec.margin_line = False

    @api.onchange('product_id')
    def onchange_margin_product_id(self):
        for rec in self:
            if rec.product_id.categ_id.use_margin_scheme:
                tax_id = self.env['account.tax'].search(
                    [('code', '=', 'PVM32'),
                     ('type_tax_use', '=', 'sale'),
                     ('price_include', '=', False)], limit=1).ids
                rec.invoice_line_tax_ids = tax_id

    @api.multi
    def unlink(self):
        line_ids = self.ids
        res = super(AccountInvoiceLine, self).unlink()
        self.env.cr.execute('''DELETE FROM account_tax WHERE margin_invoice_line_id in %s''', (tuple(line_ids),))
        return res


AccountInvoiceLine()


class AccountTax(models.Model):
    _inherit = 'account.tax'

    margin_invoice_line_id = fields.Integer(string='Margin invoice line')

    @api.model
    def cron_delete_unused_margin_taxes(self):
        to_unlink = self.env['account.tax']
        tax_lines = self.search([('margin_invoice_line_id', '!=', 0)])
        for line_id in tax_lines:
            if not self.env['account.invoice.line'].search_count([('id', '=', line_id.margin_invoice_line_id)]):
                to_unlink += line_id
        to_unlink.unlink()


AccountTax()
