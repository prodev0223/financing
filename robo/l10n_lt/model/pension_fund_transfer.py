# -*- coding: utf-8 -*-

from odoo import fields, models, api, _, exceptions, tools


class PensionFundTransfer(models.Model):
    _name = 'pension.fund.transfer'

    def _default_journal_id(self):
        return self.env.user.company_id.payroll_bank_journal_id.id

    def _default_credit_account_id(self):
        return self.env['account.account'].search([('code', '=', '4430')], limit=1).id

    def _default_debit_account_id(self):
        return self.env['account.account'].search([('code', '=', '63031')], limit=1).id

    def _default_currency_id(self):
        return self.env.user.company_id.currency_id.id

    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed')], string='Status', readonly=True,
                             default='draft')
    pension_fund_id = fields.Many2one('res.pension.fund', 'Pension Fund', required=True)
    partner_id = fields.Many2one('res.partner', 'Related partner', compute='_compute_partner_id', store=True,
                                 readonly=True)
    employee_id = fields.Many2one('hr.employee', 'For Employee', required=True)
    journal_id = fields.Many2one('account.journal', 'Journal', required=True, default=_default_journal_id)
    credit_account_id = fields.Many2one('account.account', 'Credit account', required=True,
                                        default=_default_credit_account_id)
    debit_account_id = fields.Many2one('account.account', 'Debit account', required=True,
                                        default=_default_debit_account_id)
    amount = fields.Monetary('Amount', required=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', required=True, default=_default_currency_id)
    payment_date = fields.Date('Payment date', required=True)
    transfer_purpose = fields.Text('Transfer Purpose')
    account_move_id = fields.Many2one('account.move', 'Account move', readonly=True)

    @api.multi
    @api.depends('pension_fund_id')
    def _compute_partner_id(self):
        for rec in self:
            rec.partner_id = rec.pension_fund_id.partner_id

    @api.constrains('pension_fund_id')
    def _check_pension_fund_issues(self):
        for rec in self:
            pension_fund_issues = rec.pension_fund_id.issues
            if pension_fund_issues:
                raise exceptions.ValidationError(
                    _('Can not create pension fund transfer due to the issues with the pension fund: {}').format(
                        pension_fund_issues
                    )
                )

    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if tools.float_compare(rec.amount, 0.0, precision_digits=2) < 0:
                raise exceptions.ValidationError(_('Incorrect amount'))

    @api.multi
    @api.depends('transfer_purpose')
    def name_get(self):
        return [(rec.id, rec.transfer_purpose) for rec in self]

    @api.multi
    def action_open_account_move(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'target': 'self',
            'res_id': self.account_move_id.id
        }

    @api.model
    def _check_action_rights(self):
        if not self.env.user.is_accountant():
            raise exceptions.ValidationError(_('You do not have sufficient rights to perform this action'))

    @api.multi
    def action_confirm(self):
        self._check_action_rights()
        transfers = self.filtered(lambda t: t.state == 'draft')
        transfers.write({'state': 'confirmed'})
        for transfer in transfers:
            move = transfer.create_account_move()
            move.post()
            transfer.write({'account_move_id': move.id})

    @api.multi
    def action_cancel(self):
        self._check_action_rights()
        transfers = self.filtered(lambda t: t.state == 'confirmed')
        transfers.write({'state': 'draft'})
        moves = transfers.mapped('account_move_id')
        if moves:
            moves.button_cancel()
            moves.unlink()

    @api.multi
    def _get_transfer_purpose(self):
        self.ensure_one()
        return self.transfer_purpose or _('Pension payment for employee {}').format(self.employee_id.name)

    @api.model
    def _get_a_class_code(self):
        return False

    @api.multi
    def create_account_move(self):
        self.ensure_one()

        transfer_purpose = self._get_transfer_purpose()

        move_line_base = {
            'name': transfer_purpose,
            'ref': '',
            'journal_id': self.journal_id.id,
            'partner_id': self.partner_id.id,
            'date': self.payment_date,
            'a_klase_kodas_id': self._get_a_class_code(),
        }

        credit_move_line_values = move_line_base.copy()
        credit_move_line_values.update({
            'account_id': self.credit_account_id.id,
            'debit': 0.0,
            'credit': self.amount
        })

        debit_move_line_values = move_line_base.copy()
        debit_move_line_values.update({
            'account_id': self.debit_account_id.id,
            'credit': 0.0,
            'debit': self.amount
        })

        move_vals = {
            'name': _('Pension payment'),
            'ref': '',
            'date': self.payment_date,
            'journal_id': self.journal_id.id,
            'line_ids': [(0, 0, credit_move_line_values), (0, 0, debit_move_line_values)],
            'pension_fund_transfer_id': self.id,
        }
        move = self.env['account.move'].create(move_vals)
        return move
