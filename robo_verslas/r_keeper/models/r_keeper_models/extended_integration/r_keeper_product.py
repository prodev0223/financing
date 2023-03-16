# -*- coding: utf-8 -*-

from odoo import exceptions, models, fields, api, _


class RKeeperProduct(models.Model):
    """
    TODO: FILE NOT USED AT THE MOMENT
    Model used to hold rKeeper products.
    Corresponds to product.template in our system.
    """
    _name = 'r.keeper.product'

    ext_id = fields.Integer(string='External ID', inverse='_set_bom_data')
    code = fields.Char(string='Code', inverse='_set_bom_data')
    name = fields.Char(string='Name')
    uom_code = fields.Char(string='Unit of measure')

    product_type = fields.Selection([('complex', 'Complex'), ('raw', 'Raw')])

    r_bom_id = fields.Many2one('r.keeper.bom', string='Bill of materials')
    r_category_id = fields.Many2one('r.keeper.product.category', string='Product category')
    product_id = fields.Many2one('product.product', string='Related product')
    configured = fields.Boolean(compute='_compute_configured')

    @api.multi
    @api.depends('r_bom_id.configured', 'r_category_id.configured', 'product_id')
    def _compute_configured(self):
        """
        Compute //
        Check whether product is fully configured
        and ready to use
        :return: None
        """
        for rec in self:
            rec.configured = rec.r_bom_id and rec.r_category_id.configured and rec.product_id

    @api.multi
    def _set_bom_data(self):
        """
        Inverse //
        Find matching rKeeper bill of material
        record for current product
        :return: None
        """
        for rec in self.filtered(lambda x: not x.r_bom_id):
            r_bom = self.env['r.keeper.bom'].search([('ext_man_r_product_id', '=', rec.ext_id)])
            if not r_bom and rec.code:
                r_bom = r_bom.search([('man_r_product_code', '=', rec.code)])
            # Write changes to both records
            rec.r_bom_id = r_bom
            r_bom.man_r_product_id = rec

    @api.multi
    @api.constrains('ext_id')
    def _check_ext_id(self):
        for rec in self:
            if self.search_count([('ext_id', '=', rec.ext_id)]) > 1:
                raise exceptions.ValidationError(_('Product with this external ID already exists!'))

