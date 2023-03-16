# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    autocreate_lot_number = fields.Boolean(
        string='Gamybos metu automatiškai sukurti SN/partijos numerį', default=False,
        help='Nustačius, gamybos metu pagamintai produkcijai bus automatiškai suteikiami SN/partijų numeriai',
        sequence=100,
    )
    default_production_location_id = fields.Many2one(
        'stock.location', string='Numatytoji žaliavų lokacija',
        domain=[('usage', '=', 'internal')],
        sequence=100
    )
    production_location_id = fields.Many2one(
        'stock.location', string='Paveldėta numatytoji žaliavų lokacija',
        compute='_compute_production_location',
    )
    bom_id = fields.Many2one(
        'mrp.bom', string='Susijusi komplektacija',
        compute='_compute_bom_id',
        seqence=100
    )
    skip_recursive_bom_splitting = fields.Boolean(
        string='Neskaidyti produkto komplektacijos komponentuose'
    )
    produce_delay = fields.Float(sequence=100)
    bom_ids = fields.One2many(sequence=100)
    uom_id = fields.Many2one('product.uom', inverse='_set_uom_id')

    @api.multi
    def _compute_bom_id(self):
        """
        Gets active bill of material
        for current product at current date
        :return: None
        """
        for rec in self:
            rec.bom_id = self.env['mrp.bom']._bom_find(product_tmpl=rec)

    @api.one
    @api.depends('default_production_location_id', 'categ_id')
    def _compute_production_location(self):
        location = self.default_production_location_id
        category = self.categ_id
        while not location and category:
            location = category.default_production_location_id
            category = category.parent_id
        if location:
            self.production_location_id = location

    @api.multi
    def _set_uom_id(self):
        """Ensure that related BOM UOMs are changed if product UOM is changed"""
        for rec in self.filtered('uom_id'):
            bom_recs = self.env['mrp.bom'].search([('product_tmpl_id', '=', rec.id)])
            bom_recs.write({'product_uom_id': rec.uom_id.id})

    @api.onchange('tracking')
    def onchange_tracking(self):
        if self.tracking == 'lot':
            self.autocreate_lot_number = self.env.user.company_id.sudo().autocreate_lot_number
        elif self.tracking == 'serial':
            self.autocreate_lot_number = self.env.user.company_id.sudo().autocreate_serial_number

        return super(ProductTemplate, self).onchange_tracking()
