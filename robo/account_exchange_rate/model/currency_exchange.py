# -*- coding: utf-8 -*-
from odoo import models, fields, _, tools, api, exceptions
from datetime import datetime


class ResCompanyExchange(models.Model):
    _inherit = 'res.company'

    def default_account_exchange_revenue(self):
        return self.env['account.account'].search([('code', '=', 5803)], limit=1)

    def default_account_exchange_expenses(self):
        return self.env['account.account'].search([('code', '=', 6803)], limit=1)

    account_exchange_revenue = fields.Many2one('account.account', string='Exchange Revenue Account',
                                               default=default_account_exchange_revenue)
    account_exchange_expenses = fields.Many2one('account.account', string='Exchange Expenses Account',
                                                default=default_account_exchange_expenses)

ResCompanyExchange()


class AccountConfigSettings(models.TransientModel):
    _inherit = 'account.config.settings'

    account_exchange_revenue = fields.Many2one('account.account', string='Exchange Revenue Account',
                                               related='company_id.account_exchange_revenue')
    account_exchange_expenses = fields.Many2one('account.account', string='Exchange Expenses Account',
                                                related='company_id.account_exchange_expenses')


AccountConfigSettings()


class AccountPaymentExt(models.Model):
    _inherit = 'account.payment'

    calculate_exchange_diff = fields.Boolean(string='Calculate currency exchange rate difference?')
    exchange_type = fields.Selection([('ratio', 'Ratio'), ('fixed', 'Fixed')], string='Exchange Type')
    exchange_rate = fields.Float(string='Exchange Rate')
    rate_label = fields.Char(string='Rate Information', compute='rate_label_compute')
    exchange_fixed_amount = fields.Float(string='Fixed Amount')
    currency_dest_id = fields.Many2one('res.currency', string='Fixed amount currency',
                                       compute='currency_dest_id_compute')

    @api.depends('journal_id', 'destination_journal_id')
    def rate_label_compute(self):
        for rec in self:
            if not rec.journal_id or not rec.destination_journal_id:
                rec.rate_label = False
                continue
            currency = rec.journal_id.currency_id if rec.journal_id.currency_id else self.env.user.company_id.currency_id
            currency_dest = rec.destination_journal_id.currency_id if rec.destination_journal_id.currency_id else \
                self.env.user.company_id.currency_id
            rec.rate_label = currency.name + ' / ' + currency_dest.name

    @api.depends('destination_journal_id')
    def currency_dest_id_compute(self):
        for rec in self.filtered('destination_journal_id'):
            rec.currency_dest_id = rec.destination_journal_id.currency_id.id

    @api.multi
    def post(self):
        for rec in self:
            if not rec.calculate_exchange_diff or rec.payment_type != 'transfer':
                super(AccountPaymentExt, rec).post()
                continue
            if rec.state != 'draft':
                raise exceptions.UserError(
                    _("Only a draft payment can be posted. Trying to post a payment in state %s.") % rec.state)

            if any(inv.state != 'open' for inv in rec.invoice_ids):
                raise exceptions.ValidationError(_("The payment cannot be processed because the invoice is not open!"))

            sequence_code = 'account.payment.transfer'

            rec.name = self.env['ir.sequence'].with_context(ir_sequence_date=rec.payment_date).next_by_code(
                sequence_code)

            currency_id = rec.journal_id.currency_id if rec.journal_id.currency_id else rec.journal_id.company_id.currency_id
            currency_id_dest = rec.destination_journal_id.currency_id if rec.destination_journal_id.currency_id else rec.destination_journal_id.company_id.currency_id
            if rec.exchange_type == 'ratio':
                actual_dest_amount = rec.amount * self.exchange_rate
            elif rec.exchange_type == 'fixed':
                actual_dest_amount = rec.exchange_fixed_amount
            else:
                actual_dest_amount = rec.amount

            amount_buh_dest = currency_id.with_context(date=rec.payment_date).compute(rec.amount, currency_id_dest)
            diff_ratio = amount_buh_dest / actual_dest_amount
            actual_amount = rec.amount / diff_ratio
            amount_diff = actual_amount - rec.amount
            amount_diff_abs = abs(amount_diff)
            company_id = self.env.user.company_id

            if amount_diff > 0:
                acc_dest_id = company_id.account_exchange_revenue.id
            else:
                acc_dest_id = company_id.account_exchange_expenses.id

            # Create the journal entry

            move = rec._create_payment_entry(rec.amount)
            if amount_diff != 0:
                move_line_dest = {
                    'date_maturity': rec.payment_date,
                    'name': rec.name,
                    'debit': amount_diff_abs if amount_diff < 0 else 0,  # signed
                    'credit': amount_diff_abs if amount_diff > 0 else 0,
                    'account_id': acc_dest_id,
                    'quantity': 1.00,
                    'payment_id': self.id
                }

                move_line_source = {
                    'date_maturity': rec.payment_date,
                    'name': rec.name,
                    'debit': amount_diff_abs if amount_diff > 0 else 0,
                    'credit': amount_diff_abs if amount_diff < 0 else 0,
                    'account_id': rec.destination_account_id.id,
                    'quantity': 1.00,
                    'payment_id': self.id
                }

                lines = [(0, 0, move_line_source), (0, 0, move_line_dest)]

                move_vals = {
                    'ref': rec.name,
                    'line_ids': lines,
                    'journal_id': rec.journal_id.id,
                    'date': rec.payment_date,
                }

                # In case of a transfer, the first journal entry created debited the source liquidity account and credited
                # the transfer account. Now we debit the transfer account and credit the destination liquidity account.
                if rec.payment_type == 'transfer':
                    transfer_credit_aml = move.line_ids.filtered(
                        lambda r: r.account_id == rec.company_id.transfer_account_id)
                    transfer_debit_aml = rec._create_transfer_entry(actual_amount)
                    if amount_diff != 0:
                        exchange_move = self.env['account.move'].create(move_vals)
                        exchange_move.post()
                        exchange_move_aml = exchange_move.line_ids.filtered(
                            lambda r: r.account_id == rec.company_id.transfer_account_id)
                        (transfer_credit_aml + transfer_debit_aml + exchange_move_aml).reconcile()
                    else:
                        (transfer_credit_aml + transfer_debit_aml).reconcile()
            rec.state = 'posted'


AccountPaymentExt()
