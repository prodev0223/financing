# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, tools


class NsoftInvoiceLine(models.Model):
    _name = 'nsoft.invoice.line'
    _description = 'nSoft lines that belong to specific external invoice'
    _inherit = ['mail.thread']

    ext_id = fields.Integer(string='Išorinis identifikatorius')
    name = fields.Char(string='Prekės pavadinimas')
    product_code = fields.Char(string='Prekės kodas', required=True, inverse='_product_code')
    product_id = fields.Many2one('product.product', compute='_product_id', store=True)
    quantity = fields.Float(string='Kiekis')
    price_unit = fields.Float(string='Vnt. kaina be PVM')
    vat_price = fields.Float(string='Vnt. kaina su PVM')
    item_sum = fields.Float(string='Kaina be PVM')
    vat_sum = fields.Float(string='PVM Suma')
    discount = fields.Float(string='Nuolaida')
    ext_invoice_id = fields.Integer(string='Sąskaitos ID', inverse='_ext_invoice_id')
    vat_rate = fields.Float(string='Procentai')
    nsoft_invoice_id = fields.Many2one('nsoft.invoice', string='Susijusi nSoft sąskaita')
    tax_id = fields.Many2one('account.tax', compute='_tax_id', store=True, string='PVM')
    state = fields.Selection([('imported', 'Pardavimo eilutė importuota'),
                              ('created', 'Sąskaita sukurta sistemoje'),
                              ('failed', 'Klaida kuriant sąskaitą'),
                              ('failed2', 'Pardavimo eilutė importuota su įspėjimais')],
                             string='Būsena', default='imported', track_visibility='onchange')
    invoice_id = fields.Many2one('account.invoice', string='Sukurta sąskaita faktūra',
                                 compute='_invoice', store=True)
    invoice_line_id = fields.Many2one('account.invoice.line', string='Sąskaitos faktūros eilutė')
    cash_register_id = fields.Many2one('nsoft.cash.register', string='nSoft kasos aparatas')
    nsoft_product_category_id = fields.Many2one('nsoft.product.category', string='nSoft produkto kategorija')
    ext_product_category_id = fields.Integer(string='Išorinis prekės categorijos ID',
                                             inverse='_ext_product_category_id')

    # Computes / Inverses --------------------------------------------------

    @api.one
    def _ext_product_category_id(self):
        """Inverse"""
        self.nsoft_product_category_id = self.env['nsoft.product.category'].search(
            [('external_id', '=', self.ext_product_category_id)])

    @api.one
    @api.depends('invoice_line_id')
    def _invoice(self):
        """Compute"""
        self.invoice_id = self.invoice_line_id.invoice_id

    @api.one
    def _ext_invoice_id(self):
        """Inverse"""
        if self.ext_invoice_id:
            self.nsoft_invoice_id = self.env['nsoft.invoice'].sudo().search(
                [('ext_id', '=', self.ext_invoice_id)], limit=1).id

    @api.one
    @api.depends('product_code')
    def _product_id(self):
        """Compute"""
        accounting_type = self.sudo().env.user.company_id.nsoft_accounting_type
        if (not accounting_type or accounting_type in ['detail']) and self.product_code:
            self.product_id = self.env['product.product'].sudo().search(
                [('default_code', '=', self.product_code)], limit=1).id
        elif accounting_type in ['sum'] and self.nsoft_product_category_id:
            self.product_id = self.nsoft_product_category_id.parent_product_id

    @api.one
    @api.depends('vat_rate')
    def _tax_id(self):
        """Compute"""
        code = str()
        if tools.float_compare(self.vat_rate, 21, precision_digits=2) == 0:
            code = 'PVM1'
        elif tools.float_compare(self.vat_rate, 5, precision_digits=2) == 0:
            code = 'PVM3'
        elif tools.float_compare(self.vat_rate, 9, precision_digits=2) == 0:
            code = 'PVM2'
        elif tools.float_compare(self.vat_rate, 0, precision_digits=2) == 0:
            code = 'PVM5'
        if code:
            tax_obj = self.env['account.tax'].sudo()
            self.tax_id = tax_obj.search([('code', '=', code), ('type_tax_use', '=', 'sale'),
                                          ('price_include', '=', True)], limit=1).id

    @api.one
    def _product_code(self):
        """Inverse"""
        cash_register_id = self.env['nsoft.cash.register'].sudo().search([('no_receipt_register', '=', True)]).id
        if cash_register_id:
            self.cash_register_id = cash_register_id
        else:
            journal_id = self.env['account.journal'].search([('code', '=', 'TCKNS')]).id
            values = {
                'cash_register_number': 'NO-RECEIPT-REGISTER',
                'no_receipt_register': True,
                'journal_id':  journal_id
            }
            self.cash_register_id = self.env['nsoft.cash.register'].sudo().with_context(allow_write=True).create(values)

    @api.multi
    def recompute_fields(self):
        self._tax_id()
        self._product_id()
        self._product_code()
        self._ext_invoice_id()
        self._invoice()


NsoftInvoiceLine()
