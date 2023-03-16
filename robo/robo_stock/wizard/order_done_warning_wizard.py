# -*- coding: utf-8 -*-
from odoo import models, fields, api


class OrderDoneWarningWizard(models.TransientModel):
    """
    Wizard used to display the warning to the user that may be raised during
    purchase/sale order action_done
    """
    _name = 'order.done.warning.wizard'

    sale_order_id = fields.Many2one('sale.order', string='Pardavimo užsakymas')
    purchase_order_id = fields.Many2one('purchase.order', string='Pirkimo užsakymas')
    warning_message = fields.Text(string='Klaidos pranešimas')

    @api.multi
    def action_order_close(self):
        """
        Execute action_done/button_done on related sale or purchase order by skipping amount constraints
        :return: None
        """
        self.ensure_one()
        if self.sale_order_id:
            self.sale_order_id.with_context(skip_amount_constraints=True).action_done()
        if self.purchase_order_id:
            self.purchase_order_id.with_context(skip_amount_constraints=True).button_done()


OrderDoneWarningWizard()
