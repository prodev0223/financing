# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

from odoo import fields, models, api, tools, _


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    intrastat_transaction_id = fields.Many2one('sl_intrastat.transaction', string='Intrastat Transaction Type',
                                               help="Intrastat nature of transaction")


AccountInvoiceLine()


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    incoterm_id = fields.Many2one('stock.incoterms', string='Incoterm',
                                  help=("International Commercial Terms are a series of predefined commercial terms "
                                         "used in international transactions."), 
                                  sequence=100,
                                  )
    transport_mode_id = fields.Many2one('sl_intrastat.transport_mode', string='Intrastat Transport Mode', readonly=True,
                                        sequence=100,
                                        )
    intrastat_country_id = fields.Many2one('res.country', string='Country (Intrastat)',
                                           help='Intrastat country, delivery for sales, origin for purchases',
                                           domain=[('intrastat', '=', True)], readonly=False)

    @api.onchange('partner_id')
    def onchange_set_intrastat(self):
        country = False
        partner_vat = self.partner_id.vat
        if partner_vat:
            country = self.env['res.country'].search([('code', '=', partner_vat[:2])], limit=1)
        self.intrastat_country_id = country or self.partner_id.country_id

    @api.model
    def create(self, vals):
        res = super(AccountInvoice, self).create(vals)
        if not res.sudo().intrastat_country_id:
            country = False
            partner_vat = res.partner_vat
            if partner_vat:
                country = self.env['res.country'].search([('code', '=', partner_vat[:2])], limit=1)
            res.intrastat_country_id = country or res.partner_id.country_id
        return res


AccountInvoice()


class SlIntrastatRegion(models.Model):
    _name = 'sl_intrastat.region'

    code = fields.Char(string='Code', required=True, lt_string='Kodas')
    country_id = fields.Many2one('res.country', string='Country', lt_string='Valstybė')
    name = fields.Char(string='Name', translate=True, lt_string='Pavadinimas')
    description = fields.Char(string='Description', lt_string='Aprašymas')

    _sql_constraints = [
        ('sl_intrastat_regioncodeunique', 'UNIQUE (code)', 'Code must be unique.'),
    ]


SlIntrastatRegion()


class SlIntrastatTransaction(models.Model):
    _name = 'sl_intrastat.transaction'
    _rec_name = 'code'

    code = fields.Char('Code', required=True, readonly=True)
    description = fields.Text(string='Description', lt_string='Aprašymas', readonly=True)

    _sql_constraints = [
        ('sl_intrastat_trcodeunique', 'UNIQUE (code)', 'Code must be unique.'),
    ]


SlIntrastatTransaction()


class SlIntrastatTransportMode(models.Model):
    _name = 'sl_intrastat.transport_mode'

    code = fields.Char('Code', required=True, readonly=True)
    name = fields.Char(string='Description', lt_string='Aprašymas', readonly=True)

    _sql_constraints = [
        ('sl_intrastat_trmodecodeunique', 'UNIQUE (code)', 'Code must be unique.'),
    ]


SlIntrastatTransportMode()


class ProductCategory(models.Model):
    _name = 'product.category'
    _inherit = 'product.category'

    intrastat_id = fields.Many2one('report.intrastat.code', string='Intrastat Code')

    @api.multi
    def get_intrastat_recursively(self):
        """ Recursively search in categories to find an intrastat code id
        """
        if self.intrastat_id:
            res = self.intrastat_id.id
        elif self.parent_id:
            res = self.parent_id.get_intrastat_recursively()
        else:
            res = None
        return res


ProductCategory()


class ProductProduct(models.Model):
    _name = 'product.product'
    _inherit = 'product.product'

    @api.multi
    def get_intrastat_recursively(self):
        """ Recursively search in categories to find an intrastat code id
        """
        if self.intrastat_id:
            res = self.intrastat_id.id
        elif self.categ_id:
            res = self.categ_id.get_intrastat_recursively()
        else:
            res = None
        return res


ProductProduct()


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def _prepare_invoice(self):
        """
        copy incoterm from purchase order to invoice
        """
        invoice = super(PurchaseOrder, self)._prepare_invoice()
        if self.incoterm_id:
            invoice['incoterm_id'] = self.incoterm_id.id
        #Try to determine products origin
        if self.partner_id.country_id:
            #It comes from vendor
            invoice['intrastat_country_id'] = self.partner_id.country_id.id

        return invoice


PurchaseOrder()


class ReportIntrastatCode(models.Model):
    _inherit = 'report.intrastat.code'

    description = fields.Text(string='Description', translate=True, lt_string='Aprašymas')


ReportIntrastatCode()


class ResCompany(models.Model):
    _inherit = 'res.company'

    region_id = fields.Many2one('sl_intrastat.region', 'Intrastat region')
    transport_mode_id = fields.Many2one('sl_intrastat.transport_mode', string='Default transport mode')
    incoterm_id = fields.Many2one('stock.incoterms', string='Default incoterm for Intrastat',
                                  help=("International Commercial Terms are a series of "
                                        "predefined commercial terms used in international transactions."))
    default_intrastat_transport = fields.Char(string='Numatytasis intrastat transportas', default='3')


