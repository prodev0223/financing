# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, exceptions
from odoo.addons.queue_job.job import identity_exact


class StockInventoryAdjustmentConfirmation(models.TransientModel):
    _name = 'stock.inventory.adjustment.confirmation'

    inventory_id = fields.Many2one('stock.inventory')
    warning_message = fields.Text(string='Warning message')

    @api.model
    def default_get(self, fields):
        res = super(StockInventoryAdjustmentConfirmation, self).default_get(fields)
        if not res.get('inventory_id') and self._context.get('active_id'):
            res['inventory_id'] = self._context['active_id']
        return res

    @api.multi
    def confirm(self):
        self.ensure_one()
        if self.inventory_id.job_status in ['progress', 'in_queue']:
            raise exceptions.UserError(_('There is already a job in progress on this stock inventory act'))
        if self.inventory_id.state != 'confirm':
            raise exceptions.UserError(_('You cannot do this action in the current state of the act'))

        if self.inventory_id:
            # self.inventory_id.action_done()
            self.inventory_id.with_delay(eta=5, channel='root.inventory', identity_key=identity_exact).action_done_job()
            self.inventory_id.write({'job_status': 'in_queue'})
