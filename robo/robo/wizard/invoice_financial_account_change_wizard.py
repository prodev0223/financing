# -*- coding: utf-8 -*-
from odoo import fields, models, api, _, exceptions


class InvoiceFinancialAccountChangeWizard(models.TransientModel):
    """
    Wizard that is used to change account-account
    on every current invoice line
    """
    _name = 'invoice.financial.account.change.wizard'

    # invoice_id = fields.Many2one('account.invoice', string='Sąskaita faktūra')  # Moved to invoice_ids
    account_id = fields.Many2one('account.account', string='Buhalterinė sąskaita')
    invoice_ids = fields.Many2many('account.invoice', string='Invoices')

    show_forced_taxes_warning = fields.Boolean(compute='_compute_show_forced_taxes_warning')
    remove_forced_taxes = fields.Boolean(string='Remove forced taxes when changing the account')

    has_picking = fields.Boolean(compute='_compute_has_picking')

    @api.multi
    @api.depends('invoice_ids')
    def _compute_has_picking(self):
        """Checks whether related invoice has pickings"""
        for rec in self:
            rec.has_picking = any(invoice.get_related_pickings() for invoice in self.invoice_ids)

    @api.multi
    def _compute_show_forced_taxes_warning(self):
        """Check whether forced tax warning should be displayed"""
        for rec in self:
            rec.show_forced_taxes_warning = any(invoice.force_taxes for invoice in rec.invoice_ids)

    @api.multi
    def change_account(self):
        """
        Changes financial account for each invoice line.
        Base constraints are checked before execution.
        :return: None
        """
        self.ensure_one()
        if not self.user_has_groups('robo_basic.group_robo_premium_accountant'):
            raise exceptions.ValidationError(_('Tik buhalteriai gali keisti patvirtintos sąskaitos buh. sąskaitą.'))
        invoices = self.invoice_ids

        # Ref non deductible accounts
        non_deductible_profit = self.env.ref('l10n_lt.1_account_485')
        non_deductible = self.env.ref('l10n_lt.1_account_484')
        nd_accounts = non_deductible_profit | non_deductible

        # Invoice can be edited in all states except for cancel
        do_not_change_with_multiple_accounts = self._context.get('check_multiple_accounts')

        for invoice in invoices:
            if invoice.state == 'cancel':
                raise exceptions.ValidationError(_('Negalima keisti buh. sąskaitos šioje būsenoje.'))

            inv_lines = invoices.mapped('invoice_line_ids')

            # Accounts with multiple accounting accounts are skipped
            if do_not_change_with_multiple_accounts and len(inv_lines.mapped('account_id')) > 1:
                continue

            # Check if invoice needs to be reopened, and if any lines need their taxes switched
            re_open = invoice.state in ['paid', 'open']
            deductible_type_mapping = {
                non_deductible_profit.id: '_switch_to_nondeductible_profit_taxes',
                non_deductible.id: '_switch_to_nondeductible_taxes',
            }
            # If account is neither 652 or 651 apply deductible conversion method.
            # Method itself checks the taxes, and if they are already deductible, they're skipped
            tax_conversion_method = deductible_type_mapping.get(self.account_id.id, 'switch_to_deductible_taxes')

            # Check whether type conversion is occurring in current change
            type_conversion = (
                self.account_id in nd_accounts and any(line.account_id not in nd_accounts for line in inv_lines)
            ) or (
                self.account_id not in nd_accounts and any(line.account_id in nd_accounts for line in inv_lines)
            )
            preserve_forced_tax_values = invoice.force_taxes and not type_conversion

            forced_tax_values = {}
            if preserve_forced_tax_values:
                # If invoice has forced taxes, save it's initial values
                # and un-force the taxes until the splitting is done
                for t_line in invoice.tax_line_ids:
                    group_key = '{}-{}'.format(t_line.tax_id.id, t_line.sudo().account_analytic_id.id)
                    forced_tax_values[group_key] = t_line.amount

            if self.remove_forced_taxes or preserve_forced_tax_values:
                invoice.force_taxes = False
                invoice.recompute_taxes_if_neccesary()

            # Remove the payments if any and write the account
            payments = invoice.action_invoice_cancel_draft_and_remove_outstanding()
            inv_lines.write({'account_id': self.account_id.id,})
            for line in inv_lines:
                getattr(line.with_context(ignore_exceptions=True), tax_conversion_method)()

            if forced_tax_values:
                for group_key, forced_amount in forced_tax_values.items():
                    invoice_tax_line = invoice.tax_line_ids.filtered(
                        lambda x: '{}-{}'.format(
                            x.tax_id.id, x.sudo().account_analytic_id.id) == group_key
                    )
                    if invoice_tax_line:
                        invoice_tax_line.write({'amount': forced_amount})
                invoice.force_taxes = True

            # Re-open the invoice and assign the re-payments
            if re_open:
                invoice.with_context(skip_attachments=True).action_invoice_open()
                invoice.action_re_assign_outstanding(payments, raise_exception=False)

        return {'type': 'ir.actions.act_close_wizard_and_reload_view'}
