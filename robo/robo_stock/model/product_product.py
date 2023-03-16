# -*- coding: utf-8 -*-
from odoo import models, api, tools


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.multi
    def get_product_quantities(self, location):
        """
        Returns usable, total and display product
        quantities based on passed location and date
        :param location: stock.location record
        :return: dict
        """
        self.ensure_one()
        product = self.with_context(location=location.id)
        usable_quantity = total_quantity = 0.0
        if product.type != 'consu' and location:
            # Build quant domain
            location_domain = product._get_domain_locations()[0]
            base_quant_domain = [('product_id', '=', product.id)] + location_domain
            # Add only internal locations based on context
            if self._context.get('show_only_internal', True):
                base_quant_domain += [('location_id.usage', '=', 'internal')]

            # Behaviour moved from add-ons
            if self._context.get('lot_id'):
                base_quant_domain += [('lot_id', '=', self._context.get('lot_id'))]
            if self._context.get('owner_id'):
                base_quant_domain += [('owner_id', '=', self._context.get('owner_id'))]
            if self._context.get('package_id'):
                base_quant_domain += [('package_id', '=', self._context.get('package_id'))]

            # Read quant group cluster and group them into the dict
            quant_cluster = self.env['stock.quant'].read_group(
                base_quant_domain, ['product_id', 'qty'], ['product_id'])
            quantities_available = dict(
                (res['product_id'][0], res['qty']) for res in quant_cluster)
            # Get quantity available for current moment
            total_quantity = tools.float_round(
                quantities_available.get(product.id, 0.0), precision_rounding=product.uom_id.rounding)

            self.env.cr.execute('''
                SELECT SUM(qty) FROM stock_quant SQ 
                INNER JOIN stock_move SM ON SQ.reservation_id = SM.id 
                WHERE SM.product_id = %s AND SM.state in ('assigned', 'confirmed')
                AND SM.location_id = %s
                ''', (product.id, location.id, )
            )
            qty_reserved = self.env.cr.fetchone()[0] or 0.0
            qty_reserved = tools.float_round(qty_reserved, precision_rounding=product.uom_id.rounding)
            # Calculate usable quantity for current product
            usable_quantity = tools.float_round(
                total_quantity - qty_reserved, precision_rounding=product.uom_id.rounding)

        return {
            'usable_quantity': usable_quantity,
            'total_quantity': total_quantity,
            'display_quantity': '{} / ({})'.format(usable_quantity, total_quantity),
        }
