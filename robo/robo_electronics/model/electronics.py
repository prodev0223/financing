# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, tools, exceptions
import odoo.addons.decimal_precision as dp
import math


BATTERY_TYPES = [
    ('17', 'Baterijos (galvaniniai elementai)'),
    ('18', 'Į prietaisus įmontuotos baterijos (galvaniniai elementai)'),
    ('19', 'Automobiliams skirti akumuliatoriai'),
    ('20', 'Automobiliams skirti akumuliatoriai, įmontuoti į transporto priemones'),
    ('21', 'Pramoniniai akumuliatoriai'),
    ('22', 'Į prietaisus įmontuoti pramoniniai akumuliatoriai'),
    ('23', 'Nešiojami akumuliatoriai'),
    ('24', 'Į prietaisus įmontuoti nešiojami akumuliatoriai')
]


ELECTRONICS_CATEGORIES = [
    ('69', 'Temperatūros keitimo įranga'),
    ('70', 'Ekranai, monitoriai ir įranga, kurioje yra ekranų, kurių paviršiaus plotas didesnis nei 100 cm2'),
    ('71', 'Lempos'),
    ('72', 'Stambi įranga (bent vienas iš išorinių išmatavimų didesnis nei 50 cm)'),
    ('73', 'Smulki įranga (nė vienas iš išorinių išmatavimų neviršija 50 cm)'),
    ('74', 'Smulki IT ir telekominukacijų įranga (nė vienas iš išorinių išmatavimų neviršija 50 cm)')
]


class ProductBatteryLines(models.Model):

    _name = 'product.battery.line'

    product_tmpl_id = fields.Many2one('product.template', string='Produktas', required=True)
    battery_id = fields.Many2one('product.battery', string="Baterija", required=True)
    battery_qty = fields.Integer(string='Vnt.', required=True)
    total_weight = fields.Float(string='Bendras svoris, kg', compute='_compute_total_weights', store=True)
    date_from = fields.Date(string='Naudojama nuo')
    date_to = fields.Date(string='Naudojama iki')
    # battery_category = fields.Selection(related='battery_id.category')
    # battery_weight = fields.Float(related='battery_id.weight')

    @api.one
    @api.depends('battery_qty', 'battery_id.weight')
    def _compute_total_weights(self):
        if self.battery_qty and self.battery_id.weight:
            self.total_weight = self.battery_qty * self.battery_id.weight

    @api.multi
    @api.constrains('date_to', 'date_from')
    def _check_dates(self):
        for rec in self:
            if rec.date_to and rec.date_from and rec.date_to < rec.date_from:
                raise exceptions.ValidationError(_('Data nuo negali būti vėliau, nei data iki.'))


ProductBatteryLines()


class ProductBattery(models.Model):

    _name = 'product.battery'

    name = fields.Char(string='Unikalus pavadinimas', required=True)
    category = fields.Selection(BATTERY_TYPES, required=True, string="Kategorija",
                                help="Baterijos/Akumuliatoriaus kategorija")
    weight = fields.Float(string='Vnt. svoris, kg', required=True, digits=(16, 4))

    _sql_constraints = [
        ('product_battery_name_unique', 'UNIQUE (name)', 'Pavadinimas turi būti unikalus'),
    ]


ProductBattery()


class ProductTemplate(models.Model):

    _inherit = 'product.template'

    product_electronics_category = fields.Selection(ELECTRONICS_CATEGORIES, string='Elektronikos kategorija', )
    product_battery_line_ids = fields.One2many('product.battery.line', 'product_tmpl_id',
                                               string='Priskirtos baterijos, akumuliatoriai',
                                               sequence=100,
                                               )


ProductTemplate()


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    package_direction = fields.Selection([('in_lt', 'Įvežta iš Lietuvos'),
                                          ('in', 'Importas'),
                                          ('out_lt', 'Išleista į Lietuvos rinką'),
                                          ('out_kt', 'Išsiuntimai už Lietuvos ribų'),
                                          ('int', 'Vidiniai')],
                                         string='Tiekimas', compute='_package_direction', store=True)

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
