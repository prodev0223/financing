# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, tools, exceptions
import odoo.addons.decimal_precision as dp
import math


class ProductPackageDefault(models.Model):
    _name = "product.package.default"

    package_id = fields.Many2one('product.package', required=True, string='Pakuotė')
    date_from = fields.Date(string='Naudojama nuo')
    date_to = fields.Date(string='Naudota iki')
    partner_id = fields.Many2one('res.partner', string='Partneris')
    qty_in_pack = fields.Integer(string='Kiekis pakuotėje', required=True)
    product_uom = fields.Many2one('product.uom', 'Matavimo vnt.') # nenaudojamas
    # related, readonly
    package_category = fields.Selection(related='package_id.package_category', readonly=True)
    material_type = fields.Selection(related='package_id.material_type', readonly=True)
    use_type = fields.Selection(related='package_id.use_type', readonly=True)
    recycling_type = fields.Selection(related='package_id.recycling_type', readonly=True)
    weight = fields.Float(related='package_id.weight', readonly=True)

    product_tmpl_id = fields.Many2one('product.template', required=True, string='Produktas', ondelete='cascade')

    @api.one
    @api.depends('product_uom')
    def _compute_qty_in_pack_uom_id(self):
        if self.product_tmpl_id:
            self.qty_in_pack_uom_id = self.product_tmpl_id.uom_id.id

    @api.constrains('qty_in_pack')
    def constrain_qty_in_pack(self):
        for rec in self:
            if rec.qty_in_pack <= 0:
                raise exceptions.ValidationError(_('Kiekis pakuotėje privalo būti teigiamas'))

    @api.multi
    @api.constrains('date_to', 'date_from')
    def _check_dates(self):
        for rec in self:
            if rec.date_to and rec.date_from and rec.date_to < rec.date_from:
                raise exceptions.ValidationError(_('Data nuo negali būti vėliau, nei data iki.'))

    @api.multi
    def name_get(self):
        return [(rec.id, _('Pakuotė')) for rec in self]


ProductPackageDefault()


class ProductPackage(models.Model):
    _name = "product.package"

    name = fields.Char(string='Pavadinimas', required=True)

    package_category = fields.Selection([('pirmine', 'Prekinė (pirminė)'), ('antrine', 'Grupinė (antrinė)'),
                                         ('tretine', 'Transporto (tretinė)'), ('nenurodoma', 'Nenurodoma')],
                                        required=True, string="Pakuotės kategorija")

    material_type = fields.Selection([('metalas', 'Metalas'), ('plastikas', 'Plastikas'), ('stiklas', 'Stiklas'),
                                      ('popierius', 'Popierius'), ('medis', 'Medis'), ('pet', 'PET'),
                                      ('kombinuota', 'Kombinuota'), ('kita', 'Kita')],
                                     required=True, string='Medžiaga', inverse='_set_material_type')

    weight = fields.Float(
        string='Pakuotės svoris, kg', required=True,
        digits=dp.get_precision('Stock Weight'),
    )
    use_type = fields.Selection([('vienkartine', 'Vienkartinė'), ('daukartine', 'Daugkartinė')],
                                string='Vienkartinė/Daugkartinė', required=True)
    recycling_type = fields.Selection([('perdirbama', 'Perdirbama'), ('neperdirbama', 'Neperdirbama')],
                                      string='Perdirbama/Neperdirbama', required=True)
    combined_material = fields.Selection([('metalas', 'Metalas'), ('plastikas', 'Plastikas'), ('stiklas', 'Stiklas'),
                                          ('popierius', 'Popierius'), ('medis', 'Medis'), ('pet', 'PET'),
                                          ('kita', 'Kita')], string='Kombinuota (vyraujanti medžiaga)')

    _sql_constraints = [
        ('teigiamas_svoris', 'CHECK(weight >= 0.0)', 'Svoris turi būti teigiamas!')
    ]

    @api.multi
    def _set_material_type(self):
        self.filtered(lambda p: p.material_type != 'kombinuota').write({'combined_material': False})

    @api.constrains('material_type', 'combined_material')
    def _check_material_type_combined_material(self):
        if any(rec.material_type == 'kombinuota' and not rec.combined_material for rec in self):
            raise exceptions.ValidationError(_('Nurodykite vyraujančią medžiagą.'))


