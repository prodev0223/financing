# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import api, fields, models, _, exceptions, tools


class AccountPayment(models.Model):
    _name = 'account.payment'
    _inherit = ['account.payment', 'ir.attachment.drop']

    def _default_get_cashier_employee_ids(self):
        employees = self.env['hr.employee'].search([('main_accountant', '=', False)])
        cashier_employees = employees.filtered(
            lambda e: e.user_id and e.user_id.has_group('robo_basic.group_robo_cash_manager'))
        return [(6, 0, cashier_employees.ids if cashier_employees else employees.ids)]

    def _default_get_cash_register_employee_ids(self):
        current_employee_is_cashier = self.env.user.has_group('robo_basic.group_robo_kasos_aparatas') and \
                                      not self.env.user.has_group('robo_basic.group_robo_premium_manager') and \
                                      self.env.user.employee_ids
        if current_employee_is_cashier:
            return [(6, 0, self.env.user.employee_ids.ids)]
        employees = self.env['hr.employee'].search([('main_accountant', '=', False)])
        cashier_employees = employees.filtered(
            lambda e: e.user_id and e.user_id.has_group('robo_basic.group_robo_kasos_aparatas'))
        return [(6, 0, cashier_employees.ids if cashier_employees else employees.ids)]

    cashier_employee_ids = fields.Many2many('hr.employee', compute='_compute_cashier_employee_ids',
                                            default=_default_get_cashier_employee_ids)

    cash_register_employee_ids = fields.Many2many('hr.employee', compute='_compute_cash_register_employee_ids',
                                                  default=_default_get_cash_register_employee_ids)
    partner_ids = fields.Many2many('res.partner', compute='_compute_partner_ids')  # TODO: remove

    partner_type = fields.Selection(selection_add=[('employee', 'Darbuotojas')])
    cash_operation_type = fields.Selection([('payroll', 'Darbo užmokestis'),
                                            ('other', 'Kita'),
                                            ('allowance', 'Dienpinigiai'),],
                                           string='Kasos operacijos tipas', default='other')

    @api.multi
    def _compute_cashier_employee_ids(self):
        employees = self.env['hr.employee'].search([('main_accountant', '=', False)])
        cashier_employees = employees.filtered(
            lambda e: e.user_id and e.user_id.has_group('robo_basic.group_robo_cash_manager'))
        for rec in self:
            rec.cashier_employee_ids = [(6, 0, cashier_employees.ids if cashier_employees else employees.ids)]

    @api.multi
    def _compute_cash_register_employee_ids(self):
        current_employee_is_cashier = self.env.user.has_group('robo_basic.group_robo_kasos_aparatas') and \
                                      not self.env.user.has_group('robo_basic.group_robo_premium_manager') and \
                                      self.env.user.employee_ids
        all_employees = self.env['hr.employee'].search([('main_accountant', '=', False)])
        cash_register_employees = all_employees.filtered(
            lambda e: e.user_id and e.user_id.has_group('robo_basic.group_robo_kasos_aparatas'))
        for rec in self:
            if current_employee_is_cashier:
                employees = self.env.user.employee_ids
            else:
                employees = cash_register_employees if cash_register_employees else all_employees
            rec.cash_register_employee_ids = [(6, 0, employees.ids)]

    @api.multi
    @api.depends('partner_type')
    def _compute_partner_ids(self):
        return

    @api.multi
    def print_order(self):
        self.ensure_one()
        if self.journal_id.type == 'cash' and not self.journal_id.code.startswith('CSH') \
                and self.journal_id.code != 'KVIT':
            return self.env['report'].get_action(self, 'l10n_lt.report_cash_register_template')
        return self.env['report'].get_action(self, 'l10n_lt.report_islaidu_orderis_template')

    @api.multi
    def print_income_expense_order(self):
        self.ensure_one()
        return self.env['report'].get_action(self, 'l10n_lt.report_islaidu_orderis_template')

    @api.model
    def default_get(self, fields):
        res = super(AccountPayment, self).default_get(fields)
        if self._context.get('cash_reg_view', False):
            res['journal_id'] = False
        return res

    @api.onchange('cash_operation_type', 'payment_date')
    def _onchange_cash_operation_type_payment_date(self):
        """
        Method to block setting cash operation type to payroll from the year it is outlawed to pay salary with cash;
        """
        if not self.payment_date:
            return
        year = datetime.strptime(self.payment_date, tools.DEFAULT_SERVER_DATE_FORMAT).year
        year_block_types_from = 2022
        if self.cash_operation_type in ['payroll', 'allowance'] and year >= year_block_types_from:
            blocked_type = dict(
                self.fields_get(['cash_operation_type'])['cash_operation_type']['selection'])[self.cash_operation_type]
            self.cash_operation_type = 'other'
            self.communication = str()
            return {
                'warning': {
                    'title': _('Warning'),
                    'message': _('As of {}, You can\'t set cash operation type to {}.').format(year_block_types_from,
                                                                                               blocked_type),
                }
            }

    @api.onchange('partner_id', 'partner_type', 'cash_operation_type')
    def _onchange_partner_id_partner_type_cash_operation_type(self):
        if self.partner_id.is_employee and self.partner_type in ['customer', 'employee']:
            if self.cash_operation_type == 'payroll':
                self.force_destination_account_id = self.env['account.account'].search([('code', '=', '4480')],
                                                                                       limit=1).id
                self.communication = _('Darbo užmokesčio išmokėjimas')
            elif self.cash_operation_type == 'other':
                self.force_destination_account_id = self.env['account.account'].search([('code', '=', '24450')],
                                                                                       limit=1).id
            elif self.cash_operation_type == 'allowance':
                self.force_destination_account_id = self.env['account.account'].search([('code', '=', '4483')],
                                                                                       limit=1).id

    @api.multi
    @api.constrains('cash_operation_type', 'payment_date')
    def _check_cash_operation_type(self):
        year_block_types_from = 2022
        for rec in self:
            year = datetime.strptime(rec.payment_date, '%Y-%m-%d').year
            cash_operation_type = dict(
                self.fields_get(['cash_operation_type'])['cash_operation_type']['selection'])[rec.cash_operation_type]
            if rec.cash_operation_type in ['payroll', 'allowance'] and year >= year_block_types_from:
                raise exceptions.ValidationError(
                    _('As of {}, You can\'t set cash operation type to {}.').format(
                        year_block_types_from, cash_operation_type))

    @api.onchange('partner_type')
    def _onchange_partner_type(self):
        domain = []
        if self.partner_type == 'customer':
            domain = [('customer', '=', True)]
        elif self.partner_type == 'supplier':
            domain = [('supplier', '=', True)]
        elif self.partner_type == 'employee':
            domain = [('is_active_employee', '=', True)]
        return {'domain': {'partner_id': domain}}

    @api.model
    def create_multi_cash_payment_print_action(self):
        action = self.env.ref('robo.multi_cash_payment_print_action', raise_if_not_found=False)
        if action:
            action.create_action()

    @api.model
    def create_multi_cash_register_payment_print_action(self):
        action = self.env.ref('robo.multi_cash_register_payment_print_action', raise_if_not_found=False)
        if action:
            action.create_action()

    @api.multi
    def unlink(self):
        if any(rec.move_name for rec in self) and not self.env.user.is_accountant():
            raise exceptions.UserError(_('Negalima ištrinti įrašo, kuriam yra nustatytas numeris. '
                                         'Kreipkitės į buhalterį.'))
        return super(AccountPayment, self).unlink()
