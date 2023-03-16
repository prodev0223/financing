# -*- coding: utf-8 -*-

from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, exceptions, tools
from odoo.tools.translate import _


class ExportWizard(models.TransientModel):
    _name = 'schedule.export.wizard'

    def default_work_schedule_to_use(self):
        month_start, month_end = self.get_schedule_month_dates()
        default_work_schedule = self.env['work.schedule'].determine_work_schedule(month_start)
        planned_schedule = self.env.ref('work_schedule.planned_company_schedule')
        return 'planned' if default_work_schedule == planned_schedule else 'factual'

    user_group_above_basic = fields.Boolean(default="_get_user_group")
    export_for_all_users = fields.Boolean(default=True, string="Eksportuoti visų darbuotojų grafikus")
    employee_ids = fields.Many2many('hr.employee', string='Darbuotojai', readonly=True)
    export_for_all_departments = fields.Boolean(default=True, string="Eksportuoti visų skyrių grafikus")
    department_ids = fields.Many2many('hr.department', string='Skyriai', required=False)
    export_for_all_job_ids = fields.Boolean(default=True, string="Eksportuoti visų pareigų grafikus")
    job_ids = fields.Many2many('hr.job', string='Pareigos', required=False)
    export_view_type = fields.Selection([('month_view', _('Mėnuo')),
                                         ('week_view', _('Savaitė'))], string='Eksportavimo rodinys', default='month_view')
    show_other_month_days = fields.Boolean(default=True, string="Rodyti kitų mėnesių grafikus")
    break_users_separate_tables = fields.Boolean(default=False, string="Darbuotojai atskirose lentelėse")
    break_users_separate_pages = fields.Boolean(default=False, string="Darbuotojai atskirose puslapiuose")
    work_schedule_to_use = fields.Selection(selection=[('planned', 'Planned'),
                                                       ('factual', 'Factual'),
                                                       ],
                                            string='Work schedule to use',
                                            default=default_work_schedule_to_use)

    @api.one
    @api.depends('user_group_above_basic')
    def _get_user_group(self):
        if self.env.user.has_group('work_schedule.group_schedule_manager') or self.env.user.has_group(
                'work_schedule.group_schedule_super'):
            self.user_group_above_basic = True

    @api.model
    def default_get(self, fields):
        res = super(ExportWizard, self).default_get(fields)
        department = self._context.get('department', False)
        if department and len(self.env['hr.department'].sudo().search([('id','=',department)])) == 1:
            res['export_for_all_departments'] = False
            res['department_ids'] = [(6, 0, [int(department)])]
        return res

    def get_schedule_month_dates(self):
        month = self._context.get('sched_month', [])
        year = self._context.get('sched_year', [])
        if month and year:
            month_start = (datetime.utcnow().date() + relativedelta(month=month, year=year, day=1)).strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT)
            month_end = (datetime.utcnow().date() + relativedelta(month=month, year=year, day=31)).strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT)
            return (month_start, month_end)
        else:
            raise exceptions.UserError(_("Įvyko sistemos klaida, prašome perkrauti puslapį."))

    @api.one
    def validate_export(self):
        if not self.env.user.is_schedule_manager:
            self.write({'employee_ids': [(6, 0, self.env.user.employee_ids)]})
            self.break_users_separate_tables = False
            self.break_users_separate_pages = False
        else:
            month_start, month_end = self.get_schedule_month_dates()
            start_date_dt = datetime.strptime(month_start, tools.DEFAULT_SERVER_DATE_FORMAT)
            year = start_date_dt.year
            month = start_date_dt.month
            month_line_ids = self.env['work.schedule.line'].search([
                ('year', '=', year),
                ('month', '=', month)
            ])
            if self.export_for_all_users:
                month_employee_ids = month_line_ids.mapped('employee_id.id')
                self.write({'employee_ids': [(6, 0, month_employee_ids)]})
            if self.export_for_all_departments:
                month_employee_ids = month_line_ids.mapped('department_id.id')
                self.write({'department_ids': [(6, 0, month_employee_ids)]})
            if self.export_for_all_job_ids:
                month_job_ids = month_line_ids.mapped('employee_job_id.id')
                self.write({'job_ids': [(6, 0, month_job_ids)]})

    @api.multi
    def export_pdf(self):
        # TODO DO IT
        self.validate_export()

    @api.multi
    def export_xls(self):
        self.ensure_one()
        self.validate_export()
        if self.work_schedule_to_use == 'planned':
            work_schedule_to_use = self.env.ref('work_schedule.planned_company_schedule').id
        else:
            work_schedule_to_use = self.env.ref('work_schedule.factual_company_schedule').id
        month_start, month_end = self.get_schedule_month_dates()
        month_days = self.with_context(active_test=False).env['work.schedule.day'].search(
            [('date', '>=', month_start), ('date', '<=', month_end),
             ('employee_id', 'in', self.with_context(active_test=False).employee_ids.mapped('id')),
             ('department_id', 'in', self.department_ids.mapped('id')),
             ('employee_id.job_id','in', self.with_context(active_test=False).job_ids.mapped('id')),
             ('work_schedule_id', '=', work_schedule_to_use),
             ])
        data = {'show_other_month_days': self.show_other_month_days,
                'break_users_separate_tables': self.break_users_separate_tables,
                'break_users_separate_pages': self.break_users_separate_pages,
                'export_view_type': self.export_view_type}
        if month_days:
            return month_days.export_excel(data)
        else:
            raise exceptions.UserError(_("Pagal pasirinktus kriterijus nėra grafikų, kuriuos būtų galima eksportuoti"))

    @api.model
    def get_wizard_view_id(self):
        return self.env.ref('work_schedule.schedule_export_wizard_form').id


ExportWizard()
