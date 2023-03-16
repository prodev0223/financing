# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, tools, _


class RasoInvoicesLine(models.Model):
    _name = 'raso.invoices.line'
    _inherit = ['mail.thread', 'raso.line.base']

    raso_invoice_id = fields.Many2one('raso.invoices', string='Susieta sąskaita')
    raso_invoice_number = fields.Char(string='Raso sąskaitos numeris')
    sale_date = fields.Datetime(required=True, string='Pardavimo data')
    code = fields.Char(required=True, string='Produkto barkodas')
    name = fields.Char(required=True, string='Produkto pavadinimas')
    qty = fields.Float(string='Kiekis')
    amount = fields.Float(string='Kaina su PVM', digits=(12, 3))
    price_unit = fields.Float(compute='compute_price_unit')
    discount = fields.Float(string='Nuolaida')
    vat_sum = fields.Float(string='PVM suma', digits=(12, 3))

    has_man = fields.Boolean(compute='get_has_man')
    vat_sum_man = fields.Float(string='PMV suma (RN)', digits=(12, 3))
    qty_man = fields.Float(string='Kiekis (RN)')
    amount_man = fields.Float(string='Kaina su PVM (RN)', digits=(12, 3))
    price_unit_man = fields.Float(compute='compute_price_unit_man')
    man_tax_id = fields.Many2one('account.tax', compute='_compute_man_tax_id', string='PVM man')
    tax_id = fields.Many2one('account.tax', compute='_compute_tax_id', store=True, string='PVM')
    product_id = fields.Many2one('product.product', compute='get_product_id', store=True)
    invoice_id = fields.Many2one('account.invoice')
    invoice_line_id = fields.Many2one('account.invoice.line')
    force_taxes = fields.Boolean(default=False)
    line_type = fields.Char(compute='get_line_type', store=True)
    state = fields.Selection([('imported', 'Importuota'),
                              ('created', 'Sukurta'),
                              ('failed', 'Klaida kuriant sąskaitą'),
                              ('warning', 'Importuota su įspėjimais')],
                             string='Būsena', default='imported', track_visibility='onchange')

    @api.one
    @api.depends('amount_man', 'qty_man', 'has_man')
    def compute_price_unit_man(self):
        if self.has_man:
            self.price_unit_man = self.amount_man / self.qty_man if self.qty_man else 0

    @api.one
    @api.depends('amount', 'qty')
    def compute_price_unit(self):
        self.price_unit = self.amount / self.qty if self.qty else 0

    @api.multi
    def open_inv_line(self):
        self.ensure_one()
        return {
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'raso.invoices.line',
                'res_id': self.id,
                'view_id': self.env.ref('raso_retail.raso_invoiceline_form').id,
                'type': 'ir.actions.act_window',
                'target': 'current',
        }

    @api.one
    @api.depends('code')
    def get_product_id(self):
        if self.code:
            self.product_id = self.env['product.product'].search([('barcode', '=', self.code)])

    @api.one
    @api.depends('qty_man', 'amount_man')
    def get_has_man(self):
        if self.qty_man and self.amount_man:
            self.has_man = True
        else:
            self.has_man = False

    @api.multi
    @api.depends('qty', 'qty_man')
    def get_line_type(self):
        for rec in self:
            if tools.float_compare(rec.qty, 0.0, precision_digits=2) > 0 or \
                    tools.float_compare(rec.qty_man, 0.0, precision_digits=2) > 0:
                rec.line_type = 'out_invoice'
            else:
                rec.line_type = 'out_refund'

    @api.multi
    def unlink(self):
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Negalite ištrinti įrašų!'))
        return super(RasoInvoicesLine, self).unlink()