ResCompany()


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _prepare_invoice(self):
        """
        copy incoterm from sale order to invoice
        """
        invoice = super(SaleOrder, self)._prepare_invoice()
        if self.incoterm:
            invoice['incoterm_id'] = self.incoterm.id
        # Guess products destination
        if self.partner_shipping_id.country_id:
            invoice['intrastat_country_id'] = self.partner_shipping_id.country_id.id
        elif self.partner_id.country_id:
            invoice['intrastat_country_id'] = self.partner_id.country_id.id
        elif self.partner_invoice_id.country_id:
            invoice['intrastat_country_id'] = self.partner_invoice_id.country_id.id
        return invoice


SaleOrder()


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    region_id = fields.Many2one('sl_intrastat.region', string='Intrastat region')

    def get_regionid_from_locationid(self, location):
        location_ids = location.search([('parent_left', '<=', location.parent_left), ('parent_right', '>=', location.parent_right)])
        warehouses = self.search([('lot_stock_id', 'in', location_ids.ids), ('region_id', '!=', False)])
        if warehouses and warehouses[0]:
            return warehouses[0].region_id.id
        return None


StockWarehouse()


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    intrastat_description = fields.Char(string='Intrastat aprašymas', size=100, copy=False, sequence=100)


ProductTemplate()


class ReportIntrastat(models.Model):
    _inherit = 'report.intrastat'

    kilmes_salis = fields.Char(string='Kilmės šalis')
    transaction_code = fields.Char(string='Operacija')
    delivery_terms = fields.Char(string='Incoterm sąlygos')
    intrastat_description = fields.Char(string='Intrastat aprašymas')
    product_description = fields.Char(string='Produkto aprašymas')
    partner_vat = fields.Char('Partner VAT code')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        weight_uom_categ_id = self.env.ref('product.product_uom_categ_kgm').id
        unit_uom_categ_id = self.env.ref('product.product_uom_categ_unit').id
        self.env.cr.execute("""
            create or replace view report_intrastat as (
                select
                    to_char(inv.date_invoice, 'YYYY') as name,
                    to_char(inv.date_invoice, 'MM') as month,
                    min(inv_line.id) as id,
                    intrastat.id as intrastat_id,
                    upper(inv_country.code) as code,
                    inv_address.vat as partner_vat,
                    sum(case when inv_line.price_unit is not null
                            then inv_line.price_unit * inv_line.quantity
                            else 0
                        end) as value,
                    sum(
                        case 
                        when uom.category_id = puom.category_id and puom.category_id = %s
                        then (inv_line.quantity / uom.factor)
                        when uom.category_id = puom.category_id and puom.category_id != %s
                        then (pt.weight * inv_line.quantity / uom.factor)
                        else 0 end
                    ) as weight,
                    sum(
                        case 
                        when uom.category_id = %s
                        then (inv_line.quantity / uom.factor)
                        else 0 end
                    ) as supply_units,

                    inv.currency_id as currency_id,
                    case when inv.type in ('out_invoice', 'out_refund') then inv.number else inv.reference end as ref,
                    case when inv.type in ('out_invoice','in_refund')
                        then 'export'
                        else 'import'
                        end as type,
                    inv.company_id as company_id,
                    stock_incoterms.code as delivery_terms,
                    ks.code as kilmes_salis,
                     case when inv.type in ('out_invoice','in_invoice')
                        then '1'
                        else '2'
                        end as transaction_code,
                    pt.intrastat_description as intrastat_description,
                    pt.name as product_description
                from
                    account_invoice inv
                    left join stock_incoterms on inv.incoterms_id=stock_incoterms.id
                    left join account_invoice_line inv_line on inv_line.invoice_id=inv.id
                    left join (product_template pt
                        left join product_product pp on (pp.product_tmpl_id = pt.id))
                    on (inv_line.product_id = pp.id)
                    left join res_country ks on pt.kilmes_salis=ks.id
                    left join product_uom uom on uom.id=inv_line.uom_id
                    left join product_uom puom on puom.id = pt.uom_id
                    left join report_intrastat_code intrastat on pt.intrastat_id = intrastat.id
                    left join (res_partner inv_address
                        left join res_country inv_country on (inv_country.id = inv_address.country_id))
                    on (inv_address.id = inv.partner_id)
                where
                    inv.state in ('open','paid')
                    and inv_line.product_id is not null
                    and inv_country.intrastat=true
                group by to_char(inv.date_invoice, 'YYYY'), to_char(inv.date_invoice, 'MM'),intrastat.id,inv.type,pt.intrastat_id, inv_country.code,inv.number,inv.reference,inv.currency_id, inv.company_id, stock_incoterms.code, ks.code, pt.intrastat_description, pt.name, inv_address.vat
            )""", (weight_uom_categ_id, weight_uom_categ_id, unit_uom_categ_id))


ReportIntrastat()
