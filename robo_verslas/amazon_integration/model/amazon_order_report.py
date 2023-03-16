# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AmazonOrderReport(models.Model):
    """
    Model that is used to collect significant information about
    Amazon orders and their lines and display them in a pivot view
    """
    _name = 'amazon.order.report'
    _auto = False

    order_id = fields.Char(string='Užsąkymo numeris')
    currency_id = fields.Many2one('res.currency', string='Valiuta')
    marketplace_id = fields.Many2one('amazon.marketplace', string='Prekiavietė')
    invoice_id = fields.Many2one('account.invoice', string='Sisteminė sąskaita')
    product_id = fields.Many2one('product.product', string='Sisteminis produktas')
    state = fields.Selection([('imported', 'Užsakymas importuotas'),
                              ('created', 'Užsakymas sukurtas sistemoje'),
                              ('ext_cancel', 'Užsakymas atšauktas išorinėje sistemoje'),
                              ('failed', 'Klaida kuriant užsakymą')],
                             string='Būsena', default='imported')
    ext_order_status = fields.Char(string='Išorinis užsakymo statusas')
    order_date = fields.Date(string='Užsakymo data')
    refund_order = fields.Boolean(string='Grąžinimas')
    asin_product_code = fields.Char(string='ASIN produkto kodas')
    line_amount = fields.Float(string='Suma')
    line_type = fields.Selection(
        [('principal', 'Pagrindinė paslauga/produktas'),
         ('shipping', 'Siuntimo mokesčiai'),
         ('promotion', 'Nuolaida'),
         ('gift_wraps', 'Pakavimo mokestis')], string='Eilutės tipas')

    @api.model_cr
    def init(self):
        self._cr.execute('DROP VIEW IF EXISTS amazon_order_report')
        self._cr.execute("""
            CREATE VIEW amazon_order_report AS (
                    SELECT aol.id AS id,
                           ao.order_id,
                           ao.currency_id,
                           ao.marketplace_id,
                           ao.invoice_id,
                           ao.refund_order,
                           ap.product_id,
                           ao.state,
                           ao.ext_order_status,
                           ao.order_date,
                           aol.asin_product_code,
                           aol.line_amount,
                           aol.line_type
                    FROM amazon_order_line AS aol 
                    INNER JOIN amazon_order AS ao
                    ON aol.amazon_order_id = ao.id
                    LEFT JOIN amazon_product AS ap ON
                    ap.asin_product_code = aol.asin_product_code
                    WHERE line_type <> 'fees')""")


AmazonOrderReport()