ProductPackage()


class PickingPackageLine(models.Model):
    _name = 'picking.package.line'

    product_tmpl_id = fields.Many2one('product.template', string='Produktas', required=False)
    product_uom_qty = fields.Float(string='Produkto kiekis', digits=dp.get_precision('Product Unit of Measure'))  # Default is Vaztarascio
    product_uom = fields.Many2one('product.uom', string='Matavimo vienetas', compute='_compute_product_uom',
                                  store=True)
    package_id = fields.Many2one('product.package', string='Pakuotė', required=True)
    qty_package = fields.Integer(string='Pakuočių kiekis')

    picking_id = fields.Many2one('stock.picking', string='Važtaraštis', required=True, ondelete='cascade')

    third_category = fields.Boolean(compute='_compute_package_category')
    package_category = fields.Selection(related='package_id.package_category', readonly=True)

    # @api.one
    # @api.constrains('package_id', 'product_tmpl_id', 'package_category')
    # def constraint_product_required(self):
    #     if self.package_id and self.package_id.package_category != 'tretine' and not self.product_tmpl_id:
    #         raise exceptions.ValidationError(_('Parinkite produktą pakuotei, jei ji ne tretinės kategorijos'))

    @api.onchange('package_id')
    def _compute_package_category(self):
        for r in self:
            r.third_category = False
            if r.package_id and r.package_id.package_category == 'tretine':
                r.third_category = True

    @api.one
    @api.depends('product_tmpl_id')
    def _compute_product_uom(self):
        if self.product_tmpl_id:
            self.product_uom = self.product_tmpl_id.uom_id.id


PickingPackageLine()


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    product_package_default_ids = fields.One2many('product.package.default', 'product_tmpl_id',
                                                  string='Produkto numatytosios pakuotės', copy=True)


