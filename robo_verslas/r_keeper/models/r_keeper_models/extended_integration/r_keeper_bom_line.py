# -*- coding: utf-8 -*-

from odoo import models, fields


class RKeeperBomLine(models.Model):
    """
    TODO: FILE NOT USED AT THE MOMENT
    Model used to hold rKeeper bill of materials
    for specific product. Corresponds to mr.bom
    in our system.
    """
    _name = 'r.keeper.bom.line'

    # Man stands for manufactured
    ext_man_product_id = fields.Integer(string='External ID')
    man_product_code = fields.Char(string='Product code')

    component_id = fields.Many2one('r.keeper.product')
    r_keeper_bom_id = fields.Many2one('r.keeper.bom', string='Bill of material')
