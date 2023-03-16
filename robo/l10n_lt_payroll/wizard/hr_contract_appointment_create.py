# coding=utf-8
from __future__ import division
from odoo import fields, _, api, models, tools
from datetime import datetime

from dateutil.relativedelta import relativedelta


class HrContractAppointmentCreate(models.TransientModel):

    _name = 'hr.contract.appointment.create'

    def get_original_avansu_politika_selection(self):
        return self.env['res.company']._fields['avansu_politika'].selection

    def default_contract(self):
        return self._context.get('contract_id', False)

    def default_struct_id(self):
        return self.env['hr.payroll.structure'].search([('code', '=', 'MEN')], limit=1)

    def default_date_start(self):
        contract = self.env['hr.contract'].browse(self._context.get('contract_id', False))
        return contract.date_start

    def default_date_end(self):
        contract = self.env['hr.contract'].browse(self._context.get('contract_id', False))
        return contract.date_end

    name = fields.Char(string='Appointment Reference', required=True)
    contract_id = fields.Many2one('hr.contract', string='Contract', required=True, readonly=True,
                                  default=default_contract, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', string='Employee', related='contract_id.employee_id', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department')
    type_id = fields.Many2one('hr.contract.type', string='Contract Type', required=False,
                              default=lambda self: self.env['hr.contract.type'].search([], limit=1))
    job_id = fields.Many2one('hr.job', string='Job Title')
    struct_id = fields.Many2one('hr.payroll.structure', string='Salary structure', required=True, default=default_struct_id)
    date_start = fields.Date(string='Start Date', required=True, default=default_date_start)
    date_end = fields.Date(string='End Date', default=default_date_end)
    wage = fields.Float(string='Wage', digits=(16, 2), required=True, help='Basic Salary of the employee')
    sodra_papildomai = fields.Boolean(string='Sodra papildomai')
    sodra_papildomai_type = fields.Selection([('full', 'Pilnas (3%)'), ('exponential', 'Palaipsniui (Nuo 2022 - 2.7%)')],
                                             string='Sodros kaupimo būdas', default='full')
    avansu_politika_suma = fields.Float(string='Avanso dydis (neto)', digits=(2, 2), default=0.0)
    avansu_politika = fields.Selection(selection=get_original_avansu_politika_selection, string='Avansų politika',
                                       default='fixed_sum')
    avansu_politika_proc = fields.Float(string='Atlyginimo proc.',
                                        default=lambda self: self.env.user.company_id.avansu_politika_proc)
    schedule_template_id = fields.Many2one('schedule.template', string='Darbo grafikas', required=True, domain="[('appointment_id', '=', False)]")
    use_npd = fields.Boolean(string='Naudoti NPD')
    invalidumas = fields.Boolean(string='Neįgalumas')
    darbingumas = fields.Many2one('darbuotojo.darbingumas', string='Darbingumo lygis')
    struct_name = fields.Char(compute='_compute_struct_name')
    contract_priority = fields.Selection([('foremost', 'Foremost'), ('secondary', 'Secondary')],
                                         string='Contract Priority', default='foremost')

    @api.one
    @api.depends('struct_id.code')
    def _compute_struct_name(self):
        self.struct_name = self.struct_id.code

    @api.onchange('contract_id')
    def set_defaults(self):
        if self.contract_id:
            last_appointment = self.contract_id.get_last_appointment()
            if last_appointment:
                self.name = last_appointment.name
                self.department_id = last_appointment.department_id.id
                self.type_id = last_appointment.type_id.id
                self.job_id = last_appointment.job_id.id
                self.struct_id = last_appointment.struct_id.id
                self.date_start = last_appointment.date_start
                self.date_end = last_appointment.date_end
                self.wage = last_appointment.wage
                self.sodra_papildomai = last_appointment.sodra_papildomai
                self.sodra_papildomai_type = last_appointment.sodra_papildomai_type
                self.avansu_politika_suma = last_appointment.avansu_politika_suma
                self.avansu_politika = last_appointment.avansu_politika
                self.avansu_politika_proc = last_appointment.avansu_politika_proc
                self.use_npd = last_appointment.use_npd
                self.invalidumas = last_appointment.invalidumas
                self.darbingumas = last_appointment.darbingumas.id
                self.contract_priority = last_appointment.contract_priority or 'foremost'

    @api.multi
    def create_appointment(self):
        existing_app_end_date = (datetime.strptime(self.date_start, tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        existing_appointment = self.env['hr.contract.appointment'].search([('contract_id', '=', self.contract_id.id),
                                                                           ('date_start', '<=', existing_app_end_date),
                                                                          '|',
                                                                           ('date_end', '=', False),
                                                                           ('date_end', '>', existing_app_end_date)])
        for appointment in existing_appointment:
            appointment.date_end = existing_app_end_date
        job_id = self.contract_id.job_id.id or self.employee_id.job_id.id

        num_leaves_default = self.env['hr.holidays'].get_employee_default_holiday_amount(
            job_id,
            self.schedule_template_id,
            employee_dob=self.employee_id.birthday,
            invalidumas=self.invalidumas
        )
        num_leaves_last_appointment = self.contract_id.get_last_appointment().num_leaves_per_year if self.contract_id \
            else 0.0
        num_leaves = max(num_leaves_default, num_leaves_last_appointment)

        leaves_accumulation_type = 'work_days'
        if self.schedule_template_id.template_type in ('suskaidytos', 'sumine', 'lankstus', 'individualus'):
            num_leaves = num_leaves * 7.0 / 5.0  # P3:DivOK
            leaves_accumulation_type = 'calendar_days'
        vals = {
            'name': self.name,
            'contract_id': self.contract_id.id,
            'type_id': self.type_id.id,
            'job_id': self.job_id.id or self.contract_id.job_id.id or self.employee_id.job_id.id,
            'struct_id': self.struct_id.id,
            'date_start': self.date_start,
            'date_end': self.date_end,
            'wage': self.wage,
            'sodra_papildomai': self.sodra_papildomai,
            'sodra_papildomai_type': self.sodra_papildomai_type,
            'avansu_politika_suma': self.avansu_politika_suma,
            'avansu_politika': self.avansu_politika,
            'avansu_politika_proc': self.avansu_politika_proc,
            'schedule_template_id': self.schedule_template_id.id,
            'num_leaves_per_year': num_leaves,
            'leaves_accumulation_type': leaves_accumulation_type,
            'use_npd': self.use_npd,
            'invalidumas': self.invalidumas,
            'darbingumas': self.darbingumas.id,
            'contract_priority': self.contract_priority or 'foremost',
        }
        appointment_id = self.env['hr.contract.appointment'].create(vals)

        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.contract.appointment',
            'view_id': False,
            'res_id': appointment_id.id,
        }


HrContractAppointmentCreate()