# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions, tools
from dateutil.relativedelta import relativedelta
from datetime import datetime


class StockToAccountingMatcher(models.TransientModel):
    _name = 'stock.to.accounting.matcher'

    @api.model
    def _default_date_from(self):
        """Previous months' first day"""
        return datetime.now() - relativedelta(months=1, day=1)

    @api.model
    def _default_date_to(self):
        """Previous months' last day"""
        return datetime.now() - relativedelta(months=1, day=31)

    date_from = fields.Date(string='Data nuo', default=_default_date_from)
    date_to = fields.Date(string='Data iki', default=_default_date_to)

    @api.multi
    def match_lines_prep(self):
        """
        Separate method so match_lines
        can be called independently of the wizard
        :return: None
        """
        self.ensure_one()
        if not self.date_from:
            raise exceptions.ValidationError(_('Nepaduota data nuo!'))
        self.match_lines(self.date_from, self.date_to)

    @api.model
    def match_lines(self, date_from, date_to=None):
        """
        Match invoice lines to stock accounting entries.
        Date from/to indicates the gap for invoice search.
        :param date_from: date_invoice from (str)
        :param date_to: date_invoice to (str)
        :return: None
        """
        if not self.env.user.is_accountant():
            return
        # Set date_to to today if it's not passed
        if not date_to:
            date_to = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        # Search for the open or paid invoices
        invoices = self.env['account.invoice'].sudo().search([
            ('state', 'in', ['open', 'paid']),
            ('date_invoice', '>=', date_from),
            ('date_invoice', '<=', date_to),
        ])

        for invoice in invoices:
            # Collect all possible pickings for the invoice
            base_pickings = invoice.picking_id | invoice.sale_ids.mapped('picking_ids')
            if invoice.number:
                base_pickings |= self.env['stock.picking'].search([('origin', '=', invoice.number)])
            base_move_lines = self.env['account.move.line']
            # Collect the move lines
            for picking in base_pickings:
                base_move_lines |= self.env['account.move.line'].search([('ref', '=', picking.name)])
            if not base_move_lines:
                continue

            # Next, loop through invoice lines, and collect rest of the
            # pickings and move lines from them
            for line in invoice.invoice_line_ids:
                # Collect all possible pickings using the specific line
                pickings = line.purchase_line_id.mapped('move_ids').filtered(
                    lambda r: r.product_id.id == line.product_id.id and r.state == 'done').mapped('picking_id')
                pickings |= line.sale_line_ids.mapped('procurement_ids.move_ids').filtered(
                    lambda r: r.product_id.id == line.product_id.id and r.state == 'done').mapped('picking_id')

                # Gather up the move lines
                move_lines = base_move_lines
                for picking in pickings:
                    move_lines |= self.env['account.move.line'].search([('ref', '=', picking.name)])
                if not move_lines:
                    continue

                # Broad filter, product and account code
                found_lines = move_lines.filtered(
                    lambda x: x.product_id.id == line.product_id.id
                    and x.account_id.code.startswith('6')
                )
                if found_lines:
                    # Try to make the filter more narrow, by matching the quantity
                    specific_line = found_lines.filtered(lambda x: x.quantity == line.quantity)
                    object_to_write = specific_line
                    # If there's no line, check whether summed quantity of found
                    # lines is the same one as in account invoice line
                    if not specific_line:
                        quantity = sum(found_lines.mapped('quantity'))
                        if not tools.float_compare(quantity, line.quantity, precision_digits=2):
                            object_to_write = found_lines

                    # Write the changes
                    if object_to_write:
                        object_to_write.write({
                            'write_off_invoice_id': invoice.id,
                            'write_off_invoice_line_id': line.id
                        })


StockToAccountingMatcher()
