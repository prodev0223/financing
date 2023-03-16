# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo import tools, models, fields, api, exceptions
from odoo.tools import float_compare, float_is_zero
from odoo.tools.translate import _
from six import iteritems, itervalues
from .darbuotojai import get_vdu
from sys import platform
import xlrd
import os
from xlutils.filter import process, XLRDReader, XLWTWriter
import cStringIO as StringIO
from xlwt import Formula
import calendar
from collections import defaultdict
from .schedule_template import SCHEDULE_TEMPLATE_TYPES
from .payroll_codes import PAYROLL_CODES

def copy2(wb):
    w = XLWTWriter()
    process(XLRDReader(wb, 'unknown.xlsx'), w)
    return w.output[0][1], w.style_list

def _getOutCell(outSheet, colIndex, rowIndex):
    """ HACK: Extract the internal xlwt cell representation. """
    row = outSheet._Worksheet__rows.get(rowIndex)
    if not row: return None

    cell = row._Row__cells.get(colIndex)
    return cell

def setOutCell(outSheet, col, row, value):
    """ Change cell value without changing formatting. """
    # HACK to retain cell style.
    previousCell = _getOutCell(outSheet, col, row)
    # END HACK, PART I

    outSheet.write(row, col, value)

    # HACK, PART II
    if previousCell:
        newCell = _getOutCell(outSheet, col, row)
        if newCell:
            newCell.xf_idx = previousCell.xf_idx


default_inputs = [] # TODO disability needed? (u'INV', u'Invalidumo išmoka')

koeficientai = ['DN', 'VD', 'VDN', 'VSS', 'SNV', 'DP']


