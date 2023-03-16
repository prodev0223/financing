# -*- coding: utf-8 -*-


from odoo import api, models, exceptions


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    @api.multi
    def _assign_bank_statement(self, invoice):
        """ Reconcile bank statement line with invoice payment line """
        self.ensure_one()
        invoice.ensure_one()
        if invoice.need_action_info and not invoice.need_action_repr and invoice.state == 'draft' \
                and invoice.expense_state == 'imported':
            invoice.app_inv_company(mark_paid=False)
        if not self.account_id:
            account_code = '2410' if invoice.type in ['out_invoice', 'out_refund'] else '4430'
            account_id = self.env['account.account'].search([('code', '=', account_code)], limit=1).id
            self.sudo().write({'account_id': account_id})
        else:
            account_id = self.account_id.id
        counterpart_move = self.sudo().fast_counterpart_creation()
        counterpart_move_line_id = counterpart_move.line_ids.filtered(lambda r: r.account_id.id == account_id).id
        if counterpart_move_line_id:
            invoice.assign_outstanding_credit(counterpart_move_line_id)

    @api.multi
    def assign_bank_statement(self, invoice_id):
        """
        Reconcile bank statement line with invoice payment line
        :param invoice_id: ID of invoice to reconcile with (int)
        :return: None
        """
        self.ensure_one()
        invoice = self.env['account.invoice'].browse(invoice_id)
        use_sudo = self.env.user.has_group('robo.group_menu_kita_analitika') or self.env.user.is_manager()
        # Users with those groups should not see the wizard:
        use_sudo = use_sudo or invoice.type in ['out_invoice', 'out_refund'] and self.env.user.has_group('robo.group_robo_see_all_incomes')
        use_sudo = use_sudo or invoice.type in ['in_invoice', 'in_refund'] and self.env.user.has_group('robo.group_robo_see_all_expenses')
        if not use_sudo:
            try:
                self.check_access_rights('write')
                self.check_access_rule('write')
                invoice.check_access_rights('write')
                invoice.check_access_rule('write')
                use_sudo = True
            except (exceptions.UserError, exceptions.AccessError):
                pass
        if use_sudo and not self.env.user.has_group('base.group_system'):
            self.env['account.bank.statement.line'].check_global_readonly_access()
            invoice.message_post('Adding payment')
            self.sudo()._assign_bank_statement(invoice.sudo())
        else:
            self._assign_bank_statement(invoice)
