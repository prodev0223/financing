# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _
import logging

_logger = logging.getLogger(__name__)


class RKeeperPOSUpdateWizard(models.TransientModel):
    _name = 'r.keeper.pos.update.wizard'
    _description = '''
    Wizard that is used to update point of sale data
    with passed product configuration. Called from the template
    '''

    product_ids = fields.Many2many('product.template', string='Perkeliami produktai')
    point_of_sale_ids = fields.Many2many(
        'r.keeper.point.of.sale',
        string='Atnaujinami pardavimo taškai'
    )

    @api.multi
    def update_points_of_sale(self):
        """
        Method that is used to update
        points of sale lines with information
        from product template. If product
        line does not exist - line is created.
        :return: JS action to reload view
        """

        def prepare_new_line(prod, update=False):
            """Gathers data from product template"""
            base_data = {
                'price_unit': prod.r_keeper_price_unit,
                'vat_rate': prod.r_keeper_vat_rate,
                'product_state': prod.r_keeper_product_state,
                'is_weighed': prod.r_keeper_is_weighed,
                'related_product_id': prod.r_keeper_related_product_id.id,
                'related_product_uom_id': prod.r_keeper_related_product_id.uom_id.id,
            }
            if not update:
                base_data.update({
                    'product_id': prod.id,
                    'category_id': prod.categ_id.id,
                    'uom_id': prod.uom_id.id,
                })
            return base_data

        # Check basic constraints
        if not self.point_of_sale_ids:
            raise exceptions.ValidationError(_('Nepaduotas nė vienas pardavimo taškas'))
        if not self.product_ids:
            raise exceptions.ValidationError(_('Nepaduotas nė vienas produktas'))

        non_r_keeper_products = self.product_ids.filtered(lambda x: not x.r_keeper_product)
        if non_r_keeper_products:
            error_message = _('Apačioje pateikti produktai nepriklauso rKeeper produktų kategorijai: \n\n')
            for product in non_r_keeper_products:
                error_message += '{}\n'.format(product.display_name)
            raise exceptions.ValidationError(error_message)

        # Loop through points of sale, and create/update product lines
        for pos in self.point_of_sale_ids:
            lines = pos.point_of_sale_product_ids
            product_lines_to_create = []

            # Map current point of sale lines - product ID is the key, and related line is the value
            product_data = {}
            for line in lines:
                product_data.setdefault(line.product_id.id, self.env['r.keeper.point.of.sale.product'])
                product_data[line.product_id.id] |= line

            # Loop through passed products and check whether they exist in current point of sale
            for product in self.product_ids:
                product_line = product_data.get(product.id)
                # If product exists in current pos, update it's data
                if product_line:
                    data_to_write = prepare_new_line(product, update=True)
                    product_line.write(data_to_write)
                else:
                    # Otherwise, product is created
                    data_to_create = prepare_new_line(product)
                    product_lines_to_create.append((0, 0, data_to_create))

                # After product info was transferred, mark need to update as False
                product.r_keeper_update = False

            # If we have product lines to created after looping is done
            # create them and link them to the POS
            if product_lines_to_create:
                pos.write({'point_of_sale_product_ids': product_lines_to_create})

        return {'type': 'ir.actions.act_close_wizard_and_reload_view'}
