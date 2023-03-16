# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions, tools
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


def same_quarter(date1, date2):
    date_1_dt = datetime.strptime(date1, tools.DEFAULT_SERVER_DATE_FORMAT)
    date_2_dt = datetime.strptime(date2, tools.DEFAULT_SERVER_DATE_FORMAT)
    year_1, month_1 = date_1_dt.year, date_1_dt.month
    year_2, month_2 = date_2_dt.year, date_2_dt.month

    if year_1 != year_2:
        return False
    if (month_1 - 1) // 3 != (month_2 - 1) // 3:
        return False
    return True


def same_month(date1, date2):
    date_1_dt = datetime.strptime(date1, tools.DEFAULT_SERVER_DATE_FORMAT)
    date_2_dt = datetime.strptime(date2, tools.DEFAULT_SERVER_DATE_FORMAT)
    year_1, month_1 = date_1_dt.year, date_1_dt.month
    year_2, month_2 = date_2_dt.year, date_2_dt.month

    if year_1 != year_2:
        return False
    if month_1 != month_2:
        return False
    return True


class InvoicePickingDateConsistency(models.Model):
    _name = 'invoice.picking.date.consistency'
    _rec_name = 'invoice_id'

    invoice_id = fields.Many2one('account.invoice', string='Invoice', required=True, readonly=True)
    date_invoice = fields.Date(string='Date invoice', related='invoice_id.date_invoice', store=True, readonly=True)
    state = fields.Selection([('not_fixed', 'Not fixed'), ('fixed', 'Fixed')],
                             string='State', required=True,
                             copy=False, readonly=True)
    diff_month = fields.Boolean(string='Different month', compute='_state', store=True)
    diff_quarter = fields.Boolean(string='Different quarter', compute='_state', store=True)
    min_date = fields.Date(string='Min date', readonly=True)
    max_date = fields.Date(string='Max date', readonly=True)

    @api.depends('min_date', 'max_date')
    def _state(self):
        for rec in self:
            min_date = rec.min_date
            max_date = rec.max_date
            diff_quarter = False
            diff_month = False
            if min_date and max_date:
                if not same_quarter(min_date, max_date):
                    diff_quarter = True
                if not same_month(min_date, max_date):
                    diff_month = True
            rec.diff_quarter = diff_quarter
            rec.diff_month = diff_month

    @api.multi
    def fix(self):
        self.ensure_one()
        if self.env.user.has_group('account.group_account_manager'):
            self = self.sudo()
        else:
            return
        invoice = self.invoice_id
        date_invoice = invoice.date_invoice
        all_pickings = self.env['stock.picking']
        for invoice_line in invoice.invoice_line_ids:
            all_pickings |= invoice_line.sale_line_ids.mapped('procurement_ids.move_ids').filtered(
                lambda r: r.product_id.id == invoice_line.product_id.id and r.state == 'done').mapped('picking_id')
        stock_moves = self.env['stock.move']
        for picking in all_pickings:
            for move in picking.move_lines:
                parent_move = move
                while parent_move.error and parent_move.origin_returned_move_id:
                    parent_move = parent_move.origin_returned_move_id
                    stock_moves |= parent_move
                stock_moves |= move
        pickings = stock_moves.mapped('picking_id') | invoice.picking_id
        date_invoice_dtm = datetime.strptime(date_invoice, tools.DEFAULT_SERVER_DATE_FORMAT).strftime(
            tools.DEFAULT_SERVER_DATETIME_FORMAT)
        for picking in pickings:
            picking.min_date = date_invoice_dtm
        account_move_lines = self.env['account.move.line']
        for picking in pickings:
            account_move_lines |= self.env['account.move.line'].search([('ref', '=', picking.name)])
        account_moves = account_move_lines.mapped('move_id')
        for stock_move in stock_moves.filtered(lambda r: r.state == 'done'):
            if stock_move.date[:10] != date_invoice:
                stock_move.state = 'draft'
                stock_move.date = date_invoice_dtm
                stock_move.state = 'done'
        for account_move in account_moves:
            if account_move.date != date_invoice:
                account_move.state = 'draft'
                account_move.date = date_invoice
                account_move.line_ids.write({'date': date_invoice})
                account_move.state = 'posted'
        self.write({'min_date': date_invoice,
                    'max_date': date_invoice,
                    'state': 'fixed',
                    })

    @api.model
    def cron_calculate_account_date_fixes(self, create_date_min=False):
        if not create_date_min:
            create_date_min = (datetime.now() - relativedelta(months=2)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        invoices = self.env['account.invoice'].search([('type', 'in', ['out_invoice', 'out_refund']),
                                                       ('state', 'in', ('open', 'paid')),
                                                       ('create_date', '>', create_date_min)])
        for invoice in invoices:
            date_invoice = invoice.date_invoice
            min_date = date_invoice
            max_date = date_invoice
            all_pickings = self.env['stock.picking']
            for invoice_line in invoice.invoice_line_ids:
                all_pickings |= invoice_line.sale_line_ids.mapped('procurement_ids.move_ids').filtered(
                    lambda r: r.product_id.id == invoice_line.product_id.id and r.state == 'done').mapped('picking_id')
            stock_moves = self.env['stock.move']
            # diff_quarters = False
            for picking in set(all_pickings):
                for move in picking.move_lines:
                    parent_move = move
                    while parent_move.error and parent_move.origin_returned_move_id:
                        parent_move = parent_move.origin_returned_move_id
                        stock_moves |= parent_move
                    stock_moves |= move
            pickings = stock_moves.mapped('picking_id') | invoice.picking_id
            pickings = pickings.filtered(lambda x: x.min_date and x.move_lines)
            account_move_lines = self.env['account.move.line']
            for picking in pickings:
                account_move_lines |= self.env['account.move.line'].search([('ref', '=', picking.name)])
            account_moves = account_move_lines.mapped('move_id')
            for picking in pickings:
                picking_date = picking.min_date[:10]
                if not min_date or min_date > picking_date:
                    min_date = picking_date
                if not max_date or max_date < picking_date:
                    max_date = picking_date
            for stock_move in stock_moves:
                stock_move_date = stock_move.date[:10]
                if not min_date or min_date > stock_move_date:
                    min_date = stock_move_date
                if not max_date or max_date < stock_move_date:
                    max_date = stock_move_date
            for account_move in account_moves:
                account_move_date = account_move.date
                if not min_date or min_date > account_move_date:
                    min_date = account_move_date
                if not max_date or max_date < account_move_date:
                    max_date = account_move_date
            for account_move_line in account_move_lines:
                account_move_line_date = account_move_line.date
                if not min_date or min_date > account_move_line_date:
                    min_date = account_move_line_date
                if not max_date or max_date < account_move_line_date:
                    max_date = account_move_line_date
            if min_date and min_date != date_invoice or max_date and max_date != date_invoice:
                # state = 'same_quarter' if same_quarter(min_date, date_invoice)
                # and same_quarter(date_invoice, max_date) else 'diff_quarter'
                existing_record = self.env['invoice.picking.date.consistency'].search([('invoice_id', '=', invoice.id),
                                                                                       ('state', '!=', 'fixed')])
                if existing_record:
                    existing_record.write({
                        'state': 'not_fixed',
                        'min_date': min_date,
                        'max_date': max_date}
                    )
                else:
                    self.env['invoice.picking.date.consistency'].create({'invoice_id': invoice.id,
                                                                         'state': 'not_fixed',
                                                                         'min_date': min_date,
                                                                         'max_date': max_date})


InvoicePickingDateConsistency()
