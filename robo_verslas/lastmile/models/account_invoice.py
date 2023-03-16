# -*- encoding: utf-8 -*-
import logging
from odoo import api, models
from odoo.addons.queue_job.job import job, identity_exact


_logger = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'
    
    @api.model
    def _get_default_payment_journal(self):

        payment_journal_code = 'CARD'
        payment_journal= self.env['account.journal'].search([
            ('code', '=', payment_journal_code),
            ('type', '=', 'bank'),
        ], limit=1)
        return payment_journal

    @api.model
    def cron_reconcile_api_invoice(self, invoices_to_process=200, channel='root', order='date_invoice asc'):
        payment_journal = self._get_default_payment_journal()

        invoices = self.env['account.invoice'].search([
            ('state', '=', 'open'),
            ('imported_api', '=', True),
            ('type', '=', 'out_invoice'),
            ('date_invoice', '>=', '2021-03-01'),
            ('user_id', '=', 1)
        ], limit=invoices_to_process, order=order)

        for invoice in invoices:
            invoice.with_delay(identity_key=identity_exact, channel=channel)._reconcile_api_invoice(
                payment_journal=payment_journal)

    @api.multi
    @job
    def _reconcile_api_invoice(self, payment_journal=None):
        """ Create Stripe payment entry for API invoices """
        if not payment_journal:
            payment_journal = self._get_default_payment_journal()

        ResPartner = self.env['res.partner']
        AccountMoveLine = self.env['account.move.line']
        company_currency = self.env.user.company_id.currency_id
        for invoice in self:
            if invoice.state == 'paid':
                continue
            domain = [
                ('account_id', '=', invoice.account_id.id),
                ('date', '=', invoice.date_invoice),
                ('partner_id', '=', ResPartner._find_accounting_partner(invoice.partner_id).id),
                ('reconciled', '=', False),
                ('amount_residual', '!=', 0.0),
                ('credit', '>', 0),
                ('debit', '=', 0),
            ]
            line = AccountMoveLine.sudo().search(domain, limit=1)
            if line:
                _logger.info('Assigning existing credit to invoice %s', invoice.number)
                invoice.sudo().assign_outstanding_credit(line.id)
            else:
                # check currency
                payment_currency_id = invoice.currency_id if invoice.currency_id != company_currency else False
                move_amount = invoice.residual
                payment_amount_currency = 0.0
                if payment_currency_id:
                    payment_amount_currency = move_amount
                    move_amount = payment_currency_id.with_context(date=invoice.date_invoice).compute(
                        move_amount, company_currency)

                ref = 'Mokėjimas stripe'
                lines = []
                line1_vals = {
                    'name': ref,
                    'account_id': invoice.account_id.id,
                    'date': invoice.date_invoice,
                }
                if payment_currency_id:
                    line1_vals['currency_id'] = payment_currency_id.id
                    sign = -1.0 if invoice.type in ['out_invoice', 'in_refund'] else 1.0
                    line1_vals['amount_currency'] = payment_amount_currency * sign

                if invoice.type in ['out_invoice', 'in_refund']:
                    line1_vals['credit'] = move_amount
                    line1_vals['debit'] = 0.0
                else:
                    line1_vals['debit'] = move_amount
                    line1_vals['credit'] = 0.0
                line2_vals = {
                    'name': ref,
                    'date': invoice.date_invoice,
                }
                if payment_currency_id:
                    line2_vals['currency_id'] = payment_currency_id.id
                    sign = 1.0 if invoice.type in ['out_invoice', 'in_refund'] else -1.0
                    line2_vals['amount_currency'] = payment_amount_currency * sign

                if invoice.type in ['out_invoice', 'in_refund']:
                    line2_vals['debit'] = move_amount
                    line2_vals['credit'] = 0.0
                    line2_vals['account_id'] = payment_journal.default_debit_account_id.id
                else:
                    line2_vals['credit'] = move_amount
                    line2_vals['debit'] = 0.0
                    line2_vals['account_id'] = payment_journal.default_credit_account_id.id
                lines.append((0, 0, line1_vals))
                lines.append((0, 0, line2_vals))
                move_vals = {
                    'ref': ref,
                    'line_ids': lines,
                    'journal_id': payment_journal.id,
                    'date': invoice.date_invoice,
                    'partner_id': invoice.partner_id.id,
                }
                _logger.info('Creating matching Stripe payment for invoice %s', invoice.number)
                move_id = self.env['account.move'].create(move_vals)
                move_id.post()
                line_ids = move_id.line_ids.filtered(lambda r: r.account_id.id == invoice.account_id.id)
                line_ids |= invoice.move_id.line_ids.filtered(lambda r: r.account_id.id == invoice.account_id.id)
                if len(line_ids) > 1:
                    line_ids.with_context(reconcile_v2=True).reconcile()
