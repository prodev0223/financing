# -*- coding: utf-8 -*-

from odoo import models, fields, api


class RKeeperBom(models.Model):
    """
    TODO: FILE NOT USED AT THE MOMENT
    Model used to hold rKeeper bill of materials
    for specific product. Corresponds to mrp.bom
    in robo system.
    """
    _name = 'r.keeper.bom'

    # Man stands for manufactured
    ext_man_product_id = fields.Integer(string='External ID')
    man_product_code = fields.Char(string='Product code')

    valid_from = fields.Datetime(string='Valid from')
    valid_to = fields.Datetime(string='Expires on')

    ext_man_r_product_id = fields.Integer(string='External manufactured product ID', inverse='_set_man_product_data')
    man_r_product_code = fields.Char(string='Manufactured product code', inverse='_set_man_product_data')
    man_r_product_id = fields.Many2one('r.keeper.product', string='Manufactured product')
    bom_type = fields.Selection([
        ('complex', 'Complex'),
        ('normal', 'Normal'),
        ('view', 'View')], compute='_compute_bom_type', store=True
    )
    r_keeper_bom_line_ids = fields.One2many('r.keeper.bom.line', 'r_keeper_bom_id', string='Components')
    can_expire = fields.Boolean(compute='_compute_can_expire')

    bom_id = fields.Many2one('mrp.bom', string='Bill of material')

    @api.multi
    def _compute_bom_type(self):
        """
        Compute //
        If no other product is contained in the lines, BOM type is 'view' it means, that
        product cannot be manufactured and is already meant for selling.
        If current BOM has at least one line, and all of their BOMs are views,
        type is 'normal', if current BOM has at least one line and
        their type is 'normal' or 'complex', type is set as complex.
        :return: None
        """
        for rec in self:
            if not rec.r_keeper_bom_line_ids:
                rec.bom_type = 'view'
            elif rec.r_keeper_bom_line_ids and all(
                    x.bom_type == 'view' for x in rec.r_keeper_bom_line_ids.mapped('component_id.r_bom_id')):
                rec.bom_type = 'normal'
            else:
                rec.bom_type = 'complex'

    @api.multi
    @api.depends('valid_to')
    def _compute_can_expire(self):
        for rec in self:
            # Might as well just use valid_to, however
            # this naming provides more clarity
            rec.can_expire = rec.valid_to

    @api.multi
    def _set_man_product_data(self):
        """
        Inverse //
        Find matching rKeeper product record
        for current bom
        :return: None
        """
        for rec in self.filtered(lambda x: not x.man_r_product_id):
            man_product = self.env['r.keeper.product']
            if rec.ext_man_r_product_id:
                man_product = man_product.search([('ext_id', '=', rec.ext_man_r_product_id)])
            if not man_product and rec.man_r_product_code:
                man_product = man_product.search([('code', '=', rec.man_r_product_code)])

            # Write changes to both records
            rec.man_r_product_id = man_product
            man_product.r_bom_id = rec
