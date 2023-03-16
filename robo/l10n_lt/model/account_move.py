# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions, SUPERUSER_ID
from collections import OrderedDict
from six import iteritems


class AccountMove(models.Model):

    _name = 'account.move'
    _inherit = ['account.move', 'mail.thread']

    change_reason_text = fields.Text(string='Keitimo priežastis', track_visibility='onchange')
    expense_invoice_id = fields.One2many('account.invoice', 'expense_move_id',
                                         string='Susijusi avansinės apyskaitos sąskaita')
    pension_fund_transfer_id = fields.Many2one('pension.fund.transfer')
    show_print_report_write_off = fields.Boolean(compute='_compute_show_print_report_write_off')
    not_posted = fields.Boolean(string="Not posted", default=True)

    @api.constrains('statement_line_id')
    def bank_statement_id_unique(self):
        for rec in self.sudo():
            if rec.statement_line_id:
                if self.env['account.move'].search([('statement_line_id', '=', rec.statement_line_id.id),
                                                    ('id', '!=', rec.id)]):
                    raise exceptions.ValidationError(
                        _('Jau sukurtas apskaitos įrašas išrašo eilutei (%s)') % rec.statement_line_id.name or '')

    @api.multi
    def assert_balanced(self):
        if self._context.get('unbalanced_entry', False):
            return True
        return super(AccountMove, self).assert_balanced()

    @api.multi
    def get_line_vals_to_post(self):
        res = OrderedDict()
        for line in self.line_ids:
            res[line.id] = {'account_id': line.account_id.id,
                            'credit': line.credit,
                            'debit': line.debit,
                            }
        return res

    @api.multi
    def write(self, vals):
        if 'line_ids' in vals:
            post_lines = True
        else:
            post_lines = False
        if post_lines:
            prev_line_values = dict((m.id, m.get_line_vals_to_post()) for m in self)
        else:
            prev_line_values = {}
        res = super(AccountMove, self).write(vals)
        if post_lines:
            for rec in self:
                message = '''<strong>Buvusios reikšmės:\n</strong>
<table border="2" width=100%%>
    <tr>
        <td><b>Sąskaita</b<</td>
        <td><b>Debetas</b></td>
        <td><b>Kreditas</b></td>
    </tr>'''
                for prev_line_id, prev_line_vals in iteritems(prev_line_values.get(rec.id, {})):
                    new_line = rec.line_ids.filtered(lambda r: r.id == prev_line_id)
                    if len(new_line) > 1:
                        continue
                    bold_fields = {'account_id': False if new_line and new_line.account_id.id == prev_line_vals.get('account_id') else True,
                                   'credit': False if new_line and new_line.credit == prev_line_vals.get('credit') else True,
                                   'debit': False if new_line and new_line.debit == prev_line_vals.get('debit') else True}
                    new_line = '''<tr>'''
                    if bold_fields['account_id']:
                        new_line += '<td><b>%s</b></td>' % self.env['account.account'].browse(prev_line_vals.get('account_id', False)).display_name
                    else:
                        new_line += '<td>%s</td>' % self.env['account.account'].browse(prev_line_vals.get('account_id', False)).display_name
                    if bold_fields['debit']:
                        new_line += '<td><b>%s</b></td>' % prev_line_vals.get('debit', '0.00')
                    else:
                        new_line += '<td>%s</td>' % prev_line_vals.get('debit', '0.00')
                    if bold_fields['credit']:
                        new_line += '<td><b>%s</b></td>' % prev_line_vals.get('credit', '0.00')
                    else:
                        new_line += '<td>%s</td>' % prev_line_vals.get('credit', '0.00')
                    new_line += '''</tr>
'''
                    message += new_line
                message += '</table>'
                rec.message_post(body=message)
        return res

    @api.multi
    def post(self):
        res = super(AccountMove, self).post()
        self.write({'not_posted': False})
        vmi = self.env['res.partner'].search([('kodas', '=', '188659752')], limit=1)
        vmi_accounts = [
            self.env.ref('l10n_lt.1_account_246', raise_if_not_found=False).id,
            self.env.ref('l10n_lt.1_account_248', raise_if_not_found=False).id,
            self.env.ref('l10n_lt.1_account_249', raise_if_not_found=False).id,
            self.env.ref('l10n_lt.1_account_250', raise_if_not_found=False).id,
            self.env.ref('l10n_lt.1_account_386', raise_if_not_found=False).id,
            self.env.ref('l10n_lt.account_account_7', raise_if_not_found=False).id,
            self.env.ref('l10n_lt.1_account_398', raise_if_not_found=False).id,
            self.env.ref('l10n_lt.1_account_399', raise_if_not_found=False).id,
            self.env.ref('l10n_lt.1_account_401', raise_if_not_found=False).id,
            self.env.ref('l10n_lt.1_account_403', raise_if_not_found=False).id,
        ]
        for rec in self:
            if rec.journal_id.code == 'PVM' and rec.company_id.sudo().period_lock_date < rec.date:
                rec.company_id.sudo().write({'period_lock_date': rec.date})
            for line in rec.line_ids:
                if not line.partner_id and line.account_id.id in vmi_accounts:
                    line.partner_id = vmi.id
        return res

    @api.multi
    def _check_lock_date(self):
        """
        Check whether account_move record is in locked period.
        If it is, raise an error message, otherwise return True
        :return: True/None
        """
        bypass_lock_check = self._context.get('sepa_export') and \
            self.env.user.id == SUPERUSER_ID or self._context.get('reconciliation_actions')
        if not bypass_lock_check:
            company = self.env.user.company_id
            lock_date = company.get_user_accounting_lock_date()
            # Check whether stock moves should be filtered
            if self._context.get('lock_dates_ignore_state'):
                moves = self
            else:
                moves = self.filtered(lambda x: x.sudo().state != 'draft' or not x.sudo().not_posted)
            for move in moves:
                if move.date <= lock_date:
                    raise exceptions.UserError(company.accounting_lock_error_message(lock_date))
        return True

    @api.multi
    def _compute_show_print_report_write_off(self):
        debt_account = self.env['account.account'].search([('code', '=', '6811')])
        if not debt_account:
            return
        for rec in self:
            rec.show_print_report_write_off = any(
                account == debt_account for account in rec.line_ids.mapped('account_id'))

    @api.multi
    def action_open_account_move_split_wizard(self):
        self.ensure_one()
        wizard = self.env['account.move.split.wizard'].create({'move_id': self.id})

        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.move.split.wizard',
            'res_id': wizard.id,
            'view_id': self.env.ref('l10n_lt.account_move_split_wizard_form').id,
            'type': 'ir.actions.act_window',
            'target': 'new'
        }

    @api.multi
    def print_report(self):
        self.ensure_one()
        if len(self.line_ids.mapped('partner_id')) != 1:
            raise exceptions.ValidationError(_('Offsetting can only be printed if the lines contain the same partner'))
        if self.ref != 'Užskaita':
            raise exceptions.ValidationError(_('You can only print a PDF for offsetting'))
        data = {
            'date_offsetting': self.date,
            'move_id': self.id,
        }
        res = self.env['report'].get_action(self, 'l10n_lt.report_offsetting_template', data=data)
        if 'report_type' in res:
            if self._context.get('force_pdf'):
                res['report_type'] = 'qweb-pdf'
            if self._context.get('force_html'):
                res['report_type'] = 'qweb-html'
        return res

    @api.multi
    def print_report_write_off(self):
        self.ensure_one()
        debt_account = self.env['account.account'].search([('code', '=', '6811')])
        if not debt_account:
            raise exceptions.ValidationError(_('Debt account was not found. Please contact the system administrators.'))
        if not any(account_id == debt_account.id for account_id in self.line_ids.mapped('account_id').ids):
            raise exceptions.ValidationError(
                _('Write-off may only be generated for moves that have a line with a bad debt account (#{})').format(
                    debt_account.code))
        partner = self.line_ids.mapped('partner_id')
        if not len(partner) == 1:
            raise exceptions.ValidationError(_('To generate a write-off a record must have one and only one partner'))

        data = {
            'name': self.name,
            'partner_id': partner.id,
            'reconciled_line_ids': self.line_ids.mapped('full_reconcile_id').reconciled_line_ids.ids,
            'write_off_line_ids': self.line_ids.ids,
        }
        res = self.env['report'].get_action(self, 'l10n_lt.report_write_off_template', data=data)
        if 'report_type' in res:
            if self._context.get('force_pdf'):
                res['report_type'] = 'qweb-pdf'
            if self._context.get('force_html'):
                res['report_type'] = 'qweb-html'
        return res

    @api.multi
    def action_backend_view(self):
        action = self.env.ref('account.action_move_journal_line')
        if not action or not self.env.user.is_accountant() or not self:
            return {}
        action = action.read()[0]
        view_type = 'form' if len(self) == 1 else 'tree'
        action.update({
            'view_type': view_type,
            'view_mode': view_type,
        })
        if view_type == 'form':
            form_view_id = self.env.ref('account.view_move_form').id
            action['res_id'] = self.id
            action['view_id'] = form_view_id
            action['views'] = [(form_view_id, 'form')]
        else:
            action['domain'] = [('id', 'in', self.ids)]
        return action
