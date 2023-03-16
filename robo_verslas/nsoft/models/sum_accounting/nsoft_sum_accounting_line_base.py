# -*- coding: utf-8 -*-
from odoo import models, fields, api


class NsoftSumAccountingLineBase(models.Model):
    """
    Model that holds data that is shared by nSoft sum accounting line objects:
        - nsoft.report.move.line
        - nsoft.purchase.line
    """
    _name = 'nsoft.sum.accounting.line.base'

    ext_product_category_id = fields.Integer(string='Išorinis prekės categorijos ID',
                                             inverse='_ext_product_category_id')
    nsoft_product_category_id = fields.Many2one('nsoft.product.category',
                                                string='nSoft produkto kategorija')

    @api.multi
    def _ext_product_category_id(self):
        """Inverse -- Get related nsoft product category"""
        for rec in self:
            rec.nsoft_product_category_id = self.env['nsoft.product.category'].search(
                [('external_id', '=', rec.ext_product_category_id)])

    @api.multi
    def recompute_fields(self):
        """
        Recalculate every inverse/compute field in the model
        :return:
        """
        self._ext_product_category_id()


NsoftSumAccountingLineBase()
