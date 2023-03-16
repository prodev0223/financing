# -*- coding: utf-8 -*-
from odoo import models, api


class StockPicking(models.Model):

    _inherit = 'stock.picking'

    @api.multi
    def do_print_picking(self):
        self.write({'printed': True})
        return self.env["report"].get_action(self, 'stock.report_deliveryslip')

StockPicking()
