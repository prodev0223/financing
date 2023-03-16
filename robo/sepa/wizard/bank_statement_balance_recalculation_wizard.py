# -*- encoding: utf-8 -*-
import exceptions

from odoo import fields, models, api, exceptions, _


class BankStatementBalanceRecalculationWizard(models.TransientModel):
    _name = 'bank.statement.balance.recalculation.wizard'

    journal_id = fields.Many2one(
        'account.journal', string='Journal',
        required=True, ondelete='cascade',
    )
    end_balance = fields.Float(
        string='End balance', compute='_compute_statement_balances',
        store=True, readonly=False, inverse='_set_statement_balances',
    )
    start_balance = fields.Float(
        string='Start balance', compute='_compute_statement_balances',
        store=True, readonly=False, inverse='_set_statement_balances',
    )
    mode = fields.Selection([
        ('ascending', 'Calculate from first to last statement'),
        ('descending', 'Calculate from last to first statement'),
    ], string='Calculation mode', default='descending')

    filter_date = fields.Date(string='Filter date')

    @api.multi
    def _set_statement_balances(self):
        """Dummy inverse, without it balances are always recomputed on button click"""
        pass

    @api.multi
    @api.depends('journal_id', 'filter_date')
    def _compute_statement_balances(self):
        """Computes default starting/ending balances for the user. Triggered on date change"""
        for rec in self:
            # Are already filtered by date inside of the method
            statement_data = rec.get_starting_closing_statements()
            rec.start_balance = statement_data['first_statement'].balance_start
            rec.end_balance = statement_data['last_statement'].balance_end_real

    @api.multi
    def get_date_domain(self):
        """Returns extra domain for statements if filter date is set"""
        self.ensure_one()
        return [('date', '>=', self.filter_date)] if self.filter_date else []

    @api.multi
    def get_starting_closing_statements(self):
        """
        Returns first and last statement for current journal.
        If filter date is set, statements are filtered based on date and mode:
            * Ascending: Statements are normalized from the filter date
            * Descending: Statements are normalized until the filter date
        :return: Account bank statement record dict
        """
        self.ensure_one()

        AccountBankStatement = self.env['account.bank.statement']
        statement_domain = [
            ('journal_id', '=', self.journal_id.id),
            ('sepa_imported', '=', True),
            ('partial_statement', '=', False),
        ]
        statement_domain += self.get_date_domain()

        # Get first and last statements for the journal
        first_statement = AccountBankStatement.search(statement_domain, limit=1, order='date')
        last_statement = AccountBankStatement.search(statement_domain, limit=1, order='date desc')

        if not first_statement or not last_statement:
            raise exceptions.ValidationError(_('Incorrect filter date, no corresponding statements were found'))

        return {
            'first_statement': first_statement,
            'last_statement': last_statement,
        }

    @api.multi
    def recalculate_and_normalize_balances(self):
        """
        Writes specified starting/ending balance to corresponding statements
        and runs statement normalization. If filter date is set,
        statements are normalized from certain threshold.
        :return: None
        """
        self.ensure_one()

        AccountBankStatement = self.env['account.bank.statement']
        # Get statement data and date domain
        statement_data = self.get_starting_closing_statements()
        extra_domain = self.get_date_domain()

        if self.mode == 'ascending':
            statement_data['first_statement'].write({
                'balance_start': self.start_balance,
            })
            AccountBankStatement.normalize_balances_ascending(
                journal_ids=self.journal_id.ids, extra_domain=extra_domain,
                force_normalization=True,
            )
        else:
            # Write the end balance to last statement and proceed with descending normalization
            statement_data['last_statement'].write({
                'balance_end_real': self.end_balance,
                'balance_end_factual': self.end_balance,
            })
            AccountBankStatement.normalize_balances_descending(
                journal_ids=self.journal_id.ids, extra_domain=extra_domain,
            )
