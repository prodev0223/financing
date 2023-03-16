# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, tools, _


class ProductCategory(models.Model):
    _inherit = 'product.category'

    r_keeper_category = fields.Boolean(
        string='rKeeper importuojamų produktų kategorija', track_visibility='onchange',
        help='Pažymėjus, produktai priklausantys šiai kategorijai '
             'bus versijuojami ir periodiškai siunčiami į rKeeper',
        inverse='_set_r_keeper_category',
    )
    r_keeper_pos_category = fields.Boolean(
        string='rKeeper kasos produktų kategorija', track_visibility='onchange',
        help='Pažymėjus, produktai priklausantys šiai kategorijai '
             'bus filtruojami iš gamybos, inventorizacijos ir važtaraščių dokumentų',
        inverse='_set_r_keeper_pos_category'
    )
    pos_filtering_activated = fields.Boolean(compute='_compute_pos_filtering_activated')

    # Constraints -----------------------------------------------------------------------------------------------------

    @api.multi
    def _compute_pos_filtering_activated(self):
        """Check whether POS filtering is activated globally"""
        configuration = self.env['r.keeper.configuration'].sudo().get_configuration(raise_exception=False)
        pos_filtering_activated = configuration.enable_pos_product_filtering
        for rec in self:
            rec.pos_filtering_activated = pos_filtering_activated

    @api.multi
    @api.constrains('r_keeper_category')
    def _check_r_keeper_category(self):
        """
        Constraints //
        If category is marked as non-rKeeper category,
        check whether it has any products that were
        exported to rKeeper server, and if it does
        raise an error.
        :return: None
        """
        for rec in self:
            if not rec.r_keeper_category:
                products = self.env['product.template'].search([('categ_id', '=', rec.id)])
                for product in products:
                    if self.env['r.keeper.point.of.sale.product'].search_count([('product_id', '=', product.id)]):
                        raise exceptions.ValidationError(
                            _('Negalite pakeisti šios kategorijos iš rKeeper į paprastą kategoriją. '
                              'Egzistuoja produktų kurie yra susiję su pardavimo taškais')
                        )

    @api.multi
    def _set_r_keeper_category(self):
        """
        If category is set as rKeeper category
        set rKeeper prices of related products
        if they are zero
        :return: None
        """
        for rec in self.filtered(lambda x: x.r_keeper_category):
            # Set default rKeeper prices to each category product
            products = self.env['product.template'].search([('categ_id', '=', rec.id)])
            # Filter out products with zero rKeeper price
            products = products.filtered(
                lambda x: tools.float_is_zero(x.r_keeper_price_unit, precision_digits=2)
            )
            for product in products:
                product.write({
                    'r_keeper_price_unit': product.list_price,
                })

    @api.multi
    def _set_r_keeper_pos_category(self):
        """
        If global POS filtering is activated, mark products
        as filtered or not based on the category setting
        :return: None
        """
        configuration = self.env['r.keeper.configuration'].sudo().get_configuration(raise_exception=False)
        if configuration.enable_pos_product_filtering:
            for rec in self:
                # Set default rKeeper prices to each category product
                product_variants = self.env['product.template'].search([('categ_id', '=', rec.id)]).mapped(
                    'product_variant_ids')
                product_variants.write({'r_keeper_pos_filter': rec.r_keeper_pos_category})
