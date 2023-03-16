# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, tools, exceptions, _


class EmployeeMonthlyAnalyticAmounts(models.Model):
    _name = 'employee.monthly.analytic.amounts'

    _sql_constraints = [
        ('single_payslip', 'UNIQUE (payslip_id)', _('Negali egzistuoti du analitinių sumų įrašai su vienu algalapiu')),
    ]

    year = fields.Integer('Metai', required=True)
    month = fields.Integer('Mėnuo', required=True)
    payslip_id = fields.Many2one('hr.payslip', string='Algalapis', required=False, readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', required=False)
    user_id = fields.Many2one('res.users', string='Naudotojas', required=False)
    amount = fields.Float('Suma', required=True, default=0.0)

    @api.onchange('employee_id', 'user_id')
    def _sync_employee_and_user(self):
        if self.employee_id:
            user = self.employee_id.user_id.id or False
            if self.user_id.id != user:
                self.user_id = user
        elif self.user_id:
            employee = self.user_id.employee_ids[0].id if self.user_id.employee_ids and self.user_id.employee_ids[0].active else False
            if self.employee_id != employee:
                self.employee_id = employee
        if not self.user_id and not self.employee_id:
            raise exceptions.ValidationError(_('Privaloma nurodyti naudotoją arba darbuotoją'))

    @api.multi
    @api.constrains('month')
    def _check_month_valid(self):
        for rec in self:
            if not 1 <= rec.month <= 12:
                raise exceptions.ValidationError(_('Mėnuo turi būti tarp 1 ir 12'))

    @api.onchange('payslip_id', 'year', 'month', 'employee_id', 'amount')
    def _set_payslip_values(self):
        if self.payslip_id:
            start_date = datetime.strptime(self.payslip_id.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            if self.year != start_date.year:
                self.year = start_date.year
            if self.month != start_date.month:
                self.month = start_date.month
            amount = self.get_default_slip_amount(self.payslip_id)
            if tools.float_compare(self.amount, amount, precision_digits=2) != 0:
                self.amount = amount
            if self.employee_id.id != self.payslip_id.employee_id.id:
                self.employee_id = self.payslip_id.employee_id.id

    @api.multi
    @api.constrains('payslip_id', 'year', 'month', 'employee_id', 'amount')
    def _check_payslip_values(self):
        for rec in self.filtered('payslip_id'):
            start_date = datetime.strptime(rec.payslip_id.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            if rec.year != start_date.year:
                rec.year = start_date.year
            if rec.month != start_date.month:
                rec.month = start_date.month
            amount = rec.get_default_slip_amount(rec.payslip_id)
            if tools.float_compare(rec.amount, amount, precision_digits=2) != 0:
                rec.amount = amount
            if rec.employee_id.id != rec.payslip_id.employee_id.id:
                rec.employee_id = rec.payslip_id.employee_id.id

    @api.one
    def unlink(self, cancelling_payslip=False):
        if self.payslip_id and not cancelling_payslip:
            raise exceptions.ValidationError(_('Negalite ištrinti eilutės, kuri susieta su algalapiu'))
        return super(EmployeeMonthlyAnalyticAmounts, self).unlink()

    @api.model
    def get_default_slip_amount(self, slip):
        return sum(slip.line_ids.filtered(
            lambda l: l.code in ['SDD', 'BM', 'BUD', 'BV', 'A', 'L', 'P', 'PNVDU', 'KR', 'MA', 'NTR', 'INV', 'IST',
                                 'AK', 'VD', 'VDN', 'VSS', 'DN', 'SNV', 'NDL', 'VDL', 'T', 'V', 'DP', 'KM', 'PR', 'PD',
                                 'PRI', 'PDN', 'PDNM', 'KOMP', 'KKPD', 'KNDDL']).mapped('amount'))

    @api.model
    def create_from_payslip(self, slips):
        for slip in slips.filtered(lambda s: not s.monthly_analytic_amount_ids):
            start_date = datetime.strptime(slip.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            self.create({
                'year': start_date.year,
                'month': start_date.month,
                'employee_id': slip.employee_id.id,
                'user_id': slip.employee_id.user_id.id if slip.employee_id.user_id else False,
                'amount': self.get_default_slip_amount(slip),
                'payslip_id': slip.id
            })


EmployeeMonthlyAnalyticAmounts()


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    monthly_analytic_amount_ids = fields.One2many('employee.monthly.analytic.amounts', 'payslip_id')

    @api.multi
    def atsaukti(self):
        res = super(HrPayslip, self).atsaukti()
        self.env['employee.monthly.analytic.amounts'].search([
            ('payslip_id', 'in', self.mapped('id'))
        ]).unlink(cancelling_payslip=True)
        return res

    @api.multi
    def action_payslip_done(self):
        res = super(HrPayslip, self).action_payslip_done()
        for slip in self:
            self.env['employee.monthly.analytic.amounts'].search([
                ('payslip_id', '=', slip.id)
            ]).unlink(cancelling_payslip=True)
        self.env['employee.monthly.analytic.amounts'].create_from_payslip(self)
        return res

    @api.multi
    def unlink(self):
        res = super(HrPayslip, self).unlink()
        self.env['employee.monthly.analytic.amounts'].search([
            ('payslip_id', 'in', self.mapped('id'))
        ]).unlink(cancelling_payslip=True)
        return res


HrPayslip()
