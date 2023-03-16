# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, _
from dateutil.parser import parse
import pytz


def convert_to_dt_str(date_str, offset):
    dt = parse(date_str + ' 00:00:00 ' + offset)
    dt = dt.astimezone(pytz.utc)
    return dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    supplier_note = fields.Char(string='Supplier delivery note')


StockPicking()


class StockMove(models.Model):
    _inherit = 'stock.move'

    product_category = fields.Many2one('product.category', string='Product category',
                                       related='product_id.product_tmpl_id.categ_id',
                                       store=True)
    picking_partner_id = fields.Many2one('res.partner', compute='_picking_partner_id', store=True)
    supplier_note = fields.Char(string='Supplier note', related='picking_id.supplier_note', store=True)

    @api.multi
    @api.depends('picking_id.partner_id')
    def _picking_partner_id(self):
        for rec in self:
            if rec.picking_id and rec.picking_id.partner_id:
                rec.picking_partner_id = rec.picking_id.partner_id.id
            else:
                rec.picking_partner_id = False


StockMove()


class StockMoveReport(models.Model):
    _name = 'stock.move.report'
    _inherit = 'read.group.full.expand'
    _auto = False

    @api.model
    def get_loc_prod_categ_domain(self, domain):
        real_dom = []
        for el in domain:
            if len(el) == 3:
                (key, operator, val) = el
                if key in ['product_id', 'product_category', 'location_id']:
                    if key == 'product_category':
                        key = 'product_categ_id'
                    real_dom.append((key, operator, val))
        return real_dom

    @api.model
    def get_add_ids(self, dom, target_field, product_ids=None, categ_ids=None, location_ids=None):
        real_dom = self.get_loc_prod_categ_domain(dom)
        if product_ids:
            real_dom.append(('product_id', 'not in', product_ids))
        if categ_ids:
            real_dom.append(('product_categ_id', 'not in', categ_ids))
        if location_ids:
            real_dom.append(('location_id', 'not in', location_ids))
        # real_dom.extend(dom)

        query = self.env['stock.history']._where_calc(real_dom)
        # order_by = self._generate_order_by(cr, user, order, query, context=context)
        from_clause, where_clause, where_clause_params = query.get_sql()

        where_str = where_clause and (" WHERE %s" % where_clause) or ''
        query_str = 'SELECT distinct(%s) FROM ' % target_field + from_clause + where_str
        self._cr.execute(query_str, where_clause_params)
        res = self._cr.fetchall()
        ids = [row[0] for row in res]
        return ids

    @api.model
    def _read_group_product_ids_full(self, products, domain, read_group_order=None, access_rights_uid=None):
        add_products = self.get_add_ids(domain, 'product_id', product_ids=products.ids)
        all_products = products + self.env['product.product'].browse(add_products)
        return all_products

    # @api.model
    # def _read_group_date_full(self, vals, domain, read_group_order=None, access_rights_uid=None):
    #     add_product_ids = self.get_add_ids(domain, 'product_id', product_ids=product_ids)
    #     all_product_ids = product_ids + add_product_ids
    #     all_products = self.env['product.product'].browse(all_product_ids)
    #     result = [product.name_get()[0] for product in all_products]
    #     return result, False

    @api.model
    def _read_group_categ_ids_full(self, categs, domain, read_group_order=None, access_rights_uid=None):
        add_categ_ids = self.get_add_ids(domain, 'product_categ_id', categ_ids=categs.ids)
        all_categs = categs + self.env['product.category'].browse(add_categ_ids)
        return all_categs

    @api.model
    def _read_group_location_ids_full(self, locations, domain, read_group_order=None, access_rights_uid=None):
        add_location_ids = self.get_add_ids(domain, 'location_id', location_ids=locations.ids)
        all_locations = locations + self.env['stock.location'].browse(add_location_ids)
        return all_locations

    product_id = fields.Many2one('product.product', string='Produktas', index=True,
                                 group_expand='_read_group_product_ids_full')
    product_category = fields.Many2one('product.category', string='Produkto kategorija',
                                       group_expand='_read_group_categ_ids_full')
    partner_id = fields.Many2one('res.partner', string='Partneris')
    picking_id = fields.Many2one('stock.picking', string='Važtaraščio numeris')
    transfer_reference = fields.Char(string='Tiekėjo važtaraščio nr.')
    location_id = fields.Many2one('stock.location', string='Vieta', group_expand='_read_group_location_ids_full')
    date = fields.Datetime(string='Data', index=True)
    qty_ordered = fields.Float(string='Užsakytas kiekis')
    start_stock = fields.Float(string='Pradinis likutis', sequence=1)
    start_value = fields.Float(string='Pradinė vertė', sequence=12)
    end_stock = fields.Float(string='Pabaigos likutis', sequence=11)
    end_value = fields.Float(string='Pabaigos vertė', sequence=22)
    qty_supplied = fields.Float(string='Gauta iš tiekėjų', sequence=2)
    value_supplied = fields.Float(string='Vertė iš tiekėjų', sequence=13)
    qty_delivered = fields.Float(string='Parduotas kiekis', sequence=6)
    value_delivered = fields.Float(string='Parduota vertė', sequence=17)
    qty_produced = fields.Float(string='Pagamintas kiekis', sequence=3)
    value_produced = fields.Float(string='Pagaminta vertė', sequence=14)
    qty_consumed = fields.Float(string='Suvartotas kiekis', sequence=7)
    value_consumed = fields.Float(string='Suvartota vertė', sequence=18)
    qty_in_reverse = fields.Float(string='Grąžintas kiekis klientams', sequence=4)
    value_in_reverse = fields.Float(string='Grąžinta vertė klientams', sequence=15)
    qty_out_reverse = fields.Float(string='Grąžintas kiekis tiekėjams', sequence=8)
    value_out_reverse = fields.Float(string='Grąžinta vertė tiekėjams', sequence=19)
    qty_scrap = fields.Float(string='Subrokuotas kiekis', sequence=9)
    value_scrap = fields.Float(string='Subrokuota vertė', sequence=20)
    qty_in_other = fields.Float(string='Kitas gautas kiekis', sequence=5)
    value_in_other = fields.Float(string='Kita gauta vertė', sequence=16)
    qty_out_other = fields.Float(string='Kitas išsiųstas kiekis', sequence=10)
    value_out_other = fields.Float(string='Kita išsiųsta vertė', sequence=21)

    @api.multi
    def name_get(self):
        return [(rec.id, "%s - %s" % (rec['product_id'].name, rec['location_id'].name)) for rec in self]

    @api.model_cr
    def init(self):
        self._cr.execute('Drop MATERIALIZED VIEW IF EXISTS stock_move_report')
        self._cr.execute("""
            CREATE MATERIALIZED VIEW stock_move_report AS (
              SELECT
              ROW_NUMBER() OVER (order by product_id) AS id,
              product_id,
              product_category,
              sum(qty_ordered) as qty_ordered,
              date,
              location_id,
              0.0 as start_stock,
              0.0 as end_stock,
              partner_id,
              picking_id,
              transfer_reference,
              0.0 as start_value,
              0.0 as end_value,
              sum(qty_supplied) as qty_supplied,
              sum(value_supplied) as value_supplied,
              sum(qty_produced) as qty_produced,
              sum(value_produced) as value_produced,
              sum(qty_in_reverse) as qty_in_reverse,
              sum(value_in_reverse) as value_in_reverse,
              sum(qty_out_reverse) as qty_out_reverse,
              sum(value_out_reverse) as value_out_reverse,
              sum(qty_consumed) as qty_consumed,
              sum(value_consumed) as value_consumed,
              sum(qty_scrap) as qty_scrap,
              sum(value_scrap) as value_scrap,
              sum(qty_in_other) as qty_in_other,
              sum(value_in_other) as value_in_other,
              sum(qty_out_other) as qty_out_other,
              sum(value_out_other) as value_out_other,
              sum(qty_delivered) as qty_delivered,
              sum(value_delivered) as value_delivered
                FROM
            ((SELECT
                stock_move.product_id as product_id,
                stock_move.product_category as product_category,
                (case when dest.usage = 'internal' and src.usage != 'internal' then stock_move.location_dest_id when src.usage = 'internal' and dest.usage != 'internal' then stock_move.location_id end) as location_id,
                0.0 as qty_ordered,
                sum(case when src.usage = 'supplier' and dest.usage = 'internal' and COALESCE(stock_move.is_reverse, FALSE) = FALSE then stock_move.product_qty when src.usage = 'internal' and dest.usage = 'supplier' and COALESCE(stock_move.is_reverse, FALSE) = FALSE and COALESCE(stock_move.error, FALSE) = True then -stock_move.product_qty end) as qty_supplied,
                sum(case when src.usage = 'supplier' and dest.usage = 'internal' and COALESCE(stock_move.is_reverse, FALSE) = FALSE then bar.move_value when src.usage = 'internal' and dest.usage = 'supplier' and COALESCE(stock_move.is_reverse, FALSE) = FALSE and COALESCE(stock_move.error, FALSE) = True then -bar.move_value end) as value_supplied,
                sum(case when src.usage = 'production' and dest.usage = 'internal' and stock_move.production_id is not NULL and COALESCE(stock_move.error, FALSE) = FALSE then stock_move.product_qty when src.usage = 'internal' and dest.usage = 'production' and stock_move.raw_material_production_id is not NULL and COALESCE(stock_move.error, FALSE) = TRUE then -stock_move.product_qty when src.usage = 'internal' and dest.usage = 'production' and raw_material_production_id is NULL and production_id is NULL and stock_move.error = TRUE then -stock_move.product_qty when src.usage = 'production' and dest.usage = 'internal' and stock_move.raw_material_production_id is NULL and stock_move.production_id is NULL and COALESCE(stock_move.error, FALSE) = FALSE then stock_move.product_qty end) as qty_produced,
                sum(case when src.usage = 'production' and dest.usage = 'internal' and stock_move.production_id is not NULL and COALESCE(stock_move.error, FALSE) = FALSE then bar.move_value when src.usage = 'internal' and dest.usage = 'production' and stock_move.raw_material_production_id is not NULL and COALESCE(stock_move.error, FALSE) = TRUE then -bar.move_value when src.usage = 'internal' and dest.usage = 'production' and raw_material_production_id is NULL and production_id is NULL and stock_move.error = TRUE then -bar.move_value when src.usage = 'production' and dest.usage = 'internal' and stock_move.raw_material_production_id is NULL and stock_move.production_id is NULL and COALESCE(stock_move.error, FALSE) = FALSE then bar.move_value end) as value_produced,
                sum(case when src.usage = 'customer' and dest.usage = 'internal' and stock_move.is_reverse = TRUE then stock_move.product_qty when src.usage = 'internal' and dest.usage = 'customer' and stock_move.is_reverse = TRUE then -stock_move.product_qty end) as qty_in_reverse,
                sum(case when src.usage = 'customer' and dest.usage = 'internal' and stock_move.is_reverse = TRUE then bar.move_value when src.usage = 'internal' and dest.usage = 'customer' and stock_move.is_reverse = TRUE then -bar.move_value end) as value_in_reverse,
                sum(case when src.usage = 'internal' and dest.usage = 'supplier' and stock_move.is_reverse = TRUE then -stock_move.product_qty when src.usage = 'supplier' and dest.usage = 'internal' and stock_move.is_reverse = TRUE then stock_move.product_qty end) as qty_out_reverse,
                sum(case when src.usage = 'internal' and dest.usage = 'supplier' and stock_move.is_reverse = TRUE then -bar.move_value when src.usage = 'supplier' and dest.usage = 'internal' and stock_move.is_reverse = TRUE then bar.move_value end) as value_out_reverse,
                sum(case when src.usage = 'internal' and dest.usage = 'production' and stock_move.raw_material_production_id is not NULL and COALESCE(stock_move.error, FALSE) = FALSE then -stock_move.product_qty when src.usage = 'production' and dest.usage = 'internal' and stock_move.production_id is not NULL and COALESCE(stock_move.error, FALSE) = TRUE then stock_move.product_qty when src.usage = 'internal' and dest.usage = 'production' and stock_move.production_id is NULL and stock_move.raw_material_production_id is NULL and COALESCE(stock_move.error, False) = False then -stock_move.product_qty when src.usage = 'production' and dest.usage = 'internal' and stock_move.raw_material_production_id is NULL and stock_move.production_id is NULL and stock_move.error = TRUE then stock_move.product_qty end) as qty_consumed,
                sum(case when src.usage = 'internal' and dest.usage = 'production' and stock_move.raw_material_production_id is not NULL and COALESCE(stock_move.error, FALSE) = FALSE then -bar.move_value when src.usage = 'production' and dest.usage = 'internal' and stock_move.production_id is not NULL and COALESCE(stock_move.error, FALSE) = TRUE then bar.move_value when src.usage = 'internal' and dest.usage = 'production' and stock_move.production_id is NULL and stock_move.raw_material_production_id is NULL and COALESCE(stock_move.error, False) = False then -bar.move_value when src.usage = 'production' and dest.usage = 'internal' and stock_move.raw_material_production_id is NULL and stock_move.production_id is NULL and stock_move.error = TRUE then bar.move_value end) as value_consumed,
                sum(case when src.usage = 'internal' and dest.usage != 'internal' and dest.scrap_location = TRUE then -stock_move.product_qty when src.usage = 'inventory' and dest.usage = 'internal' and COALESCE(dest.scrap_location, False) = False then stock_move.product_qty end) as qty_scrap,
                sum(case when src.usage = 'internal' and dest.usage != 'internal' and dest.scrap_location = TRUE then -bar.move_value when src.usage = 'inventory' and dest.usage = 'internal' and COALESCE(dest.scrap_location, False) = False then bar.move_value end) as value_scrap,
                sum(case when dest.usage = 'internal' and ((src.usage = 'customer' and COALESCE(stock_move.is_reverse, False) = False and COALESCE(stock_move.error, False) = False) or (src.usage = 'inventory' and dest.usage <> 'internal')) then stock_move.product_qty end) as qty_in_other,
                sum(case when dest.usage = 'internal' and ((src.usage = 'customer' and COALESCE(stock_move.is_reverse, False) = False and COALESCE(stock_move.error, False) = False) or (src.usage = 'inventory' and dest.usage <> 'internal')) then bar.move_value end) as value_in_other,
                sum(case when src.usage = 'internal' and (dest.usage = 'customer' and COALESCE(stock_move.is_reverse, False) = False and stock_move.error = True or dest.usage = 'supplier' and COALESCE(stock_move.is_reverse, False) = False and COALESCE(stock_move.error, False) = False) then -stock_move.product_qty when src.usage = 'internal' and dest.usage = 'inventory' and COALESCE(dest.scrap_location, FALSE) = FALSE then -stock_move.product_qty end)as qty_out_other,
                sum(case when src.usage = 'internal' and (dest.usage = 'customer' and COALESCE(stock_move.is_reverse, False) = False and stock_move.error = True or dest.usage = 'supplier' and COALESCE(stock_move.is_reverse, False) = False and COALESCE(stock_move.error, False) = False) then -bar.move_value when src.usage = 'internal' and dest.usage = 'inventory' and COALESCE(dest.scrap_location, FALSE) = FALSE then -bar.move_value end)as value_out_other,
                sum(case when src.usage = 'internal' and dest.usage = 'customer' and COALESCE(stock_move.is_reverse, FALSE) = FALSE and COALESCE(stock_move.error, FALSE) = FALSE then -stock_move.product_qty when src.usage = 'customer' and dest.usage = 'internal' and COALESCE(stock_move.is_reverse, FALSE) = FALSE and stock_move.error = True then stock_move.product_qty end) as qty_delivered,
                sum(case when src.usage = 'internal' and dest.usage = 'customer' and COALESCE(stock_move.is_reverse, FALSE) = FALSE and COALESCE(stock_move.error, FALSE) = FALSE then -bar.move_value when src.usage = 'customer' and dest.usage = 'internal' and COALESCE(stock_move.is_reverse, FALSE) = FALSE and stock_move.error = True then bar.move_value end) as value_delivered,
                stock_move.date as date,
                stock_move.picking_partner_id as partner_id,
                stock_move.picking_id as picking_id,
                stock_move.supplier_note as transfer_reference
            FROM
                stock_move JOIN stock_location AS dest ON
                    stock_move.location_dest_id = dest.id
                JOIN stock_location as src ON
                    stock_move.location_id = src.id

                FULL OUTER JOIN purchase_order_line ON
                    stock_move.purchase_line_id = purchase_order_line.id
                JOIN product_product ON
                    stock_move.product_id = product_product.id

                LEFT JOIN product_uom ON stock_move.product_uom = product_uom.id
                LEFT JOIN product_uom as uom2 ON purchase_order_line.product_uom = uom2.id
                LEFT JOIN (SELECT 
							stock_move.id as move_id,
							sum(stock_quant.qty * (stock_quant.cost - case when date_trunc('month', slc.date) > date_trunc('month', stock_move.date) then sval.additional_landed_cost/stock_move.product_qty else 0 end)) as move_value
							FROM stock_quant_move_rel
								JOIN stock_quant ON stock_quant_move_rel.quant_id = stock_quant.id
								LEFT JOIN stock_move ON stock_move.id = stock_quant_move_rel.move_id
								LEFT JOIN stock_valuation_adjustment_lines sval ON sval.move_id = stock_move.id
								LEFT JOIN stock_landed_cost_lines slcl ON (slcl.id = sval.cost_line_id)
								LEFT JOIN stock_landed_cost slc ON (slc.id = slcl.cost_id)
							GROUP BY stock_move.id) as bar
                    ON stock_move.id = bar.move_id
                JOIN product_template on product_product.product_tmpl_id = product_template.id
            WHERE
                stock_move.state = 'done' AND (src.usage != 'internal' OR dest.usage != 'internal') AND product_template.type = 'product'
             GROUP BY
                stock_move.product_id, stock_move.location_id, stock_move.location_dest_id, date, dest.usage, src.usage, stock_move.product_category, stock_move.picking_partner_id, stock_move.picking_id, stock_move.supplier_note
            ORDER BY stock_move.product_id ASC)
            UNION
            (SELECT
                stock_move.product_id as product_id,
                stock_move.product_category as product_category,
                (case when dest.usage = 'internal' and src.usage != 'internal' then stock_move.location_dest_id when src.usage = 'internal' and dest.usage != 'internal' then stock_move.location_id end) as location_id,
                sum(case when stock_move.origin like 'PO%' and stock_move.split_from is NULL then purchase_order_line.product_qty * (case when uom2.uom_type = 'bigger' then 1.0/uom2.factor when uom2.uom_type = 'smaller' then uom2.factor else 1.0 end) end) as qty_ordered,
                0.0 as qty_supplied,
                0.0 as value_supplied,
                0.0 as qty_produced,
                0.0 as value_produced,
                0.0 as qty_in_reverse,
                0.0 as value_in_reverse,
                0.0 as qty_out_reverse,
                0.0 as value_out_reverse,
                0.0 as qty_consumed,
                0.0 as value_consumed,
                0.0 as qty_scrap,
                0.0 as value_scrap,
                0.0 as qty_in_other,
                0.0 as value_in_other,
                0.0 as qty_out_other,
                0.0 as value_out_other,
                0.0 as qty_delivered,
                0.0 as value_delivered,
                stock_move.date as date,
                stock_move.picking_partner_id as partner_id,
                stock_move.picking_id as picking_id,
                stock_move.supplier_note as transfer_reference
            FROM
                stock_move JOIN stock_location AS dest ON
                    stock_move.location_dest_id = dest.id
                JOIN stock_location as src ON
                    stock_move.location_id = src.id
                FULL OUTER JOIN purchase_order_line ON
                    stock_move.purchase_line_id = purchase_order_line.id
                JOIN product_product ON
                    stock_move.product_id = product_product.id
                LEFT JOIN product_uom ON stock_move.product_uom = product_uom.id
                LEFT JOIN product_uom as uom2 ON purchase_order_line.product_uom = uom2.id
                LEFT JOIN (SELECT 
							stock_move.id as move_id,
							sum(stock_quant.qty * (stock_quant.cost - case when date_trunc('month', slc.date) > date_trunc('month', stock_move.date) then sval.additional_landed_cost/stock_move.product_qty else 0 end)) as move_value
							FROM stock_quant_move_rel
								JOIN stock_quant ON stock_quant_move_rel.quant_id = stock_quant.id
								LEFT JOIN stock_move ON stock_move.id = stock_quant_move_rel.move_id
								LEFT JOIN stock_valuation_adjustment_lines sval ON sval.move_id = stock_move.id
								LEFT JOIN stock_landed_cost_lines slcl ON (slcl.id = sval.cost_line_id)
								LEFT JOIN stock_landed_cost slc ON (slc.id = slcl.cost_id)
							GROUP BY stock_move.id) as bar
                    ON stock_move.id = bar.move_id
                JOIN product_template on product_product.product_tmpl_id = product_template.id
            WHERE
                stock_move.state not in ('draft', 'cancel') AND (src.usage != 'internal' OR dest.usage != 'internal') AND product_template.type = 'product'
             GROUP BY
                stock_move.product_id, stock_move.location_id, stock_move.location_dest_id, date, dest.usage, src.usage, stock_move.product_category, stock_move.picking_partner_id, stock_move.picking_id, stock_move.supplier_note
            ORDER BY stock_move.product_id ASC)
              UNION (
                SELECT
                    stock_move.product_id as product_id,
                    stock_move.product_category as product_category,
                    (case when dest.usage = 'internal' and src.usage = 'internal' then stock_move.location_dest_id end) as location_id,
                    0.0 as qty_ordered,
                    0.0 as qty_supplied,
                    0.0 as value_supplied,
                    0.0 as qty_produced,
                    0.0 as value_produced,
                    0.0 as qty_in_reverse,
                    0.0 as value_in_reverse,
                    0.0 as qty_out_reverse,
                    0.0 as value_out_reverse,
                    0.0 as qty_consumed,
                    0.0 as value_consumed,
                    0.0 as qty_scrap,
                    0.0 as value_scrap,
                    0.0 as qty_in_other,
                    0.0 as value_in_other,
                    0.0 as qty_out_other,
                    0.0 as value_out_other,
                    0.0 as qty_delivered,
                    0.0 as value_delivered,
                    stock_move.date as date,
                    stock_move.picking_partner_id as partner_id,
                    stock_move.picking_id as picking_id,
                    stock_move.supplier_note as transfer_reference
                FROM
                    stock_move JOIN stock_location AS dest ON
                        stock_move.location_dest_id = dest.id
                    JOIN stock_location as src ON
                        stock_move.location_id = src.id
                    FULL OUTER JOIN purchase_order_line ON
                        stock_move.purchase_line_id = purchase_order_line.id
                    JOIN product_product ON
                        stock_move.product_id = product_product.id
                    LEFT JOIN product_uom ON stock_move.product_uom = product_uom.id
                    LEFT JOIN (SELECT 
								stock_move.id as move_id,
								sum(stock_quant.qty * (stock_quant.cost - case when date_trunc('month', slc.date) > date_trunc('month', stock_move.date) then sval.additional_landed_cost/stock_move.product_qty else 0 end)) as move_value
								FROM stock_quant_move_rel
									JOIN stock_quant ON stock_quant_move_rel.quant_id = stock_quant.id
									LEFT JOIN stock_move ON stock_move.id = stock_quant_move_rel.move_id
									LEFT JOIN stock_valuation_adjustment_lines sval ON sval.move_id = stock_move.id
									LEFT JOIN stock_landed_cost_lines slcl ON (slcl.id = sval.cost_line_id)
									LEFT JOIN stock_landed_cost slc ON (slc.id = slcl.cost_id)
								GROUP BY stock_move.id) as bar
                        ON stock_move.id = bar.move_id
                    JOIN product_template on product_product.product_tmpl_id = product_template.id
                WHERE
                    stock_move.state = 'done' and src.usage = 'internal' and dest.usage = 'internal' and product_template.type = 'product'
             GROUP BY
                stock_move.product_id, stock_move.location_id, stock_move.location_dest_id, date, dest.usage, src.usage, stock_move.product_category, stock_move.picking_partner_id, stock_move.picking_id, stock_move.supplier_note
            ORDER BY stock_move.product_id ASC)
                UNION  -- we want to see zeroes for existing quants
            (SELECT
                product_product.id as product_id,
                product_template.categ_id as product_category,
                stock_quant.location_id as location_id,
                0.0 as qty_ordered,
                0.0 as qty_supplied,
                0.0 as value_supplied,
                0.0 as qty_produced,
                0.0 as value_produced,
                0.0 as qty_in_reverse,
                0.0 as value_in_reverse,
                0.0 as qty_out_reverse,
                0.0 as value_out_reverse,
                0.0 as qty_consumed,
                0.0 as value_consumed,
                0.0 as qty_scrap,
                0.0 as value_scrap,
                0.0 qty_in_other,
                0.0 as value_in_other,
                0.0 as qty_out_other,  -- so that it would be counted twice
                0.0 as value_out_other,     -- -""-
                0.0 as qty_delivered,
                0.0 as value_delivered,
                CURRENT_DATE as date,
                NULL as partner_id,
                NULL as picking_id,
                NULL as transfer_reference
            FROM
                stock_quant JOIN stock_location ON
                    stock_quant.location_id = stock_location.id
                JOIN product_product ON
                    stock_quant.product_id = product_product.id
                JOIN product_template ON
                    product_product.product_tmpl_id = product_template.id
            WHERE
                stock_location.usage = 'internal' and product_template.type = 'product'
             GROUP BY
                product_product.id, stock_quant.location_id, product_template.categ_id
            ORDER BY product_product.id ASC)

                UNION (SELECT
                    stock_move.product_id as product_id,
                    stock_move.product_category as product_category,
                    stock_move.location_id as location_id,
                    0.0 as qty_ordered,
                    0.0 as qty_supplied,
                    0.0 as value_supplied,
                    0.0 as qty_produced,
                    0.0 as value_produced,
                    0.0 as qty_in_reverse,
                    0.0 as value_in_reverse,
                    0.0 as qty_out_reverse,
                    0.0 as value_out_reverse,
                    0.0 as qty_consumed,
                    0.0 as value_consumed,
                    0.0 as qty_scrap,
                    0.0 as value_scrap,
                    0.0 as qty_in_other,
                    0.0 as value_in_other,
                    -sum(stock_move.product_qty) as qty_out_other,
                    -sum(bar.move_value) as value_out_other,
                    0.0 as qty_delivered,
                    0.0 as value_delivered,
                    stock_move.date as date,
                    stock_move.picking_partner_id as partner_id,
                    stock_move.picking_id as picking_id,
                    stock_move.supplier_note as transfer_reference
                FROM
                    stock_move JOIN stock_location AS dest ON
                        stock_move.location_dest_id = dest.id
                    JOIN stock_location as src ON
                        stock_move.location_id = src.id
                    JOIN product_product ON
                        stock_move.product_id = product_product.id
                    LEFT JOIN (SELECT 
								stock_move.id as move_id,
								sum(stock_quant.qty * (stock_quant.cost - case when date_trunc('month', slc.date) > date_trunc('month', stock_move.date) then sval.additional_landed_cost/stock_move.product_qty else 0 end)) as move_value
								FROM stock_quant_move_rel
									JOIN stock_quant ON stock_quant_move_rel.quant_id = stock_quant.id
									LEFT JOIN stock_move ON stock_move.id = stock_quant_move_rel.move_id
									LEFT JOIN stock_valuation_adjustment_lines sval ON sval.move_id = stock_move.id
									LEFT JOIN stock_landed_cost_lines slcl ON (slcl.id = sval.cost_line_id)
									LEFT JOIN stock_landed_cost slc ON (slc.id = slcl.cost_id)
								GROUP BY stock_move.id) as bar
                        ON stock_move.id = bar.move_id
                    JOIN product_template on product_product.product_tmpl_id = product_template.id
                WHERE
                    stock_move.state = 'done' and src.usage = 'internal' and dest.usage = 'internal' and product_template.type = 'product'
             GROUP BY
                stock_move.product_id, stock_move.location_id, stock_move.location_dest_id, date, dest.usage, src.usage, stock_move.product_category, stock_move.picking_partner_id, stock_move.picking_id, stock_move.supplier_note
            ORDER BY stock_move.product_id ASC)
            UNION (SELECT
                    stock_move.product_id as product_id,
                    stock_move.product_category as product_category,
                    stock_move.location_dest_id as location_id,
                    0.0 as qty_ordered,
                    0.0 as qty_supplied,
                    0.0 as value_supplied,
                    0.0 as qty_produced,
                    0.0 as value_produced,
                    0.0 as qty_in_reverse,
                    0.0 as value_in_reverse,
                    0.0 as qty_out_reverse,
                    0.0 as value_out_reverse,
                    0.0 as qty_consumed,
                    0.0 as value_consumed,
                    0.0 as qty_scrap,
                    0.0 as value_scrap,
                    sum(stock_move.product_qty) as qty_in_other,
                    sum(bar.move_value) as value_in_other,
                    0.0 as qty_out_other,
                    0.0 as value_out_other,
                    0.0 as qty_delivered,
                    0.0 as value_delivered,
                    stock_move.date as date,
                    stock_move.picking_partner_id as partner_id,
                    stock_move.picking_id as picking_id,
                    stock_move.supplier_note as transfer_reference
                FROM
                    stock_move JOIN stock_location AS dest ON
                        stock_move.location_dest_id = dest.id
                    JOIN stock_location as src ON
                        stock_move.location_id = src.id
                    JOIN product_product ON
                        stock_move.product_id = product_product.id
                    LEFT JOIN (SELECT 
								stock_move.id as move_id,
								sum(stock_quant.qty * (stock_quant.cost - case when date_trunc('month', slc.date) > date_trunc('month', stock_move.date) then sval.additional_landed_cost/stock_move.product_qty else 0 end)) as move_value
								FROM stock_quant_move_rel
									JOIN stock_quant ON stock_quant_move_rel.quant_id = stock_quant.id
									LEFT JOIN stock_move ON stock_move.id = stock_quant_move_rel.move_id
									LEFT JOIN stock_valuation_adjustment_lines sval ON sval.move_id = stock_move.id
									LEFT JOIN stock_landed_cost_lines slcl ON (slcl.id = sval.cost_line_id)
									LEFT JOIN stock_landed_cost slc ON (slc.id = slcl.cost_id)
								GROUP BY stock_move.id) as bar
                        ON stock_move.id = bar.move_id
                    JOIN product_template on product_product.product_tmpl_id = product_template.id
                WHERE
                    stock_move.state = 'done' and src.usage = 'internal' and dest.usage = 'internal' and product_template.type = 'product'
             GROUP BY
                stock_move.product_id, stock_move.location_id, stock_move.location_dest_id, date, dest.usage, src.usage, stock_move.product_category, stock_move.picking_partner_id, stock_move.picking_id, stock_move.supplier_note
            ORDER BY stock_move.product_id ASC
            )) AS foo WHERE foo.location_id is not NULL

            GROUP BY foo.product_id, foo.product_category, foo.date, foo.location_id, foo.partner_id, foo.picking_id, foo.transfer_reference
        ) """)

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True, expand_full=False):
        offset = self.env.user.tz_offset
        res = super(StockMoveReport, self).read_group(domain, fields, groupby, offset=offset, limit=limit,
                                                      orderby=orderby, lazy=lazy)
        if self._context.get('skip_computations', False):
            return res
        if 'end_stock' in fields or 'end_value' in fields:  # todo start?
            company_ids = self.env['res.company'].search([('id', 'child_of', self.env.user.company_id.id)]).mapped('id')
            location_ids = self.env['stock.location'].search([('company_id', 'in', company_ids)]).mapped('id')
            if 'start_stock' in fields:
                start_stock = True
            else:
                start_stock = False
            if 'start_value' in fields:
                start_value = True
            else:
                start_value = False
            if 'end_stock' in fields:
                end_stock = True
            else:
                end_stock = False
            if 'end_value' in fields:
                end_value = True
            else:
                end_value = False
            for line in res:
                if '__domain' in line:
                    dom = line['__domain']
                else:
                    dom = domain
                if start_stock or start_value or end_stock or end_value:
                    loc_id = False
                    current_stock_dom = []
                    for t in dom:
                        if t[0] == 'location_id':
                            loc_id = t[2]
                        if t[0] in ['product_id', 'location_id'] and 'like' not in t[1]:
                            current_stock_dom.append(t)
                        if t[0] == 'product_category':
                            current_stock_dom.append(('category_id', t[1], t[2]))
                    if not loc_id:
                        current_stock_dom.append(('location_id', 'in', location_ids))

                    if current_stock_dom:
                        if end_stock and not end_value:
                            current_stock_query = 'select sum(qty) from stock_quant where '
                        elif end_value and not end_stock:
                            current_stock_query = 'select sum(qty*cost) from stock_quant where '
                        else:
                            current_stock_query = 'select sum(qty), sum(qty*cost) from stock_quant where '
                        index = 1
                        index_end = len(current_stock_dom)
                        for d in current_stock_dom:
                            current_stock_query += str(d[0]) + ' '
                            if type(d[2]) not in [str, unicode, list]:
                                current_stock_query += str(d[1]) + ' '
                                current_stock_query += str(d[2])
                            elif type(d[2]) == list:
                                current_stock_query += str(d[1]) + ' '
                                current_stock_query += '(' + ','.join(map(str, d[2])) + ')'
                            else:
                                field = d[0]
                                field_class = self._fields[field] if field != 'category_id' \
                                    else self._fields['product_category']
                                if field_class:
                                    model = field_class.comodel_name
                                    model_class = self.env[model]
                                    model_ids = model_class.search([(model_class._rec_name, d[1], d[2])]).mapped('id')
                                    current_stock_query += ' in '
                                    current_stock_query += '(' + ','.join(map(str, model_ids)) + ')'
                            if index != index_end:
                                current_stock_query += ' AND '
                            index += 1
                        self._cr.execute(current_stock_query)
                        if end_stock and not end_value:
                            qty_current_stock = self._cr.fetchone()[0]
                            value_current_stock = 0.0
                        elif end_value and not end_stock:
                            qty_current_stock = 0.0
                            value_current_stock = self._cr.fetchone()[0]
                        else:
                            qty_current_stock, value_current_stock = self._cr.fetchone()
                    else:
                        qty_current_stock = 0.0
                        value_current_stock = 0.0

                    if end_stock or end_value:
                        loc_id = False
                        real_dom = []
                        date_to = False
                        included = False
                        for t in dom:
                            if t[0] == 'location_id':
                                loc_id = t[2]
                            if t[0] in ['product_id', 'location_id'] and 'like' not in t[1]:
                                real_dom.append(t)
                            if t[0] == 'product_category':
                                real_dom.append(('product_categ_id', t[1], t[2]))
                            if t[0] == 'date' and t[1] in ['<', '<='] and (not date_to or date_to and (
                                    t[2] < date_to or t[2] == date_to and included)):
                                date_to = t[2]
                                if '00:00:00' in date_to:
                                    date_to = convert_to_dt_str(date_to, offset)
                                if t[1] == '<':
                                    included = False
                                else:
                                    included = True
                        if date_to:
                            if included:
                                real_dom.append(('date', '>', date_to))
                            else:
                                real_dom.append(('date', '>=', date_to))
                        if not loc_id:
                            real_dom.append(('location_id', 'in', location_ids))
                        if real_dom:
                            if end_stock and not end_value:
                                query = 'select sum(quantity) from stock_history where '
                            elif end_value and not end_stock:
                                query = 'select sum(total_value) from stock_history where '
                            else:
                                query = 'select sum(quantity), sum(total_value) from stock_history where '
                            index = 1
                            index_end = len(real_dom)
                            for d in real_dom:
                                query += str(d[0]) + ' '
                                if type(d[2]) not in [str, unicode, list]:
                                    query += str(d[1]) + ' '
                                    query += str(d[2])
                                elif type(d[2]) == list:
                                    query += str(d[1]) + ' '
                                    query += '(' + ','.join(map(str, d[2])) + ')'
                                elif d[0] == 'date':
                                    query += str(d[1]) + ' '
                                    query += "'%s'" % d[2]
                                else:
                                    field = d[0]
                                    field_class = self._fields[field] if field != 'category_id' \
                                        else self._fields['product_category']
                                    if field_class:
                                        model = field_class.comodel_name
                                        model_class = self.ev[model]
                                        model_ids = model_class.search([(model_class._rec_name, d[1], d[2])])
                                        query += ' in '
                                        query += '(' + ','.join(map(str, model_ids)) + ')'
                                if index != index_end:
                                    query += ' AND '
                                index += 1
                            self._cr.execute(query)
                            if end_stock and not end_value:
                                qty_stock_history = self._cr.fetchone()[0]
                                value_stock_history = 0.0
                            elif end_value and not end_stock:
                                qty_stock_history = 0.0
                                value_stock_history = self._cr.fetchone()[0]
                            else:
                                qty_stock_history, value_stock_history = self._cr.fetchone()
                        else:
                            qty_stock_history = 0.0
                            value_stock_history = 0.0

                        if type(qty_stock_history) != float:
                            qty_stock_history = 0
                        if type(value_stock_history) != float:
                            value_stock_history = 0
                        if type(qty_current_stock) != float:
                            qty_current_stock = 0
                        if type(value_current_stock) != float:
                            value_current_stock = 0
                        if end_stock:
                            line['end_stock'] = qty_current_stock - qty_stock_history
                        if end_value:
                            line['end_value'] = value_current_stock - value_stock_history
                    if start_stock or start_value:
                        loc_id = False
                        real_dom = []
                        date_from = False
                        included = False
                        for t in dom:
                            if t[0] == 'location_id':
                                loc_id = t[2]
                            if t[0] in ['product_id', 'location_id'] and 'like' not in t[1]:
                                real_dom.append(t)
                            if t[0] == 'product_category':
                                real_dom.append(('product_categ_id', t[1], t[2]))
                            if t[0] == 'date' and t[1] in ['>', '>='] and (not date_from or date_from and (
                                    t[2] > date_from or t[2] == date_from and included)):
                                date_from = t[2]
                                if '00:00:00' in date_from:
                                    date_from = convert_to_dt_str(date_from, offset)
                        if date_from:
                            real_dom.append(('date', '>=', date_from))
                        if not loc_id:
                            real_dom.append(('location_id', 'in', location_ids))
                        if real_dom:
                            if start_stock and not start_value:
                                query = 'select sum(quantity) from stock_history where '
                            elif start_value and not start_stock:
                                query = 'select sum(total_value) from stock_history where '
                            else:
                                query = 'select sum(quantity), sum(total_value) from stock_history where '
                            index = 1
                            index_end = len(real_dom)
                            for d in real_dom:
                                query += str(d[0]) + ' '
                                if type(d[2]) not in [str, unicode, list]:
                                    query += str(d[1]) + ' '
                                    query += str(d[2])
                                elif type(d[2]) == list:
                                    query += str(d[1]) + ' '
                                    query += '(' + ','.join(map(str, d[2])) + ')'
                                elif d[0] == 'date':
                                    query += str(d[1]) + ' '
                                    query += "'%s'" % d[2]
                                else:
                                    field = d[0]
                                    field_class = self._fields[field] if field != 'category_id' else \
                                        self._fields['product_category']
                                    if field_class:
                                        model = field_class.comodel_name
                                        model_class = self.env[model]
                                        model_ids = model_class.search([(model_class._rec_name, d[1], d[2])])
                                        query += ' in '
                                        query += '(' + ','.join(map(str, model_ids)) + ')'
                                if index != index_end:
                                    query += ' AND '
                                index += 1
                            self._cr.execute(query)
                            if start_stock and not start_value:
                                qty_stock_history = self._cr.fetchone()[0]
                                value_stock_history = 0.0
                            elif start_value and not start_stock:
                                qty_stock_history = 0.0
                                value_stock_history = self._cr.fetchone()[0]
                            else:
                                qty_stock_history, value_stock_history = self._cr.fetchone()
                        else:
                            qty_stock_history = 0.0
                            value_stock_history = 0.0

                        if type(qty_stock_history) != float:
                            qty_stock_history = 0
                        if type(value_stock_history) != float:
                            value_stock_history = 0
                        if type(qty_current_stock) != float:
                            qty_current_stock = 0
                        if type(value_current_stock) != float:
                            value_current_stock = 0
                        if start_stock:
                            line['start_stock'] = qty_current_stock - qty_stock_history
                        if start_value:
                            line['start_value'] = value_current_stock - value_stock_history
        return res


