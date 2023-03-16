# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, tools


class EmployeeCountReport(models.TransientModel):
    _name = 'employee.count.report'

    def default_date_from(self):
        return self.env.user.company_id.compute_fiscalyear_dates()['date_from'].strftime(
            tools.DEFAULT_SERVER_DATE_FORMAT)

    employee_count = fields.Float(string='Vidutinis darbuotojų skaičius per periodą', compute='_get_employee_count')
    show_warning = fields.Boolean(compute='_compute_show_warning')
    date_from = fields.Date(string='Periodo pradžia', default=default_date_from, required=True)
    date_to = fields.Date(string='Periodo pabaiga', compute='_compute_date_to_date_from_factual')
    date_from_factual = fields.Date(compute='_compute_date_to_date_from_factual')

    @api.one
    @api.depends('date_from')
    def _compute_date_to_date_from_factual(self):
        date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        self.date_to = (date_from_dt + relativedelta(months=11, day=31)).strftime(
            tools.DEFAULT_SERVER_DATE_FORMAT)
        self.date_from_factual = (date_from_dt - relativedelta(months=1, day=1)).strftime(
            tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.one
    @api.depends('date_from')
    def _compute_show_warning(self):
        all_employees = self.env['hr.employee'].search(['|', ('active', '=', True), ('active', '=', False)])
        create_dates = all_employees.mapped('create_date')
        min_create_date = datetime.strptime(min(create_dates), tools.DEFAULT_SERVER_DATETIME_FORMAT)
        self.show_warning = relativedelta(datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT),
                                          min_create_date).years < 1

    @api.one
    @api.depends('date_from')
    def _get_employee_count(self):
        """
        Compute average employee count according to formula provided by
        https://e-seimas.lrs.lt/portal/legalAct/lt/TAD/TAIS.317054
                D12(-1)                                                           D12
                _______ + D1 + D2 + D3 + D4 +D5 + D6 + D7 + D8 + D9 + D10 + D11 + ___
                   2                                                               2
            D = _____________________________________________________________________
                                                12
        where Dx is employee count at the end of month x
        :return: None
        """
        date_from = datetime.strptime(self.date_from_factual, tools.DEFAULT_SERVER_DATE_FORMAT)
        employee_amount = 0
        ziniarastis_period_lines = self.env['ziniarastis.period.line'].search([
            ('date_from', '>=', date_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
        ])
        to_divide_by = 12.0
        for i in range(0, 13):
            month_start = (date_from + relativedelta(months=i, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            month_end = (date_from + relativedelta(months=i, day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            month_lines = ziniarastis_period_lines.filtered(
                lambda l: l.date_from == month_start and l.date_to == month_end)

            month_days = month_lines.mapped('ziniarastis_day_ids').filtered(lambda r: r.date == month_end)

            # if datetime.strptime(month_end, tools.DEFAULT_SERVER_DATE_FORMAT) < datetime.utcnow():
            #     payslips_for_month = self.env['hr.payslip'].search_count([
            #         ('date_from', '=', month_start),
            #         ('date_to', '=', month_end),
            #         ('state', '!=', 'draft')
            #     ])
            #     invoices_for_month = self.env['account.invoice'].search_count([
            #         ('date_invoice', '<=', month_end),
            #         ('date_invoice', '>=', month_start),
            #         ('state', 'in', ['open', 'paid'])
            #     ])
            #     if payslips_for_month > 0 or invoices_for_month > 0:
            #         to_divide_by += 1.0
            # else:
            #     to_divide_by += 1.0

            employee_ids = list()
            for day in month_days:
                contract = day.employee_id.with_context(date=day.date).contract_id
                day_line_codes = day.mapped('ziniarastis_day_lines.tabelio_zymejimas_id.code')
                is_on_special_holidays = any(code in ['G', 'PV'] for code in day_line_codes)
                if contract and not is_on_special_holidays:
                    employee_ids.append(day.employee_id.id)

            to_add = len(set(employee_ids))
            if i in [0, 12]:
                # P3:DivOK
                to_add = to_add / 2.0
            employee_amount += to_add

        self.employee_count = employee_amount / min(to_divide_by, 12.0) if not tools.float_is_zero(to_divide_by,
                                                                                                   precision_digits=2) else 0.0
