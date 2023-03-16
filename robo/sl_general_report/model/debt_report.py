# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, _
from odoo.tools import float_is_zero
from datetime import datetime
from six import iteritems


class DebtReport(models.Model):

    _name = 'partner.debt.report'
    _auto = False

    partner_id = fields.Many2one('res.partner', string='Partner')
    date_maturity = fields.Date(string='Due date')
    date = fields.Date(string='Date')
    days_difference = fields.Integer(string='Delay', group_operator='max')
    amount_debt = fields.Float(string='Amount')
    name = fields.Char(string='Label')
    ref = fields.Char(string='Reference')
    invoice_id = fields.Many2one('account.invoice', string='Invoice')
    account_id = fields.Many2one('account.account', string='Account')
    account_type_id = fields.Many2one('account.account.type', string='Account type')
    invoice_type = fields.Selection([
        ('out_invoice', 'Customer Invoice'),
        ('in_invoice', 'Vendor Bill'),
        ('out_refund', 'Customer Refund'),
        ('in_refund', 'Vendor Refund'),
    ], string='Invoice Type')

    @api.model_cr
    def init(self):
        cr = self._cr
        tools.drop_view_if_exists(cr, 'partner_debt_report')
        cr.execute("""
            CREATE OR REPLACE VIEW partner_debt_report AS (
            SELECT
            account_move_line.id AS id,
            account_move_line.partner_id as partner_id,
            COALESCE(account_move_line.date_maturity, account_move_line.date) as date_maturity,
            CURRENT_DATE::date - COALESCE(account_move_line.date_maturity, account_move_line.date)::date as days_difference,
            account_move_line.date as date,
            sum(account_move_line.amount_residual) as amount_debt,
            account_move_line.invoice_id as invoice_id,
            account_move_line.name as name,
            account_move_line.ref as ref,
            account_account.user_type_id as account_type_id,
            account_account.id as account_id,
            account_invoice.type as invoice_type
            FROM account_move_line JOIN account_account ON account_move_line.account_id = account_account.id
                JOIN account_move ON account_move_line.move_id = account_move.id
                LEFT JOIN account_invoice ON account_move_line.invoice_id = account_invoice.id
            WHERE account_move_line.amount_residual != 0 AND account_move.state = 'posted'
                AND account_account.user_type_id in
                (SELECT res_id FROM ir_model_data WHERE
                    module = 'account' AND name in ('data_account_type_receivable', 'data_account_type_payable')
                )
            GROUP BY account_move_line.partner_id, account_move_line.date_maturity, account_move_line.date, account_move_line.invoice_id, account_move_line.id, account_account.user_type_id, account_account.id,account_invoice.type
            )"""
                   )

DebtReport()


