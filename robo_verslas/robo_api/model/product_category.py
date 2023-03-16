# -*- encoding: utf-8 -*-
from odoo import models, fields, api


class ProductCategory(models.Model):

    _inherit = 'product.category'

    skip_api_sync = fields.Boolean(string='Nesinchronizuoti per API')

    @api.model_cr
    def init(self):
        """
        Set systemic categories to skip API sync
        :return: None
        """
        categories_to_sync_ids = self.get_sys_categories_to_sync_ids()

        self.env['product.category'].search([('robo_category', '=', True), ('skip_api_sync', '=', False),
                                             ('id', 'not in', categories_to_sync_ids)]).write({'skip_api_sync': True})

    @api.model
    def get_sys_categories_to_sync_ids(self):
        """
        Get a list of systemic categories IDs that should be synced in API
        :return: A list of IDs
        """
        sys_categories_to_sync_ids = [
            self.env.ref('l10n_lt.product_category_30').id,
            self.env.ref('l10n_lt.product_category_2').id
        ]
        return sys_categories_to_sync_ids


ProductCategory()
