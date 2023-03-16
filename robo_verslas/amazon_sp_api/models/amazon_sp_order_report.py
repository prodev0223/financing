# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class AmazonSPOrderReport(models.Model):
    _name = 'amazon.sp.order.report'
    _description = _(
        'Model that is used to collect significant information about '
        'Amazon orders and their lines and display them in a pivot view'
    )
    _auto = False

    # Oder fields
    ext_order_id = fields.Char(string='Order ID')
    state = fields.Selection([
        ('imported', 'Order imported'),
        ('created', 'Order created'),
        ('ext_cancel', 'Order canceled externally'),
        ('failed', 'Failed to create the order')
    ], string='State')

    external_state = fields.Char(string='External order status')
    factual_order_day = fields.Date(string='Order date')
    refund_order = fields.Boolean(string='Refund order')

    # Line fields
    asin_product_code = fields.Char(string='ASIN product code')
    total_report_display_amount = fields.Float(string='Total line amount')
    total_amount_untaxed = fields.Float(string='Total line amount (untaxed)')
    total_tax_amount = fields.Float(string='Total line tax amount')

    line_type = fields.Selection(
        [('principal', 'Main product/service'),
         ('shipping', 'Shipping fees'),
         ('promotion', 'Discounts/Promotion coupons'),
         ('fees', 'Other fees'),
         ('withheld_taxes', 'Withheld taxes'),
         ('gift_wraps', 'Gift wrap fees')],
        string='Order line type'
    )

    # Relational fields
    currency_id = fields.Many2one('res.currency', string='Currency')
    marketplace_id = fields.Many2one('amazon.sp.marketplace', string='Marketplace')
    invoice_id = fields.Many2one('account.invoice', string='Related invoice')
    product_id = fields.Many2one('product.product', string='Related product')

    @api.model_cr
    def init(self):
        self._cr.execute('DROP VIEW IF EXISTS amazon_sp_order_report')
        self._cr.execute("""
            CREATE VIEW amazon_sp_order_report AS (
                    SELECT aol.id AS id,
                           ao.ext_order_id,
                           ao.currency_id,
                           ao.marketplace_id,
                           ao.invoice_id,
                           ao.refund_order,
                           ap.product_id,
                           ao.state,
                           ao.external_state,
                           ao.factual_order_day,
                           aol.asin_product_code,
                           aol.total_amount_untaxed,
                           aol.total_tax_amount,
                           aol.total_report_display_amount,
                           aol.line_type
                    FROM amazon_sp_order_line AS aol 
                    INNER JOIN amazon_sp_order AS ao
                    ON aol.amazon_order_id = ao.id
                    LEFT JOIN amazon_sp_product AS ap ON
                    ap.asin_product_code = aol.asin_product_code)""")