class AccountMoveLine(models.Model):

    _inherit = 'account.move.line'

    days_delay = fields.Integer(string='Delay', readonly=True)

    @api.model
    def cron_compute_delay(self):
        current_date = datetime.now()
        current_date = datetime(year=current_date.year, month=current_date.month, day=current_date.day)
        account_ids = self.env['account.account'].search([('user_type_id', 'in', (1, 2))]).ids
        base_domain = [('account_id', 'in', account_ids)]
        lines_zero_delay = self.env['account.move.line'].search(base_domain + [
            ('amount_residual', '=', 0),
            ('invoice_id', '=', False),
            ('days_delay', '!=', 0),
        ])
        lines_zero_delay.with_context(check_move_validity=False).write({'days_delay': 0})
        lines_to_compute = self.env['account.move.line'].search(base_domain + [
            ('amount_residual', '!=', 0),
        ])
        lines_by_date = {}
        for line in lines_to_compute:
            lines_by_date.setdefault(line.date_maturity, self.env['account.move.line'])
            lines_by_date[line.date_maturity] |= line
        for date_maturity, lines in iteritems(lines_by_date):
            due_date = datetime.strptime(date_maturity, tools.DEFAULT_SERVER_DATE_FORMAT)
            days_delay = (due_date - current_date).days
            lines.with_context(check_move_validity=False).write({'days_delay': days_delay})

        lines_to_compute = self.env['account.move.line'].search(base_domain + [
            ('amount_residual', '=', 0),
            ('invoice_id', '!=', False),
            ('invoice_id.type', 'in', ('out_invoice', 'out_refund'))
        ], order='date_maturity')
        due_date_str = False
        for line in lines_to_compute:
            if line.date_maturity != due_date_str:
                due_date_str = line.date_maturity
                due_date = datetime.strptime(line.date_maturity, tools.DEFAULT_SERVER_DATE_FORMAT)
            payment_lines = line.full_reconcile_id.reconciled_line_ids.filtered(lambda r: r.credit > 0.0).sorted(
                lambda r: r.date, reverse=True)
            if payment_lines:
                payment_date = datetime.strptime(payment_lines[0].date, tools.DEFAULT_SERVER_DATE_FORMAT)
                days_delay = (due_date - payment_date).days
                line.with_context(check_move_validity=False).days_delay = days_delay
            else:
                line.with_context(check_move_validity=False).days_delay = 0
        lines_to_compute = self.env['account.move.line'].search(base_domain + [
            ('amount_residual', '=', 0),
            ('invoice_id', '!=', False),
            ('invoice_id.type', 'in', ('in_invoice', 'in_refund'))
        ])
        for line in lines_to_compute:
            if line.date_maturity != due_date_str:
                due_date_str = line.date_maturity
                due_date = datetime.strptime(line.date_maturity, tools.DEFAULT_SERVER_DATE_FORMAT)
            payment_lines = line.full_reconcile_id.reconciled_line_ids.filtered(lambda r: r.debit > 0.0).sorted(
                lambda r: r.date, reverse=True)
            if payment_lines:
                payment_date = datetime.strptime(payment_lines[0].date, tools.DEFAULT_SERVER_DATE_FORMAT)
                days_delay = (due_date - payment_date).days
                line.with_context(check_move_validity=False).days_delay = days_delay
            else:
                line.with_context(check_move_validity=False).days_delay = 0
        # invoices_to_compute = self.env['account.invoice'].search([('date_due', '!=', False)])
        # for invoice in invoices_to_compute:
        #     due_date = datetime.strptime(invoice.date_due, tools.DEFAULT_SERVER_DATE_FORMAT)
        #     days_delay = (current_date - due_date).days
        #     if float_is_zero(invoice.residual_company_signed, precision_rounding=rounding):
        #         debt_line = invoice.move_id.line_ids.filtered(lambda r: r.account_id.id == invoice.account_id.id)
        #         if 'out' in invoice.type:
        #             payment_lines = debt_line.full_reconcile_id.reconciled_line_ids.filtered(
        #                 lambda r: r.credit > 0.0).sorted(lambda r: r.date, reverse=True)
        #         else:
        #             payment_lines = debt_line.full_reconcile_id.reconciled_line_ids.filtered(
        #                 lambda r: r.debit > 0.0).sorted(lambda r: r.date, reverse=True)
        #         if payment_lines:
        #             payment_date = datetime.strptime(payment_lines[0].date, tools.DEFAULT_SERVER_DATE_FORMAT)
        #             days_delay = (due_date - payment_date).days
        #             invoice.due_days = days_delay
        #     else:
        #         invoice.due_days = days_delay

AccountMoveLine()


class AccountPartialReconcile(models.Model):

    _inherit = 'account.partial.reconcile'

    reconcile_date = fields.Date(string='Sudengimo data', compute='_reconcile_date', store=True)

    @api.depends('credit_move_id.date', 'debit_move_id.date')
    def _reconcile_date(self):
        for rec in self:
            date_c = rec.credit_move_id.date
            date_d = rec.debit_move_id.date
            rec.reconcile_date = max(date_c, date_d)

AccountPartialReconcile()
