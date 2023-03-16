# -*- encoding: utf-8 -*-
import logging
from odoo import fields, models, _, api, exceptions, tools
from odoo.addons.sepa.wizard.account_revolut_import import find_partner_name
from odoo.addons.sepa.model.revolut_api import CRYPTO_CURRENCIES
from six import iteritems

_logger = logging.getLogger(__name__)


class RevolutApiTransactionLeg(models.Model):
    _name = 'revolut.api.transaction.leg'
    _description = 'Store legs info from Revolut Business API'

    revolut_api_id = fields.Many2one('revolut.api', related='transaction_id.revolut_api_id')
    uuid = fields.Char(string='ID (Revolut)', required=True)
    revolut_account_id = fields.Many2one('revolut.account', string='Sąskaita')
    transaction_id = fields.Many2one('revolut.api.transaction', string='Transakcija', ondelete='cascade', required=True)
    created_at = fields.Datetime(string='Sukurta', related='transaction_id.created_at', store=True)
    updated_at = fields.Datetime(string='Atnaujinta', related='transaction_id.completed_at', store=True)
    completed_at = fields.Datetime(string='Užbaigta', related='transaction_id.updated_at', store=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('declined', 'Declined'),
        ('failed', 'Failed'),
        ('reverted', 'Reverted')
    ], related='transaction_id.state', store=True)
    account_uuid = fields.Char(string='Sąskaitos ID (Revolut)', inverse='_set_revolut_account_id', required=True, sequence=100)
    description = fields.Char(string='Aprašymas')
    currency = fields.Char(inverse='_set_currency_id')
    currency_id = fields.Many2one('res.currency', string='Valiuta', sequence=100)
    amount = fields.Monetary(string='Suma')
    fee = fields.Monetary(string='Įmokos suma')
    balance = fields.Monetary(string='Balansas')
    bill_currency = fields.Char(inverse='_set_bill_currency_id')
    bill_currency_id = fields.Many2one('res.currency', string='Valiuta')
    bill_amount = fields.Monetary(string='Suma (Valiuta)', currency_field='bill_currency_id')
    bank_statement_line_ids = fields.Many2many('account.bank.statement.line', string='Banko išrašo eilutės',
                                               compute='_compute_bank_statement_line_ids')

    @api.one
    def _compute_bank_statement_line_ids(self):
        lines = self.env['account.bank.statement.line'].search([
            '|', ('entry_reference', '=', self.transaction_id.uuid),
            ('commission_of_id.entry_reference', '=', self.transaction_id.uuid),
            ('journal_id.revolut_account_id', '=', self.revolut_account_id.id)
        ])
        self.bank_statement_line_ids = [(6, 0, lines.ids)]

    @api.multi
    @api.constrains('uuid')
    def _check_unique_uuid(self):
        for rec in self:
            if rec.uuid and self.env['revolut.api.transaction.leg'].search_count([('uuid', '=', rec.uuid), ('id', '!=', rec.id)]):
                raise exceptions.ValidationError(_('Leg UUID turi būti unikalus'))

    @api.one
    def _set_revolut_account_id(self):
        if self.account_uuid:
            account_id = self.env['revolut.account'].search([('uuid', '=', self.account_uuid)], limit=1)
            if not account_id:
                try:
                    account_data = self.revolut_api_id.get_account(self.account_uuid)
                    account_id = self.env['revolut.account'].create({
                        'name': account_data.get('name'),
                        'uuid': self.account_uuid,
                        'revolut_api_id': self.revolut_api_id.id,
                    })
                except:
                    _logger.info('Revolut API: account %s for transaction leg %s was not found. Setting to False.',
                                 self.account_uuid, self.uuid)
                    account_id = False
            if account_id:
                self.write({'revolut_account_id': account_id.id})

    @api.multi
    def _set_currency_id(self):
        for rec in self:
            if rec.currency:
                currency_id = self.env['res.currency'].search([('name', '=', rec.currency)], limit=1)
                is_currency_crypto = rec.currency in CRYPTO_CURRENCIES
                if not currency_id and not is_currency_crypto:
                    raise exceptions.UserError(_('Nerasta valiuta %s') % rec.currency)
                rec.write({'currency_id': currency_id.id if not is_currency_crypto else False})

    @api.multi
    def _set_bill_currency_id(self):
        for rec in self:
            if rec.bill_currency:
                currency_id = self.env['res.currency'].search([('name', '=', rec.bill_currency)], limit=1)
                is_currency_crypto = rec.bill_currency in CRYPTO_CURRENCIES
                if not currency_id and not is_currency_crypto:
                    raise exceptions.UserError(_('Nerasta valiuta %s') % rec.currency)
                rec.write({'bill_currency_id': currency_id.id if not is_currency_crypto else False})

    @api.multi
    def unlink(self):
        if self.mapped('transaction_id.bank_statement_line_ids'):
            raise exceptions.UserError(_('Transakcijos turi susijusias banko išrašų eilutes, trinti negalima'))
        return super(RevolutApiTransactionLeg, self).unlink()

    @api.multi
    def btn_create_statement(self):
        self.ensure_one()
        statement = self.create_statements(apply_import_rules=True)
        if statement:
            return {
                'name': _('Banko ruošinys'),
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'account.bank.statement',
                'res_id': statement.id,
                'view_id': self.env.ref('account.view_bank_statement_form').id,
                'type': 'ir.actions.act_window',
                'target': 'new',
            }

    @api.multi
    def create_statements(self, filtered_journal=None, apply_import_rules=False):
        """
        Create bank statement / statement lines for the existing legs

        :param filtered_journal: an account_journal Record, if specified, will only create for the revolut.account
                                 linked to that journal. Otherwise, will create for all revolut.account which are linked
        :param apply_import_rules: applies auto_import_rules set in the journal corresponding to the statement
        """
        transaction_vals = self._prepare_statement_data(filtered_journal)
        return self._create_statements(transaction_vals, apply_import_rules)

    @api.multi
    def _prepare_statement_data(self, filtered_journal=None):
        """
        Prepare data to create bank statements from leg records

        :param filtered_journal: an account_journal Record, if specified, will only create for the revolut.account
                                 linked to that journal. Otherwise, will create for all revolut.account which are linked
        :returns: dict (account_journal.id, dict(date, list of bank statement line values for create method))
        """
        legs = self.filtered(lambda l: l.transaction_id.state == 'completed'
                                       and not tools.float_is_zero(l.amount, precision_digits=2))
        transaction_vals = {}
        for leg in legs.sorted(key=lambda l: l.transaction_id.completed_at):
            if filtered_journal and filtered_journal.revolut_account_id != leg.revolut_account_id:
                continue
            journal = self.env['account.journal'].search([('revolut_account_id', '=', leg.revolut_account_id.id)])
            if not journal:
                continue
            transaction = leg.transaction_id
            if self.env['account.bank.statement.line'].search([('journal_id', '=', journal.id), ('entry_reference', '=', transaction.uuid)]):
                continue
            #Try to guess partner:
            partner_name = ''
            try:
                transaction_type = transaction.transaction_type
                desc = leg.description
                partner_name = find_partner_name(transaction_type, desc)
                partner_name = partner_name or transaction.merchant_name
                partner_id = self.env['sepa.csv.importer'].get_partner_id(partner_name=partner_name)
            except Exception as e:
                _logger.info('Revolut API: failed to determine partner name on leg id %s.\nException: %r', leg.id, e)
                partner_id = False

            vals = {
                'date': transaction.completed_day,
                'completed_at': transaction.completed_at,
                'journal_id': journal.id,
                'entry_reference': transaction.uuid,
                'partner_id': partner_id,
                'info_type': 'unstructured',
                'name': leg.description,
                'ref': transaction.reference,
                'imported_partner_name': partner_name,
                'amount': leg.amount,
            }
            if leg.bill_currency and leg.bill_currency != leg.currency:
                vals.update(amount_currency=leg.bill_amount, currency_id=leg.bill_currency_id.id)
            transaction_vals.setdefault(journal.id, {}).setdefault(transaction.completed_day, []).append(vals)
            if not tools.float_is_zero(leg.fee, precision_rounding=leg.currency_id.rounding):
                fee_vals = vals.copy()
                fee_vals.update({
                    'amount': -abs(leg.fee),
                    'is_fee': True,
                    'name': leg.description + ' (%s)' % _('Įmoka'),
                })
                fee_vals.pop('amount_currency', None)
                fee_vals.pop('currency_id', None)
                transaction_vals.setdefault(journal.id, {}).setdefault(transaction.completed_day, []).append(fee_vals)
        return transaction_vals

    @api.model
    def _create_statements(self, data, apply_import_rules=False):
        """
        Create bank statements from leg records

        :param data: data for statement line creations, as provided by _prepare_statement_data
                    dict (account_journal.id, dict(date, list of bank statement line values for create method))
        :param apply_import_rules: applies auto_import_rules set in the journal corresponding to the statement
        :returns: RecordSet of all created or updated bank statements
        """
        statements = self.env['account.bank.statement']
        for journal_id, days in iteritems(data):
            if not days:
                continue
            for date in sorted(days):
                lines = days[date]
                if not lines:
                    continue
                statement = self.env['account.bank.statement'].search([('journal_id', '=', journal_id),
                                                                       ('sepa_imported', '=', True),
                                                                       ('date', '=', date)], limit=1)
                lines.sort(key=lambda l: l.get('completed_at'))

                if not statement:
                    vals = {
                        'date': date,
                        'journal_id': journal_id,
                        'name': 'Revolut API import',
                        'sepa_imported': True,
                    }
                    statement = self.env['account.bank.statement'].create(vals)
                if statement.state != 'open':
                    statement.button_draft()

                StatementLine = self.env['account.bank.statement.line']
                fee_lines = [line for line in lines if line.get('is_fee')]
                nonfee_lines = [line for line in lines if not line.get('is_fee')]
                for line in nonfee_lines:
                    for key in ['completed_at', 'fee', 'balance']:
                        line.pop(key, None)
                statement.line_ids = [(0, 0, line) for line in nonfee_lines]
                for line in fee_lines:
                    orig_line = StatementLine.search([('entry_reference', '=', line['entry_reference']),
                                                      ('journal_id', '=', journal_id)], limit=1)
                    if orig_line:
                        line['commission_of_id'] = orig_line.id
                    for key in ['imported_partner_name', 'completed_at']:
                        line.pop(key, None)
                statement.line_ids = [(0, 0, line) for line in fee_lines]
                statements |= statement
                statement.update_balance_from_revolut_legs()

        if statements and apply_import_rules:
            statements.with_context(skip_error_on_import_rule=False).apply_journal_import_rules()
        # Update factual balances
        for statement in statements:
            statement.balance_end_factual = statement.balance_end_real
        return statements


RevolutApiTransactionLeg()