class HrPayslip(models.Model):

    _inherit = 'hr.payslip'

    _order = 'date_from DESC, tabelio_numeris asc, number'

    def default_journal_id(self):
        return self.env.user.company_id.salary_journal_id

    journal_id = fields.Many2one('account.journal', default=default_journal_id)
    tabelio_numeris = fields.Char(string='Tabelio numeris', related='employee_id.tabelio_numeris', store=True,
                                  readonly=True)
    payment_line_ids = fields.One2many('hr.payslip.payment.line', 'payslip_id')
    other_line_ids = fields.One2many('hr.payslip.other.line', 'payslip_id', readonly=True)
    imported = fields.Boolean(string='Imported', readonly=True)
    date_computation = fields.Date(string='Skaičiavimo data', help='Kurios datos skaičiavimo taisykles naudoti',
                                   states={'done': [('readonly', True)]})
    date_to = fields.Date(inverse='_set_date_computation')
    use_favourable_sdd = fields.Boolean(string='Lengvatinis darbdavio sodros skaičiavimas',
                                        help=('Jei mėnesinis uždarbis nesiekia MMA, skaičiuojant darbdavio sodrą '
                                               'naudoti mėnesinį, o ne MMA'),
                                        states={'done': [('readonly', True)]})
    employee_id = fields.Many2one('hr.employee', inverse='_set_use_favourable_sdd')
    ziniarastis_period_line_id = fields.Many2one('ziniarastis.period.line')
    appointment_info_lines = fields.One2many('hr.payslip.appointment.info.line', 'payslip', string="Sutarties priedai", readonly=True)
    show_line_ids = fields.One2many('hr.payslip.line', 'slip_id', domain=[('salary_rule_id.appears_on_payslip', '=', True), '|', ('total', '>', 0), ('total', '<', 0)])
    unconfirmed_employee_payments_exist = fields.Boolean(compute='_compute_unconfirmed_employee_payments_exist')
    planned_periodic_payments_exist = fields.Boolean(compute='_compute_planned_periodic_payments_exist')
    planned_periodic_deductions_exist = fields.Boolean(compute='_compute_planned_periodic_deductions_exist')
    has_need_action_holidays = fields.Boolean(string='Egzistuoja atostogos, kurias reikia perskaičiuti',
                                              compute='_compute_has_need_action_holidays')
    has_natura_invoices = fields.Boolean(compute='_compute_has_natura_invoices')
    has_negative_holidays = fields.Boolean(compute='_compute_has_negative_holidays')

    @api.one
    @api.depends('employee_id', 'date_from', 'date_to', 'atostogu_likutis')
    def _compute_has_negative_holidays(self):
        self.has_negative_holidays = tools.float_compare(self.atostogu_likutis, 0.0, precision_digits=2) < 0

    @api.one
    @api.depends('date_to', 'date_from', 'employee_id.address_home_id')
    def _compute_has_natura_invoices(self):
        def _strf(date):
            return date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        if not self.date_to or not self.date_from:
            self.has_natura_invoices = False
            return

        has_invoices = False

        date_from = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        registration_start = _strf(date_to + relativedelta(months=-1, day=21))
        registration_end = _strf(date_to + relativedelta(day=20))
        date_from = _strf(date_from)
        date_to = _strf(date_to)

        invoices = self.env['account.invoice'].search([
            ('state', '=', 'open'),
            ('type', 'in', ['in_invoice', 'in_refund']),
            ('partner_id', '=', self.employee_id.address_home_id.id),
            '|', '&', '&', '&',
            ('registration_date', '<=', registration_end),
            ('registration_date', '>=', date_from),
            ('date_invoice', '>=', date_from),
            ('date_invoice', '<=', date_to),
            '&', '&',
            ('date_invoice', '<', date_from),
            ('registration_date', '>=', registration_start),
            ('registration_date', '<=', registration_end),
        ])

        if invoices:
            invoice_line_account_codes = invoices.mapped('invoice_line_ids.account_id.code')
            natura_acc_code = '631215'
            if any(acc_code == natura_acc_code for acc_code in invoice_line_account_codes):
                has_invoices = True
        self.has_natura_invoices = has_invoices

    @api.multi
    def open_employee_natura_invoices(self):
        self.ensure_one()

        def _strf(date):
            return date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        date_from = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        registration_start = _strf(date_to + relativedelta(months=-1, day=21))
        registration_end = _strf(date_to + relativedelta(day=20))
        date_from = _strf(date_from)
        date_to = _strf(date_to)

        invoices = self.env['account.invoice'].search([
            ('state', '=', 'open'),
            ('type', 'in', ['in_invoice', 'in_refund']),
            ('partner_id', '=', self.employee_id.address_home_id.id),
            '|', '&', '&', '&',
            ('registration_date', '<=', registration_end),
            ('registration_date', '>=', date_from),
            ('date_invoice', '>=', date_from),
            ('date_invoice', '<=', date_to),
            '&', '&',
            ('date_invoice', '<', date_from),
            ('registration_date', '>=', registration_start),
            ('registration_date', '<=', registration_end),
        ])
        natura_acc_code = '631215'
        invoices = invoices.mapped('invoice_line_ids').filtered(lambda l: l.account_id.code == natura_acc_code).invoice_id
        return {
            'id': self.env.ref('robo.robo_expenses_action').id,
            'name': _('%s pajamos natūra, %s - %s') % (self.employee_id.name_related, self.date_from, self.date_to),
            'view_type': 'form',
            'view_mode': 'tree_expenses_robo,form,kanban',
            'views': [(False, 'tree_expenses_robo'), (False, 'form'), (False, 'kanban')],
            'res_model': 'account.invoice',
            'type': 'ir.actions.act_window',
            'target': 'self',
            'domain': [('id', 'in', invoices.mapped('id'))],
            'view_id': self.env.ref('robo.robo_expenses_tree').id,
        }

    @api.one
    @api.depends('date_to', 'date_from', 'employee_id')
    def _compute_has_need_action_holidays(self):
        need_action_holidays = self.env['hr.holidays'].find_holidays_that_need_to_be_recomputed(
            self.date_from,
            self.date_to,
            self.employee_id,
            self.contract_id)

        self.has_need_action_holidays = True if need_action_holidays else False

    @api.multi
    def open_need_action_holidays(self):
        self.ensure_one()
        if self.env.user.is_accountant():
            need_action_holidays_ids = self.env['hr.holidays'].find_holidays_that_need_to_be_recomputed(
                self.date_from,
                self.date_to,
                self.employee_id,
                self.contract_id).mapped('id')

            return {
                'id': self.env.ref('hr_holidays.open_department_holidays_approve').id,
                'name': _('Darbuotojo %s neatvykimai, kuriuos reiktų perskaičiuoti %s-%s') % (
                    self.employee_id.name_related, self.date_from, self.date_to),
                'view_type': 'form',
                'view_mode': 'tree, form',
                'views': [(False, 'tree'), (False, 'form')],
                'res_model': 'hr.holidays',
                'type': 'ir.actions.act_window',
                'target': 'self',
                'domain': [('id', 'in', need_action_holidays_ids)],
                'view_id': self.env.ref('l10n_lt_payroll.hr_employee_payment_tree').id,
                'context': {
                    'search_default_employee_id': self.employee_id.id,
                }
            }

    @api.one
    @api.depends('date_to', 'date_from', 'employee_id.address_home_id')
    def _compute_unconfirmed_employee_payments_exist(self):
        unconfirmed_payments = self.env['hr.employee.payment'].search([
            ('date_from', '<=', self.date_to),
            ('date_to', '>=', self.date_from),
            ('partner_id', '=', self.employee_id.address_home_id.id),
            ('state', '!=', 'done')
        ])
        self.unconfirmed_employee_payments_exist = True if unconfirmed_payments else False

    @api.multi
    def open_unconfirmed_employee_payments(self):
        self.ensure_one()
        if self.env.user.is_accountant():
            return {
                'id': self.env.ref('l10n_lt_payroll.action_holiday_pay').id,
                'name': _('Išmokėjimai %s-%s') % (self.date_from, self.date_to),
                'view_type': 'form',
                'view_mode': 'tree, form',
                'views': [(False, 'tree'), (False, 'form')],
                'res_model': 'hr.employee.payment',
                'type': 'ir.actions.act_window',
                'target': 'self',
                'domain': [('date_from', '>=', self.date_from), ('date_to', '<=', self.date_to)],
                'view_id': self.env.ref('l10n_lt_payroll.hr_employee_payment_tree').id,
                'context': {
                    'search_default_partner_id': self.employee_id.address_home_id.id,
                    'search_default_not_done': 1,
                }
            }

    @api.multi
    @api.depends('date_to', 'date_from', 'employee_id')
    def _compute_planned_periodic_payments_exist(self):
        HrEmployeeBonusPeriodic = self.env['hr.employee.bonus.periodic']
        for rec in self:
            contract_ends = bool(rec.contract_id.date_end) and rec.contract_id.date_end < rec.date_to
            exists = False
            if contract_ends:
                planned_bonuses = HrEmployeeBonusPeriodic.search_count([
                    ('employee_id', '=', rec.employee_id.id),
                    ('date', '>', rec.contract_id.date_end),
                    '|',
                    ('date_stop', '=', False),
                    ('date_stop', '>=', rec.contract_id.date_end)
                ])
                exists = bool(planned_bonuses)
            rec.planned_periodic_payments_exist = exists

    @api.multi
    @api.depends('date_to', 'date_from', 'employee_id', 'contract_id.date_end')
    def _compute_planned_periodic_deductions_exist(self):
        HrEmployeeDeductionPeriodic = self.env['hr.employee.deduction.periodic']
        for rec in self:
            contract_ends = bool(rec.contract_id.date_end) and rec.contract_id.date_end < rec.date_to
            exists = False
            if contract_ends:
                planned_deductions = HrEmployeeDeductionPeriodic.search_count([
                    ('employee_id', '=', rec.employee_id.id),
                    ('state', '=', 'confirm'),
                    ('date', '>', rec.contract_id.date_end),
                    ('date', '<=', rec.date_to)
                ])
                exists = bool(planned_deductions)
            rec.planned_periodic_deductions_exist = exists

    @api.multi
    def open_planned_periodic_payments(self):
        self.ensure_one()
        if self.env.user.is_accountant() and self.contract_id.date_end:
            return {
                'id': self.env.ref('l10n_lt_payroll.action_periodic_bonus').id,
                'name': _('Periodinės premijos darbuotojui %s (%s-%s)') % (self.employee_id.name, self.date_from, self.date_to),
                'view_type': 'form',
                'view_mode': 'tree, form',
                'views': [(False, 'tree'), (False, 'form')],
                'res_model': 'hr.employee.bonus.periodic',
                'type': 'ir.actions.act_window',
                'target': 'self',
                'domain': [
                    ('date', '>', self.contract_id.date_end),
                    ('employee_id', '=', self.employee_id.id),
                    '|',
                    ('date_stop', '=', False),
                    ('date_stop', '>', self.contract_id.date_end)
                ],
                'view_id': self.env.ref('l10n_lt_payroll.periodic_bonus_tree').id,
            }

    @api.multi
    def open_planned_periodic_deductions(self):
        self.ensure_one()
        if self.env.user.is_accountant() and self.contract_id.date_end:
            return {
                'id': self.env.ref('l10n_lt_payroll.action_open_periodic_deduction').id,
                'name': _('Periodinės išskaitos %s-%s') % (self.date_from, self.date_to),
                'view_type': 'form',
                'view_mode': 'tree, form',
                'views': [(False, 'tree'), (False, 'form')],
                'res_model': 'hr.employee.deduction.periodic',
                'type': 'ir.actions.act_window',
                'target': 'self',
                'domain': [
                    ('date', '>', self.contract_id.date_end),
                    ('date', '<=', self.date_to),
                    ('state', '=', 'confirm')
                ],
                'view_id': self.env.ref('l10n_lt_payroll.periodic_deduction_tree_view').id,
                'context': {
                    'search_default_employee_id': self.employee_id.id
                }
            }

    @api.model
    def get_salary_work_time_codes(self):
        regular_codes = set(PAYROLL_CODES['NORMAL'] + PAYROLL_CODES['OUT_OF_OFFICE'])
        regular_codes -= set(PAYROLL_CODES['OTHER_PAID'])
        return {
            'normal': list(regular_codes),
            'extra': PAYROLL_CODES['ALL_EXTRA'] + PAYROLL_CODES['OTHER_SPECIAL'],
        }

    @api.model
    def form_payslip_local_dict(self, localdict):  # Robo overriden addons
        salary_work_time_code_data = self.get_salary_work_time_codes()
        NORMAL_WORK_TIME_CODES = salary_work_time_code_data.get('normal', {})
        EXTRA_WORK_TIME_CODES = salary_work_time_code_data.get('extra', {})
        company = self.env.user.company_id
        zymejimai = self.env['tabelio.zymejimas'].search([])
        localdict.update({zymejimas.code + '_coefficient': 1.0 for zymejimas in zymejimai})
        localdict['BI_coefficient'] = 1.0
        for key in koeficientai:
            full_coef = getattr(company, key.lower() + '_coefficient')
            localdict[key + '_coefficient'] = full_coef
        if localdict is None:
            return localdict
        employee_id = localdict['payslip'].employee_id
        number_of_days, number_of_hours = self.env['hr.salary.rule'].get_all_workdays(localdict['payslip'])
        localdict['number_of_days'] = number_of_days
        localdict['number_of_hours'] = number_of_hours
        payslip_id = localdict['payslip'].id
        payslip = self.browse(payslip_id)
        employee = payslip.employee_id
        err_msg = _('Nepavyko gauti sisteminio grafiko darbuotojui %s, %s datai') % (employee.name, payslip.date_from)
        # we use same localdict for multiple rules so we have to delete previously computed content
        for key in localdict.keys():
            if 'base_amount_' in key:
                localdict.pop(key)

        partial_downtime_exists = self.env['hr.employee.downtime'].search_count([
            ('date_from_date_format', '<=', payslip.date_to),
            ('date_to_date_format', '>=', payslip.date_from),
            ('employee_id', '=', employee.id),
            ('holiday_id.state', '=', 'validate'),
            ('downtime_type', '!=', 'full')
        ])

        regular_work_lines = payslip.worked_days_line_ids.filtered(lambda l: str(l.code) in NORMAL_WORK_TIME_CODES)
        total_days_worked = sum(regular_work_lines.mapped('number_of_days'))
        total_hours_worked = sum(regular_work_lines.mapped('number_of_hours'))
        total_amount = 0.0
        shorter_before_holidays_lines = payslip.worked_days_line_ids.filtered(
            lambda l: l.compensated_time_before_holidays
        )
        shorter_before_holidays_amount = sum(shorter_before_holidays_lines.mapped('number_of_hours'))
        shorter_before_holidays_days = sum(shorter_before_holidays_lines.mapped('number_of_days'))
        for worked_day_line in payslip.worked_days_line_ids:
            appointment = worked_day_line.appointment_id
            if worked_day_line.code in EXTRA_WORK_TIME_CODES and appointment and not appointment.paid_overtime:
                continue
            if appointment.struct_id.code == 'MEN':
                zero_days = float_is_zero(worked_day_line.number_of_days, precision_digits=2)
                zero_hours = float_is_zero(worked_day_line.number_of_hours, precision_digits=2)
                use_hours = appointment.use_hours_for_wage_calculations or partial_downtime_exists or \
                            any(special_code in payslip.worked_days_line_ids.mapped('code') for special_code in ['MP', 'V', 'NLL'])
                num_regular_days = appointment.with_context(date=payslip.date_from, maximum=True).num_regular_work_days
                num_regular_days += shorter_before_holidays_days
                num_regular_hours = appointment.with_context(date=payslip.date_from,
                                                             maximum=True).num_regular_work_hours + shorter_before_holidays_amount
                if (zero_days and not zero_hours) or (
                        not zero_days and not zero_hours and str(worked_day_line.code) in set(NORMAL_WORK_TIME_CODES) - {'FD'}) or use_hours:
                    if not num_regular_hours:
                        raise exceptions.UserError(err_msg)
                    amount = appointment.wage * worked_day_line.number_of_hours / num_regular_hours  # P3:DivOK
                else:
                    if not num_regular_days:
                        raise exceptions.UserError(err_msg)
                    amount = appointment.wage * worked_day_line.number_of_days / num_regular_days  # P3:DivOK
            else:
                amount = appointment.wage * round(worked_day_line.number_of_hours, 2)
            amount = float(amount) if str(worked_day_line.code) in NORMAL_WORK_TIME_CODES else 0.0
            total_amount += amount
            dict_el_name = 'base_amount_' + worked_day_line.code if worked_day_line.code != 'BĮ' else 'base_amount_BI'
            localdict[dict_el_name] = localdict[dict_el_name] + amount if dict_el_name in localdict else amount

        # Bonuses
        # P3:DivOK
        total_amount += sum(l.amount for l in payslip.input_line_ids if l.code in ['PD'])  # Ordinary
        total_amount += sum(l.amount / 3.0 for l in payslip.input_line_ids if l.code == 'PR')  # Quarterly
        total_amount += sum(l.amount / 12.0 for l in payslip.input_line_ids if l.code == 'PRI')  # Long term

        # P3:DivOK
        factual_work_time = max(total_hours_worked - shorter_before_holidays_amount, 0.0)
        localdict['vdu_h'] = total_amount / factual_work_time if \
            tools.float_compare(factual_work_time, 0.0, precision_digits=2) > 0 else 0.0
        localdict['vdu_d'] = total_amount / total_days_worked if total_days_worked > 0 else 0.0

        insurable_period_days = 0.0
        for appointment in payslip.mapped('worked_days_line_ids.appointment_id'):
            insurable_period_days += self.env['ziniarastis.period.line'].num_days_by_accounting_month(
                max(payslip.date_from, appointment.date_start),
                min(payslip.date_to, appointment.date_end or payslip.date_to),
                appointment.contract_id
            )
        localdict['insurable_period_days'] = insurable_period_days

        for code in zymejimai.mapped('code'):
            code = 'BI' if code == 'BĮ' else code
            dict_el_name = 'base_amount_' + code
            if dict_el_name not in localdict:
                localdict[dict_el_name] = 0.0
        # in case we need to calculate new vdu in rules
        date_from = localdict['payslip'].date_from
        date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_vdu_to = (date_from_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_vdu_from = (date_from_dt + relativedelta(months=-2, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_premijos_from = (date_from_dt + relativedelta(months=-12, day=1)).strftime(
            tools.DEFAULT_SERVER_DATE_FORMAT)
        vdu_records = self.env['employee.vdu'].search([('employee_id', '=', employee_id),
                                                       ('date_from', '>=', date_vdu_from),
                                                       ('date_from', '<', date_vdu_to)])
        if payslip.contract_id:
            related_contracts = payslip.contract_id.get_contracts_related_to_work_relation()
            vdu_records = vdu_records.filtered(lambda r: not r.contract_id or r.contract_id.id in related_contracts.ids)
        num_days_worked = sum(vdu_rec.time_worked for vdu_rec in vdu_records)
        total_amount = sum(vdu_records.mapped(lambda r: r.time_worked * r.vdu))
        payslips = self.env['hr.payslip'].search([('employee_id', '=', employee_id),
                                                  ('date_from', '>=', date_vdu_from),
                                                  ('date_from', '<', date_vdu_to),
                                                  ('state', '=', 'done')
                                                  ])
        ketvirtines_pr = self.env['hr.payslip.line'].search([('slip_id', 'in', payslips.ids),
                                                             ('code', '=', 'PR'),
                                                             ('amount', '>', 0)])
        ketvirtines_pr = ketvirtines_pr.sorted(lambda r: r.slip_id.date_from, reverse=True)
        if ketvirtines_pr:
            kv = ketvirtines_pr[0]
            ketvirtine_amount = kv.amount
            if kv.slip_id.date_from < '2019-01-01' <= date_from:
                ketvirtine_amount *= 1.289
        else:
            ketvirtine_amount = 0.0

        payslips = self.env['hr.payslip'].search([('employee_id', '=', employee_id),
                                                  ('date_from', '>=', date_premijos_from),
                                                  ('date_from', '<', date_vdu_to),
                                                  ('state', '=', 'done')])
        ilgesnes_premijos = self.env['hr.payslip.line'].search([('slip_id', 'in', payslips.ids),
                                                                ('code', '=', 'PRI'),
                                                                ('amount', '>', 0)])
        amt = sum(bonus.amount * 1.289 if bonus.slip_id.date_from < '2019-01-01' <= date_from else bonus.amount
                  for bonus in ilgesnes_premijos)
        ilgesniu_premiju_suma = amt / 4.0  # P3:DivOK
        total_amount += ilgesniu_premiju_suma
        localdict['num_days_worked_prev_two_months'] = num_days_worked
        localdict['amount_prev_two_months'] = total_amount
        localdict['amount_ketvirtine'] = ketvirtine_amount

        localdict.update(payslip.get_npd_values())
        npd_date = localdict.get('npd_date')
        localdict.update(payslip.get_applicable_tax_rates(npd_date))
        localdict.update(payslip.get_disability_npd(npd_date))
        localdict.update(payslip.get_npd_used_and_gpm_paid())

        localdict['adjusted_holiday_balance'] = payslip._get_adjusted_holiday_balance()
        localdict['use_holiday_accumulation_records'] = payslip.holiday_accumulation_usage_policy
        return localdict

    @api.multi
    def get_npd_values(self):
        self.ensure_one()
        npd_date = self.npd_used
        if npd_date == 'auto':
            if self.employee_is_being_laid_off:
                npd_date = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            else:
                salary_payment_day = self.company_id.salary_payment_day
                date_to_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
                npd_date_dt = date_to_dt + relativedelta(months=1, day=salary_payment_day)
                npd_date = npd_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        res = {'npd_date': npd_date, 'force_npd': False}
        return res

    @api.multi
    def get_applicable_tax_rates(self, npd_date=None):
        self.ensure_one()
        calculation_date = self.date_to
        if not npd_date:
            npd_date = calculation_date
        contract = self.contract_id
        regular_fields = ['darbuotojo_pensijos_proc', 'darbuotojo_sveikatos_proc', 'darbdavio_sodra_proc',
                          'sodra_papild_proc', 'gpm_proc', 'gpm_ligos_proc', 'mma', 'mma_first_day_of_year']
        res = contract.with_context(date=calculation_date).get_payroll_tax_rates(fields_to_get=regular_fields)
        npd_fields = ['npd_max', 'npd_koeficientas', 'average_wage', 'under_avg_wage_npd_coefficient',
                      'under_avg_wage_npd_max', 'under_avg_wage_minimum_wage_for_npd', 'above_avg_wage_npd_coefficient',
                      'above_avg_wage_npd_max', 'above_avg_wage_minimum_wage_for_npd' ]
        res.update(contract.with_context(date=npd_date).get_payroll_tax_rates(fields_to_get=npd_fields))
        zero_npd_periods = self.env['zero.npd.period'].search_count([
            ('date_start', '<=', self.date_to),
            ('date_end', '>=', self.date_from)
        ])
        res['enforce_zero_npd'] = zero_npd_periods > 0
        return res

    @api.multi
    def get_disability_npd(self, date=None):
        self.ensure_one()
        if not date:
            date = self.date_to
        employee = self.employee_id
        return {
            'invalidumo_npd': employee.with_context(date=date).darbingumas.npd
            if employee.with_context(date=date).appointment_id.invalidumas else 0.0
        }

    @api.multi
    def get_npd_used_and_gpm_paid(self):
        self.ensure_one()
        payment_lines = self.payment_line_ids
        res = {'npd_already_used': sum(payment_lines.mapped('amount_npd'))}
        gpm_already_paid = 0.0
        for payment_line in payment_lines:
            holidays = payment_line.payment_id.holidays_ids
            if holidays:
                # TODO is this the way to do it? holidays_ids - o2m. Can a payment have multiple holidays?
                holiday = holidays[0]
                if holiday.ismokejimas == 'before_hand' and holiday.gpm_paid:
                    gpm_already_paid += payment_line.amount_gpm
        res['gpm_already_paid'] = gpm_already_paid
        return res

    @api.multi
    @api.constrains('contract_id', 'date_from', 'date_to')
    def _check_single_payslip_for_period(self):
        for rec in self:
            if rec.contract_id and rec.date_from and rec.date_to:
                payslips = self.env['hr.payslip'].search_count([
                    ('date_from', '=', rec.date_from),
                    ('date_to', '=', rec.date_to),
                    ('contract_id', '=', rec.contract_id.id),
                    ('id', '!=', rec.id)
                ])
                if payslips:
                    raise exceptions.ValidationError(
                        _('Negali egzistuoti daugiau nei vienas algalapis vienam darbuotojui vienam periodui')
                    )

    @api.multi
    def _compute_details_by_salary_rule_category(self):
        for payslip in self:
            payslip.details_by_salary_rule_category = self.env['hr.payslip.line'].search([('slip_id', '=', payslip.id)]).filtered(lambda line: line.category_id)

    @api.model
    def recalc_a_klase_payslip(self):
        a_klase_kodas_id = self.env.ref('l10n_lt_payroll.a_klase_kodas_1').id
        account_id = self.env['account.account'].search([('code', '=', '4480')], limit=1).id
        for payslip in self.search([]):
            for aml in payslip.move_id.line_ids:
                if aml.partner_id == payslip.employee_id.address_home_id and aml.account_id.id == account_id and not aml.a_klase_kodas_id:
                    aml.a_klase_kodas_id = a_klase_kodas_id

    @api.one
    def _set_use_favourable_sdd(self):
        employee = self.employee_id
        use_favourable = False
        if employee.use_favourable_sdd:
            use_favourable = True
        elif employee.pensionner:
            use_favourable = True
        elif employee.invalidumas:
            use_favourable = True
        elif employee.with_context(date=self.date_to).age < 24:
            use_favourable = True
        else:
            codes = self.worked_days_line_ids.mapped('code') or \
                    self.ziniarastis_period_line_id.mapped('ziniarastis_day_ids.ziniarastis_day_lines.code')
            if any(code in ['G', 'PV', 'KT'] for code in codes):
                use_favourable = True
        self.use_favourable_sdd = use_favourable

    @api.one
    def _set_date_computation(self):
        if not self.date_computation:
            self.date_computation = self.date_to

    # @api.multi
    # def calculate_actual_npd(self):
    #     for rec in self.filtered(lambda r: r.imported):
    #         bruto = sum(rec.line_ids.filtered(lambda r: r.code in ['MEN', 'VAL']).mapped('total'))- sum(rec.line_ids.filtered(lambda r: r.code in ['AM']).mapped('total'))  # todo?
    #         gpm = sum(rec.line_ids.filtered(lambda r: r.code in ['GPM']).mapped('total'))
    #         rate = rec.with_context(date=rec.date_to).contract_id.get_payroll_tax_rates(['gpm_proc'])['gpm_proc'] / 100.0
    #         if rate > 0:
    #             npd = bruto - float(gpm) / rate
    #         else:
    #             npd = 0.0
    #         npd_rule = self.env.ref('l10n_lt_payroll.hr_payroll_rules_eff_npd', raise_if_not_found=False)
    #         if not npd_rule:
    #             return
    #         rec.line_ids.filtered(lambda r: r.code == 'PRTNPD').unlink()
    #         self.env['hr.payslip.line'].create({'slip_id': rec.id,
    #                                             'salary_rule_id': npd_rule.id,
    #                                             'employee_id': rec.employee_id.id,
    #                                             'contract_id': rec.contract_id.id,
    #                                             'amount': npd,
    #                                             'code': npd_rule.code,
    #                                             'name': npd_rule.name,
    #                                             'category_id': npd_rule.category_id.id,
    #                                             })

    @api.multi
    def calculate_theoretical_npd(self):
        for rec in self.filtered(lambda r: r.imported):
            bruto = sum(rec.line_ids.filtered(lambda r: r.code in ['MEN', 'VAL']).mapped('total')) - \
                    sum(rec.line_ids.filtered(lambda r: r.code in ['AM']).mapped('total'))
            employee = rec.employee_id
            contract = rec.contract_id

            npd_date = rec.get_npd_values()['date']

            payroll_values = self.env['hr.payroll'].sudo().get_payroll_values(
                date=rec.date_to,
                npd_date=npd_date,
                bruto=bruto,
                force_npd=contract.npd if contract.override_taxes and contract.use_npd else None,
                disability=employee.darbingumas.name if employee.invalidumas else False,
                is_foreign_resident=employee.is_non_resident,
            )
            npd_amount = payroll_values.get('npd', 0.0)

            npd_rule = self.env.ref('l10n_lt_payroll.hr_payroll_rules_min', raise_if_not_found=False)
            if not npd_rule:
                return
            rec.line_ids.filtered(lambda r: r.code == 'NPD').unlink()
            self.env['hr.payslip.line'].create({
                'slip_id': rec.id,
                'salary_rule_id': npd_rule.id,
                'employee_id': employee.id,
                'contract_id': contract.id,
                'amount': npd_amount,
                'code': npd_rule.code,
                'name': npd_rule.name,
                'category_id': npd_rule.category_id.id,
            })

    @api.model
    def calc_npd_import(self):
        payslips = self.env['hr.payslip'].search([('imported', '=', True)])
        payslips.calculate_actual_npd()
        payslips.calculate_theoretical_npd()

    @api.multi
    def update_stored_ziniarastis_values(self):
        self.ensure_one()
        period_line = self.ziniarastis_period_line_id
        if period_line:
            period_line._num_regular_work_days_contract_only()
            period_line._compute_num_regular_work_hours_without_holidays()

    @api.multi
    def compute_sheet(self):
        for rec in self:
            # rec.refresh_holidays()
            rec._atostogu_likutis()
            rec._compute_holiday_balance_by_accumulation_records()
            rec.update_stored_ziniarastis_values()
            rec.payment_line_ids = [(5,)] + rec.get_payslip_payments([rec.contract_id.id], rec.date_from, rec.date_to)
            rec.other_line_ids = rec.get_other_payment_lines_ids()
            isskaitos_ids = self.env['hr.employee.isskaitos'].search([('employee_id', '=', rec.employee_id.id),
                                                                      ('date', '>=', rec.date_from),
                                                                      ('date', '<=', rec.date_to),
                                                                      ('state', '=', 'confirm')]).ids
            rec.isskaitos_ids = [(6, 0, isskaitos_ids)]
        self.env['hr.payslip.line'].search([('slip_id', 'in', self.ids)]).unlink()
        super(HrPayslip, self).compute_sheet()
        # When ismoketi_kompensacija is True, on first compute.generate_vdu, line_ids is empty and vdu computation is
        # wrong if it includes the last month. So, in that case, we force a second computation to have correct VDU
        self.filtered(lambda r: r.ismoketi_kompensacija and r.warn_about_include_current_month).generate_vdu()
        for rec in self:
            rec.calculate_and_add_deductions_with_limited_amount()
        self.env['hr.employee.bonus'].create_bonus_inputs(self.filtered(lambda s: not s.neto_bonuses_added))
        self.write({'neto_bonuses_added': True})
        return super(HrPayslip, self).compute_sheet()

    @api.multi
    def refresh_holidays(self):
        for rec in self:
            holidays = self.env['hr.holidays'].search([('date_from_date_format', '>=', rec.date_from),
                                                       ('date_from_date_format', '<=', rec.date_to),
                                                       ('employee_id', '=', rec.employee_id.id),
                                                       ('type', '=', 'remove'),
                                                       ('holiday_status_id.kodas', '=', 'A'),
                                                       ('state', '=', 'validate'),
                                                       ('ismokejimas', '=', 'du')])
            for hol in holidays:
                vdu_correct = True
                vdu = hol.vdu
                for paym_l in hol.allocated_payment_line_ids:
                    paym_l_vdu = paym_l.vdu
                    if not float_is_zero(vdu - paym_l_vdu, precision_digits=2):
                        vdu_correct = False
                        break
                if not vdu_correct:
                    hol.force_recompute_payments()

    def get_other_payment_lines_ids(self):
        self.ensure_one()
        gpm_account_id = self.env.user.company_id.saskaita_gpm.id
        amls = self.env['account.move.line'].search([('partner_id', '=', self.employee_id.address_home_id.id),  # todo kaip gpm'ą?
                                                     ('a_klase_kodas_id', '!=', False),
                                                     ('date', '<=', self.date_to),
                                                     ('date', '>=', self.date_from)])

        # Find other payslips in the same period and make sure the move lines don't come from those payslips.
        other_payslips_in_period = self.search([
            ('id', '!=', self.id),
            ('date_from', '=', self.date_from),
            ('state', '=', 'done'),
            ('employee_id', '=', self.employee_id.id)
        ])
        amls = amls.filtered(lambda aml: aml.move_id not in other_payslips_in_period.mapped('move_id'))

        res = [(5,)]
        for aml in amls:
            advance = self.env['darbo.avansas'].search([('account_move_id', '=', aml.move_id.id)], limit=1)
            if advance:
                continue
            payment = self.env['hr.employee.payment'].search([('account_move_id', '=', aml.move_id.id)], limit=1)
            if payment.type in ('allowance', 'holidays') or payment.holidays_ids or aml.move_id == self.move_id:
                continue
            if payment:
                amount = payment.amount_bruto
                amount_gpm = payment.amount_gpm
                amount_sdb = payment.amount_sdb
                amount_sdd = payment.amount_sdd
                base_vals = {
                    'name': aml.name,
                    'a_klase_kodas_id': payment.a_klase_kodas_id.id,
                    'payment_id': payment.id,
                }
                if float_compare(amount, 0, precision_digits=2):
                    vals = base_vals.copy()
                    vals.update({
                        'amount': amount,
                        'type': 'priskaitymai'})
                    res.append((0, 0, vals))
                if float_compare(amount_gpm, 0, precision_digits=2):
                    vals = base_vals.copy()
                    vals.update({
                        'amount': amount_gpm,
                        'type': 'gpm'})
                    res.append((0, 0, vals))
                if float_compare(amount_sdb, 0, precision_digits=2):
                    vals = base_vals.copy()
                    vals.update({
                        'amount': amount_sdb,
                        'type': 'sdb'})
                    res.append((0, 0, vals))
                if float_compare(amount_sdd, 0, precision_digits=2):
                    vals = base_vals.copy()
                    vals.update({
                        'amount': amount_sdd,
                        'type': 'sdd'})
                    res.append((0, 0, vals))
            elif self.env['hr.employee.payment'].search([('account_move_ids', 'in', aml.move_id.id)], limit=1):
                continue
            else:
                vals = {
                    'name': aml.name,
                    'amount': aml.balance,
                    'a_klase_kodas_id': aml.a_klase_kodas_id.id,
                    'move_line_id': aml.id,
                    'type': 'priskaitymai',
                }
                res.append((0, 0, vals))
                for aml_gpm in aml.move_id.line_ids.filtered(lambda r: r.account_id.id == gpm_account_id):
                    vals_gpm = {
                        'name': aml_gpm.name,
                        'amount': aml_gpm.balance,
                        'a_klase_kodas_id': aml_gpm.a_klase_kodas_id.id,
                        'move_line_id': aml_gpm.id,
                        'type': 'gpm',
                    }
                    res.append(vals_gpm)
        return res

    @api.one
    def check_sick_leaves_continuation(self):
        date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_from_dt_corrected = date_from_dt - relativedelta(months=1)
        pholidays = self.env['hr.holidays'].search(
            [('date_from', '>=', date_from_dt_corrected.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)),
             ('date_to', '>', self.date_from),
             ('type', '=', 'remove'),
             ('employee_id', '=', self.employee_id.id),
             ('state', '=', 'validate'),
             ('holiday_status_id.kodas', '=', 'L'),
             ('sick_leave_continue', '=', True)])
        for sick_leave in pholidays:
            from_dt = datetime.strptime(sick_leave.date_from, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            orig_to = from_dt - relativedelta(days=1)
            orig_to_strft = orig_to.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            orig_to_strf = orig_to.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            orig_leave = self.env['hr.holidays'].search_count(
                [('date_to', '>=', orig_to_strft),
                 ('date_to', '<=', sick_leave.date_from),
                 ('type', '=', 'remove'),
                 ('employee_id', '=', self.employee_id.id),
                 ('state', '=', 'validate'),
                 ('holiday_status_id.kodas', '=', 'L')])
            if not orig_leave:
                raise exceptions.Warning(_(
                    'Darbuotojo %s nedarbingumas pratęsiamas nuo %s, tačiau nėra kito nedarbingumo pasibaigiančio %s') %
                                         (self.employee_id.name, sick_leave.date_from_date_format, orig_to_strf))

    @api.multi
    def recompute_slip_holidays(self):
        self.ensure_one()
        holidays = self.env['hr.holidays'].search([('employee_id', '=', self.employee_id.id),
                                                   ('date_from_date_format', '<=', self.date_to),
                                                   ('date_to_date_format', '>=', self.date_from),
                                                   ('holiday_status_id.kodas', '=', 'A')])
        if holidays:
            holidays.recalculate_holiday_payment_amounts()
            for payment in holidays.mapped('payment_id').filtered(lambda p: p.state != 'done'):
                payment.atlikti()
            self.compute_sheet()

    @api.multi
    def action_payslip_done(self):
        move_obj = self.env['account.move']
        precision = self.env['decimal.precision'].precision_get('Payroll')

        #Basic Checks
        payslips_without_set_partner = self.filtered(lambda s: not s.employee_id.address_home_id)
        if payslips_without_set_partner:
            empl_list = '\n'.join(payslips_without_set_partner.mapped('employee_id.name'))
            raise exceptions.Warning(_('Šių darbuotojų kortelėse nenurodytas partneris:\n') % empl_list)

        du_a_klase_kodas_id = self.env.ref('l10n_lt_payroll.a_klase_kodas_1').id

        for slip in self:
            slip.check_sick_leaves_continuation()
            if not self._context.get('automatic_payroll', False): # If you're really gonna pass this context, make sure you recompute holidays and recompute sheet manually
                slip.recompute_slip_holidays()
            if slip.move_id:
                continue
            line_ids = []
            debit_sum = 0.0
            credit_sum = 0.0
            date = slip.date_to
            date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
            payment_day = slip.company_id.salary_payment_day
            date_maturity_dt = date_dt + relativedelta(months=1, day=payment_day)
            date_maturity = date_maturity_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if slip.contract_id.date_end and slip.date_from <= slip.contract_id.date_end <= slip.date_to:
                date_payment_to_employee = slip.contract_id.date_end
                date_payment_gpm = slip.date_to
            else:
                date_payment_to_employee = date_maturity
                date_payment_gpm = date_maturity
            name = _('Payslip of %s') % slip.employee_id.name
            move = {
                'narration': name,
                'ref': slip.number,
                'journal_id': slip.journal_id.id,
                'date': date,
            }
            date = datetime.strptime(slip.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            year = str(date.year)
            month = str(date.month)
            if len(month) < 2:
                month = '0' + month
            for line in slip.details_by_salary_rule_category:
                amt = slip.credit_note and -line.total or line.total
                if float_is_zero(amt, precision_digits=precision):
                    continue
                debit_account_id = line.salary_rule_id.get_account_debit_id(slip.employee_id, slip.contract_id)
                credit_account_id = line.salary_rule_id.get_account_credit_id(slip.employee_id, slip.contract_id)
                if line.code == 'M':
                    aml_name = _('Darbo užmokestis už %s m - %s mėnesį') % (year, month)
                else:
                    aml_name = line.name + _(' už %s m - %s mėnesį') % (year, month)

                if debit_account_id:
                    debit_line = (0, 0, {
                        'name': aml_name,
                        'partner_id': line.slip_id.employee_id.address_home_id.id,
                        'account_id': debit_account_id,
                        'journal_id': slip.journal_id.id,
                        'date': date,
                        'debit': amt > 0.0 and amt or 0.0,
                        'credit': amt < 0.0 and -amt or 0.0,
                        'analytic_account_id': line.salary_rule_id.analytic_account_id and
                                               line.salary_rule_id.analytic_account_id.id or False,
                        'tax_line_id': line.salary_rule_id.account_tax_id and
                                       line.salary_rule_id.account_tax_id.id or False,
                    })
                    if line.code in ['SDP', 'GPM', 'SDB']:
                        debit_line[2]['a_klase_kodas_id'] = du_a_klase_kodas_id
                    line_ids.append(debit_line)
                    debit_sum += debit_line[2]['debit'] - debit_line[2]['credit']
                if credit_account_id:
                    credit_line = (0, 0, {
                        'name': aml_name,
                        'partner_id': line._get_partner_id(credit_account=True),
                        'account_id': credit_account_id,
                        'journal_id': slip.journal_id.id,
                        'date': date,
                        'debit': amt < 0.0 and -amt or 0.0,
                        'credit': amt > 0.0 and amt or 0.0,
                        'analytic_account_id': line.salary_rule_id.analytic_account_id and
                                               line.salary_rule_id.analytic_account_id.id or False,
                        'tax_line_id': line.salary_rule_id.account_tax_id and
                                       line.salary_rule_id.account_tax_id.id or False,
                        'date_maturity': date_maturity,
                    })
                    if line.code in ['BRUTON',]:
                        credit_line[2]['a_klase_kodas_id'] = du_a_klase_kodas_id
                    elif line.code in ['PDNM', 'KOMP', 'KKPD']:
                        credit_line[2]['a_klase_kodas_id'] = self.env.ref('l10n_lt_payroll.a_klase_kodas_5').id
                    if line.code == 'GPM':
                        credit_line[2]['date_maturity'] = date_payment_gpm
                    if line.code in ['VAL', 'MEN', 'BRUTON']:
                        credit_line[2]['date_maturity'] = date_payment_to_employee
                    line_ids.append(credit_line)
                    credit_sum += credit_line[2]['credit'] - credit_line[2]['debit']

            if float_compare(credit_sum, debit_sum, precision_digits=precision) != 0:
                raise exceptions.Warning(
                    _('Neteisinga atlyginimo taisyklių konfigūracija. Kreipkitės į sistemos administratorių.'))

            payslip_values = {'date': date, 'paid': True, 'state': 'done'}

            # Create account move
            acc_move = move_obj
            if line_ids:
                move.update({'line_ids': line_ids})
                acc_move = move_obj.create(move)
                payslip_values['move_id'] = acc_move.id

            slip.write(payslip_values)  # Update payslip with values

            if acc_move:
                acc_move.post()
                if self.env.user.company_id.automatic_salary_reconciliation:
                    acc_id = self.env['hr.salary.rule'].search([
                        ('code', '=', 'BRUTON')
                    ], limit=1).get_account_credit_id(slip.employee_id, None)
                    deduction_lines = slip.isskaitos_ids.mapped('move_id.line_ids').filtered(
                        lambda r: r.account_id.id == acc_id
                    )
                    lines_to_reconcile = acc_move.line_ids.filtered(lambda r: r.account_id.id == acc_id)
                    lines_to_reconcile |= deduction_lines
                    lines_to_reconcile.reconcile()
            slip.generate_vdu()
            slip.create_holiday_fix()
            slip.create_employer_benefit_in_kind_tax_move()

    @api.multi
    def create_employer_benefit_in_kind_tax_move(self):
        """
        Creates benefit in kind tax account move when the employer pays taxes.
        """
        self.ensure_one()

        # Check if theres benefit in kind that the employer has to pay tax on
        employer_pays_tax_benefit_in_kind_lines = self.line_ids.filtered(lambda l: l.code == 'NTRD')
        employer_pays_tax_benefit_in_kind_amount = sum(employer_pays_tax_benefit_in_kind_lines.mapped('amount'))
        if tools.float_is_zero(employer_pays_tax_benefit_in_kind_amount, precision_digits=2):
            return

        # Check the current payslip tax amount
        sodra_lines = self.line_ids.filtered(lambda l: l.code in ['EMPLRSDB', 'EMPLRSDP', 'EMPLRSDDMAIN'])
        gpm_lines = self.line_ids.filtered(lambda l: l.code in ['EMPLRGPM'])
        sodra_to_pay = sum(sodra_lines.mapped('total'))
        gpm_to_pay = sum(gpm_lines.mapped('total'))
        if tools.float_compare(sodra_to_pay + gpm_to_pay, 0.0, precision_digits=2) <= 0:
            self.write({'show_benefit_in_kind_employer_pays_taxes_warning': True})
            return

        # Create the move
        partner = self.employee_id.address_home_id
        benefit_in_kind_move = self.env['hr.employee.natura']._create_employer_pays_tax_account_move(
            partner,
            sodra_to_pay,
            gpm_to_pay,
            self.date_to
        )

        related_benefit_in_kind_records = self.env['hr.employee.natura'].search([
            ('employee_id', '=', self.employee_id.id),
            ('date_from', '=', self.date_from),
            ('date_to', '=', self.date_to),
            ('state', '=', 'confirm'),
            ('taxes_paid_by', '=', 'employer')
        ])
        related_benefit_in_kind_records.write({'move_ids': [(4, benefit_in_kind_move.id)]})
        self.write({'employer_benefit_in_kind_tax_move': benefit_in_kind_move.id})

    @api.multi
    def create_holiday_fix(self):
        for payslip in self:
            if payslip.state != 'done':
                continue
            next_contract = False
            contract_id = payslip.contract_id
            contract_end = contract_id.date_end
            if contract_end:
                contract_immediate_start = (datetime.strptime(contract_end, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                max_date_to = (datetime.strptime(payslip.date_to, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                next_contract = self.env['hr.contract'].search([
                    ('employee_id', '=', payslip.contract_id.employee_id.id),
                    ('date_start', '=', contract_immediate_start),
                    ('date_start', '<=', max_date_to)
                ])
            if not next_contract and not payslip.ismoketi_kompensacija:
                continue
            calendar_days_left = 0.0 if payslip.ismoketi_kompensacija else payslip.atostogu_likutis
            if not next_contract:
                date_to_use = min(contract_end or payslip.date_to, payslip.date_to)
                date = datetime.strptime(date_to_use, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)
            else:
                date = datetime.strptime(next_contract.date_start, tools.DEFAULT_SERVER_DATE_FORMAT)

            if payslip.holiday_accumulation_usage_policy and payslip.ismoketi_kompensacija:
                # Adjust the holiday balance by setting a fix of "add" holiday days with the negative holiday balance
                # since it's being paid out
                date_strf = date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                if payslip.employee_id.with_context(date=date_strf).leaves_accumulation_type == 'work_days':
                    accumulation_field = 'work_days_left'
                else:
                    accumulation_field = 'calendar_days_left'
                self.env['hr.holidays.fix'].create({
                    'employee_id': payslip.employee_id.id,
                    'date': date_strf,
                    accumulation_field: -payslip.atostogu_likutis,
                    'type': 'add'
                })
            else:
                # Create a holiday fix of type "set"
                self.env['hr.holidays.fix'].create({
                    'employee_id': payslip.employee_id.id,
                    'date': date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                    'calendar_days_left': calendar_days_left,
                })

    @api.model
    def get_payslip_payments(self, contract_ids, date_from, date_to):   # todo kokie kodai?
        payslip_payment_lines = []
        employee_ids = self.env['hr.contract'].browse(contract_ids).mapped('employee_id.id')  # will always be one
        holiday_payments = self.env['hr.holidays.payment.line'].search([('period_date_from', '<=', date_to),
                                                                        ('period_date_to', '>=', date_from),
                                                                        '|',
                                                                            ('holiday_id.contract_id', 'in', contract_ids),
                                                                            ('holiday_id.contract_id', '=', False),
                                                                        ('holiday_id.employee_id', 'in', employee_ids),
                                                                        ('holiday_id.state', '=', 'validate')
                                                                        ])
        for h_payment in holiday_payments:
            payment = h_payment.holiday_id.payment_id
            if not payment or payment.state == 'cancel':
                amount_paid = amount_npd = amount_gpm = amount_sodra = 0
            else:
                lines = payment.payment_line_ids.filtered(
                    lambda r: r.date_from >= date_from and r.date_to <= date_to)
                amount_paid = sum(l.amount_paid for l in lines)
                amount_npd = sum(l.amount_npd for l in lines)
                amount_gpm = sum(l.amount_gpm for l in lines)
                amount_sodra = sum(l.amount_sodra for l in lines)

            # if not h_payment.recomputed_values_match:
            #     vdu = h_payment.vdu_recomputed
            #     amount_bruto = h_payment.amount_recomputed
            # else:
            vdu = h_payment.holiday_id.vdu
            amount_bruto = h_payment.amount

            vals = {'contract_id': h_payment.holiday_id.contract_id.id,
                    'vdu': vdu,
                    'date_from': h_payment.period_date_from,
                    'date_to': h_payment.period_date_to,
                    'code': h_payment.holiday_id.holiday_status_id.kodas,
                    'amount_bruto': amount_bruto,
                    'payment_id': payment.id,
                    'amount_paid': amount_paid,
                    'amount_npd': amount_npd,
                    'amount_gpm': amount_gpm,
                    'amount_sodra': amount_sodra,
                    }
            payslip_payment_lines.append(vals)
        return payslip_payment_lines

    @api.model
    def get_worked_day_lines(self, contract_ids, date_from, date_to):
        res = []

        ziniarastis_days = self.env['ziniarastis.day'].search([
            ('date', '<=', date_to),
            ('date', '>=', date_from),
            ('contract_id', 'in', contract_ids)
        ])

        special_paid_holidays = self.env['hr.holidays'].search([
            ('contract_id', 'in', contract_ids),
            ('date_from_date_format', '<=', date_to),
            ('date_to_date_format', '>=', date_from),
            ('is_paid_for', '=', True)
        ])

        national_holiday_dates = self.env['sistema.iseigines'].search([
            ('date', '<=', date_to),
            ('date', '>=', date_from)
        ]).mapped('date')

        work_day_data_by_code = defaultdict(
            lambda: {'minutes': 0, 'num_days': 0, 'name': '', 'num_work_days': 0, 'number_of_work_days': 0})

        for ziniarastis_day in ziniarastis_days:
            ziniarastis_day_lines = ziniarastis_day.mapped('ziniarastis_day_lines').filtered(lambda r:
                                                                                             r.worked_time_hours > 0 or
                                                                                             r.worked_time_minutes > 0 or
                                                                                             r.tabelio_zymejimas_id.is_holidays)
            if not ziniarastis_day_lines:
                continue

            day_date = ziniarastis_day.date
            day_date_weekday = datetime.strptime(day_date, tools.DEFAULT_SERVER_DATE_FORMAT).weekday()
            day_contract = ziniarastis_day.contract_id
            date_appointment = day_contract.with_context(date=day_date).appointment_id
            if not date_appointment:
                continue
            is_national_holiday = day_date in national_holiday_dates
            is_weekend = day_date_weekday in [5, 6]

            day_has_special_paid_holiday = special_paid_holidays.filtered(lambda h: h.contract_id == ziniarastis_day.contract_id and
                                                                          h.date_from_date_format <= day_date <= h.date_to_date_format)
            day_special_paid_holiday_codes = day_has_special_paid_holiday.mapped('holiday_status_id.tabelio_zymejimas_id.code')
            day_declared_as_worked_day = False
            for line in ziniarastis_day_lines:
                code = line.code
                if code in ['NT', 'DLS']:
                    code = 'FD'

                six_day_work_week = False
                if date_appointment:
                    six_day_work_week = date_appointment.schedule_template_id.six_day_work_week
                    schedule_template = date_appointment.schedule_template_id
                    is_accumulative_work_time_accounting = schedule_template.template_type == 'sumine'
                else:
                    is_accumulative_work_time_accounting = False

                weekends = [5, 6] if not six_day_work_week else [6]
                is_work_day_by_accounting_calendar = not (day_date_weekday in weekends or is_national_holiday)

                line_has_special_paid_holidays = code in day_special_paid_holiday_codes

                name = line.tabelio_zymejimas_id.name
                key = (code, line_has_special_paid_holidays, date_appointment.id)

                work_day_data_by_code[key]['appointment'] = date_appointment

                if code == 'VD' and (line.ziniarastis_id.not_by_schedule or line.ziniarastis_id.holiday):
                    code = 'VSS'
                    name = 'Viršvalandžiai savaitgaliais ir švenčių dienomis'

                work_day_data_by_code[key]['name'] = name

                is_absence = line.tabelio_zymejimas_id.is_holidays or line.tabelio_zymejimas_id.holiday_status_ids
                worked_time = line.worked_time_hours * 60 + line.worked_time_minutes
                if tools.float_is_zero(worked_time, precision_digits=2) and \
                        (not is_absence or not is_accumulative_work_time_accounting):
                    # Skip calculating number of [work]days if the worked time (minutes) is zero unless the day is an
                    # absence and the employee is working by accumulative work time accounting. In that case the total
                    # amount of days are shown so the calculations continue.
                    continue
                work_day_data_by_code[key]['minutes'] += worked_time
                if not day_declared_as_worked_day:
                    if code == 'FD':
                        work_day_data_by_code[key]['num_days'] += 1
                        day_declared_as_worked_day = True
                    else:
                        relevant_codes = line.ziniarastis_id.ziniarastis_day_lines.filtered(
                            lambda r: r.worked_time_hours or r.worked_time_minutes or r.tabelio_zymejimas_id.is_holidays
                        ).mapped('code')
                        if 'FD' not in relevant_codes and relevant_codes and code == min(relevant_codes):
                            work_day_data_by_code[key]['num_days'] += 1
                            day_declared_as_worked_day = True
                            if code in ['L', 'NA', 'NS', 'N', 'PB'] and is_work_day_by_accounting_calendar:
                                work_day_data_by_code[key]['number_of_work_days'] += 1
        for key, data in iteritems(work_day_data_by_code):
            code = key[0]
            special_paid_for = key[1]

            name = data['name']
            worked_time_minutes = data['minutes']
            number_of_hours = float(worked_time_minutes) / 60.0  # P3:DivOK
            number_of_days = data['num_days']
            number_of_work_days = False
            appointment = data['appointment']
            if code == 'FD':
                number_of_work_days = self.env['ziniarastis.period.line'].with_context(
                    without_holidays=True).num_days_by_accounting_month(
                    max(date_from, appointment.date_start),
                    min(date_to, appointment.date_end or date_to),
                    appointment.contract_id
                )
            elif code in ['L', 'NA', 'NS', 'N', 'PB', 'MA']:
                number_of_work_days = data['number_of_work_days']
            attendances = {
                'name': name,
                'sequence': 1,
                'code': code,
                'number_of_days': number_of_days,
                'number_of_hours': number_of_hours,
                'number_of_work_days': number_of_work_days,
                'contract_id': appointment.contract_id.id,
                'appointment_id': appointment.id,
                'is_paid_for': special_paid_for
            }
            res += [attendances]

        # Find business trips with travel times that need to be compensated
        business_trip_domain = [
            ('contract_id.id', 'in', contract_ids),
            ('date_from_date_format', '<=', date_to),
            ('date_to_date_format', '>=', date_from),
            ('holiday_status_id.tabelio_zymejimas_id.id', '=', self.env.ref('l10n_lt_payroll.tabelio_zymejimas_K').id),
            ('state', '=', 'validate')
        ]
        business_trip_leaves = self.env['hr.holidays'].search_count(business_trip_domain)
        if business_trip_leaves:
            business_trip_doc_template = self.env.ref('e_document.isakymas_del_tarnybines_komandiruotes_template', raise_if_not_found=False)
            if business_trip_doc_template:
                business_trip_leaves = self.env['hr.holidays'].search(business_trip_domain)
                for business_trip_leave in business_trip_leaves:
                    related_orders = self.env['e.document'].search([
                        ('template_id', '=', business_trip_doc_template.id),
                        ('date_from', '=', business_trip_leave.date_from_date_format),
                        ('date_to', '=', business_trip_leave.date_to_date_format),
                        ('state', '=', 'e_signed'),
                        ('cancelled_ids', '=', False)
                    ])
                    order_business_trip_lines = related_orders.mapped('business_trip_employee_line_ids')
                    business_trip_employee_lines = order_business_trip_lines.filtered(
                        lambda l: l.employee_id == business_trip_leave.employee_id and l.journey_has_to_be_compensated
                    )

                    # Create context to skip departure or return journey times to compensate if the business trip
                    # starts or ends in another month
                    journey_time_context = {}
                    if business_trip_leave.date_from_date_format < date_from:
                        journey_time_context['skip_departure_journey'] = True
                    if business_trip_leave.date_to_date_format > date_to:
                        journey_time_context['skip_return_journey'] = True

                    total_hours_to_pay = sum(business_trip_employee_lines.with_context(
                        journey_time_context
                    ).mapped('journey_amount_to_be_compensated'))

                    if not tools.float_is_zero(total_hours_to_pay, precision_digits=2):
                        business_trip_compensation_extra = {
                            'name': 'Apmokamas komandiruotės kelionės laikas',
                            'sequence': 1,
                            'code': 'KS',
                            'number_of_days': 0,
                            'number_of_hours': total_hours_to_pay,
                            'number_of_work_days': 0,
                            'contract_id': business_trip_leave.contract_id.id,
                            'appointment_id': business_trip_leave.contract_id.with_context(date=business_trip_leave.date_from_date_format).appointment_id.id
                        }
                        res += [business_trip_compensation_extra]
        return res

    @api.model
    def _get_advance_payment_inputs(self, date_from, date_to, contracts):
        advances = self.env['darbo.avansas'].search([
            ('date_from', '>=', date_from),
            ('date_to', '<=', date_to),
            ('employee_id', 'in', contracts.mapped('employee_id').ids),
            ('contract_id', 'in', contracts.ids),
            ('included_in_payslip', '=', True),
            ('state', '=', 'done')
        ])
        advance_inputs = dict()
        for contract in contracts:
            advances_for_contract = advances.filtered(lambda advance: advance.contract_id == contract)
            advance_amount = sum(advances_for_contract.mapped('algalapio_suma'))
            if tools.float_compare(advance_amount, 0.0, precision_digits=2) > 0:
                advance_inputs[contract.id] = {
                    'name': _('Darbo užmokesčio avansas'),
                    'code': 'AVN',
                    'contract_id': contract.id,
                    'amount': advance_amount,
                }
        return advance_inputs

    @api.model
    def _get_business_trip_payment_inputs(self, date_from, date_to, contracts):
        business_trips = self.env['hr.holidays'].search([
            ('employee_id', 'in', contracts.mapped('employee_id').ids),
            ('contract_id', 'in', contracts.ids),
            ('state', '=', 'validate'),
            ('holiday_status_id.kodas', '=', 'K'),
            ('date_from_date_format', '>=', date_from),
            ('date_from_date_format', '<=', date_to)
        ])

        ziniarastis_period_lines = self.env['ziniarastis.period.line'].search([
            ('contract_id', 'in', contracts.ids),
            ('date_from', '=', date_from),
            ('date_to', '=', date_to)
        ], limit=1)

        country_allowance_lt = self.env.ref('l10n_lt_payroll.country_allowance_lt')

        business_trip_inputs = dict()

        for contract in contracts:
            contract_business_trip_inputs = list()

            contract_business_trips = business_trips.filtered(lambda trip: trip.contract_id == contract)
            contract_ziniarastis_period_line = ziniarastis_period_lines.filtered(
                lambda line: line.contract_id == contract
            )

            appointment = contract.with_context(date=date_to).appointment_id
            monthly_wage = appointment.wage
            if appointment.struct_id.code == 'VAL':
                regular_hours = contract_ziniarastis_period_line.with_context(
                    dont_shorten_before_holidays=True).num_regular_work_hours
                monthly_wage = appointment.wage * regular_hours
            wage_cutoff = monthly_wage * 0.5

            business_trips_in_lt = contract_business_trips.filtered(
                lambda x, country_allowance=country_allowance_lt: x.country_allowance_id == country_allowance)
            other_business_trips = contract_business_trips.filtered(
                lambda x, country_allowance=country_allowance_lt: x.country_allowance_id != country_allowance)
            total_allowance = 0.0
            total_taxable_allowance = 0.0
            if business_trips_in_lt:
                allowance = sum(x.amount_business_trip for x in business_trips_in_lt)
                norm = sum(x.allowance_norm for x in business_trips_in_lt)
                business_trip_taxable_amount = 0.0

                if float_compare(allowance, wage_cutoff, precision_digits=2) > 0:
                    business_trip_taxable_amount = allowance - wage_cutoff
                elif float_compare(allowance, norm, precision_digits=2) > 0:
                    business_trip_taxable_amount = allowance - norm

                total_taxable_allowance += max(business_trip_taxable_amount, 0.0)
                total_allowance += allowance

            if other_business_trips:
                allowance = sum(x.amount_business_trip for x in other_business_trips)
                norm = sum(x.allowance_norm for x in other_business_trips)
                contract = contract.with_context(date=date_to)
                tax_rate_code = 'mma' if contract.struct_id.code == 'MEN' else 'min_hourly_rate'
                minimum_wage = contract.get_payroll_tax_rates([tax_rate_code])[tax_rate_code]
                cutoff_coefficient = 1.3 if date_to < '2020-01-01' else 1.65
                cutoff = minimum_wage * cutoff_coefficient

                business_trip_taxable_amount = 0.0
                if float_compare(appointment.wage, cutoff, precision_digits=2) > 0:
                    business_trip_taxable_amount = allowance - norm
                elif float_compare(allowance, wage_cutoff, precision_digits=2) > 0:
                    business_trip_taxable_amount = allowance - wage_cutoff

                total_taxable_allowance += max(business_trip_taxable_amount, 0.0)
                total_allowance += allowance

            nontaxable_allowance = total_allowance - total_taxable_allowance

            if not tools.float_is_zero(total_allowance, precision_digits=2):
                contract_business_trip_inputs.append({
                    'name': _('Dienpinigiai'),
                    'code': 'KM',
                    'contract_id': contract.id,
                    'amount': total_allowance,
                })
            if not tools.float_is_zero(nontaxable_allowance, precision_digits=2):
                contract_business_trip_inputs.append({
                    'name': _('Neapmokestinami Dienpinigiai'),
                    'code': 'NAKM',
                    'contract_id': contract.id,
                    'amount': nontaxable_allowance,
                })

            business_trip_inputs[contract.id] = contract_business_trip_inputs
        return business_trip_inputs

    @api.model
    def _get_deduction_inputs(self, date_from, date_to, contracts):
        employees = contracts.mapped('employee_id')

        deductions = self.env['hr.employee.isskaitos'].search([
            ('employee_id', 'in', employees.ids),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('state', '=', 'confirm'),
            ('limit_deduction_amount', '=', False),
        ])

        deduction_inputs = dict()

        for contract in contracts:
            employee = contract.employee_id
            employee_contracts = contracts.filtered(lambda contract: contract.employee_id == employee)
            if any(employee_contract.id in deduction_inputs for employee_contract in employee_contracts):
                continue  # hr.employee.isskaitos only has employee so we should only add once per employee

            date_from_intersection = max(contract.date_start, date_from)
            date_to_intersection = min(contract.date_end or date_to, date_to)
            employee_deductions = deductions.filtered(
                lambda deduction: deduction.employee_id == employee and
                                  date_from_intersection <= deduction.date <= date_to_intersection
            )
            deduction_amount = sum(employee_deductions.mapped('amount'))
            if tools.float_compare(deduction_amount, 0.0, precision_digits=2) > 0:
                deduction_inputs[contract.id] = {
                    'name': _('Išskaitos'),
                    'code': 'ISSK',
                    'contract_id': contract.id,
                    'amount': deduction_amount,
                }

        return deduction_inputs

    @api.model
    def _get_benefit_in_kind_inputs(self, date_from, date_to, contracts):
        employees = contracts.mapped('employee_id')

        pay_in_kind_records = self.env['hr.employee.natura'].search([
            ('employee_id', 'in', employees.ids),
            ('date_from', '=', date_from),
            ('date_to', '=', date_to),
            ('state', '=', 'confirm')
        ])

        benefit_in_kind_inputs = dict()

        for contract in contracts:
            employee = contract.employee_id
            employee_contracts = contracts.filtered(lambda contract: contract.employee_id == employee)
            if any(employee_contract.id in benefit_in_kind_inputs for employee_contract in employee_contracts):
                continue  # hr.employee.natura only has employee so we should only add once per employee

            contract_benefit_in_kind_inputs = list()
            employee_benefit_in_kind_inputs = pay_in_kind_records.filtered(lambda rec: rec.employee_id == employee)
            taxes_paid_by_employee_benefit_in_kind_amount = sum(employee_benefit_in_kind_inputs.filtered(
                lambda r: r.taxes_paid_by == 'employee'
            ).mapped('amount'))
            if tools.float_compare(taxes_paid_by_employee_benefit_in_kind_amount, 0.0, precision_digits=2) > 0:
                contract_benefit_in_kind_inputs.append({
                    'name': _('Natūra'),
                    'code': 'NTR',
                    'contract_id': contract.id,
                    'amount': taxes_paid_by_employee_benefit_in_kind_amount,
                })
            taxes_paid_by_employer_benefit_in_kind_amount = sum(employee_benefit_in_kind_inputs.filtered(
                lambda r: r.taxes_paid_by == 'employer'
            ).mapped('amount'))
            if tools.float_compare(taxes_paid_by_employer_benefit_in_kind_amount, 0.0, precision_digits=2) > 0:
                contract_benefit_in_kind_inputs.append({
                    'name': _('Natūra (mokesčius moka darbdavys)'),
                    'code': 'NTRD',
                    'contract_id': contract.id,
                    'amount': taxes_paid_by_employer_benefit_in_kind_amount,
                })

            benefit_in_kind_inputs[contract.id] = contract_benefit_in_kind_inputs

        return benefit_in_kind_inputs

    @api.model
    def _get_study_leave_inputs(self, date_from, date_to, contracts):
        employees = contracts.mapped('employee_id')
        holiday_status_id = self.env.ref('hr_holidays.holiday_status_MA').id

        holidays = self.env['hr.holidays'].search([
            ('date_from_date_format', '<=', date_to),
            ('date_to_date_format', '>=', date_from),
            ('employee_id', 'in', employees.ids),
            ('holiday_status_id', '=', holiday_status_id),
            ('state', '=', 'validate'),
            ('type', '=', 'remove'),
        ])

        amounts_by_contract = defaultdict(lambda: 0.0)

        for holiday in holidays:
            # skip if the holiday is unpaid
            if not holiday.is_paid_for:
                continue
            date_from_intersection = max(holiday.date_from_date_format, date_from)
            date_to_intersection = min(holiday.date_to_date_format, date_to)
            contract = holiday.contract_id
            appointments = contract.appointment_ids.filtered(lambda a:
                                                             a.date_start <= date_to_intersection and
                                                             (not a.date_end or a.date_end >= date_from_intersection)
                                                             )
            use_calendar_days = any(app.leaves_accumulation_type == 'calendar_days' for app in appointments)

            if use_calendar_days:
                leaves_context = {
                    'force_use_schedule_template': True, 'do_not_use_ziniarastis': True,
                    'calculating_holidays': True
                }
            else:
                leaves_context = {'calculating_preliminary_holiday_duration': True}

            num_days = holiday.contract_id.with_context(leaves_context).get_num_work_days(
                date_from_intersection,
                date_to_intersection,
            )

            if holiday.holiday_payment in ['paid_at_vdu', 'paid_half_of_vdu']:
                if not num_days or num_days == 0:
                    continue

                include_last = False
                work_relation_end_date = holiday.contract_id.work_relation_end_date
                ends_on_the_last_work_day_of_month = holiday.contract_id.ends_on_the_last_work_day_of_month
                if work_relation_end_date and ends_on_the_last_work_day_of_month:
                    work_relation_end_date_dt = datetime.strptime(work_relation_end_date,
                                                                  tools.DEFAULT_SERVER_DATE_FORMAT)
                    date_to_dt = datetime.strptime(date_to_intersection, tools.DEFAULT_SERVER_DATE_FORMAT)
                    if work_relation_end_date_dt.year == date_to_dt.year and \
                            work_relation_end_date_dt.month == date_to_dt.month:
                        include_last = True

                vdu = get_vdu(self.env, date_from_intersection, holiday.employee_id, contract_id=holiday.contract_id.id,
                              include_last=include_last, vdu_type='d').get('vdu', 0.0)
                amount = num_days * vdu
                if holiday.holiday_payment == 'paid_half_of_vdu':
                    amount /= 2
            else:
                total_holiday_duration = abs(holiday.number_of_days) if use_calendar_days else abs(holiday.darbo_dienos)
                try:
                    amount = num_days / total_holiday_duration * holiday.payment_amount
                except ZeroDivisionError:
                    amount = 0.0

            amounts_by_contract[holiday.contract_id.id] += amount

        study_leave_inputs = dict()
        for contract_id, amount in iteritems(amounts_by_contract):
            study_leave_inputs[contract_id] = {
                'name': _('Mokymosi atostogos'),
                'code': 'MA',
                'contract_id': contract_id,
                'amount': amount,
            }

        return study_leave_inputs

    @api.model
    def get_inputs(self, contract_ids, date_from, date_to):
        res = []
        if len(self) == 1 and self.contract_id:
            contract_ids = self.contract_id.ids
        contracts = self.env['hr.contract'].browse(contract_ids)

        advance_inputs = self._get_advance_payment_inputs(date_from, date_to, contracts)
        business_trip_inputs = self._get_business_trip_payment_inputs(date_from, date_to, contracts)
        study_leave_inputs = self._get_study_leave_inputs(date_from, date_to, contracts)
        deduction_inputs = self._get_deduction_inputs(date_from, date_to, contracts)
        benefit_in_kind_inputs = self._get_benefit_in_kind_inputs(date_from, date_to, contracts)

        for contract in contracts:
            contract_advance_inputs = advance_inputs.get(contract.id, dict())
            if contract_advance_inputs:
                res.append(contract_advance_inputs)

            contract_business_trip_inputs = business_trip_inputs.get(contract.id, list())
            res += contract_business_trip_inputs

            contract_deduction_inputs = deduction_inputs.get(contract.id, dict())
            if contract_deduction_inputs:
                res.append(contract_deduction_inputs)

            contract_benefit_in_kind_inputs = benefit_in_kind_inputs.get(contract.id, list())
            res += contract_benefit_in_kind_inputs

            contract_study_leave_inputs = study_leave_inputs.get(contract.id, dict())
            if contract_study_leave_inputs:
                res.append(contract_study_leave_inputs)

            res += [{
                'code': default_input[0],
                'name': default_input[1],
                'contract_id': contract.id,
            } for default_input in default_inputs]

        res += self.env['hr.employee.compensation'].get_payslip_inputs(contract_ids, date_from, date_to)
        return res

    @api.multi
    def refresh_and_recompute(self):
        if any(rec.state != 'draft' for rec in self):
            raise exceptions.UserError(_('Įrašas jau patvirtintas'))
        self.refresh_inputs()
        self.write({'neto_bonuses_added': False})
        self.compute_sheet()
        for rec in self:
            if rec.contract_id.ends_on_the_last_work_day_of_month and rec.ismoketi_kompensacija:
                # No VDU record exists before computing sheet thus second recompute is needed to get the correct amounts
                rec.compute_sheet()

    @api.multi
    def refresh_inputs(self):
        def merge_input_line_vals(input_vals, saved_vals):
            input_dict = {(str(v['code']), v['contract_id']): v for v in input_vals}
            saved_dict = {(str(v['code']), v['contract_id']): v for v in saved_vals}
            input_dict.update(saved_dict)
            return itervalues(input_dict)

        self.write({'show_benefit_in_kind_employer_pays_taxes_warning': False})

        for rec in self:
            rec._compute_has_negative_holidays()
            rec._compute_has_need_action_holidays()
            rec._compute_unconfirmed_employee_payments_exist()
            contract = rec.contract_id
            employee = rec.employee_id
            manual_input_line_vals = rec.input_line_ids.filtered(lambda l: l.manual).get_input_vals()
            slip_data = self.with_context(contract=True).env['hr.payslip'].onchange_employee_id(rec.date_from, rec.date_to,
                                                                                                employee.id,
                                                                                                contract_id=contract.id)
            input_line_vals = slip_data['value'].get('input_line_ids')
            if manual_input_line_vals:
                input_line_vals = merge_input_line_vals(input_line_vals, manual_input_line_vals)
            vals = {
                'struct_id': slip_data['value'].get('struct_id'),
                'contract_id': slip_data['value'].get('contract_id'),
                'input_line_ids': [(5,)] + [(0, 0, x) for x in input_line_vals],
                'worked_days_line_ids': [(5,)] + [(0, 0, x) for x in slip_data['value'].get('worked_days_line_ids')],
                'payment_line_ids': [(0, 0, x) for x in slip_data['value'].get('payment_line_ids')],
                'credit_note': False,
            }
            rec.write(vals)

    @api.model
    def generate_all_vdus(self):
        self.env['hr.payslip'].search([('state', '=', 'done')]).generate_vdu()

    @api.multi
    def generate_vdu(self):
        values = self.get_vdu_values()
        for rec in self:
            date_dt = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            year_id = self.env['years'].search([('code', '=', date_dt.year)], limit=1).id
            if not year_id:
                raise exceptions.UserError(_('Sistemoje nėra metų %s') % date_dt.year)
            month = date_dt.month
            related_contracts = rec.contract_id.get_contracts_related_to_work_relation()
            vdu_record = self.env['employee.vdu'].search([
                ('employee_id', '=', rec.employee_id.id),
                ('year_id', '=', year_id),
                ('month', '=', month),
                '|',
                ('contract_id', 'in', related_contracts.ids),
                ('contract_id', '=', False)
            ], limit=1)
            if not vdu_record:
                vdu_record = self.env['employee.vdu'].create({'employee_id': rec.employee_id.id,
                                                              'contract_id': rec.contract_id.id,
                                                              'year_id': year_id,
                                                              'month': month,
                                                              'type': 'men',
                                                              })
            vals = values[rec.id]
            vdu_record.write(vals)

    @api.multi
    def get_vdu_values(self):
        res = {}
        EXTRA_WORK_TIME_CODES = PAYROLL_CODES['ALL_EXTRA']
        EXTRA_HOURS = PAYROLL_CODES['ALL_EXTRA'] + PAYROLL_CODES['BUDEJIMAS']
        VDU_CODES = EXTRA_HOURS + PAYROLL_CODES['REGULAR'] + PAYROLL_CODES['OUT_OF_OFFICE']
        for rec in self:
            lines_to_include_in_vdu = rec.worked_days_line_ids.filtered(lambda r: r.code in VDU_CODES and
                                                                                  not r.compensated_time_before_holidays)
            lines_without_paid_overtime_check = rec.worked_days_line_ids.filtered(lambda l: not (l.code in EXTRA_WORK_TIME_CODES
                                                                                      and l.appointment_id and not
                                                                                      l.appointment_id.paid_overtime))
            lines_to_include_in_vdu = lines_to_include_in_vdu.filtered(lambda l: not (l.code in EXTRA_WORK_TIME_CODES
                                                                                      and l.appointment_id and not
                                                                                      l.appointment_id.paid_overtime))

            vdu_lines = lines_to_include_in_vdu
            days_worked = sum(vdu_lines.mapped('number_of_days'))
            hours_worked = sum(vdu_lines.mapped('number_of_hours'))

            extra_hours = sum(lines_without_paid_overtime_check.filtered(lambda r: r.code in EXTRA_HOURS).mapped('number_of_hours'))
            bruto = sum(rec.line_ids.filtered(lambda r: r.code in ['MEN', 'VAL']).mapped('total'))
            bruto += sum(rec.line_ids.filtered(lambda r: r.code in ['NAKM']).mapped('total')) - sum(rec.line_ids.filtered(lambda r: r.code in ['KM']).mapped('total'))
            ne_vdu = sum(rec.line_ids.filtered(lambda r: r.code in ['PR', 'PRI', 'PDN', 'AK', 'A',
                                                                    'L', 'IST', 'NTR', 'T', 'V', 'PNVDU',
                                                                    'KR', 'MA', 'PN', 'KNDDL']).mapped('total'))
            total_pay = bruto - ne_vdu
            force_calculate_in_hours = False
            if 'PN' in rec.line_ids.mapped('code'):
                partial_downtime_exists = self.env['hr.employee.downtime'].search_count([
                    ('date_from_date_format', '<=', rec.date_to),
                    ('date_to_date_format', '>=', rec.date_from),
                    ('employee_id', '=', rec.employee_id.id),
                    ('holiday_id.state', '=', 'validate'),
                    ('downtime_type', '!=', 'full')
                ])
                if partial_downtime_exists:
                    force_calculate_in_hours = True

            if rec.struct_id.code == 'MEN':  # todo premijos, M
                if rec.contract_id.appointment_id.use_hours_for_wage_calculations:
                    vdu = total_pay / hours_worked if hours_worked > 0 else 0  # P3:DivOK
                    vdu_type = 'val'
                else:
                    if float_is_zero(extra_hours, precision_digits=2) and not force_calculate_in_hours:
                        vdu = total_pay / days_worked if days_worked > 0 else 0  # P3:DivOK
                    else:
                        # P3:DivOK
                        vdu = total_pay / hours_worked * rec.contract_id.appointment_id.schedule_template_id.avg_hours_per_day if hours_worked > 0 else 0
                    vdu_type = 'men'
            elif rec.struct_id.code == 'VAL':
                vdu = total_pay / hours_worked if hours_worked > 0 else 0  # P3:DivOK
                vdu_type = 'val'
            else:
                raise exceptions.UserError(_('Nurodyta neteisinga atlyginimo struktūra'))
            res[rec.id] = {'vdu': vdu,
                           'type': vdu_type,
                           'amount': total_pay,
                           'hours_worked': hours_worked,
                           'days_worked': days_worked}
        return res

    @api.multi
    def onchange_employee_id(self, date_from, date_to, employee_id=False, contract_id=False):
        res = super(HrPayslip, self).onchange_employee_id(date_from, date_to, employee_id=employee_id, contract_id=contract_id)
        payment_line_ids = self.get_payslip_payments([contract_id or self.contract_id.id], date_from, date_to)
        res['value'].update({'payment_line_ids': payment_line_ids})
        isskaitos_ids = self.env['hr.employee.isskaitos'].search([('employee_id', '=', employee_id),
                                                                  ('date', '>=', date_from),
                                                                  ('date', '<=', date_to),
                                                                  ('state', '=', 'confirm')]).ids
        res['value'].update({'isskaitos_ids': isskaitos_ids})

        worked_lines = res['value']['worked_days_line_ids']
        schedule_special_hours = self.get_special_hours_from_schedule(res, date_from, date_to)
        contract = self.env['hr.contract'].browse(contract_id)
        if contract and [line for line in res['value']['worked_days_line_ids'] if line['code'] in ['BĮ', 'BN']]:
            days_sum = {}
            hours_sum = {}

            for code, data in iteritems(schedule_special_hours):
                code_lines = [line for line in res['value']['worked_days_line_ids'] if line['code'] == code]
                appointments = [line['appointment_id'] for line in code_lines]
                for appointment in appointments:
                    if not days_sum.get(appointment):
                        days_sum[appointment] = {}
                    if not hours_sum.get(appointment):
                        hours_sum[appointment] = {}
                    appointment_lines = [line for line in code_lines if line['appointment_id'] == appointment]
                    for line in appointment_lines:
                        if not days_sum[appointment].get(code):
                            days_sum[appointment][code] = 0.0
                        if not hours_sum[appointment].get(code):
                            hours_sum[appointment][code] = 0.0
                        days_sum[appointment][code] += line['number_of_days']
                        hours_sum[appointment][code] += line['number_of_hours']

            for code, data in iteritems(schedule_special_hours):
                for app_id, app_data in iteritems(data):
                    app_code_line = [line for line in res['value']['worked_days_line_ids'] if line['code'] == code and line['appointment_id'] == app_id]
                    tabelio_zymejimas = self.env['tabelio.zymejimas'].search([('code', '=', code)], limit=1)
                    if app_code_line:
                        if code in ['SNV', 'DN']:
                            app_code_line[0]['number_of_hours'] = app_data['hours']
                            # app_code_line['number_of_days'] = app_data['days']
                        else:
                            app_code_line[0]['number_of_hours'] += app_data['hours']
                            # app_code_line['number_of_days'] += app_data['days']
                    else:
                        res['value']['worked_days_line_ids'].append({
                            'name': tabelio_zymejimas.name,
                            'appointment_id': app_id,
                            'code': tabelio_zymejimas.code,
                            'contract_id': contract_id,
                            'number_of_days': 0.0,
                            'number_of_hours': app_data.get('hours', 0.0),
                            'sequence': 10
                        })
                        app_code_line = [line for line in res['value']['worked_days_line_ids'] if
                                         line['code'] == code and line['appointment_id'] == app_id]
                    bi_line = [line for line in res['value']['worked_days_line_ids'] if line['code'] == 'BĮ' and line['appointment_id'] == app_id]
                    hours_app = hours_sum.get(app_id, {})
                    hours = hours_app.get(code, 0.0)
                    days_app = days_sum.get(app_id, {})
                    days = days_app.get(code, 0.0)
                    if bi_line:
                        bi_line = bi_line[0]
                        if code in ['SNV', 'DN']:
                            bi_line['number_of_hours'] -= (app_code_line[0]['number_of_hours'] - hours)
                            # bi_line['number_of_days'] -= (app_code_line['number_of_days'] - days)
                        else:
                            bi_line['number_of_hours'] -= app_code_line[0]['number_of_hours']
                            # bi_line['number_of_days'] -= app_code_line['number_of_days']

        contract = self.env['hr.contract'].browse(res['value']['contract_id']) if res['value'] and res['value']['contract_id'] else False
        if date_from and date_to and contract:
            holiday_dates = self.env['sistema.iseigines'].search([('date', '<=', date_to), ('date', '>=', date_from)]).mapped('date')
            shorter_dates = self.env['sistema.iseigines'].get_dates_with_shorter_work_date(date_from, date_to)
            hours_to_pay_for = 0.0
            hours_to_pay_for_on_holidays = 0.0
            additional_days = 0
            additional_days_on_holidays = 0
            for date in shorter_dates:
                date_appointment = contract.with_context(date=date).appointment_id
                if not date_appointment or not date_appointment.schedule_template_id.shorter_before_holidays:
                    continue
                # If a holiday for the date exists (which is not a business trip) we should not compensate the hour for
                # shorter before holidays
                ignore_holiday_ids = [
                    self.env.ref('hr_holidays.holiday_status_K').id,
                    self.env.ref('hr_holidays.holiday_status_MP').id,
                    self.env.ref('hr_holidays.holiday_status_NLL').id,
                    self.env.ref('hr_holidays.holiday_status_SŽ').id,
                    self.env.ref('hr_holidays.holiday_status_KV').id,
                    self.env.ref('hr_holidays.holiday_status_KVN').id,
                    self.env.ref('hr_holidays.holiday_status_D').id,
                ]  # Holidays that does not mean the employee was not working
                date_holidays = self.env['hr.holidays'].search([
                    ('state', '=', 'validate'),
                    ('employee_id', '=', contract.employee_id.id),
                    ('date_from_date_format', '<=', date),
                    ('date_to_date_format', '>=', date),
                    ('holiday_status_id.kodas', '!=', 'K')
                ])
                if date_holidays.filtered(lambda h: h.holiday_status_id.id not in ignore_holiday_ids):
                    continue

                # Find out worked time for date
                ziniarastis_day = self.env['ziniarastis.day'].search([
                    ('contract_id', '=', contract.id),
                    ('date', '=', date)
                ], limit=1)
                ziniarastis_day_lines = ziniarastis_day.mapped('ziniarastis_day_lines')
                worked_time = sum(ziniarastis_day_lines.mapped('worked_time_hours')) + \
                              sum(ziniarastis_day_lines.mapped('worked_time_minutes')) / 60.0  # P3:DivOK

                # Find out how much the person should have worked
                schedule_template = date_appointment.schedule_template_id
                regular_hours = schedule_template.with_context(calculating_before_holidays=True,
                                                               calculating_work_norm=True, maximum=True).get_regular_hours(date)
                if tools.float_is_zero(regular_hours, precision_digits=2) and \
                        schedule_template.template_type in ['fixed', 'suskaidytos']:
                    regular_hours = self.env['hr.employee'].employee_work_norm(
                        calc_date_from=date,
                        calc_date_to=date,
                        contract=date_appointment.contract_id,
                        appointment=date_appointment)['hours']

                should_work_less_than_an_hour = tools.float_compare(regular_hours, 1.0, precision_digits=2) <= 0 < \
                                                tools.float_compare(regular_hours, 0.0, precision_digits=2)

                # Skip if the person did not work and had to work more than an hour (because there might be cases where
                # the employee should have worked for an hour or less but did not work at all but still has to be
                # compensated.
                if tools.float_is_zero(worked_time, precision_digits=2) and not should_work_less_than_an_hour:
                    continue

                # Wage is calculated in days - so we should skip the compensation
                if date_appointment.struct_id.code == 'MEN' and not date_appointment.use_hours_for_wage_calculations \
                        and not date_holidays and not should_work_less_than_an_hour:
                    continue

                to_pay_for = min(regular_hours, 1.0)
                if tools.float_is_zero(to_pay_for, precision_digits=2) and \
                        not tools.float_is_zero(worked_time, precision_digits=2):
                    to_pay_for = 1.0
                if date in holiday_dates:
                    hours_to_pay_for_on_holidays += to_pay_for
                    if should_work_less_than_an_hour:
                        additional_days_on_holidays += 1
                else:
                    hours_to_pay_for += to_pay_for
                    if should_work_less_than_an_hour:
                        additional_days += 1
            appointments = contract.appointment_ids.filtered(lambda a: a.date_start <= date_to)
            if not tools.float_is_zero(hours_to_pay_for, precision_digits=2) and appointments:
                res['value']['worked_days_line_ids'].append({
                    'appointment_id': appointments.sorted(key='date_start', reverse=True)[0].id,
                    'code': 'FD',
                    'contract_id': contract.id,
                    'name': 'Trumpinimas prieš šventes',
                    'number_of_days': additional_days,
                    'number_of_hours': hours_to_pay_for,
                    'number_of_work_days': 1,
                    'sequence': 1,
                    'compensated_time_before_holidays': True,
                })
            if not tools.float_is_zero(hours_to_pay_for_on_holidays, precision_digits=2) and appointments:
                res['value']['worked_days_line_ids'].append({
                    'appointment_id': appointments.sorted(key='date_start', reverse=True)[0].id,
                    'code': 'DP',
                    'contract_id': contract.id,
                    'name': 'Trumpinimas prieš šventes, dirbant švenčių dieną',
                    'number_of_days': additional_days_on_holidays,
                    'number_of_hours': hours_to_pay_for_on_holidays,
                    'number_of_work_days': 1,
                    'sequence': 1,
                    'compensated_time_before_holidays': True,
                })

        if contract and contract.date_end and date_to:
            date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            contract_end_dt = datetime.strptime(contract.date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
            iseitine_month_amount = contract.num_men_iseitine
            pay_iseitine = not tools.float_is_zero(iseitine_month_amount, precision_digits=2)
            contract_ends_same_month_as_payslip = date_to_dt.year == contract_end_dt.year and date_to_dt.month == contract_end_dt.month
            if contract_ends_same_month_as_payslip and pay_iseitine:
                is_hourly_structure = contract.struct_id.code == 'VAL'
                employee_payslips = self.search([('employee_id', '=', contract.employee_id.id)])
                curr_payslip = employee_payslips.filtered(lambda s: s.date_to == date_to and s.contract_id.id == contract.id)

                appointment = contract.with_context(date=contract.date_end).appointment_id
                if not appointment:
                    appointments = contract.mapped('appointment_ids').sorted(key=lambda a: a.date_start, reverse=True)
                    if appointments:
                        appointment = appointments[0]
                    else:
                        appointment = contract.with_context(date=curr_payslip.date_from).appointment_id

                if appointment:
                    year_start = (contract_end_dt+relativedelta(month=1, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    year_end = (contract_end_dt+relativedelta(month=12, day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    yearly_work_norm = self.env['hr.employee'].with_context(maximum=True).employee_work_norm(
                        calc_date_from=year_start,
                        calc_date_to=year_end,
                        contract=contract,
                        appointment=appointment)

                    if is_hourly_structure:
                        work_norm = yearly_work_norm['hours']
                        vdu = curr_payslip.with_context(vdu_type='h', AK=True).vdu_previous
                    else:
                        work_norm = yearly_work_norm['days']
                        vdu = curr_payslip.with_context(vdu_type='d', AK=True).vdu_previous

                    # P3:DivOK
                    avg_per_month = work_norm / 12.0  # 12 Months in a year
                    let_off_amount = avg_per_month * float(iseitine_month_amount) * vdu

                    if is_hourly_structure:
                        iseitine_line_name = _('Išeitinės išmoka ({0}(mėn.) * {1}(val.) * {2}(VDU))').format(
                            round(iseitine_month_amount, 3), round(avg_per_month, 3), round(vdu, 3)
                        )
                    else:
                        iseitine_line_name = _('Išeitinės išmoka ({}(mėn.) * {}(d.) * {}(VDU))').format(
                            round(iseitine_month_amount, 3), round(avg_per_month, 3), round(vdu, 3)
                        )

                    if not tools.float_is_zero(let_off_amount, precision_digits=2):
                        res['value']['input_line_ids'].append({
                            'code': 'IST',
                            'contract_id': contract.id,
                            'name': iseitine_line_name,
                            'amount': let_off_amount
                        })
        return res

    @api.multi
    def get_special_hours_from_schedule(self, res, date_from, date_to):
        return {'BĮ': {}, 'BN': {}}  # Overriden in payroll schedule

    @api.multi
    @api.constrains('employee_id', 'contract_id')
    def constrain_contract_employee(self):
        for rec in self:
            if rec.contract_id.employee_id != rec.employee_id:
                raise exceptions.ValidationError(
                    _('Kontraktas %s nepriklauso darbuotojui %s') % (rec.contract_id.name, rec.employee_id.name)
                )


HrPayslip()


class HrSalaryRule(models.Model):

    _inherit = 'hr.salary.rule'

    account_credit = fields.Many2one(company_dependent=True)
    account_debit = fields.Many2one(company_dependent=True)

    def get_account_debit_id(self, employee, contract):
        res = False
        if self.code in ['BRUTON']:
            res = contract.du_debit_account_id.id or employee.department_id.saskaita_debetas.id or employee.company_id.saskaita_debetas.id
        elif self.code in ['GPM', 'SDB', 'SDP', 'AVN', 'AM']:
            res = employee.department_id.saskaita_kreditas.id or employee.company_id.saskaita_kreditas.id
        elif self.code in ['SDD', 'SDAS']:
            res = employee.department_id.darbdavio_sodra_debit.id or employee.company_id.darbdavio_sodra_debit.id or res
        elif self.code in ['PDNM', 'KOMP', 'KKPD']:
            res = self.account_debit.id
        else:
            return False
        if not res:
            raise exceptions.Warning(
                _('Nenurodyta debetinė sąskaita darbuotojui %s kodui %s') % (employee.name, self.code))
        return res

    def get_account_credit_id(self, employee, contract):
        # if self.code in ['SDD']:
        #     res = employee.department_id.darbdavio_sodra_credit.id or self.env.user.company_id.darbdavio_sodra_credit.id or res
        if self.code in ['SDB', 'SDD', 'SDP']:
            res = contract.sodra_credit_account_id.id or employee.department_id.saskaita_sodra.id \
                  or employee.company_id.saskaita_sodra.id
        elif self.code in ['GPM']:
            res = contract.gpm_credit_account_id.id or employee.department_id.saskaita_gpm.id \
                  or employee.company_id.saskaita_gpm.id
        elif self.code in ['BRUTON']:
            res = employee.department_id.saskaita_kreditas.id or employee.company_id.saskaita_kreditas.id
        elif self.code in ['AM']:
            res = employee.department_id.atostoginiu_kaupiniai_account_id.id or employee.company_id.atostoginiu_kaupiniai_account_id.id
        elif self.code in ['AVN']:
            res = employee.department_id.employee_advance_account.id or employee.company_id.employee_advance_account.id
        elif self.code in ['PDNM', 'KOMP', 'KKPD']:
            res = self.account_credit.id
        else:
            return False
        if not res:
            raise exceptions.Warning(
                _('Nenurodyta kreditinė sąskaita darbuotojui %s kodui %s') % (employee.name, self.code))
        return res

    @api.model
    def get_all_workdays(self, payslip):
        number_of_hours = number_of_days = 0.0
        if payslip.worked_days_line_ids: # If its nothing - it return 0.0 (float)
            WORK_TIME_CODES = PAYROLL_CODES['NORMAL'] + PAYROLL_CODES['SUMINE'] + PAYROLL_CODES['OUT_OF_OFFICE']
            number_of_hours = sum(payslip.worked_days_line_ids.filtered(
                lambda r: r.code in WORK_TIME_CODES).mapped(
                'number_of_hours'))
            number_of_days = sum(payslip.worked_days_line_ids.filtered(
                lambda r: r.code in WORK_TIME_CODES).mapped(
                'number_of_days'))
        return number_of_days, number_of_hours

    # @api.model
    # def suma(self, employee_id, code, from_date, to_date=None):
    #     if to_date is None:
    #         to_date = datetime.now().strftime('%Y-%m-%d')
    #     self._cr.execute("SELECT sum(case when hp.credit_note = False then (pl.total) else (-pl.total) end)\
    #                 FROM hr_payslip as hp, hr_payslip_line as pl \
    #                 WHERE hp.employee_id = %s AND hp.state = 'done' \
    #                 AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pl.slip_id AND pl.code = %s",
    #                      (employee_id, from_date, to_date, code))
    #     res = self._cr.fetchone()
    #     return res and res[0] or 0.0

    # @api.model
    # def suma_dd(self, employee_id, codes, from_date, to_date=None):
    #     if to_date is None:
    #         to_date = datetime.now().strftime('%Y-%m-%d')
    #     self._cr.execute("SELECT sum(case when hp.credit_note = False then (pl.number_of_days) else (-pl.number_of_days) end)\
    #                 FROM hr_payslip AS hp, hr_payslip_worked_days AS pl \
    #                 WHERE hp.employee_id = %s AND hp.state = 'done' \
    #                 AND hp.date_from >= '%s' AND hp.date_to <= '%s' AND hp.id = pl.payslip_id AND pl.code IN ('%s') " %
    #                      (employee_id, from_date, to_date, "','".join(codes)))
    #     res = self._cr.fetchone()
    #     return res and res[0] or 0.0

    # @api.model
    # def suma_dv(self, employee_id, codes, from_date, to_date=None):
    #     if to_date is None:
    #         to_date = datetime.now().strftime('%Y-%m-%d')
    #     self._cr.execute("SELECT sum(case when hp.credit_note = False then (pl.number_of_hours) else (-pl.number_of_hours) end)\
    #                 FROM hr_payslip AS hp, hr_payslip_worked_days AS pl \
    #                 WHERE hp.employee_id = %s AND hp.state = 'done' \
    #                 AND hp.date_from >= '%s' AND hp.date_to <= '%s' AND hp.id = pl.payslip_id AND pl.code IN ('%s')" %
    #                      (employee_id, from_date, to_date, "','".join(codes)))
    #     res = self._cr.fetchone()
    #     return res and res[0] or 0.0


HrSalaryRule()


class HrHolidayStatus(models.Model):

    _inherit = 'hr.holidays.status'

    @api.multi
    def get_days(self, employee_id):
        result = dict((id, dict(max_leaves=0, leaves_taken=0, remaining_leaves=0,
                                virtual_remaining_leaves=0)) for id in self._ids)

        holidays = self.env['hr.holidays'].search([('employee_id', '=', employee_id),
                                                   ('state', 'in', ['validate']),
                                                   ('holiday_status_id', 'in', self.mapped('id'))
                                                   ])
        for holiday in holidays:
            status_dict = result[holiday.holiday_status_id.id]
            if holiday.type == 'add':
                if holiday.state == 'validate':
                        status_dict['virtual_remaining_leaves'] += holiday.number_of_days
                        status_dict['max_leaves'] += holiday.number_of_days
                        status_dict['remaining_leaves'] += holiday.number_of_days
            elif holiday.type == 'remove':  # number of days is negative
                status_dict['virtual_remaining_leaves'] += holiday.number_of_days
                if holiday.state == 'validate':
                    status_dict['leaves_taken'] += holiday.number_of_days
        return result

    @api.multi
    def _user_left_days(self):
        employee_id = False
        if 'employee_id' in self._context:
            employee_id = self._context['employee_id']
        else:
            employee_ids = self.env['hr.employee'].search([('user_id', '=', self.env.uid)])
            if employee_ids:
                employee_id = employee_ids[0].id
        if employee_id:
            res = self.sudo().get_days(employee_id)
        else:
            res = dict((res_id, {'leaves_taken': 0, 'remaining_leaves': 0, 'max_leaves': 0}) for res_id in self._ids)
        for rec in self:
            rec.max_leaves = res.get(rec.id, {}).get('max_leaves')
            rec.leaves_taken = res.get(rec.id, {}).get('leaves_taken')
            rec.remaining_leaves = res.get(rec.id, {}).get('remaining_leaves')
            rec.virtual_remaining_leaves = res.get(rec.id, {}).get('virtual_remaining_leaves')
        return res

    max_leaves = fields.Float(compute='_user_left_days', string='Maximum Allowed',
                              help='This value is given by the sum of all holidays requests with a positive value.',
                              multi='user_left_days')
    leaves_taken = fields.Float(compute='_user_left_days', string='Leaves Already Taken',
                                help='This value is given by the sum of all holidays requests with a negative value.',
                                multi='user_left_days')
    remaining_leaves = fields.Float(compute='_user_left_days', string='Remaining Leaves',
                                    help='Maximum Leaves Allowed - Leaves Already Taken',
                                    multi='user_left_days')
    virtual_remaining_leaves = fields.Float(compute='_user_left_days', string='Virtual Remaining Leaves',
                                            help='Maximum Leaves Allowed - Leaves Already Taken - Leaves Waiting Approval',
                                            multi='user_left_days')

    @api.multi
    def name_get(self):
        return [(rec.id, rec.name) for rec in self]  # FIXME: is it needed? Doesn't name get already return 'name' ?


HrHolidayStatus()


class HrPayslipPaymentLine(models.Model):

    _name = 'hr.payslip.payment.line'

    payslip_id = fields.Many2one('hr.payslip', string='Payslip', required=True, ondelete='cascade')
    code = fields.Char(string='Kodas', required=True)
    vdu = fields.Float(string='VDU')
    date_from = fields.Date(string='Laikotarpis nuo', required=True)
    date_to = fields.Date(string='Laikotarpis iki', required=True)
    amount_bruto = fields.Float(string='Bruto')
    payment_id = fields.Many2one('hr.employee.payment', string='Išmokėjimas', readonly=True)
    amount_npd = fields.Float(string='NPD', refault=0.0, readonly=True, required=True)
    amount_gpm = fields.Float(string='GPM', refault=0.0, readonly=True, required=True)
    amount_sodra = fields.Float(string='SODRA', refault=0.0, readonly=True, required=True)
    amount_paid = fields.Float(string='Išmokėta')
    payment_status = fields.Selection([('cancel', 'Atšauktas'),
                                       ('draft', 'Preliminarus'),
                                       ('ready', 'Paruošta tvirtinimui'),
                                       ('done', 'Patvirtinta'),
                                       ('not_created', 'Nesukurtas')], string='Apmokėjimo būsena', compute='_payment_info',
                                      store=True, help='Informacinis laukelis, rodantis susijusio apmokėjimo įrašo būseną')

    @api.one
    @api.depends('payment_id', 'payment_id.payment_line_ids.amount_paid', 'payment_id.state')
    def _payment_info(self):
        if self.payment_id:
            self.payment_status = self.payment_id.state
        else:
            self.payment_status = 'not_created'


HrPayslipPaymentLine()


class HrPayslipOtherLine(models.Model):

    _name = 'hr.payslip.other.line'

    payslip_id = fields.Many2one('hr.payslip', string='Payslip', required=True, ondelete='cascade')
    name = fields.Char(string='Pavadinimas', required=True)
    code = fields.Char(string='Kodas')
    amount = fields.Float(string='Suma')
    a_klase_kodas_id = fields.Many2one('a.klase.kodas', string='A klasės kodas')
    move_line_id = fields.Many2one('account.move.line', string='Account move line')
    payment_id = fields.Many2one('hr.employee.payment', string='Payment')
    type = fields.Selection([('priskaitymai', 'Priskaitymai'),
                             ('gpm', 'GPM'),
                             ('sdb', 'Darbuotojo sodra'),
                             ('sdd', 'Darbdavio sodra')], string='Tipas', required=True,
                            default='priskaitymas')


HrPayslipOtherLine()


class HrEmployee(models.Model):

    _inherit = 'hr.employee'

    remaining_leaves = fields.Float(string='Sukauptų atostogų likutis', compute='_remaining_leaves',
                                    inverse='_set_remaining_days', lt_string='Sukauptų atostogų likutis',
                                    help='Total number of legal leaves allocated to this employee, change this value to'
                                         ' create allocation/leave request. Total based on all the leave types without '
                                         'overriding limit.')

    use_favourable_sdd = fields.Boolean(string='Lengvatinis darbdavio sodros skaičiavimas',
                                        help=('Jei mėnesinis uždarbis nesiekia MMA, skaičiuojant darbdavio sodrą '
                                              'naudoti mėnesinį, o ne MMA'),
                                        groups="robo_basic.group_robo_premium_manager",
                                        sequence=100,
                                        )
    age = fields.Integer(string='Amžius', compute='_age', groups="robo_basic.group_robo_premium_manager")
    pensionner = fields.Boolean(string='Pensininkas', groups="robo_basic.group_robo_premium_manager")

    @api.one
    def _age(self):
        date = self._context.get('date', datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
        date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_birth = self.birthday
        default_age = 30  # todo dabar padaryta, kad neskaičiuotų lengvatos
        if not date_birth and (not self.country_id or self.country_id.code == 'LT') and self.identification_id:
            try:
                identification = self.identification_id
                first_digit = int(identification[0])
                year = 1800 + 100 * ((first_digit - 1) // 2) + int(identification[1:3])  # P3:DivOK
                month = int(identification[3:5])
                day = int(identification[5:7])
                date_birth = datetime(year, month, day).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            except:
                pass
        if date_birth:
            age = relativedelta(date_dt, datetime.strptime(date_birth, tools.DEFAULT_SERVER_DATE_FORMAT)).years
        else:
            age = default_age
        self.age = age

    @api.model
    def fix_likutis(self):
        payslips = self.env['hr.payslip'].search([('date_to', '=', '2017-07-31')])
        payslips._atostogu_likutis()

    @api.one
    def _set_remaining_days(self):
        date = self._context.get('date', datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
        leaves_accumulation_type = self._context.get('leaves_accumulation_type')
        if not leaves_accumulation_type:
            leaves_accumulation_type = self.with_context(date=date).leaves_accumulation_type
        value = self.remaining_leaves
        prev_value = self._get_remaining_days(date=date, accumulation_type=leaves_accumulation_type)
        diff = value - prev_value
        # Find for holidays status
        holiday_status_id = self.env.ref('hr_holidays.holiday_status_cl').id
        if float_compare(diff, 0, precision_digits=2) != 0 or self._context.get('force_fix_record'):
            fix_record = self.env['hr.holidays.fix'].search([
                ('employee_id', '=', self.id),
                ('date', '=', date),
                ('holiday_status_id', '=', holiday_status_id),
                ('type', '=', 'set')
            ], limit=1)
            if not fix_record:
                fix_record = self.env['hr.holidays.fix'].create({
                    'employee_id': self.id,
                    'date': date,
                    'holiday_status_id': holiday_status_id,
                })
            if leaves_accumulation_type == 'calendar_days':
                fix_record.calendar_days_left = value
                fix_record.work_days_left = value * 5.0/7.0  # P3:DivOK
            else:
                fix_record.calendar_days_left = value * 7.0/5.0  # P3:DivOK
                fix_record.work_days_left = value

    @api.model
    def crate_hol_fix(self):
        env = self.env
        env.cr.execute('select id from hr_employee')
        res = env.cr.fetchall()
        ids = map(lambda r: r[0], res)
        for employee in env['hr.employee'].browse(ids):
            employee.with_context(date='2017-06-30', force_fix_record=True, look_for_previous_fix=True).write({
                      'remaining_leaves': employee.with_context(
                          date='2017-06-30',
                          look_for_previous_fix=True).remaining_leaves})

    @api.model
    def is_work_day(self, date, employee_id, contract_id=None):
        appointment_domain = [('date_start', '<=', date),
                              '|',
                              ('date_end', '=', False),
                              ('date_end', '>=', date)]
        if contract_id:
            appointment_domain.append(('contract_id', '=', contract_id))
        else:
            appointment_domain.append(('employee_id', '=', employee_id))
        appointment = self.env['hr.contract.appointment'].search(appointment_domain, limit=1)
        if appointment:
            return appointment.schedule_template_id.is_work_day(date)
        elif datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT).weekday() in (5, 6):
            return False
        elif self.env['sistema.iseigines'].search([('date', '=', date)]):
            return False
        return True

    @api.multi
    def _get_remaining_days(self, date=None, accumulation_type='work_days', from_date=False):
        # Commonly used methods for date formatting
        def _strf(date):
            try:
                return date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            except:
                return date.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

        def split_by_year(period_start, period_end):
            periods_by_year = []
            period_st_dt = _strp(period_start)
            period_end_dt = _strp(period_end)
            crossover_start = relativedelta()
            year_crossover_count = period_end_dt.year - period_st_dt.year
            if year_crossover_count and year_crossover_count > 0:
                for en in range(year_crossover_count + 1):
                    if not en:
                        start = _strf(period_st_dt)
                        end = period_st_dt + relativedelta(month=12, day=31)
                        periods_by_year.append((start, _strf(end), ))
                        crossover_start = end + relativedelta(days=1)
                    elif en == year_crossover_count:
                        periods_by_year.append((_strf(crossover_start), _strf(period_end_dt)))
                    else:
                        crossover_end = crossover_start + relativedelta(month=12, day=31)
                        periods_by_year.append((_strf(crossover_start), _strf(crossover_end)))
                        crossover_start = crossover_end + relativedelta(days=1)
            else:
                periods_by_year.append((period_start, period_end, ))
            return periods_by_year

        def _date_only(date):
            try:
                res = _strf(date)[:10]
            except:
                res = date[:10]
            return res

        def _strp(date):
            try:
                return datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
            except:
                return datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)

        def _get_period_data(period_from, period_to, period_appointments):
            # Gets the amount of work and calendar days accumulated for each appointment for specific period
            res = []
            if not period_from or not period_to or not period_appointments:
                return res
            for period_appointment in period_appointments:
                # Adjust for app date_start/date_end to be included in period
                period_start = max(period_appointment.date_start, period_from)
                period_end = min(period_appointment.date_end or period_to, period_to)
                if period_start > period_end:
                    return res
                year_periods = split_by_year(period_start, period_end)
                appointment_contract_id = period_appointment.contract_id
                p_dt = {
                    'id': period_appointment.id,
                    'accumulated_work_days': 0.0,
                    'accumulated_calendar_days': 0.0
                }
                for year_period in year_periods:
                    year_period_start = year_period[0]
                    year_period_end = year_period[1]
                    year_start = _strp(year_period_start) + relativedelta(month=1, day=1)
                    year_end = _strp(year_period_end) + relativedelta(month=12, day=31)
                    yearly_calendar_days = (year_end - year_start).days + 1
                    yearly_work_days = period_appointment.with_context(date=year_period_end).num_work_days_year
                    yearly_leaves = period_appointment.total_leaves_per_year
                    if period_appointment.leaves_accumulation_type == 'calendar_days':
                        num_calendar_days = abs((_strp(year_period_end) - _strp(year_period_start)).days) + 1
                        num_work_days = num_calendar_days * 5.0 / 7.0  # P3:DivOK
                        yearly_days_to_use = yearly_calendar_days
                    else:
                        num_work_days = appointment_contract_id.get_work_days_for_holidays(
                            year_period_start, year_period_end)
                        num_calendar_days = num_work_days * 7.0 / 5.0  # P3:DivOK
                        yearly_days_to_use = yearly_work_days
                    # P3:DivOK
                    p_dt['accumulated_work_days'] += num_work_days / float(yearly_days_to_use) * yearly_leaves
                    p_dt['accumulated_calendar_days'] += num_calendar_days / float(yearly_days_to_use) * yearly_leaves
                res.append(p_dt)
            return res

        # Sanity checks
        self.ensure_one()
        if not isinstance(self.id, (int, long)):
            return 0.0
        if date is None:
            date = _strf(datetime.utcnow())

        appointment_ids = self.env['hr.contract.appointment'].search([
            ('employee_id', '=', self.id),
            ('date_start', '<=', date)
        ]).filtered(lambda app: not app.contract_id.is_internship_contract)

        all_contracts = appointment_ids.mapped('contract_id').sorted(key=lambda c: c['date_start'])
        last_contract = False
        if all_contracts:
            reversed_contracts = all_contracts.sorted(key=lambda c: c['date_start'], reverse=True)
            last_contract = reversed_contracts[0] if len(reversed_contracts) > 1 else reversed_contracts

        # If employee was let off - he doesn't have anymore leaves.
        if last_contract and last_contract.date_end and last_contract.date_end <= date:
            last_payslip = self.env['hr.payslip'].search([('state', '=', 'done'),
                                                          ('contract_id', '=', last_contract.id),
                                                          ('date_from', '<=', last_contract.date_end),
                                                          ('date_to', '>=', last_contract.date_end),
                                                          ('ismoketi_kompensacija', '=', True)])
            if last_payslip and not self._context.get('ignore_contract_end', False):
                return 0.0

        if from_date:
            appointment_ids = appointment_ids.filtered(lambda a: not a.date_end or a.date_end >= from_date)

        holiday_status_id = self.env.ref('hr_holidays.holiday_status_cl').id

        holiday_ids = self.env['hr.holidays'].search([
            ('contract_id', 'in', appointment_ids.mapped('contract_id.id')),
            ('date_from_date_format', '<=', date),
            ('state', '=', 'validate'),
            ('holiday_status_id', '=', holiday_status_id)
        ])
        if from_date:
            holiday_ids = holiday_ids.filtered(lambda h: h.date_to_date_format >= from_date)

        all_fixes = self.env['hr.holidays.fix'].search([
            ('employee_id', '=', self.id),
            ('date', '<=', date)
        ])
        fixes_that_add_holiday_days = all_fixes.filtered(lambda fix: fix.type == 'add')
        all_fixes = all_fixes.filtered(lambda fix: not fix.type or fix.type == 'set')
        holiday_fixes = all_fixes
        if from_date:
            holiday_fixes = holiday_fixes.filtered(lambda f: f.date >= from_date)

        holiday_fixes = holiday_fixes.sorted(key=lambda fix: fix.date, reverse=True)
        last_fix = False
        if holiday_fixes:
            last_fix = holiday_fixes[0] if len(holiday_fixes) > 1 else holiday_fixes
            from_date = last_fix.date
            # Changes were made but we want to restore old entries so accounting matches reports for year close
            if not self._context.get('computing_old_data'):
                next_day_dt = datetime.strptime(from_date, tools.DEFAULT_SERVER_DATE_FORMAT)+relativedelta(days=1)
                next_day = next_day_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                from_date = next_day

        if not from_date:
            if all_fixes:
                all_fixes = all_fixes.sorted(key=lambda fix: fix.date)
                from_date = all_fixes[0].date if len(all_fixes) > 1 else all_fixes.date
                # Changes were made but we want to restore old entries so accounting matches reports for year close
                if not self._context.get('computing_old_data'):
                    next_day_dt = datetime.strptime(from_date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)
                    next_day = next_day_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    from_date = next_day
            else:
                from_date = all_contracts[0].date_start if len(all_contracts) > 1 else all_contracts.date_start

        if not from_date:
            return 0.0

        fixes_that_add_holiday_days = fixes_that_add_holiday_days.filtered(lambda fix: fix.date >= from_date)

        calc_date_from = from_date
        calc_date_to = date

        national_holidays = self.env['sistema.iseigines'].search([
            ('date', '<=', calc_date_to),
            ('date', '>=', calc_date_from)
        ])

        appointments_for_period = appointment_ids.filtered(
            lambda a: a.date_start <= calc_date_to and (not a.date_end or a.date_end >= calc_date_from))
        holidays_for_period = holiday_ids.filtered(lambda h: h.date_from_date_format <= calc_date_to and
                                                             (not h.date_to or h.date_to_date_format >= calc_date_from) and
                                                             h.contract_id.id in appointments_for_period.mapped('contract_id.id'))

        # Get all holiday duration as used days
        used_calendar_days = used_work_days = 0.0
        for holiday in holidays_for_period:
            period_from = max(_strp(holiday.date_from), _strp(calc_date_from))
            period_to = min(_strp(holiday.date_to), _strp(calc_date_to)+relativedelta(days=1))

            period_from_strf = _date_only(period_from)
            period_to_strf = _date_only(period_to)

            period_apps = appointments_for_period.filtered(lambda a: a.date_start <= period_to_strf and
                                                                     (not a.date_end or a.date_end >= period_from_strf))

            for app in period_apps:
                app_hol_period_from = max(period_from, _strp(app.date_start))
                app_hol_period_to = min(period_to, _strp(app.date_end)+relativedelta(days=1) if app.date_end else period_to)

                app_period_national_holidays = national_holidays.filtered(lambda h: _strf(app_hol_period_from) <= h.date <= _strf(app_hol_period_to))

                if holiday.leaves_accumulation_type == 'calendar_days':
                    num_national_holiday_days = 0.0
                    for national_holiday in app_period_national_holidays:
                        is_work_day = app.schedule_template_id.with_context(calculating_holidays=True).is_work_day(national_holiday.date)
                        if not is_work_day:
                            num_national_holiday_days += 1
                    used_calendar_days += (app_hol_period_to - app_hol_period_from).days + 1.0 - num_national_holiday_days
                else:
                    c_date = app_hol_period_from
                    while c_date < app_hol_period_to:
                        is_work_day = app.schedule_template_id.with_context(
                            force_use_schedule_template=True, calculating_holidays=True
                        ).is_work_day(_strf(c_date))
                        if is_work_day:
                            used_work_days += 1
                        c_date += relativedelta(days=1)

        # Check how much was accumulated for each period appointment
        appointment_accumulated_data = _get_period_data(calc_date_from, calc_date_to, appointments_for_period)
        accumulated_work_days = sum(app_acc_data.get('accumulated_work_days', 0.0) for app_acc_data in appointment_accumulated_data)
        accumulated_calendar_days = sum(app_acc_data.get('accumulated_calendar_days', 0.0) for app_acc_data in appointment_accumulated_data)

        # Subtract non-accumulative periods

        app_contracts = appointment_ids.mapped('contract_id')
        non_accumulative_holiday_ids = app_contracts.find_non_accumulative_holidays(calc_date_from, calc_date_to)

        not_accumulated_work_days = not_accumulated_calendar_days = 0.0

        for holiday in non_accumulative_holiday_ids:
            holiday_period_from = max(_strp(holiday.date_from), _strp(calc_date_from))
            holiday_period_to = min(_strp(holiday.date_to), _strp(calc_date_to))

            holiday_period_from_strf = _date_only(holiday_period_from)
            holiday_period_to_strf = _date_only(holiday_period_to)

            holiday_period_apps = appointments_for_period.filtered(lambda a: a.date_start <= holiday_period_to_strf and
                                                                     (not a.date_end or a.date_end >= holiday_period_from_strf))

            holiday_appointment_accumulated_data = _get_period_data(holiday_period_from_strf, holiday_period_to_strf, holiday_period_apps)
            not_accumulated_work_days += sum(
                [app_acc_data.get('accumulated_work_days', 0.0) for app_acc_data in holiday_appointment_accumulated_data])
            not_accumulated_calendar_days += sum(
                [app_acc_data.get('accumulated_calendar_days', 0.0) for app_acc_data in holiday_appointment_accumulated_data])

        # Very special case for non accumulative period
        if last_contract:
            contract = last_contract
            work_relation_start_date = contract.date_start
            while contract:
                contract_start_dt = _strp(contract.date_start)
                day_before_contract_start = _strf(contract_start_dt - relativedelta(days=1))
                contract = contract.employee_id.contract_ids.filtered(lambda c:
                                                                      c.date_start <= day_before_contract_start and
                                                                      (not c.date_end or c.date_end >= day_before_contract_start))
                if contract:
                    work_relation_start_date = contract.date_start

            work_relation_start_date_dt = datetime.strptime(work_relation_start_date, tools.DEFAULT_SERVER_DATE_FORMAT)
            work_start_month = work_relation_start_date_dt.month
            work_start_day = work_relation_start_date_dt.day
            calc_date_to_dt = _strp(calc_date_to)
            current_work_year_start_dt = calc_date_to_dt - relativedelta(month=work_start_month, day=work_start_day)
            current_work_year_start_day_before_dt = current_work_year_start_dt - relativedelta(days=1)
            current_work_year_start_day_before = _strf(current_work_year_start_day_before_dt)
            current_work_year_start = _strf(current_work_year_start_dt)
            last_work_year_start = _strf(current_work_year_start_dt-relativedelta(years=1))
            work_year_periods = [
                (last_work_year_start, current_work_year_start_day_before),
                (current_work_year_start, calc_date_to),
            ]
            for work_year_period in work_year_periods:
                date_from, date_to = work_year_period
                unpaid_non_accumulative_holiday_ids = self.env['hr.holidays'].search([
                    ('contract_id', 'in', appointment_ids.mapped('contract_id.id')),
                    ('date_from_date_format', '<=', date_to),
                    ('date_to_date_format', '>=', date_from),
                    ('state', '=', 'validate'),
                    ('holiday_status_id', '=', self.env.ref('hr_holidays.holiday_status_unpaid').id)
                ])

                unpaid_hol_len = 0.0
                ten_work_days_reached_date = False
                appointments_for_period = appointment_ids.filtered(
                    lambda a: a.date_start <= calc_date_to and (not a.date_end or a.date_end >= date_from))
                for unpaid_hol in unpaid_non_accumulative_holiday_ids.sorted(key=lambda h: h.date_to):
                    if ten_work_days_reached_date:
                        break
                    unpaid_start = _strf(_strp(unpaid_hol.date_from))
                    unpaid_end = _strf(_strp(unpaid_hol.date_to))
                    unpaid_hol_apps = appointments_for_period.filtered(
                        lambda a: a.date_start <= unpaid_end and (not a.date_end or a.date_end >= unpaid_start))

                    days_factor = 10
                    appointment = unpaid_hol_apps[0] if len(unpaid_hol_apps) > 1 else unpaid_hol_apps
                    if appointment and appointment.leaves_accumulation_type == 'calendar_days':
                        days_factor = 14 #(days_factor*7/5)
                    for unpaid_hol_app in unpaid_hol_apps:
                        if ten_work_days_reached_date:
                            break

                        unpaid_hol_app_period_from = max(_strp(unpaid_start), _strp(unpaid_hol_app.date_start))
                        unpaid_hol_app_period_to = min(_strp(unpaid_end), _strp(unpaid_hol_app.date_end) + relativedelta(days=1) if unpaid_hol_app.date_end else _strp(unpaid_end))

                        while unpaid_hol_app_period_from <= unpaid_hol_app_period_to:
                            the_date = _strf(unpaid_hol_app_period_from)
                            if unpaid_hol_app.schedule_template_id.is_work_day(the_date):
                                unpaid_hol_len += 1
                            if unpaid_hol_len == days_factor:
                                ten_work_days_reached_date = the_date
                                break
                            unpaid_hol_app_period_from += relativedelta(days=1)

                # If unpaid holidays last more than 10 days in the last work year - yearly holidays are not accumulated
                # anymore (127 str, 4, 4)
                if ten_work_days_reached_date:
                    # First of all, all non accumulative holidays will be the ones after the 10 days
                    unpaid_hol_periods_to_check = [(hol.date_from_date_format, hol.date_to_date_format)
                                                   for hol in unpaid_non_accumulative_holiday_ids.filtered(lambda h:
                                                                                                           h.date_from_date_format > max(ten_work_days_reached_date, calc_date_from))]

                    # Then we need to add the days left for the single hol after the 10 days were reached
                    next_day_after_10_is_reached = _strf(_strp(ten_work_days_reached_date) + relativedelta(days=1))
                    hol_entry_with_next_day_after = unpaid_non_accumulative_holiday_ids.filtered(lambda h:
                                                                                                 h.date_from_date_format <= next_day_after_10_is_reached <= h.date_to_date_format)
                    if hol_entry_with_next_day_after:
                        unpaid_hol_periods_to_check.append((next_day_after_10_is_reached, hol_entry_with_next_day_after.date_to_date_format))

                    for (unpaid_hol_period_from, unpaid_hol_period_to) in unpaid_hol_periods_to_check:
                        unpaid_hol_range_apps = appointments_for_period.filtered(
                            lambda a: a.date_start <= unpaid_hol_period_to and
                                      (not a.date_end or a.date_end >= unpaid_hol_period_from))
                        uhp_date_from = max(calc_date_from, unpaid_hol_period_from, date_from)
                        uhp_date_to = min(calc_date_to, unpaid_hol_period_to, date_to)
                        if uhp_date_to < calc_date_from or uhp_date_from > uhp_date_to:
                            continue
                        unpaid_hol_period_data = _get_period_data(uhp_date_from, uhp_date_to, unpaid_hol_range_apps)
                        not_accumulated_work_days += sum(app_acc_data.get('accumulated_work_days', 0.0) for app_acc_data in unpaid_hol_period_data)
                        not_accumulated_calendar_days += sum(app_acc_data.get('accumulated_calendar_days', 0.0) for app_acc_data in unpaid_hol_period_data)

        not_accumulated_work_days = min(not_accumulated_work_days, accumulated_work_days)
        not_accumulated_calendar_days = min(not_accumulated_calendar_days, accumulated_calendar_days)

        # Check what value was set in holiday fix
        fixed_calendar_days = fixed_work_days = 0.0
        if last_fix:
            fixed_calendar_days_left = last_fix.calendar_days_left
            fixed_work_days_left = last_fix.work_days_left
            no_calendar_days_set = tools.float_is_zero(fixed_calendar_days_left, precision_digits=2)
            no_work_days_set = tools.float_is_zero(fixed_work_days_left, precision_digits=2)
            if accumulation_type == 'calendar_days':
                if no_calendar_days_set and not no_work_days_set:
                    last_fix.sudo().write({'calendar_days_left': fixed_work_days_left * 7.0 / 5.0})  # P3:DivOK
                fixed_calendar_days = fixed_calendar_days_left
            else:
                if no_work_days_set and not no_calendar_days_set:
                    last_fix.sudo().write({'work_days_left': fixed_calendar_days_left * 5.0 / 7.0})  # P3:DivOK
                fixed_work_days = fixed_work_days_left

        if self._context.get('ignore_used_days'):
            used_calendar_days = used_work_days = 0.0

        holiday_compensations = self.env['hr.employee.holiday.compensation'].sudo().search([
            ('employee_id', '=', self.id),
            ('state', '=', 'confirmed'),
            ('date', '<=', calc_date_to),
            ('date', '>=', calc_date_from),
        ])
        work_days_compensated = sum(holiday_compensations.mapped('number_of_days'))
        calendar_days_compensated = work_days_compensated * 7.0 / 5.0  # P3:DivOK

        calendar_days_added_by_fixes = sum(fix.get_calendar_days() for fix in fixes_that_add_holiday_days)
        work_days_added_by_fixes = sum(fix.get_work_days() for fix in fixes_that_add_holiday_days)

        # Calculate totals
        # P3:DivOK
        work_days_total = fixed_work_days + accumulated_work_days - used_work_days - \
                          (used_calendar_days * 5.0 / 7.0) - not_accumulated_work_days + work_days_compensated + \
                          work_days_added_by_fixes
        calendar_days_total = fixed_calendar_days + accumulated_calendar_days - used_calendar_days - \
                              (used_work_days * 7.0 / 5.0) - not_accumulated_calendar_days + \
                              calendar_days_compensated + calendar_days_added_by_fixes
        if accumulation_type == 'calendar_days':
            return calendar_days_total
        else:
            return work_days_total

    # Method overriden in payroll schedule and region manager modules
    @api.multi
    def _remaining_leaves(self):
        date = self._context.get('date', datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
        for rec in self:
            if self.env.user.is_manager() or self.env.user.is_hr_manager() or rec.user_id == self.env.user:
                rec.remaining_leaves = rec._compute_employee_remaining_leaves(date)

    @api.multi
    def _compute_employee_remaining_leaves(self, date):
        self.ensure_one()
        leaves_accumulation_type = self._context.get('leaves_accumulation_type')
        if not leaves_accumulation_type:
            leaves_accumulation_type = self.sudo().with_context(date=date).leaves_accumulation_type
        if isinstance(self.id, (int, long)):
            remaining_leaves = self.sudo()._get_remaining_days(date=date, accumulation_type=leaves_accumulation_type)
        else:
            remaining_leaves = 0
        return remaining_leaves

    # @api.multi
    # def num_days_not_allocated_leaves(self, date):
    #     date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
    #     last_allocation = self.env['hr.holidays'].search([('employee_id', '=', self.id),
    #                                                       ('holiday_status_id.limit', '=', False),
    #                                                       ('type', '=', 'add'),
    #                                                       ('data', '!=', False)],
    #                                                      order='data desc', limit=1)
    #     if last_allocation:
    #         date_allocated = datetime.strptime(last_allocation.date, tools.DEFAULT_SERVER_DATE_FORMAT)
    #     else:
    #         contract = self.env['hr.employee'].search([('employee_id', '=', self.id),
    #                                                    ('date_start', '<=', date),
    #                                                    '|',
    #                                                    ('date_end', '=', False),
    #                                                    ('date_end', '>=', date)], order='date_start')
    #         if contract:
    #             date_allocated = datetime.strptime(contract.date_start)
    #         else:
    #             return 0
    #     if date_allocated >= date_dt:
    #         return 0
    #     # in case date and date_allocated are not in the same year it has to be a little complicated
    #
    #     date_from = date_allocated + timedelta(days=1)
    #     res = 0
    #     while date_from <= date_dt:
    #         date_to = min(date, date_from + relativedelta(month=12, day=31))
    #         year = date_to.year
    #         # num_days_in_year = datetime(year+1, 1, 1) - datetime(year, 1, 1)
    #         num_days = (date_to - date_from).days + 1
    #         res += num_days.date_from + 1
    #
    #         if (date_from.month, date_from.date) == (1, 1):
    #             date_from += relativedelta(years=1)
    #         else:
    #             date_from += relativedelta(years=1, month=1, day=1)

    def get_vdu(self, date, **params):
        return get_vdu(self.env, date, self, **params).get('vdu', 0.0)

    @api.multi
    def get_accumulated_during_month_holiday_reserve_amounts(self, date):
        """
        Compute the newly accumulated amounts for holiday reserve at given date by getting the expected value, and
        substracting what's already available in the accumulation account
        :param date: string, date at which to compute (expects it to be last day of month -- not checked or enforced)
        :return: dictionary with hr_employee.id as key, value is a tuple with new amounts and new amounts for SoDra
        """
        # date comes from payslip.run : it already is the last day of month
        holiday_reserve_amounts = self.get_holiday_reserve_info(date)
        res = {}
        for employee in self:
            employee_data = holiday_reserve_amounts.get(employee.id)
            if not employee_data:
                raise exceptions.UserError(_('Atostogų likutis nebuvo perskaičiuotas darbuotojui %s') % employee.name)
            holidays_obligation_account_id = employee.department_id.atostoginiu_kaupiniai_account_id.id \
                                             or employee.company_id.atostoginiu_kaupiniai_account_id.id
            if not holidays_obligation_account_id:
                raise exceptions.UserError(_('Nenustatyta darbuotojo %s atostoginių kaupinių sąskaita') % employee.name)
            aml_balance_prev = - employee.get_aml_balance_by_account(holidays_obligation_account_id, date)
            employer_sodra_coefficient = employee_data.get('employer_sodra_coefficient')
            total_amount = employee_data.get('total')
            balance_diff = total_amount - aml_balance_prev
            # P3:DivOK
            new_amount = tools.float_round(balance_diff / (1 + employer_sodra_coefficient / 100.0), precision_digits=2)
            amount_sodra = balance_diff - new_amount
            res[employee.id] = [new_amount, amount_sodra]
        return res

    @api.multi
    def get_aml_balance_by_account(self, account_id, date):
        """ Returns the sum of balance for all account.move.line related to self, on account_id, up until date """
        self.ensure_one()  # we process only one employee at a time as account_id depends on employee record and we do not want to join all possible account entries
        self._cr.execute('''
        SELECT COALESCE(sum(aml.balance), 0)
        FROM account_move_line aml
        JOIN hr_employee employee
                ON employee.address_home_id = aml.partner_id
        JOIN account_account act
            ON act.id = aml.account_id
        WHERE act.id = %s
          AND aml.date <= %s
          AND employee.id = %s
        ''', (account_id, date, self.id))
        prev_aml_balance = self._cr.fetchall()[0][0]
        return prev_aml_balance

    @api.multi
    def get_holidays_reserve_data(self, date):
        """
        Returns data for accumulated holiday reserves entry creation
        :param date: date at which to compute the amounts
        :return: dict with keys 'date' and 'data': a dict with keys hr_employee.id, and containing a dict with keys:
                 'amount', 'sodra', 'holiday_expense_account_id', 'holiday_savings_account_id' and 'partner_id'
        """
        res = {'date': date, 'data': {}}
        employee_amounts = self.get_accumulated_during_month_holiday_reserve_amounts(date)
        for employee in self:
            holiday_savings_account_id = employee.department_id.atostoginiu_kaupiniai_account_id.id \
                                         or employee.company_id.atostoginiu_kaupiniai_account_id.id
            holiday_expense_account_id = employee.department_id.kaupiniai_expense_account_id.id \
                                         or employee.company_id.kaupiniai_expense_account_id.id
            new_amount, amount_sodra = employee_amounts.get(employee.id, (0, 0))
            res['data'][employee.id] = {
                'amount': new_amount,
                'sodra': amount_sodra,
                'holiday_expense_account_id': holiday_expense_account_id,
                'holiday_savings_account_id': holiday_savings_account_id,
                'partner_id': employee.address_home_id.id
            }
        return res

    @api.model
    def get_holiday_reserve_entry_labels(self, date):
        date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        year = date_dt.year
        month = date_dt.month
        return {'amount': _('Atostogų kaupimai-%s %s') % (year, month),
                'sodra': _('Atostogų kaupimai VSD įmokoms-%s %s') % (year, month)}

    @api.model
    def create_accumulated_holidays_reserve_entry(self, data):
        """
        Create the accounting entry for accumulated holiday reserve amounts
        :param data: dictionary containing the data relative to each employees. Keys are 'date', and 'data': a dict with
                     HrEmployee ID's as key and containing values necessary for data creation: 'amount', 'sodra',
                     'holiday_expense_account_id', 'holiday_savings_account_id' and 'partner_id'
        :return: account.move record
        """
        date = data['date']
        labels = self.get_holiday_reserve_entry_labels(date)
        journal_id = self.env.user.company_id.salary_journal_id.id
        if not journal_id:
            raise exceptions.Warning(_('Nenurodytas darbo užmokesčio žurnalas'))
        company_currency = self.env.user.company_id.currency_id
        rounding = company_currency.rounding
        amls = []
        for employee_id, employee_data in iteritems(data['data']):
            partner_id = employee_data.get('partner_id')
            holiday_expense_account_id = employee_data.get('holiday_expense_account_id')
            holiday_savings_account_id = employee_data.get('holiday_savings_account_id')
            if not holiday_savings_account_id:
                raise exceptions.UserError(_('Nenustatyta darbuotojo %s atostoginių kaupinių sąskaita') % employee_id)

            new_amount = employee_data.get('amount')
            amount_sodra = employee_data.get('sodra')

            amounts_atostoginiai_by_account_id = {holiday_expense_account_id: new_amount,
                                                  holiday_savings_account_id: - new_amount}

            amounts_sodra_by_account_id = {holiday_expense_account_id: amount_sodra,
                                           holiday_savings_account_id: - amount_sodra}

            for account_id, amount in iteritems(amounts_atostoginiai_by_account_id):
                amount = company_currency.round(amount)
                if tools.float_is_zero(amount, precision_rounding=rounding):
                    continue
                aml_vals = {'account_id': account_id,
                            'debit': max(amount, 0.0),
                            'credit': max(-amount, 0.0),
                            'date': date,
                            'name': labels['amount'],
                            'partner_id': partner_id,
                            }
                amls.append((0, 0, aml_vals))

            for account_id, amount in iteritems(amounts_sodra_by_account_id):
                amount = company_currency.round(amount)
                if tools.float_is_zero(amount, precision_rounding=rounding):
                    continue
                aml_vals = {'account_id': account_id,
                            'debit': max(amount, 0.0),
                            'credit': max(-amount, 0.0),
                            'date': date,
                            'name': labels['sodra'],
                            'partner_id': partner_id,
                            }
                amls.append((0, 0, aml_vals))

        account_move = self.env['account.move']
        if amls:
            account_move_vals = {'ref': labels['amount'],
                                 'date': date,
                                 'journal_id': journal_id,
                                 'line_ids': amls}
            account_move = self.env['account.move'].create(account_move_vals)
            account_move.post()
        return account_move

    @api.multi
    def _compute_leaves_count(self):
        for rec in self:
            rec.leaves_count = rec.remaining_leaves

    @api.multi
    def get_holiday_reserve_info(self, date=None):
        """
        Compute the data needed to export holiday reserves to Excel
        :param date: computation date, default to today if not provided
        :return: dict of dict, primary key is employee reccord ID, secondary keys are remaining_leaves, vdu, total, reserve, sodra
        """
        if date is None:
            date = fields.Date.today()
        res = {}
        use_accumulation_records = self.env.user.company_id.with_context(date=date).holiday_accumulation_usage_is_enabled
        for employee in self:
            appointment = employee.with_context(date=date).contract_id.appointment_id or \
                          employee.contract_id.appointment_id
            contract = appointment.contract_id
            payslip_date = min(contract.work_relation_end_date or date, date)
            include_last = contract and contract.include_last_month_when_calculating_vdu_for_date(date)

            # Determine if accumulation records should be used and get the accumulation records if needed
            should_use_holiday_accumulation_records = employee.holiday_accumulation_usage_policy or \
                                                      use_accumulation_records
            accumulation_records = self.env['hr.employee.holiday.accumulation']
            if should_use_holiday_accumulation_records:
                date_to = date
                if contract.work_relation_end_date:
                    date_to = min(date_to, contract.work_relation_end_date)
                accumulation_records = self.env['hr.employee.holiday.accumulation'].sudo().search([
                    ('employee_id', '=', employee.id),
                    ('date_from', '>=', contract.work_relation_start_date),
                    ('date_from', '<=', date_to)
                ])

            if not should_use_holiday_accumulation_records or not accumulation_records:
                vdu = employee.get_vdu(date, vdu_type='d', include_last=include_last)
                remaining_leaves = employee.with_context(date=date).remaining_leaves
                if appointment.leaves_accumulation_type == 'calendar_days':
                    factor = appointment.schedule_template_id.num_week_work_days / 7.0  # P3:DivOK
                else:
                    factor = 1.0
                remaining_leaves *= factor
                reserve = remaining_leaves * vdu
            else:
                reserve = remaining_leaves = 0.0
                vdu = employee.get_vdu(date, vdu_type='h', include_last=include_last)
                daily_vdu = employee.get_vdu(date, vdu_type='d', include_last=include_last)
                work_norm = appointment.schedule_template_id.work_norm
                last_payslip = self.env['hr.payslip'].search_count([('state', '=', 'done'),
                                                                    ('contract_id', '=', contract.id),
                                                                    ('date_from', '<=', payslip_date),
                                                                    ('date_to', '>=', payslip_date),
                                                                    ('ismoketi_kompensacija', '=', True)])
                hours_to_multiply_by = 8.0
                use_daily_vdu = True
                # If the last payslip is already closed, the holiday reserve balance should be 0.0
                if not last_payslip:
                    # Determine if all leaves should be adjusted based on post
                    multiply_by_accumulation_record_post = len(set(accumulation_records.mapped('post'))) != 1
                    if multiply_by_accumulation_record_post:
                        use_daily_vdu = False

                    # Calculate remaining leave balance based on each accumulation record
                    for accumulation_record in accumulation_records:
                        accumulation_type = accumulation_record.accumulation_type
                        appointment_to_use = appointment
                        if accumulation_type == 'calendar_days':
                            accumulation_record_appointment = accumulation_record.appointment_id
                            if accumulation_record_appointment:
                                appointment_to_use = accumulation_record_appointment
                            factor = appointment_to_use.schedule_template_id.num_week_work_days / 7.0  # P3:DivOK
                        else:
                            factor = 1.0
                        balance_to_date = accumulation_record.get_balance_before_date(payslip_date)
                        accumulation_record_leaves = balance_to_date * factor
                        if multiply_by_accumulation_record_post:
                            accumulation_record_leaves *= accumulation_record.post
                        else:
                            hours_to_multiply_by = accumulation_record.post * 8.0
                        remaining_leaves += accumulation_record_leaves
                        if use_daily_vdu:
                            reserve += accumulation_record_leaves * daily_vdu
                        else:
                            reserve += accumulation_record_leaves * vdu * hours_to_multiply_by * work_norm
                if use_daily_vdu:
                    vdu = daily_vdu
                else:
                    vdu = vdu * hours_to_multiply_by * work_norm  # Show VDU as if etatas was full.
            employer_sodra_coefficient = employee.with_context(
                date=payslip_date, dont_check_is_tax_free=True
            ).contract_id.effective_employer_tax_rate_proc
            # P3:DivOK
            total = tools.float_round(reserve * (1 + employer_sodra_coefficient / 100.0), precision_digits=2)
            reserve = tools.float_round(total / (1 + employer_sodra_coefficient / 100.0), precision_digits=2)
            sodra = total - reserve
            res[employee.id] = {
                'remaining_leaves': remaining_leaves,
                'vdu': vdu,
                'total': total,
                'reserve': reserve,
                'sodra': sodra,
                'employer_sodra_coefficient': employer_sodra_coefficient,
            }
        return res


HrEmployee()


class HrHolidaysFix(models.Model):

    _name = 'hr.holidays.fix'
    _order = 'date desc'
    _sql_constraints = [('unique_employee_date, status', 'unique(employee_id, date, holiday_status_id, type)',
                         _('Darbuotojas negali turėti daugiau nei vieną fiksuotą atostogų kiekį tam pačiam tipui'))]

    def _default_holiday_status_id(self):
        return self.env.ref('hr_holidays.holiday_status_cl')

    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', required=True, ondelete='cascade')
    date = fields.Date(string='Data', required=True)
    calendar_days_left = fields.Float(string='Likę kalendorinių dienų atostogų', default=0.0)
    work_days_left = fields.Float(string='Likę darbo dienų', default=0.0)
    holiday_status_id = fields.Many2one('hr.holidays.status', string='Atostogų tipas', required=True,
                                        default=_default_holiday_status_id)
    type = fields.Selection([
        ('set', 'Set'),
        ('add', 'Add')
    ], default='set', string='Type', required=True)

    @api.constrains('type', 'date')
    def _check_holiday_fix_interaction_with_accumulation_records(self):
        # Don't check the date when holiday accumulation usage policy was enabled but rather just check if it is
        # enabled since we care about the integrity of the holiday accumulation records in this method and not the date
        # when the calculations start taking place
        if not self.env.user.company_id.holiday_accumulation_usage_policy:
            return
        today = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        existing_fixes = self.env['hr.holidays.fix'].search([
            ('employee_id', 'in', self.employee_id.ids),
            ('id', 'not in', self.ids)
        ])

        for fix in self:
            # Find contract and its terms
            contract = fix.employee_id.with_context(date=fix.date).contract_id
            work_relation_start_date = contract and contract.work_relation_start_date
            work_relation_end_date = contract and contract.work_relation_end_date

            # Find fixes for the contract
            employee_fixes = existing_fixes.filtered(lambda f: f.employee_id == fix.employee_id)
            if work_relation_start_date:
                employee_fixes = employee_fixes.filtered(lambda f: f.date >= work_relation_start_date)
            if work_relation_end_date:
                employee_fixes = employee_fixes.filtered(lambda f: f.date <= work_relation_end_date)

            contract_already_has_a_fix = employee_fixes
            setting_fix_after_contract_ends = work_relation_end_date and work_relation_end_date <= fix.date

            # Don't allow creating any historical holiday fixes unless it's for the current appointment
            if fix.date < today:
                appointments = contract.appointment_ids
                latest_appointment = appointments and appointments.sorted(key=lambda a: a.date_start, reverse=True)[0]
                first_appointment = appointments and appointments.sorted(key=lambda a: a.date_start)[0]
                latest_appointment_start_date = latest_appointment and latest_appointment.date_start
                first_appointment_start_date = first_appointment and first_appointment.date_start
                if not latest_appointment or first_appointment_start_date < fix.date < latest_appointment_start_date:
                    raise exceptions.UserError(_('Can not set holiday fix for past date because the company has '
                                                 'holiday accumulation usage policy enabled'))

            # Don't allow creating any fixes with type set unless the contract does not have any fixes yet or we're
            # setting a fix for the end of the contract
            if fix.type == 'set' and contract_already_has_a_fix and not setting_fix_after_contract_ends:
                raise exceptions.UserError(_('Can not set holiday fix of type "Set" because the company has holiday '
                                             'accumulation usage policy enabled'))


    @api.model
    def get_employee_remaining_leave_balance_at_date(self, employee, date):
        """
        Returns the holiday balance for a specific employee for a specific date in both calendar and work days
        :param employee: (hr.employee) employee to get the balance for
        :param date: (str) date to get the balance for

        :returns: dictionary containing the holiday balance - {'calendar_days': 0.0, 'work_days': 0.0}
        """
        return {
            'calendar_days': employee._get_remaining_days(date=date, accumulation_type='calendar_days'),
            'work_days': employee._get_remaining_days(date=date, accumulation_type='work_days')
        }

    @api.onchange('employee_id', 'date', 'type')
    def _onchange_data_set_balance_based_on_date(self):
        """Sets the holiday balance to balance based on date when setting """
        # Don't change the balance if no data is provided or if desired balance has already been entered
        basic_data_is_set = self.employee_id and self.date
        if not basic_data_is_set or not self.type or self.type != 'set':
            return
        calendar_days_have_been_set = self.calendar_days_left and \
                                          not tools.float_is_zero(self.calendar_days_left, precision_digits=2)
        work_days_have_been_set = self.work_days_left and \
                                      not tools.float_is_zero(self.work_days_left, precision_digits=2)
        if calendar_days_have_been_set or work_days_have_been_set:
            return

        balance = self.get_employee_remaining_leave_balance_at_date(self.employee_id, self.date)
        self.calendar_days_left = balance.get('calendar_days', 0.0)
        self.work_days_left = balance.get('work_days', 0.0)

    @api.model
    def auto_change_fix(self, employee_id, date_from, date_to, fix_type='add', contract_id=False):
        relevant_fixes = self.env['hr.holidays.fix'].search([
            ('employee_id', '=', employee_id),
            ('date', '>=', date_from),
            ('type', '=', 'set')
        ])
        if contract_id:
            contract = self.env['hr.contract'].browse(contract_id)
        else:
            contract = self.env['hr.contract']
        date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        for fix in relevant_fixes:
            effective_date_to = min(date_to, fix.date)
            effective_date_to_dt = datetime.strptime(effective_date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            num_days_calendar = (effective_date_to_dt - date_from_dt).days + 1
            num_work_days = contract.get_num_work_days(date_from, effective_date_to)
            if fix_type == 'remove':
                num_days_calendar *= -1
                num_work_days *= -1
            if fix.date < '2017-07-01':
                fix.calendar_days_left += num_days_calendar
                fix.work_days_left += num_days_calendar * 0.7
            else:
                fix.calendar_days_left += num_days_calendar   # not important
                fix.work_days_left += num_work_days

    @api.model
    def adjust_fix_days(self, employee, date, days, adjustment_in_work_days=False):
        # Find holiday fix
        holiday_fix = self.search([
            ('date', '=', date),
            ('employee_id', '=', employee.id),
            ('type', '=', 'add'),
        ])
        if not holiday_fix:
            holiday_fix = self.create({
                'date': date,
                'employee_id': employee.id,
                'type': 'add'
            })

        # Get appointment data
        appointment = self.env['hr.contract.appointment'].search([
            ('date_start', '<=', date),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', date)
        ], limit=1)
        leaves_accumulation_type = appointment.leaves_accumulation_type if appointment else 'calendar_days'
        week_work_days = None
        if appointment:
            week_work_days = appointment.schedule_template_id.num_week_work_days
        if not week_work_days:
            week_work_days = 5.0

        # Adjust added days
        work_days_to_add = calendar_days_to_add = days
        if not adjustment_in_work_days:
            # Adding calendar days, adjust the work days to add
            work_days_to_add *= week_work_days / 7.0  # P3:DivOK
        else:
            # Adding work days, adjust the work days to add
            calendar_days_to_add *= 7.0 / float(week_work_days)  # P3:DivOK

        # Calculate the total holiday days for the record
        calendar_days = holiday_fix.get_calendar_days() + calendar_days_to_add
        work_days = holiday_fix.get_work_days() + work_days_to_add
        holiday_fix.write({
            'calendar_days_left': calendar_days,
            'work_days_left': work_days
        })
        return holiday_fix

    @api.multi
    def get_calendar_days(self, week_work_days=None):
        self.ensure_one()
        holiday_balance = self.calendar_days_left
        if tools.float_is_zero(holiday_balance, precision_digits=2):
            if not week_work_days:
                appointment = self.employee_id.with_context(date=self.date).appointment_id
                schedule_template = appointment and appointment.schedule_template_id
                week_work_days = 6.0 if schedule_template and schedule_template.work_week_type == 'six_day' else 5.0
            try:
                holiday_balance = self.work_days_left / week_work_days * 7.0  # P3:DivOK
            except ZeroDivisionError:
                holiday_balance = 0.0
        return holiday_balance

    @api.multi
    def get_work_days(self, week_work_days=None):
        self.ensure_one()
        holiday_balance = self.work_days_left
        if tools.float_is_zero(holiday_balance, precision_digits=2):
            if not week_work_days:
                appointment = self.employee_id.with_context(date=self.date).appointment_id
                schedule_template = appointment and appointment.schedule_template_id
                week_work_days = 6.0 if schedule_template.work_week_type == 'six_day' else 5.0
            holiday_balance = self.calendar_days_left * week_work_days / 7.0  # P3:DivOK
        return holiday_balance


HrHolidaysFix()


class HrPayrollStructure(models.Model):

    _inherit = 'hr.payroll.structure'

    @api.model
    def setup_lt_payroll(self):
        try:
            bad_struct = self.env.ref('hr_payroll.structure_base')
        except ValueError:
            bad_struct = self.env['hr.payroll.structure']
        for struct in bad_struct:
            struct.unlink()
        external_salary_rule_ids = ['hr_payroll.hr_rule_basic',
                                    'hr_payroll.hr_rule_net',
                                    'hr_payroll.hr_rule_taxable']
        for ext_rule_id in external_salary_rule_ids:
            try:
                salary_rule = self.env.ref(ext_rule_id)
                salary_rule.unlink()
            except ValueError:
                pass
        external_salary_category_ids = ['hr_payroll.ALW',
                                        'hr_payroll.BASIC',
                                        'hr_payroll.COMP',
                                        'hr_payroll.DED',
                                        'hr_payroll.GROSS',
                                        'hr_payroll.NET']
        for ext_categ_id in external_salary_category_ids:
            try:
                salary_rule = self.env.ref(ext_categ_id)
                salary_rule.unlink()
            except ValueError:
                pass

        salary_journal = self.env.ref('l10n_lt_payroll.atlyginimu_zurnalas')
        company = self.env.ref('base.main_company')
        saskaita_kreditas = self.env['account.account'].search([('company_id', '=', company.id), ('code', '=', '4480')],
                                                               limit=1)
        saskaita_debetas = self.env['account.account'].search([('company_id', '=', company.id), ('code', '=', '62031')],
                                                              limit=1)
        saskaita_gpm = self.env['account.account'].search([('company_id', '=', company.id), ('code', '=', '4481')],
                                                          limit=1)
        saskaita_sodra = self.env['account.account'].search([('company_id', '=', company.id), ('code', '=', '4482')],
                                                            limit=1)

        if not company.salary_journal_id:
            company.salary_journal_id = salary_journal.id
        if not company.advance_journal_id:
            company.advance_journal_id = salary_journal.id
        if not company.saskaita_kreditas:
            company.saskaita_kreditas = saskaita_kreditas.id
        if not company.saskaita_debetas:
            company.saskaita_debetas = saskaita_debetas.id
        if not company.saskaita_gpm:
            company.saskaita_gpm = saskaita_gpm.id
        if not company.saskaita_sodra:
            company.saskaita_sodra = saskaita_sodra.id

        salary_rules_mok = self.env['hr.salary.rule'].search([('code', 'in', ['VAL', 'MEN'])])
        for rule in salary_rules_mok:
            if not rule.account_debit:
                rule.account_debit = rule.company_id.saskaita_debetas.id
            if not rule.account_credit:
                rule.account_credit = rule.company_id.saskaita_kreditas.id
        gpm_rules = self.env['hr.salary.rule'].search([('code', 'in', ['GPM'])])
        for rule in gpm_rules:
            if not rule.account_debit:
                rule.account_debit = rule.company_id.saskaita_debetas.id
            if not rule.account_credit:
                rule.account_credit = rule.company_id.saskaita_gpm.id
        sodra_rules = self.env['hr.salary.rule'].search([('code', 'in', ['SDD', 'SDB'])])
        for rule in sodra_rules:
            if not rule.account_debit:
                rule.account_debit = rule.company_id.saskaita_debetas.id
            if not rule.account_credit:
                rule.account_credit = rule.company_id.saskaita_sodra.id
        # try:
        #     default_employee = self.env.ref('hr.employee_root')
        #     if default_employee.active:
        #         default_employee.toggle_active()
        # except ValueError:
        #     pass

        if not company.payroll_bank_journal_id:
            payroll_bank_journal = self.env['account.journal'].search([('type', '=', 'bank')], limit=1)
            if payroll_bank_journal:
                company.payroll_bank_journal_id = payroll_bank_journal.id

        self.env['account.journal'].search([]).write({'update_posted': True})
        self.env['hr.payroll.dashboard'].generate_dashboards()


HrPayrollStructure()


class HrPayslipLine(models.Model):

    _inherit = 'hr.payslip.line'

    def _get_partner_id(self, credit_account):
        """
        Get partner_id of slip line to use in account_move_line
        """
        # use partner of salary rule or fallback on employee's address

        register_partner_id = self.salary_rule_id.register_id.partner_id
        partner_id = register_partner_id.id or self.slip_id.employee_id.address_home_id.id
        return partner_id

    date = fields.Date(string='Data', related='slip_id.date_to', store=True)
    department_id = fields.Many2one('hr.department', string='Department', compute='_compute_department_id',  store=True)

    @api.depends('slip_id')
    def _compute_department_id(self):
        for rec in self:
            department_id = rec.slip_id.contract_id.with_context(date=rec.date).appointment_id.department_id
            if not department_id:
                department_id = rec.slip_id.contract_id.department_id
            if not department_id:
                department_id = rec.slip_id.employee_id.department_id
            rec.department_id = department_id


HrPayslipLine()


class HrPayslipAppointmentInfoLine(models.Model):

    _name = 'hr.payslip.appointment.info.line'

    payslip = fields.Many2one('hr.payslip', string='Algalapis', ondelete='cascade')
    appointment_id = fields.Many2one('hr.contract.appointment', string='Sutarties priedas')
    name = fields.Char(string='Priedas', related='appointment_id.display_name')
    struct = fields.Char(string='Atlyginimo struktūra', related='appointment_id.struct_id.display_name')
    template_type = fields.Selection(SCHEDULE_TEMPLATE_TYPES, string='Darbo laiko režimas', related='appointment_id.schedule_template_id.template_type')
    wage = fields.Float(string='Atlyginimas', related='appointment_id.wage')
    max_hours = fields.Float(string='Maksimumas (valandų)', compute='_get_max_work_amount')
    sodra_papildomai_proc = fields.Float(string='Papildomas SODRA kaupimas (%)', compute='_get_sodra_proc_for_display')
    etatas = fields.Float(string='Etatas', compute='_compute_etatas', digits=(16, 5))
    work_norm = fields.Float(string='Darbo normos koeficientas', compute='_compute_work_norm')
    use_npd = fields.Boolean(string='Naudoti NPD', compute='_compute_use_npd')

    @api.multi
    @api.depends('appointment_id')
    def _compute_use_npd(self):
        for rec in self:
            rec.use_npd = rec.appointment_id.use_npd

    @api.one
    @api.depends('appointment_id')
    def _compute_work_norm(self):
        self.work_norm = self.appointment_id.schedule_template_id.work_norm

    @api.one
    @api.depends('appointment_id')
    def _compute_etatas(self):
        self.etatas = self.appointment_id.schedule_template_id.etatas

    @api.one
    @api.depends('appointment_id')
    def _get_max_work_amount(self):
        ziniarastis_line = self.env['ziniarastis.period.line'].search([
            ('employee_id','=', self.appointment_id.employee_id.id),
            ('date_from', '=', self.payslip.date_from),
            ('date_to', '=', self.payslip.date_to),
            ('contract_id', '=', self.appointment_id.contract_id.id)
        ])
        if not ziniarastis_line:
            self.max_hours = 0.0
        else:
            self.max_hours = ziniarastis_line.with_context(appointment_id=self.appointment_id.id).num_regular_work_hours

    @api.one
    @api.depends('appointment_id', 'payslip.date_from')
    def _get_sodra_proc_for_display(self):
        proc = 0.0
        if self.appointment_id.sodra_papildomai:
            date = self.payslip.date_from if self.payslip.date_from else datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            taxes = self.appointment_id.contract_id.with_context(date=date).get_payroll_tax_rates(['sodra_papild_proc', 'sodra_papild_exponential_proc'])
            if date < '2019-01-01':
                proc = taxes['sodra_papild_proc']
            else:
                proc = taxes['sodra_papild_proc'] if self.appointment_id.sodra_papildomai_type == 'full' else taxes['sodra_papild_exponential_proc']
        self.sodra_papildomai_proc = proc


HrPayslipAppointmentInfoLine()