# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class RKeeperDataExportWizard(models.TransientModel):
    _name = 'r.keeper.data.export.wizard'
    _description = '''
    Wizard that is used to export current point
    of sale data to remote rKeeper server
    '''

    point_of_sale_product_ids = fields.Many2many(
        'r.keeper.point.of.sale.product',
        string='Eksportuojamos eilutės'
    )
    point_of_sale_id = fields.Many2one(
        'r.keeper.point.of.sale',
        string='Eksportuojamas pardavimo taškas'
    )

    @api.multi
    def export_data(self):
        """
        Method that prepares data to be
        exported to rKeeper server:
        Revisions are generated for each product line,
        export record is created, and data exported
        to remote rKeeper server
        :return: JS action to reload view
        """
        self.ensure_one()

        product_lines = self.point_of_sale_product_ids
        revision_lines = []
        for line in product_lines:
            revision_line = {
                'product_id': line.product_id.id,
                'revision_number': line.r_keeper_revision_number,
                'point_of_sale_product_id': line.id,
            }
            revision_lines.append((0, 0, revision_line))

        export = self.env['r.keeper.data.export'].sudo().create({
            'point_of_sale_id': self.point_of_sale_id.id,
            'revision_ids': revision_lines,
        })
        export.generate_export_file()
        return {'type': 'ir.actions.act_close_wizard_and_reload_view'}