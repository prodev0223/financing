# -*- encoding: utf-8 -*-
import logging
from odoo import models, _, api, exceptions, tools
from odoo.addons.sepa.wizard.account_revolut_import import find_partner_name

_logger = logging.getLogger(__name__)


class RevolutApiTransactionLeg(models.Model):
    _inherit = 'revolut.api.transaction.leg'

    @api.multi
    def _prepare_statement_data(self, filtered_journal=None):
        """
        Prepare data to create bank statements from leg records
        Completely override default method for LastMile integration

        :param filtered_journal: an account_journal Record, if specified, will only create for the revolut.account
                                 linked to that journal. Otherwise, will create for all revolut.account which are linked
        :returns: dict (account_journal.id, dict(date, list of bank statement line values for create method))
        """

        legs = self.filtered(lambda l: l.transaction_id.state == 'completed'
                                       and not tools.float_is_zero(l.amount, precision_digits=2))
        transaction_vals = {}
        for leg in legs.sorted(key=lambda l: l.transaction_id.completed_at):
            journal = self.env['account.journal'].search([('revolut_account_id', '!=', False)])
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


RevolutApiTransactionLeg()