ProductTemplate()


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    picking_package_lines_ids = fields.One2many('picking.package.line', 'picking_id', string='Važtaraščio pakuotės',
                                                copy=True, sequence=100,
                                                )
    review_packages = fields.Boolean(string='Reikia peržiūrėti pakuotes', default=False)
    picking_package_lines_default = fields.Html(compute='_compute_default_picking_packages', store=False)
    use_default_package = fields.Boolean(string='Naudoti numatytuosius produkto pakuotės nustatymus', default=True,
                                         )
    package_direction = fields.Selection([('in_lt', 'Įvežta iš Lietuvos'),
                                          ('in', 'Importas'),
                                          ('out_lt', 'Išleista į Lietuvos rinką'),
                                          ('out_kt', 'Išsiuntimai už Lietuvos ribų'),
                                          ('int', 'Vidiniai')],
                                         string='Tiekimas', compute='_package_direction', store=True)

    @api.multi
    def action_packaged_reviewed(self):
        self.review_packages = False

    @api.multi
    @api.depends('location_id', 'location_dest_id', 'partner_id.country_id')
    def _package_direction(self):
        lt_country = self.env['res.country'].search([('code', '=', 'LT')], limit=1)
        for rec in self:
            package_direction = 'int'
            lt_partner = rec.partner_id.country_id.id == lt_country.id
            if rec.location_id.usage == 'internal' and rec.location_dest_id.usage != 'internal':
                package_direction = 'out_lt' if lt_partner else 'out_kt'
            elif rec.location_id.usage != 'internal' and rec.location_dest_id.usage == 'internal':
                package_direction = 'in_lt' if lt_partner else 'in'
            rec.package_direction = package_direction

    @api.depends('use_default_package', 'move_lines', 'min_date', 'partner_id')
    @api.one
    def _compute_default_picking_packages(self):
        Qweb = self.env['ir.qweb']
        if self.use_default_package:
            lines = ""
            for move in self.move_lines:
                for package_default in move.product_tmpl_id.product_package_default_ids:
                    if (not package_default.date_from or package_default.date_from <= (self.min_date or '')[:10]) \
                            and (not package_default.date_to or package_default.date_to >= (self.min_date or '')[:10]) \
                            and (not package_default.partner_id or package_default.partner_id == self.partner_id):
                        lines += Qweb.render('robo_package.robo_product_package_default_line',
                                            {"product": move.product_tmpl_id.name,
                                             "product_uom_qty": move.product_qty,
                                             "package": package_default.package_id.name,
                                             "qty_package": math.ceil(tools.float_round(move.product_qty / package_default.qty_in_pack, 2) if package_default.qty_in_pack > 0 else 0.0)
                                             })
            self.picking_package_lines_default = Qweb.render('robo_package.robo_product_package_default_table', {"table_body": lines})

    @api.onchange('use_default_package', 'move_lines')
    def CRUD_picking_package_line(self):
        if not self.use_default_package:
            lines_ids = []
            # TODO: maybe we want to generate new package lines if move_lines change??
            if not self.picking_package_lines_ids:
                for move in self.move_lines:
                    for package_default in move.product_tmpl_id.product_package_default_ids:
                        if (not package_default.date_from or package_default.date_from <= (self.min_date or '')[:10])\
                                and (not package_default.date_to or package_default.date_to >= (self.min_date or '')[:10])\
                                and (not package_default.partner_id or package_default.partner_id == self.partner_id):
                            lines_ids.append((0, 0, {'product_tmpl_id': move.product_tmpl_id.id,
                                                     'product_uom_qty': move.product_qty,
                                                     'package_id': package_default.package_id.id,
                                                     'qty_package': math.ceil(tools.float_round(move.product_qty / package_default.qty_in_pack, 2) if package_default.qty_in_pack > 0 else 0.0)
                                                     }))
                if len(lines_ids) != 0:
                    self.picking_package_lines_ids = lines_ids


StockPicking()


