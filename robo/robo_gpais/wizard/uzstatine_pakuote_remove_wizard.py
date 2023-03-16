# -*- coding: utf-8 -*-
from odoo import models, fields, api


class UzstatinePakuoteRemoveWizard(models.TransientModel):
    _name = 'uzstatine.pakuote.remove.wizard'

    product_id = fields.Many2one('product.template', string='Produktas', readonly=True)
    uzstatine_pakuote_ids = fields.Many2many('uzstatine.pakuote', string='Trinamos užstatinių pakuočių eilutės',
                                             domain="[('product_tmpl_id','=',product_id)]")
    num_lines = fields.Integer(compute='_num_lines')

    @api.one
    @api.depends('uzstatine_pakuote_ids')
    def _num_lines(self):
        self.num_lines = len(self.uzstatine_pakuote_ids)

    @api.one
    def action_delete_lines(self):
        self.uzstatine_pakuote_ids.sudo().unlink()
