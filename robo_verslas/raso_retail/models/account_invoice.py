# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    raso_line_ids = fields.One2many('raso.sales', 'invoice_id', string='Raso pardavimų eilutės')
    raso_invoice_id = fields.Many2one('raso.invoices')

    @api.multi
    def confirm_related_pickings(self):
        """
        Confirm (assign or transfer)
        related pickings of account.invoice records
        :return: None
        """
        pickings = self.mapped('picking_id')
        for picking in pickings:
            self.env.cr.commit()
            try:
                if picking.state in ['confirmed']:
                    picking.action_assign()
                if picking.state in ['assigned', 'partially_available']:
                    picking.do_transfer()
            except Exception as exc:
                self.env.cr.rollback()
                _logger.info(
                    'RR: Picking reconfirmation error.\nPicking ID: {}. Error: {}'.format(picking.id, exc.args[0]))


AccountInvoice()
