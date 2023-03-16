# -*- coding: utf-8 -*-
from odoo import api,fields, models


class ReportProductElectronics(models.Model):
    _inherit = "report.product.electronics"
    _auto = False

    product_electronics_category = fields.Many2one('gpais.klasifikacija', string='Elektronikos kategorija', sequence=1)

    @api.model_cr
    def init(self):
        self._cr.execute('Drop MATERIALIZED VIEW IF EXISTS report_product_electronics')
        self._cr.execute("""
    CREATE MATERIALIZED VIEW report_product_electronics AS (

        SELECT ROW_NUMBER() OVER (ORDER BY product_tmpl_id) AS id, * FROM
        (
            SELECT 
                   stock_picking.id                                     AS picking_id
                 , product_product.product_tmpl_id                      AS product_tmpl_id
                 , stock_move.product_qty                               AS product_qty
                 , stock_picking.partner_id                             AS partner_id
                 , gpais_klasifikacija.id                               AS product_electronics_category
                 , product_template.weight * stock_move.product_qty     AS weight_of_electronics
                 , stock_picking.package_direction                      AS package_direction
                 , stock_picking.min_date::date                         AS date
                 , stock_picking.origin                                 AS origin

            FROM stock_picking
            
            LEFT JOIN stock_move
                    ON stock_picking.id = stock_move.picking_id
            LEFT JOIN product_product
                    ON product_product.id = stock_move.product_id
            LEFT JOIN product_template
                    ON product_template.id = product_product.product_tmpl_id
            INNER JOIN gpais_klasifikacija
                    ON product_template.klasifikacija = gpais_klasifikacija.id                          

            WHERE stock_picking.state = 'done'
              AND stock_picking.cancel_state <> 'error'
              AND gpais_klasifikacija.product_type = 'elektronineIranga'
        ) AS report
    )""")
