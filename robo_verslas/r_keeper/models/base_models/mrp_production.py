# -*- coding: utf-8 -*-
import logging
from odoo.addons.queue_job.job import identity_exact, job
from odoo import models, fields, api


_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    r_keeper_sale_line_ids = fields.One2many(
        'r.keeper.sale.line', 'mrp_production_id', string='rKeeper pardavimo eilutės'
    )

    @job
    @api.multi
    def produce_r_keeper_sales(self):
        """
        Tries to confirm production of rKeeper sales.
        If surplus production is activated in the company
        check for automatic rKeeper surplus mode.
        :return: None
        """
        self.ensure_one()
        produce_surplus = False
        configuration = self.env['r.keeper.configuration'].get_configuration()
        # Check whether base surplus production is enabled in rKeeper configuration
        base_surplus_enabled = configuration.manufacturing_surplus_enabled and \
            configuration.automatic_surplus_manufacturing_mode == 'produce_surplus'
        if base_surplus_enabled:
            insufficient_stock_moves = self.move_raw_ids.filtered(
                lambda x: x.insufficient_stock
            )
            # If surplus is enabled and we have insufficient stock moves -
            # check for uom to skip and enable surplus on condition
            if insufficient_stock_moves:
                _logger.info('rKeeper data processing: Checking if production surplus can be used for production %s', self.id)
                # Check whether there's any uom to skip
                uom_to_skip = configuration.auto_surplus_skip_uom_id
                if not uom_to_skip or uom_to_skip and all(
                        x.product_id.uom_id.id != uom_to_skip.id for x in insufficient_stock_moves):
                    produce_surplus = True
        # Either produce surplus or try to assign the moves
        if produce_surplus:
            _logger.info('rKeeper data processing: creating production surplus wizard for production %s', self.id)
            wizard = self.env['mrp.production.surplus.reserve'].create({
                'production_id': self.id,
            })
            wizard.process()
        else:
            self.action_assign()
        channel = self.env['r.keeper.data.import'].get_channel_to_use(1, 'confirm_stock_moves')
        self.with_delay(eta=30, channel=channel, identity_key=identity_exact, priority=50).produce_simplified()

    @api.model
    def get_base_product_domain(self):
        """Returns base product domain for production on-changes"""
        base_domain = [('type', '=', 'product'), ('r_keeper_pos_filter', '=', False)]
        return base_domain
