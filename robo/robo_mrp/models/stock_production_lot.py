# -*- coding: utf-8 -*-
from odoo import models, api


class StockProductionLot(models.Model):
    _inherit = 'stock.production.lot'

    @api.multi
    def _post_manual_create(self):
        """ Method to be overridden. Called after manual creation into database """
        return

    @api.multi
    def _update_expiry_dates(self, overwrite=False):
        """ Method to be overridden. Called after manual creation into database """
        return
