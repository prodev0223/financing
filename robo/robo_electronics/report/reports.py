# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, tools, exceptions
import odoo.addons.decimal_precision as dp
import math
from odoo.addons.robo_electronics.model.electronics import ELECTRONICS_CATEGORIES, BATTERY_TYPES


class ReportElectronics(models.Model):
    _name = "report.product.electronics"
    _auto = False

    picking_id = fields.Many2one('stock.picking', string='Dokumentas', sequence=2)
    product_tmpl_id = fields.Many2one('product.template', string='Produktas', sequence=3)
    partner_id = fields.Many2one('res.partner', 'Partneris')
    product_qty = fields.Float(string='Kiekis')

    product_electronics_category = fields.Selection(ELECTRONICS_CATEGORIES, _('Elektronikos kategorija'), sequence=1)
    weight_of_electronics = fields.Float(string='Elektroninkos svoris, kg')

    package_direction = fields.Selection([('in_lt', 'Įvežta iš Lietuvos'),
                                          ('in', 'Importas'),
                                          ('out_lt', 'Išleista į Lietuvos rinką'),
                                          ('out_kt', 'Išsiuntimai už Lietuvos ribų'),
                                          ('int', 'Vidiniai')],
                                         string='Pervežimo tipas')

    date = fields.Date(string='Data')
    origin = fields.Char(string='Susijęs dokumentas')

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
                         , product_template.product_electronics_category        AS product_electronics_category
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

                    WHERE stock_picking.state = 'done'
                      AND stock_picking.cancel_state <> 'error'                    
                ) report
            )""")

    def refresh_materialised_product_electronics_history(self):
        self._cr.execute(''' REFRESH MATERIALIZED VIEW report_product_electronics;''')


ReportElectronics()


class ReportBatteries(models.Model):
    _name = "report.product.batteries"
    _auto = False

    picking_id = fields.Many2one('stock.picking', string='Dokumentas', sequence=4)
    product_tmpl_id = fields.Many2one('product.template', string='Produktas', sequence=3)
    partner_id = fields.Many2one('res.partner', string='Partneris', sequence=5)

    battery_id = fields.Many2one('product.battery', string='Baterija', sequence=1)
    battery_category = fields.Selection(BATTERY_TYPES, _('Baterijos kategorija'), sequence=2)
    qty_of_batteries = fields.Float(string='#Baterijų')
    weight_of_batteries = fields.Float(string='Baterijų svoris, kg')

    package_direction = fields.Selection([('in_lt', 'Įvežta iš Lietuvos'),
                                          ('in', 'Importas'),
                                          ('out_lt', 'Išleista į Lietuvos rinką'),
                                          ('out_kt', 'Išsiuntimai už Lietuvos ribų'),
                                          ('int', 'Vidiniai')],
                                         string='Pervežimo tipas')

    date = fields.Date(string='Data')
    origin = fields.Char(string='Susijęs dokumentas')
    move_id = fields.Many2one('stock.move',sequence=6)

    @api.model_cr
    def init(self):
        self._cr.execute('Drop MATERIALIZED VIEW IF EXISTS report_product_batteries')
        self._cr.execute("""
    CREATE MATERIALIZED VIEW report_product_batteries AS (

        SELECT ROW_NUMBER() OVER (ORDER BY product_tmpl_id) AS id, * FROM
        (
            SELECT 
                   stock_picking.id                                             AS picking_id
                 , product_product.product_tmpl_id                              AS product_tmpl_id
                 , stock_picking.partner_id                                     AS partner_id
                 , product_battery.id                                           AS battery_id
                 , product_battery.category                                     AS battery_category
                 , stock_move.product_qty * product_battery_line.battery_qty    AS qty_of_batteries
                 , stock_move.product_qty * product_battery_line.battery_qty 
                   * product_battery.weight                                     AS weight_of_batteries
                 , stock_picking.package_direction                              AS package_direction
                 , stock_picking.min_date::date                                 AS date
                 , stock_picking.origin                                         AS origin
                 , product_battery_line.date_from                               AS date_from
                 , product_battery_line.date_to                                 AS date_to
                 , stock_move.id                                                AS move_id
            FROM stock_picking
            
            LEFT JOIN stock_move
                    ON stock_picking.id = stock_move.picking_id
            LEFT JOIN product_product
                    ON product_product.id = stock_move.product_id
            LEFT JOIN product_template
                    ON product_template.id = product_product.product_tmpl_id
            INNER JOIN product_battery_line
                    ON product_battery_line.product_tmpl_id = product_template.id
            LEFT JOIN product_battery
                    ON product_battery.id = product_battery_line.battery_id                                  
        
            WHERE stock_picking.state = 'done'
              AND stock_picking.cancel_state <> 'error'
              AND (date_to IS NULL
                   OR date_to >= stock_picking.min_date::date)
              AND (date_from IS NULL
                   OR date_from <= stock_picking.min_date::date)
        ) report
    )"""
                         )

    def refresh_materialised_product_batteries_history(self):
        self._cr.execute(''' REFRESH MATERIALIZED VIEW report_product_batteries;''')


ReportBatteries()
