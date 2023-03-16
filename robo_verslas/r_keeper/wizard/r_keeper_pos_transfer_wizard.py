# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _
import logging

_logger = logging.getLogger(__name__)


class RKeeperPOSTransferWizard(models.TransientModel):
    _name = 'r.keeper.pos.transfer.wizard'
    _description = '''
    Wizard that is used to transfer all point of sale
    product line data to another point of sale
    '''

    destination_point_of_sale_id = fields.Many2one(
        'r.keeper.point.of.sale',
        string='Esamas pardavimo taškas', readonly=True
    )
    source_point_of_sale_id = fields.Many2one(
        'r.keeper.point.of.sale',
        string='Perkeliamas pardavimo taškas'
    )
    transfer_mode = fields.Selection(
        [('update_data', 'Atnaujinti duomenis'),
         ('rewrite_data', 'Perrašyti duomenis')
         ], string='Perkėlimo rėžimas', default='rewrite_data'
    )

    @api.multi
    def transfer_data(self):
        """
        Transfers one point of sale product line
        data to another, based on the mode
        :return: JS action to reload view
        """

        def prepare_new_line(source_line, rewrite=True):
            """Gathers data-to-transfer from source line"""
            data = {
                'price_unit': source_line.price_unit,
                'vat_rate': source_line.vat_rate,
                'product_state': source_line.product_state,
                'is_weighed': source_line.is_weighed,
                'related_product_id': source_line.related_product_id.id,
                'related_product_uom_id': source_line.related_product_uom_id.id,
            }
            if rewrite:
                data.update({
                    'product_id': source_line.product_id.id,
                    'category_id': source_line.category_id.id,
                    'uom_id': source_line.uom_id.id,
                })
            return data

        # Check base constraints
        if not self.destination_point_of_sale_id:
            raise exceptions.ValidationError(_('Nenurodytas perkeliamas pardavimo takas'))
        if self.destination_point_of_sale_id == self.source_point_of_sale_id:
            raise exceptions.ValidationError(_('Negalima nurodyti to paties pardavimo taško'))
        if not self.transfer_mode:
            raise exceptions.ValidationError(_('Nenurodytas perkėlimo rėžimas'))

        d_lines = self.destination_point_of_sale_id.point_of_sale_product_ids
        s_lines = self.source_point_of_sale_id.point_of_sale_product_ids
        new_lines = []

        rewrite_mode = self.transfer_mode == 'rewrite_data'
        if rewrite_mode:
            # Unlink all of current lines
            d_lines.unlink()

        for line in s_lines:
            # Create the line only if it's not already in destination lines
            corresponding_d_line = d_lines.filtered(lambda x: x.product_id.id == line.product_id.id)
            if rewrite_mode or not corresponding_d_line:
                line_data = prepare_new_line(line)
                new_lines.append((0, 0, line_data))
            else:
                line_data = prepare_new_line(line, rewrite=False)
                corresponding_d_line.write(line_data)

        # Write new lines to destination POS
        if new_lines:
            self.destination_point_of_sale_id.write({
                'point_of_sale_product_ids': new_lines,
            })

        return {'type': 'ir.actions.act_close_wizard_and_reload_view'}

