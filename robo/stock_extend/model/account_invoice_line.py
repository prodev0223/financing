# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    landed_cost_id = fields.Many2one('stock.landed.cost', string='Landed cost', copy=False)

    @api.multi
    def force_picking_aml_analytics_prep(self, check_constraint=False):
        """
        Groups and prepares picking move lines
        for analytic account forcing from the
        invoice line standpoint. (Other objects
        have different grouping)
        :return: None
        """

        # Behaviour from previous code kept -- On bigger refactor, can be split for robo_stock parts
        if check_constraint and not hasattr(self.env.user.company_id, 'politika_sandelio_apskaita'):
            return

        used_lines = self.env['account.move.line']
        # Filter out invoice lines
        filtered_invoice_lines = self.filtered(
            lambda x: x.product_id and x.product_id.type == 'product'
            and x.account_analytic_id
        )

        for line in filtered_invoice_lines:
            # Collect all of related pickings
            pickings = line.mapped('sale_line_ids.procurement_ids.move_ids.picking_id')
            pickings |= line.mapped('purchase_line_id.move_ids.picking_id')
            pickings |= line.invoice_id.get_related_pickings()

            # Loop through pickings and collect related move lines
            for picking in pickings:
                move_lines = self.env['account.move.line'].search([('ref', '=', picking.name)])
                used_lines |= line.force_picking_aml_analytics(move_lines, used_lines)

    @api.model
    def invoice_line_to_aml_matcher(self, invoice_line, move_lines, used_lines):
        """
        This part is split from the main method so it can be
        easily overridden in other modules.
        Filters out account move line batch based on
        account invoice line.
        """
        return move_lines.filtered(
            lambda x: x.product_id.id == invoice_line.product_id.id
            and x.account_id.code.startswith('6')
            and x not in used_lines
        )

    @api.multi
    def force_picking_aml_analytics(self, move_lines, used_lines=None):
        """
        Forces analytic accounts on picking move lines
        that are related to specific account invoice line record.
        Analytic account is taken from the invoice line
        Used lines indicates whether filtered move line was already used
        since there are lots of overlaps in stock move lines
        :return: None
        """
        self.ensure_one()

        def force_values(data_set):
            """Unlink current analytic lines, and recreate them with new account"""
            data_set.mapped('analytic_line_ids').unlink()
            data_set.write({'analytic_account_id': analytic_id})
            data_set.create_analytic_lines()

        used_lines = self.env['account.move.line'] if used_lines is None else used_lines
        analytic_id = self.account_analytic_id.id

        # Filter out the move lines using broad filtering
        s_matched = w_matched = self.invoice_line_to_aml_matcher(self, move_lines, used_lines)
        # Apply extra filtering to s_matched
        s_matched = s_matched.filtered(lambda x: x.quantity == self.quantity)

        # Try to apply analytics in both cases
        if len(s_matched) == 1:
            force_values(s_matched)
            used_lines |= s_matched

        if len(s_matched) != len(w_matched) and (
                sum(x.quantity for x in w_matched) == self.quantity):
            force_values(w_matched)
            used_lines |= w_matched
        return used_lines
