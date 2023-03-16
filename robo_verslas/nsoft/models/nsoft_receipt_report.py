# -*- coding: utf-8 -*-

from odoo import models, fields, api


class NsoftReceiptReport(models.Model):
    _name = 'nsoft.receipt.report'
    _auto = False

    receipt_id = fields.Char(string='Čekio numeris')
    receipt_total = fields.Float(string='Čekių suma')
    partner_id = fields.Many2one('res.partner', string='Susietas partneris')
    cash_register_id = fields.Many2one('nsoft.cash.register', string='Susietas kasos aparatas')
    sale_date = fields.Date(string='Data')
    avg_receipt = fields.Float(string='Vidutinė čekio suma', group_operator='avg')
    product_id = fields.Many2one('product.product', string='Produktas')
    product_category_id = fields.Many2one('product.category', string='Produkto kategorija')

    @api.model_cr
    def init(self):
        self._cr.execute('DROP VIEW IF EXISTS nsoft_receipt_report')
        self._cr.execute("""
            CREATE VIEW nsoft_receipt_report AS (
            SELECT ROW_NUMBER() OVER (order by receipt_id) AS id, * FROM (
                SELECT *, receipt_total as avg_receipt FROM(
                    SELECT receipt_id, SUM(sale_price) AS receipt_total, cash_register_id, sale_date,
                    nsoft_cash_register.partner_id, product_id, product_template.categ_id AS product_category_id FROM 
                    nsoft_sale_line INNER JOIN nsoft_cash_register ON 
                    nsoft_sale_line.cash_register_id = nsoft_cash_register.id 
                    INNER JOIN product_product ON nsoft_sale_line.product_id = product_product.id
                    INNER JOIN product_template ON product_product.product_tmpl_id = product_template.id
                    WHERE product_template.type = 'product' and invoice_id IS NOT NULL
             GROUP BY receipt_id, cash_register_id, product_id, product_template.categ_id,
             nsoft_cash_register.partner_id, sale_date) rep1) AS rep2)""")


NsoftReceiptReport()
