# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api
from odoo.addons.queue_job.job import job


_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    r_keeper_sale_line_ids = fields.One2many(
        'r.keeper.sale.line', 'picking_id',
        string='rKeeper pardavimo eilutės',
        auto_join=True,
    )

    @api.multi
    @job
    def confirm_r_keeper_pickings(self):
        """
        Reserves and confirms the not done/cancel pickings
        of sale lines with created invoices
        :return: None
        """
        # Loop through pickings and try to reserve them
        for picking in self:
            _logger.info('rKeeper data processing: Confirming picking %s', picking.id)
            # It's always the same related invoice
            invoice = picking.invoice_ids and picking.invoice_ids[0]
            try:
                picking.confirm_delivery(invoice=invoice)
            except Exception as e:
                _logger.info('rKeeper data processing: Failed confirmation of picking %s', picking.id)
                picking.r_keeper_sale_line_ids.custom_rollback(
                    e.args[0], action_type='delivery_confirmation'
                )
            else:
                self.env.cr.commit()
