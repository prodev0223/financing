# -*- encoding: utf-8 -*-
from odoo import models, fields, api, _, tools, exceptions
from odoo.tools import float_is_zero


class AccountMoveLineReconcileWriteoff(models.TransientModel):
    _inherit = 'account.move.line.reconcile.writeoff'

    one_line = fields.Boolean(string='Pasirenkamas tik vienas žurnalo elementas')
    one_line_writeoff_amount = fields.Monetary(currency_field='one_line_writeoff_currency_id', string='Nurašoma suma')
    one_line_writeoff_currency_id = fields.Many2one('res.currency', string='Valiuta')
    partial_writeoff = fields.Boolean(default=False, string='Dalinis nurašymas')
    partner_id = fields.Many2one('res.partner', string='Priverstinis partneris')

    @api.model
    def overridable_partner_force(self, move_lines):
        if self.partner_id:
            move_lines.write({'partner_id': self.partner_id.id})
        return super(AccountMoveLineReconcileWriteoff, self).overridable_partner_force(move_lines)

    @api.model
    def default_get(self, fields_list):
        res = super(AccountMoveLineReconcileWriteoff, self).default_get(fields_list)
        company = self.env.user.company_id
        if 'journal_id' in fields_list:
            journal = company.default_currency_reval_journal_id
            res['journal_id'] = journal.id
        if 'comment' in fields_list:
            res['comment'] = _('Valiutų kursų įtaka')
        account_move_lines = self.env['account.move.line'].browse(self._context.get('active_ids', []))
        if 'writeoff_acc_id' in fields_list:
            amount_residual = sum(account_move_lines.mapped('amount_residual'))
            if tools.float_compare(amount_residual, 0, precision_digits=2) <= 0:
                res['writeoff_acc_id'] = company.income_currency_exchange_account_id.id
            else:
                res['writeoff_acc_id'] = company.expense_currency_exchange_account_id.id
        if 'date_p' in fields_list and account_move_lines:
            res['date_p'] = max(account_move_lines.mapped('date'))
        if 'one_line' in fields_list and account_move_lines:
            res['one_line'] = len(account_move_lines) == 1
        if res.get('one_line', False):
            if 'one_line_writeoff_currency_id' in fields_list:
                curr_id = account_move_lines[0].currency_id.id or self.env.user.company_id.currency_id.id
                res['one_line_writeoff_currency_id'] = curr_id
            if 'one_line_writeoff_amount' in fields_list:
                curr = account_move_lines[0].currency_id or self.env.user.company_id.currency_id
                res['one_line_writeoff_amount'] = account_move_lines[0].amount_residual \
                    if curr == self.env.user.company_id.currency_id else account_move_lines[0].amount_residual_currency
        return res

    @api.multi
    def do_partial_writeoff(self):
        line_id = self._context.get('active_ids', [])
        if len(line_id) != 1:
            raise exceptions.UserError(_('Dalinis nurašymas galimas tik vienai eilutei.'))
        line = self.env['account.move.line'].browse(line_id)
        if line.reconciled:
            raise exceptions.UserError(_('Apskaitos įrašo eilutė jau sudengta.'))
        if not line.account_id.reconcile:
            raise exceptions.UserError(_('DK sąskaita pažymėta kaip nesudengiama.'))
        currency = self.one_line_writeoff_currency_id
        if float_is_zero(self.one_line_writeoff_amount, precision_rounding=currency.rounding):
            raise exceptions.UserError(_('Jūs bandote nurašyti nulinę sumą.'))

        amount = currency.round(self.one_line_writeoff_amount)
        writeoff_vals = {
            'account_id': self.writeoff_acc_id.id,
            'journal_id': self.journal_id.id,
            'date': self.date_p,
            'name': self.comment,
            'debit': amount < 0 and abs(amount) or 0.0,
            'credit': amount > 0 and amount or 0.0,
        }
        if self.analytic_id:        # not sure if needed
            writeoff_vals['analytic_id'] = self.analytic_id.id

        if currency.id != self.env.user.company_id.currency_id.id:
            amount_currency = -amount
            amount = currency.with_context({'date': self.date_p}).compute(amount, self.env.user.company_id.currency_id)
            writeoff_vals.update({
                'amount_currency': amount_currency,
                'currency_id': self.one_line_writeoff_currency_id.id,
                'debit': amount < 0 and abs(amount) or 0.0,
                'credit': amount > 0 and amount or 0.0,
            })

        writeoff_to_reconcile = line._create_writeoff(writeoff_vals)
        (line + writeoff_to_reconcile).auto_reconcile_lines()
        return {'type': 'ir.actions.act_window_close'}
