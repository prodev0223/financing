# -*- coding: utf-8 -*-

from datetime import datetime

from odoo import _, api, exceptions, models, tools


class OffsettingReport(models.AbstractModel):
    _name = 'report.l10n_lt.report_offsetting_template'

    @api.model
    def default_date(self):
        return datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    def get_lines(self, data):
        lines = self.env['account.move.line'].search([('move_id', '=', data['move_id'])])

        line_types_set = set(lines.mapped('account_id.internal_type'))
        payable_type = 'payable'
        receivable_type = 'receivable'
        if len(line_types_set) == 1:
            # raise if account types are the same
            raise exceptions.ValidationError(_('At least one line must be of a different type in the act'))
        elif len(line_types_set) > 2:
            # raise if more than two account types
            raise exceptions.ValidationError(
                _('You can\'t print an offset with more than two different account types')
            )
        elif 'other' in line_types_set and ('payable' in line_types_set or 'receivable' in line_types_set):
            # for when one account type is 'payable'/'receivable' and another is type 'other'
            payable_type = 'payable' if 'payable' in line_types_set else 'other'
            receivable_type = 'receivable' if 'receivable' in line_types_set else 'other'

        lines_payable = lines.filtered(
            lambda l: l.account_id.internal_type == payable_type).mapped('matched_credit_ids.credit_move_id')
        lines_receivable = lines.filtered(
            lambda l: l.account_id.internal_type == receivable_type).mapped('matched_debit_ids.debit_move_id')

        # In case there are more than two lines on offset;
        if len(lines) == 2:
            amount_reconciled = abs(lines[0].balance)
        else:
            amount_reconciled = abs(sum(lines.filtered(
                lambda l: l.account_id.internal_type == 'payable').mapped('balance')))

        amount_left_to_reconcile = sum([
            sum(payable.balance for payable in lines_payable),
            sum(receivable.balance for receivable in lines_receivable)
        ])
        is_company_indebted = tools.float_compare(amount_left_to_reconcile, 0.0, precision_digits=2) < 0
        partner_id = lines[0].partner_id
        line_data = {
            'partner_id': partner_id,
            'lines_payable': lines_payable,
            'lines_receivable': lines_receivable,
            'amount_reconciled': amount_reconciled,
            'amount_left_to_reconcile': abs(amount_left_to_reconcile),
            'is_company_indebted': is_company_indebted,
        }
        return line_data

    @api.multi
    def render_html(self, doc_ids=None, data=None):
        current_user = self.env.user
        company = current_user.sudo().company_id
        representative = current_user.employee_ids[0] if current_user.employee_ids else False
        line_data = self.get_lines(data)
        accountant = current_user if current_user.is_accountant() and not current_user.has_group('base.group_system') \
            else False

        docargs = {
            'date_act': self.default_date(),
            'date_offsetting': data['date_offsetting'],
            'company': company,
            'company_representative': representative,
            'partner': line_data['partner_id'],
            'accountant': accountant,
            'current_user_timestamp': self.env.user.get_current_timestamp(),
            'lines_payable': line_data['lines_payable'],
            'lines_receivable': line_data['lines_receivable'],
            'amount_reconciled': line_data['amount_reconciled'],
            'amount_left_to_reconcile': line_data['amount_left_to_reconcile'],
            'is_company_indebted': line_data['is_company_indebted'],
        }
        return self.env['report'].render('l10n_lt.report_offsetting_template', docargs)
