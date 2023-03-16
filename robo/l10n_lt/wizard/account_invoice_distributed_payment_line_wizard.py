# -*- encoding: utf-8 -*-
from __future__ import division
from odoo import models, fields, _, api, exceptions, tools
from odoo.tools import float_compare
from datetime import datetime
from dateutil.relativedelta import relativedelta


class AccountInvoiceDistributedPaymentLineWizard(models.TransientModel):
    _name = 'account.invoice.distributed.payment.line.wizard'

    def _get_invoice_id(self):
        return self._context.get('invoice_id', False)

    def _get_default_date(self):
        return self._context.get('date', False)

    def _get_currency(self):
        return self._context.get('currency_id', self.env.user.company_id.currency_id.id)

    def _get_amount(self):
        return self._context.get('amount', 0)

    def _get_existing_lines(self):
        inv_id = self._context.get('invoice_id', False)
        if inv_id:
            inv = self.env['account.invoice'].browse(inv_id)
            inv_lines = inv.distributed_payment_ids
            lines = []
            for line in inv_lines:
                lines += [(0, 0, {'amount': line.amount, 'date': line.date})]
            if inv_lines:
                return lines

    def _get_default_payments(self):
        inv_id = self._context.get('invoice_id', False)
        if inv_id:
            return len(self.env['account.invoice'].browse(inv_id).distributed_payment_ids) or 12
        else:
            return 12

    payments = fields.Integer(default=_get_default_payments)
    invoice_id = fields.Many2one('account.invoice', default=_get_invoice_id, required=True, ondelete="cascade")
    currency_id = fields.Many2one('res.currency', default=_get_currency, readonly=True)
    amount = fields.Monetary(string='Suma', default=_get_amount, readonly=True)
    date = fields.Date(string='Pirmo mokėjimo suma', default=_get_default_date, required=True)
    line_ids = fields.One2many('account.invoice.distributed.payment.line.create', 'wizard_id',
                               default=_get_existing_lines)
    hide_generate_button = fields.Boolean(compute="_hide_generate_button")

    @api.depends('line_ids.correct')
    def _hide_generate_button(self):
        if self.line_ids:
            self.hide_generate_button = any([l.correct for l in self.line_ids])

    @api.multi
    def create_lines(self):
        lines = [(5,)]
        date = datetime.strptime(self.date, tools.DEFAULT_SERVER_DATE_FORMAT)
        new_day = 31 if date.day == (date + relativedelta(day=31)).day else date.day
        for i in range(self.payments):
            lines += [(0, 0, {'date': date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                              'currency_id': self.currency_id.id})]
            date += relativedelta(months=1, day=new_day)
        self.line_ids = lines
        self.recompute_balanced_line_amount()

        return {"type": "ir.actions.do_nothing"}

    @api.multi
    def recompute_balanced_line_amount(self):
        correct_lines = self.line_ids.filtered(lambda l: l.correct)
        for line in correct_lines:
            line.amount = self.currency_id.round(line.amount)
        lines = sorted(self.line_ids.filtered(lambda l: not l.correct), key=lambda l: l.date)
        amount_residual = self.amount - sum(l.amount for l in correct_lines)
        n_lines = len(lines)
        if n_lines == 1:
            lines[0].amount = amount_residual
        elif n_lines > 0:
            # P3:DivOK - amount residual is float
            new_amount = self.currency_id.round(amount_residual / n_lines)
            for i in range(n_lines - 1):
                lines[i].amount = new_amount
            lines[-1].amount = amount_residual - new_amount * (n_lines - 1)
        return {
            "type": "ir.actions.do_nothing",
        }

    @api.multi
    def export_lines(self):
        amount = 0.0
        for line in self.line_ids:
            line.amount = self.currency_id.round(line.amount)
            amount += line.amount
        if float_compare(amount, self.amount, precision_rounding=self.currency_id.rounding) != 0:
            raise exceptions.UserError(_('Nesibalansuoja sumos.'))
        export_lines = [(5,)]
        for line in self.line_ids:
            export_lines += [(0, 0, {'amount': line.amount, 'date': line.date})]
        self.invoice_id.distributed_payment_ids = export_lines