StockMoveReport()


class StockHistory(models.Model):
    _inherit = 'stock.history'

    total_value = fields.Float(string='Total Value')
    price_unit_on_quant = fields.Float(group_operator='quantity')

    @api.model_cr
    def init(self):
        tools.drop_view_if_exists(self._cr, 'stock_history')
        self._cr.execute("""
            CREATE OR REPLACE VIEW stock_history AS (
              SELECT MIN(id) as id,
                move_id,
                location_id,
                company_id,
                product_id,
                product_categ_id,
                product_template_id,
                SUM(quantity) as quantity,
				SUM(quantity2) as quantity2,
                date,
                COALESCE(SUM((price_unit_on_quant) * quantity2) / NULLIF(SUM(quantity2), 0), 0) as price_unit_on_quant,
				source,
                string_agg(DISTINCT serial_number, ', ' ORDER BY serial_number) AS serial_number,
                COALESCE(SUM(price_unit_on_quant * quantity2), 0) as total_value
                FROM
                (
					(
						SELECT
                    stock_move.id AS id,
                    stock_move.id AS move_id,
                    dest_location.id AS location_id,
                    dest_location.company_id AS company_id,
                    stock_move.product_id AS product_id,
                    product_template.id AS product_template_id,
                    product_template.categ_id AS product_categ_id,
                    quant.qty AS quantity,
					quant.qty AS quantity2,
                    stock_move.date AS date,
					quant.cost - bar.cost_diff as price_unit_on_quant,
                    stock_move.origin AS source,
                    stock_production_lot.name AS serial_number
                FROM
                    stock_quant as quant
                JOIN
                    stock_quant_move_rel ON stock_quant_move_rel.quant_id = quant.id
                JOIN
                    stock_move ON stock_move.id = stock_quant_move_rel.move_id
                LEFT JOIN
                    stock_production_lot ON stock_production_lot.id = quant.lot_id
                JOIN
                    stock_location dest_location ON stock_move.location_dest_id = dest_location.id
                JOIN
                    stock_location source_location ON stock_move.location_id = source_location.id
                JOIN
                    product_product ON product_product.id = stock_move.product_id
                JOIN
                    product_template ON product_template.id = product_product.product_tmpl_id
				LEFT JOIN (SELECT 
                            stock_move.id as move_id,
                            COALESCE(avg(case when date_trunc('month', slc.date) > date_trunc('month', stock_move.date) then sval.additional_landed_cost/stock_move.product_qty end),0) as cost_diff
                            FROM stock_quant_move_rel
                                JOIN stock_quant ON stock_quant_move_rel.quant_id = stock_quant.id
                                LEFT JOIN stock_move ON stock_move.id = stock_quant_move_rel.move_id
                                LEFT JOIN stock_valuation_adjustment_lines sval ON sval.move_id = stock_move.id
                                LEFT JOIN stock_landed_cost_lines slcl ON (slcl.id = sval.cost_line_id)
                                LEFT JOIN stock_landed_cost slc ON (slc.id = slcl.cost_id)
                            GROUP BY stock_move.id) as bar on bar.move_id = stock_move.id
				WHERE quant.qty>0 AND stock_move.state = 'done' AND dest_location.usage in ('internal')
                AND (
                    not (source_location.company_id is null and dest_location.company_id is null) or
                    source_location.company_id != dest_location.company_id or
                    source_location.usage not in ('internal', 'transit'))
                ) UNION ALL
                (SELECT
                    (-1) * stock_move.id AS id,
                    stock_move.id AS move_id,
                    source_location.id AS location_id,
                    source_location.company_id AS company_id,
                    stock_move.product_id AS product_id,
                    product_template.id AS product_template_id,
                    product_template.categ_id AS product_categ_id,
                    - quant.qty AS quantity,
				 	- quant.qty AS quantity2,
                    stock_move.date AS date,
				    quant.cost - bar.cost_diff as price_unit_on_quant,
				 	stock_move.origin AS source,
                    stock_production_lot.name AS serial_number
                FROM
                    stock_quant as quant
                JOIN
                    stock_quant_move_rel ON stock_quant_move_rel.quant_id = quant.id
                JOIN
                    stock_move ON stock_move.id = stock_quant_move_rel.move_id
                LEFT JOIN
                    stock_production_lot ON stock_production_lot.id = quant.lot_id
                JOIN
                    stock_location source_location ON stock_move.location_id = source_location.id
                JOIN
                    stock_location dest_location ON stock_move.location_dest_id = dest_location.id
                JOIN
                    product_product ON product_product.id = stock_move.product_id
                JOIN
                    product_template ON product_template.id = product_product.product_tmpl_id
				LEFT JOIN (SELECT 
                            stock_move.id as move_id,
                            COALESCE(avg(case when date_trunc('month', slc.date) > date_trunc('month', stock_move.date) then sval.additional_landed_cost/stock_move.product_qty end),0) as cost_diff
                            FROM stock_quant_move_rel
                                JOIN stock_quant ON stock_quant_move_rel.quant_id = stock_quant.id
                                LEFT JOIN stock_move ON stock_move.id = stock_quant_move_rel.move_id
                                LEFT JOIN stock_valuation_adjustment_lines sval ON sval.move_id = stock_move.id
                                LEFT JOIN stock_landed_cost_lines slcl ON (slcl.id = sval.cost_line_id)
                                LEFT JOIN stock_landed_cost slc ON (slc.id = slcl.cost_id)
                            GROUP BY stock_move.id) as bar on bar.move_id = stock_move.id
                WHERE quant.qty>0 AND stock_move.state = 'done' AND source_location.usage in ('internal')
                AND (
                    not (dest_location.company_id is null and source_location.company_id is null) or
                    dest_location.company_id != source_location.company_id or
                    dest_location.usage not in ('internal', 'transit'))
                ) 
					UNION ALL (
					SELECT
                    stock_move.id AS id,
                    stock_move.id AS move_id,
                    dest_location.id AS location_id,
                    dest_location.company_id AS company_id,
                    stock_move.product_id AS product_id,
                    product_template.id AS product_template_id,
                    product_template.categ_id AS product_categ_id,
                    0 AS quantity,
					quant.qty AS quantity2,
                    bar.date AS date,
					bar.cost_diff as price_unit_on_quant,
					stock_move.origin AS source,
                    stock_production_lot.name AS serial_number
                FROM
                    stock_quant as quant
                JOIN
                    stock_quant_move_rel ON stock_quant_move_rel.quant_id = quant.id
                JOIN
                    stock_move ON stock_move.id = stock_quant_move_rel.move_id
                LEFT JOIN
                    stock_production_lot ON stock_production_lot.id = quant.lot_id
                JOIN
                    stock_location dest_location ON stock_move.location_dest_id = dest_location.id
                JOIN
                    stock_location source_location ON stock_move.location_id = source_location.id
                JOIN
                    product_product ON product_product.id = stock_move.product_id
                JOIN
                    product_template ON product_template.id = product_product.product_tmpl_id
				INNER JOIN (SELECT 
                            stock_move.id as move_id,
						    min(slc.date) as date,
                            COALESCE(avg(case when date_trunc('month', slc.date) > date_trunc('month', stock_move.date) then sval.additional_landed_cost/stock_move.product_qty end),0) as cost_diff
                            FROM stock_quant_move_rel
                                INNER JOIN stock_quant ON stock_quant_move_rel.quant_id = stock_quant.id
                                INNER JOIN stock_move ON stock_move.id = stock_quant_move_rel.move_id
                                INNER JOIN stock_valuation_adjustment_lines sval ON sval.move_id = stock_move.id
                                INNER JOIN stock_landed_cost_lines slcl ON (slcl.id = sval.cost_line_id)
                                INNER JOIN stock_landed_cost slc ON (slc.id = slcl.cost_id)
                            GROUP BY stock_move.id) as bar on bar.move_id = stock_move.id
				WHERE quant.qty>0 AND stock_move.state = 'done' AND dest_location.usage in ('internal')
                AND (
                    not (source_location.company_id is null and dest_location.company_id is null) or
                    source_location.company_id != dest_location.company_id or
                    source_location.usage not in ('internal', 'transit'))
				) UNION ALL (
					SELECT
                    (-1) * stock_move.id AS id,
                    stock_move.id AS move_id,
                    source_location.id AS location_id,
                    source_location.company_id AS company_id,
                    stock_move.product_id AS product_id,
                    product_template.id AS product_template_id,
                    product_template.categ_id AS product_categ_id,
                    0 AS quantity,
					- quant.qty AS quantity2,
                    bar.date AS date,
					bar.cost_diff as price_unit_on_quant,
					stock_move.origin AS source,
                    stock_production_lot.name AS serial_number
                FROM
                    stock_quant as quant
                JOIN
                    stock_quant_move_rel ON stock_quant_move_rel.quant_id = quant.id
                JOIN
                    stock_move ON stock_move.id = stock_quant_move_rel.move_id
                LEFT JOIN
                    stock_production_lot ON stock_production_lot.id = quant.lot_id
                JOIN
                    stock_location source_location ON stock_move.location_id = source_location.id
                JOIN
                    stock_location dest_location ON stock_move.location_dest_id = dest_location.id
                JOIN
                    product_product ON product_product.id = stock_move.product_id
                JOIN
                    product_template ON product_template.id = product_product.product_tmpl_id
				INNER JOIN (SELECT 
                            stock_move.id as move_id,
						    min(slc.date) as date,
                            COALESCE(avg(case when date_trunc('month', slc.date) > date_trunc('month', stock_move.date) then sval.additional_landed_cost/stock_move.product_qty end),0) as cost_diff
                            FROM stock_quant_move_rel
                                INNER JOIN stock_quant ON stock_quant_move_rel.quant_id = stock_quant.id
                                INNER JOIN stock_move ON stock_move.id = stock_quant_move_rel.move_id
                                INNER JOIN stock_valuation_adjustment_lines sval ON sval.move_id = stock_move.id
                                INNER JOIN stock_landed_cost_lines slcl ON (slcl.id = sval.cost_line_id)
                                INNER JOIN stock_landed_cost slc ON (slc.id = slcl.cost_id)
                            GROUP BY stock_move.id) as bar on bar.move_id = stock_move.id
                WHERE quant.qty>0 AND stock_move.state = 'done' AND source_location.usage in ('internal')
                AND (
                    not (dest_location.company_id is null and source_location.company_id is null) or
                    dest_location.company_id != source_location.company_id or
                    dest_location.usage not in ('internal', 'transit'))
                ))
                AS foo
                GROUP BY move_id, location_id, company_id, product_id, product_categ_id, date, source, product_template_id
                )""")


StockHistory()


class StockHistoryDelayed(models.Model):
    _name = 'stock.history.delayed'
    _auto = False

    @api.model_cr
    def init(self):
        self._cr.execute('DROP MATERIALIZED VIEW If EXISTS stock_history_delayed')
        self._cr.execute('''CREATE materialized view stock_history_delayed AS
                   (SELECT * FROM stock_history)''')


StockHistoryDelayed()
