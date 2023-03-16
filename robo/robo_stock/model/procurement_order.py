# -*- encoding: utf-8 -*-
from odoo import models, api


class ProcurementOrder(models.Model):
    _inherit = 'procurement.order'

    @api.multi
    def action_open_purchase_order_front(self):
        """
        Reference and read the action to open
        the form view for related purchase order.
        :return: JS action (dict)
        """
        self.ensure_one()
        action = self.env.ref('robo_stock.open_robo_purchase_orders').read()[0]
        action['res_id'] = self.purchase_id.id
        action['target'] = 'current'
        return action

    @api.multi
    def action_open_procurement_orders_front(self):
        """
        Reference and read the action to open
        the tree view for procurements of related group_id.
        :return: JS action (dict)
        """
        self.ensure_one()
        action = self.env.ref('robo_stock.action_open_procurement_order').read()[0]
        action['domain'] = [('group_id', '=', self.group_id.id)]
        return action

    @api.multi
    def action_open_stock_pickings_front(self):
        """
        Reference and read the action to open
        the tree view for stock pickings of related group_id.
        :return: JS action (dict)
        """
        action = self.env.ref('robo_stock.open_robo_stock_picking').read()[0]
        action['domain'] = [('group_id', '=', self.group_id.id)]
        return action


ProcurementOrder()