class ReportPackages(models.Model):
    _name = "report.product.packages"
    _auto = False

    picking_id = fields.Many2one('stock.picking', 'Dokumentas')
    product_tmpl_id = fields.Many2one('product.template', 'Produktas')
    partner_id = fields.Many2one('res.partner', 'Partneris')
    product_qty = fields.Float(string='Kiekis')

    package_id = fields.Many2one('product.package', 'Pakuotė')
    package_category = fields.Char('Pakuotės kategorija')
    material_type = fields.Char('Medžiaga')
    use_type = fields.Char(string='Vienkartinė/Daugkartinė')
    recycling_type = fields.Char('Perdirbama/Neperdirbama')
    combined_material = fields.Char(string='Kombinuota (vyraujanti medžiaga)')
    package_direction = fields.Selection([('in_lt', 'Įvežta iš Lietuvos'),
                                          ('in', 'Importas'),
                                          ('out_lt', 'Išleista į Lietuvos rinką'),
                                          ('out_kt', 'Išsiuntimai už Lietuvos ribų'),
                                          ('int', 'Vidiniai')],
                                         string='Pervežimo tipas')

    qty_of_packages = fields.Float(string='#Pakuočių')
    weight_of_packages = fields.Float(string='Svoris, kg')

    date = fields.Date(string='Data')

    calculation_type = fields.Selection([('manual', 'Rankinis'), ('auto', 'Automatinis')], string='Suvedimo būdas')
    origin = fields.Char(string='Susijęs dokumentas')

    @api.model_cr
    def init(self):
        self._cr.execute('Drop MATERIALIZED VIEW IF EXISTS report_product_packages')
        self._cr.execute("""
            CREATE MATERIALIZED VIEW report_product_packages AS (
                SELECT ROW_NUMBER() OVER (ORDER BY product_tmpl_id) AS id, * FROM
                (
                    SELECT 
                           stock_picking.id                                 AS picking_id
                         , product_product.product_tmpl_id                  AS product_tmpl_id
                         , stock_move.product_qty                           AS product_qty
                         , stock_picking.partner_id                         AS partner_id
                         , product_package_default.package_id
                         , CASE WHEN product_package_default.qty_in_pack = 0
                                THEN 0
                                ELSE CEIL(round(stock_move.product_qty / product_package_default.qty_in_pack, 2))
                           END                                              AS qty_of_packages
                         , product_package.weight * (
                                CASE WHEN product_package_default.qty_in_pack = 0
                                     THEN 0
                                     ELSE CEIL(round(stock_move.product_qty / product_package_default.qty_in_pack, 2))
                                END)                                        AS weight_of_packages
                         , product_package.package_category
                         , product_package.material_type
                         , product_package.use_type
                         , product_package.recycling_type
                         , product_package.combined_material
                         , stock_picking.min_date::date                     AS date
                         , stock_picking.package_direction
                         , 'auto'                                           AS calculation_type
                         , stock_picking.origin                             AS origin
                    FROM stock_picking
                    LEFT JOIN stock_move
                                ON stock_picking.id = stock_move.picking_id
                    LEFT JOIN product_product
                                ON product_product.id = stock_move.product_id
                    LEFT JOIN product_package_default
                                ON product_product.product_tmpl_id = product_package_default.product_tmpl_id
                               AND (product_package_default.date_from IS NULL
                                    OR product_package_default.date_from <= (stock_picking.min_date::date))
                               AND (product_package_default.partner_id IS NULL
                                    OR product_package_default.partner_id = stock_picking.partner_id)
                               AND (product_package_default.date_to IS NULL
                                    OR product_package_default.date_to >= (stock_picking.min_date::date))
                    LEFT JOIN product_package
                                ON product_package.id = product_package_default.package_id

                    WHERE stock_picking.state = 'done'
                      AND stock_picking.use_default_package = True
                      AND stock_picking.cancel_state <> 'error'

                    UNION ALL

                    SELECT stock_picking.id                                             AS picking_id
                         , picking_package_line.product_tmpl_id                         AS product_tmpl_id
                         , picking_package_line.product_uom_qty                         AS product_uom_qty
                         , stock_picking.partner_id                                     AS partner_id
                         , picking_package_line.package_id
                         , picking_package_line.qty_package                             AS qty_of_packages
                         , product_package.weight * picking_package_line.qty_package    AS weight_of_packages
                         , product_package.package_category
                         , product_package.material_type
                         , product_package.use_type
                         , product_package.recycling_type
                         , product_package.combined_material
                         , stock_picking.min_date::date                                 AS date
                         , stock_picking.package_direction
                         , 'manual'                                                     AS calculation_type
                         , stock_picking.origin                                         AS origin
                    FROM stock_picking
                    LEFT JOIN picking_package_line
                                ON stock_picking.id = picking_package_line.picking_id
                    LEFT JOIN product_package
                                ON product_package.id = picking_package_line.package_id

                    WHERE stock_picking.state = 'done'
                      AND stock_picking.cancel_state <> 'error'
                      AND stock_picking.use_default_package = False
                      AND (stock_picking.review_packages IS NULL
                           OR stock_picking.review_packages = False)
                ) report
            )""")

    def refresh_materialised_product_packages_history(self):
        self._cr.execute(''' REFRESH MATERIALIZED VIEW report_product_packages;''')


ReportPackages()


class StockMove(models.Model):
    _inherit = 'stock.move'

    @api.multi
    def action_done(self):
        res = super(StockMove, self).action_done()
        for rec in self:
            if rec.error and rec.picking_id.original_picking_id:
                rec.picking_id.original_picking_id.write({'review_packages': True, 'use_default_package': False})
                rec.picking_id.original_picking_id.CRUD_picking_package_line()
        return res


StockMove()
