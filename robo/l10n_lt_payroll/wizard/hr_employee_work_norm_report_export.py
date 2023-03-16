# -*- coding: utf-8 -*-

from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _, exceptions, tools


class HrEmployeeWorkNormReportExport(models.TransientModel):
    _name = 'hr.employee.work.norm.report.export'
    _rec_name = 'name'
    _description = 'Work norm report'

    def default_month(self):
        current_month = datetime.now().month
        previous_month = current_month - 1
        return 12 if previous_month == 0 else previous_month

    def default_year(self):
        default_month = self.default_month()
        current_year = datetime.now().year
        return current_year - 1 if default_month == 12 else current_year

    name = fields.Char()
    employees_to_export = fields.Selection([('all', 'All'), ('by_department', 'By Department'), ('select', 'Select')],
                                           string='Which employees to export', default='all')
    all_employees = fields.Boolean(string="Export report for all employees", default=True)  # UNUSED
    department_ids = fields.Many2many(comodel_name='hr.department', string='Departments')
    employee_ids = fields.Many2many(comodel_name="hr.employee", string="Employees",
                                    domain=['|', ('active', '=', False), ('active', '=', True)])
    year = fields.Selection(string="Year", selection='_selection_year', required=True,
                            default=lambda self: self.default_year())
    month = fields.Selection(string="Month", selection='_selection_month', required=True,
                             default=lambda self: self.default_month())
    date_from = fields.Date(string="Date From", compute='_compute_dates')
    date_to = fields.Date(string="Date To", compute='_compute_dates')

    @api.multi
    def name_get(self):
        return [(rec.id, _('Work norm report {}').format(rec.id)) for rec in self]

    @api.model
    def _selection_year(self):
        current_year = datetime.now().year
        return [(year, str(year)) for year in range(current_year-3, current_year+2)]

    @api.model
    def _selection_month(self):
        return [(month, str(month)) for month in range(1, 13)]

    @api.multi
    @api.depends('year', 'month')
    def _compute_dates(self):
        for rec in self:
            if not rec.year or not rec.month:
                continue
            first_of_month = datetime(int(rec.year), int(rec.month), 1)
            last_of_month = first_of_month + relativedelta(day=31)
            rec.date_from = first_of_month.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            rec.date_to = last_of_month.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.constrains('employee_ids', 'employees_to_export', 'department_ids')
    def _check_employees_have_been_selected(self):
        for rec in self:
            if rec.employees_to_export == 'by_department' and not rec.department_ids:
                raise exceptions.UserError(_('No departments selected'))
            elif rec.employees_to_export == 'select' and not rec.employee_ids:
                raise exceptions.UserError(_('No employees selected'))

    @api.multi
    def export_xlsx(self):
        self.ensure_one()
        employees_to_export = None  # Specifying no employees will export report for all employees with active contracts
        if self.employees_to_export == 'by_department':
            employees_to_export = self.env['hr.contract.appointment'].sudo().search([
                '&',
                '|',
                ('department_id', 'in', self.department_ids.ids),
                '&',
                ('employee_id.department_id', 'in', self.department_ids.ids),
                ('department_id', '=', False),
                ('date_start', '<=', self.date_to),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', self.date_from)
            ]).mapped('employee_id')
            if not employees_to_export:
                raise exceptions.UserError(_('Selected departments don\'t have any employees that can be exported'))
        elif self.employees_to_export == 'select':
            employees_to_export = self.employee_ids
        return self.env['hr.employee.work.norm.report'].export_xlsx(self.date_from, self.date_to, employees_to_export)
