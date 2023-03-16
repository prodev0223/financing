# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools


class ScoroInvoiceLine(models.Model):
    _name = 'scoro.invoice.line'

    # Scoro fields
    external_id = fields.Integer(string='Išorinis ID')

    product_name = fields.Char(string='Produkto pavadinimas')
    product_code = fields.Char(string='Produkto kodas')
    external_product_id = fields.Integer(string='Išorinis produkto ID')

    vat_rate = fields.Float(string='PVM procentas')
    vat_code = fields.Char(string='PVM kodas')
    vat_code_id = fields.Integer(string='PVM kodo ID')

    margin_supplier_name = fields.Char(string='Tiekėjo pavadinimas (marža)')
    margin_cost = fields.Float(string='Suma (marža)')
    margin_supplier_id = fields.Integer(string='Tiekėjo ID (marža)')

    finance_account_name = fields.Char(string='Finansinės sąskaitos pavadinimas')
    finance_account_id = fields.Integer(string='Finansinės sąskaitos ID')

    project_name = fields.Char(string='Projekto pavadinimas')
    project_id = fields.Integer(string='Susijusio projekto ID')

    line_name = fields.Char(string='Eilutės komentaras')
    add_line_name = fields.Char(string='Eilutės komentaras (papildomas)')

    price_unit = fields.Float(string='Vieneto kaina')
    quantity = fields.Float(string='Kiekis')
    add_quantity = fields.Float(string='Kiekis (papildomas)')
    discount = fields.Float(string='Nuolaida')
    sum_wo_vat = fields.Float(string='Suma be PVM')
    unit_name = fields.Char(string='Matavimo vieneto pavadinimas')

    is_internal = fields.Boolean(string='Vidinė eilutė')

    # System fields
    scoro_tax_id = fields.Many2one('scoro.tax', string='Scoro Mokesčiai', compute='_scoro_tax_id', store=True)
    scoro_invoice_id = fields.Many2one('scoro.invoice', string='Susijusi Scoro sąskaita')
    product_id = fields.Many2one('product.product', string='Produktas', compute='_product_id', store=True)
    tax_id = fields.Many2one('account.tax', string='Susiję mokesčiai', compute='_tax_id', store=True)
    invoice_id = fields.Many2one('account.invoice', string='Sisteminė sąskaita')
    invoice_line_id = fields.Many2one('account.invoice.line', string='Sisteminė sąskaitos eilutė')
    state = fields.Selection([('imported', 'Eilutė importuota'),
                              ('created', 'Eilutė sukurta sistemoje'),
                              ('failed', 'Klaida kuriant Eilutė'),
                              ('warning', 'Eilutė importuota su įspėjimais')],
                             string='Būsena', default='imported', track_visibility='onchange')

    @api.one
    @api.depends('external_product_id')
    def _product_id(self):
        if self.external_product_id and self.env.user.company_id.scoro_stock_accounting:
            product_id = self.env['product.product'].search(
                [('scoro_external_id', '=', self.external_product_id)], limit=1)
            self.product_id = product_id.id

    @api.one
    @api.depends('scoro_tax_id.tax_id')
    def _tax_id(self):
        self.tax_id = self.scoro_tax_id.tax_id

    @api.one
    @api.depends('scoro_invoice_id.invoice_based_tax', 'scoro_invoice_id.vat_code_id', 'vat_code_id')
    def _scoro_tax_id(self):
        invoice_based_tax = self.scoro_invoice_id.invoice_based_tax
        eu_partner = True if self.scoro_invoice_id.partner_id.country_id.code not in ['LT'] else False
        if invoice_based_tax:
            scoro_tax_id = self.env['scoro.tax'].search(
                [('vat_code_id', '=', self.scoro_invoice_id.vat_code_id)], limit=1)
        else:
            scoro_tax_id = self.env['scoro.tax'].search([('vat_code_id', '=', self.vat_code_id)], limit=1)
        if eu_partner and tools.float_is_zero(
                scoro_tax_id.vat_percent, precision_digits=2) and not scoro_tax_id.force_eu_partners:
            res = self.env['scoro.tax'].search([]).filtered(lambda x: x.force_eu_partners)
            if res and len(res) == 1:
                scoro_tax_id = res
        self.scoro_tax_id = scoro_tax_id

    @api.one
    def recompute_taxes(self):
        self._scoro_tax_id()
        self._tax_id()

    @api.multi
    def recompute_fields(self):
        self._scoro_tax_id()
        self._tax_id()
        self._product_id()


ScoroInvoiceLine()
