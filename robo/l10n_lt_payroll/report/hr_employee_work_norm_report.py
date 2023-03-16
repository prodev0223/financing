# -*- coding: utf-8 -*-

from odoo import models, api, exceptions, _

try:
    from odoo.addons.robo_core.report.robo_xlsx_report import RoboXLSXReport
    from xlsxwriter.utility import xl_rowcol_to_cell
except ImportError:
    RoboXLSXReport = object


class HrEmployeeWorkNormReport(models.Model):
    _name = 'hr.employee.work.norm.report'
    _description = 'Work norm report'

    @api.model
    def _get_data(self, date_from, date_to, employees=None):

        # Form contract element
        HrContract = self.env['hr.contract'].with_context(active_test=False)

        # Get regular data for period
        regular_hours_for_period = self.env['hr.payroll'].standard_work_time_period_data(
            date_from, date_to
        ).get('hours', 0.0)
        regular_hours_for_six_day_period = self.env['hr.payroll'].standard_work_time_period_data(
            date_from, date_to, six_day_work_week=True
        ).get('hours', 0.0)

        # Find contracts and employees
        contract_domain = [
            ('date_start', '<=', date_to),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', date_from)
        ]
        if employees:
            contract_domain.append(('employee_id', 'in', employees.ids))
            contracts = HrContract.search(contract_domain)
        else:
            contracts = HrContract.search(contract_domain)
            employees = contracts.mapped('employee_id')

        # Sort the employees
        employees = employees.sorted(key=lambda e: e.name)

        # Get the amount of hours each employee has worked for the period
        worked_time_data = employees.get_worked_time(date_from, date_to)

        timesheet_lines = self.env['ziniarastis.day'].sudo().search([
            ('date', '<=', date_to),
            ('date', '>=', date_from),
            ('employee_id', 'in', employees.ids),
            ('ziniarastis_period_line_id.state', '=', 'done')
        ]).mapped('ziniarastis_period_line_id')

        data = []
        for employee in employees:
            # Find related payroll objects
            employee_contracts = contracts.filtered(lambda c: c.employee_id == employee)
            if not employee_contracts:
                # If an employee was selected and does not have a contract - show empty data.
                data.append({
                    'employee': {'value': employee.name},
                    'post': {'value': '-'},
                    'work_week': {'value': '-'},
                    'regular_hours': {'value': 0.0},
                    'work_norm': {'value': 0.0},
                    'worked_time': {'value': 0.0},
                    'deviation': {'value': 0.0}
                })
                continue
            main_contract = employee_contracts.sorted(key=lambda c: c.date_start, reverse=True)[0]
            appointment = main_contract.with_context(date=date_to).appointment_id
            schedule_template = appointment.schedule_template_id
            employee_timesheet_lines = timesheet_lines.filtered(lambda l: l.employee_id == employee)
            use_holiday_records = not employee_timesheet_lines or \
                                  any(state != 'done' for state in employee_timesheet_lines.mapped('state'))

            # Determine payroll vars
            six_day_work_week = schedule_template.six_day_work_week
            # is_accumulative_work_time_accounting = schedule_template.template_type == 'sumine'

            work_norm = 0.0
            for contract in employee_contracts:
                contract_date_from = max(contract.date_start, date_from)
                contract_date_to = min(contract.date_end or date_to, date_to)
                # Get work norm
                work_norm += employee.with_context(use_holiday_records=use_holiday_records).employee_work_norm(
                    calc_date_from=contract_date_from,
                    calc_date_to=contract_date_to,
                    contract=contract,
                    skip_leaves=True,
                ).get('hours', 0.0)

            # Get worked time
            employee_worked_time = worked_time_data.get(employee.id, dict()).get('worked_time', 0.0)
            regular_hours = regular_hours_for_period if not six_day_work_week else regular_hours_for_six_day_period
            data.append({
                'employee': {'value': employee.name},
                'post': {'value': schedule_template.etatas or '-'},
                'work_week': {'value': _('5 w.d.') if not six_day_work_week else _('6 w.d.')},
                'regular_hours': {'value': regular_hours},
                'work_norm': {'value': work_norm},
                'worked_time': {'value': employee_worked_time},
                'deviation': {'value': work_norm-employee_worked_time}
            })

        return data

    @api.model
    def export_xlsx(self, date_from, date_to, employees=None):
        user = self.env.user
        has_sufficient_rights = user.is_premium_manager() or user.is_accountant() or user.is_hr_manager()
        if not has_sufficient_rights:
            raise exceptions.AccessError(_('You do not have sufficient rights to access this report'))

        data = self.sudo()._get_data(date_from, date_to, employees)
        columns = [
            {'name': 'employee', 'string': _('Employee')},
            {'name': 'post', 'string': _('Post'), 'is_number': True},
            {'name': 'work_week', 'string': _('Work week'), 'is_number': True},
            {'name': 'regular_hours', 'string': _('Regular Hours'), 'is_number': True},
            {'name': 'work_norm', 'string': _('Work norm'), 'is_number': True},
            {'name': 'worked_time', 'string': _('Worked time'), 'is_number': True},
            {'name': 'deviation', 'string': _('Deviation'), 'is_number': True},
        ]

        action = self.env.ref('l10n_lt_payroll.action_hr_employee_work_norm_report_xlsx')
        action = action.read()[0]
        action['datas'] = {
            'sheets': [{
                'data': data,
                'columns': columns,
                'landscape': False
            }],
            'date_from': date_from,
            'date_to': date_to,
            'report_name': _('Work norm report')
        }
        return action


class EmployeeWorkNormXLSXReport(RoboXLSXReport):

    def generate_xlsx_report(self, workbook, data, record):
        super(EmployeeWorkNormXLSXReport, self).generate_xlsx_report(workbook, data, record)


EmployeeWorkNormXLSXReport('report.l10n_lt_payroll.employee_work_norm_xlsx_report', 'hr.employee.work.norm.report')
