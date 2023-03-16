# -*- coding: utf-8 -*-

from odoo import models, fields


class RKeeperDataExportRevision(models.Model):
    _name = 'r.keeper.data.export.revision'
    _description = '''
    Model that stores record exported to rKeeper and it's revision number
    '''

    data_export_id = fields.Many2one(
        'r.keeper.data.export',
        string='Susijęs eksporto objektas'
    )
    point_of_sale_product_id = fields.Many2one(
        'r.keeper.point.of.sale.product',
        string='Eksportuota eilutė'
    )
    product_id = fields.Many2one(
        'product.template',
        string='Eksportuotas produktas'
    )
    revision_number = fields.Integer(string='Įrašo versija')
