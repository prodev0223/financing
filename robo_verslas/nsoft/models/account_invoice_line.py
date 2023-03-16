# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    nsoft_purchase_line_ids = fields.One2many(
        'nsoft.purchase.invoice.line', 'invoice_line_id',
        string='nSoft pirkimo eilutė',
    )
    nsoft_sale_line_ids = fields.One2many(
        'nsoft.sale.line', 'invoice_line_id',
        string='Nsoft Sale Line',
    )
    nsoft_inv_line_ids = fields.One2many(
        'nsoft.invoice.line', 'invoice_line_id',
        string='Nsoft Invoice Line',
    )
    nsoft_refund_line_ids = fields.One2many(
        'nsoft.sale.line', 'refund_line_id',
        string='nSoft pardavimų eilutės kred.',
    )
    nsoft_correction_line_ids = fields.One2many(
        'nsoft.sale.line', 'correction_line_id',
        string='nSoft pardavimų eilutės kor.',
    )

    @api.multi
    def apply_default_analytics(self):
        """
        !COMPLETE OVERRIDE OF apply_default_analytics METHOD!
        Applies default analytic account to invoice line if any
        """
        # Do not apply analytics if base analytic group is not set on the user
        if not self.env.user.has_group('analytic.group_analytic_accounting'):
            return

        # Ref needed objects
        NsoftCashRegister = self.env['nsoft.cash.register'].sudo()
        AccountAnalyticAccount = self.env['account.analytic.account']

        default_analytic_errors = str()
        for rec in self.filtered(lambda x: not x.account_analytic_id):
            # Get default analytic account with sudo
            sudo_analytic_default = rec.get_default_analytic_account(with_sudo=True)
            if sudo_analytic_default:
                # If default account exists for current line, fetch the same account without sudo and check
                # the access rules for the current user. If it crashes - append it to the error string
                analytic_account = AccountAnalyticAccount.browse(sudo_analytic_default.analytic_id.id)
                try:
                    analytic_account.check_access_rule('read')
                except (exceptions.AccessError, exceptions.UserError):
                    default_analytic_errors += _('Line - "{}"\n').format(rec.name)
                else:
                    # Otherwise, account is assigned to the line
                    rec.account_analytic_id = analytic_account.id
            else:
                # Otherwise, get the analytics from the nsoft cash register
                # Get partner from invoice and get the default from nsoft cash register
                employee = rec.invoice_id.sudo().submitted_employee_id
                if employee:
                    analytic_account = NsoftCashRegister.find_matching_analytics(employee)
                    rec.account_analytic_id = analytic_account.id

        # Check if there's any default analytic errors
        if default_analytic_errors:
            error_msg = _(
                'Failed to confirm the invoice - lines listed below have default analytic accounts that '
                'are set by the rules, however, your user does not have sufficient rights to access '
                'these accounts. Contact your manager in regards to user rights configuration or fill '
                'in all of the analytic account fields in the invoice lines. \n\n'
                ) + default_analytic_errors
            raise exceptions.ValidationError(error_msg)
