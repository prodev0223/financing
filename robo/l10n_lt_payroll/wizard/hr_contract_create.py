# coding=utf-8
from __future__ import division
from datetime import datetime

from dateutil.relativedelta import relativedelta
from odoo.addons.l10n_lt_payroll.model.hr_contract import SUTARTIES_RUSYS

from odoo import exceptions, models, fields, _, api, tools


class HrContractCreate(models.TransientModel):
    _name = 'hr.contract.create'

    def get_original_avansu_politika_selection(self):
        return self.env['res.company']._fields['avansu_politika'].selection

    def default_struct_id(self):
        return self.env['hr.payroll.structure'].search([('code', '=', 'MEN')], limit=1)

    def _default_employee_id(self):
        if self._context.get('active_id'):
            return self._context.get('active_id')

    name = fields.Char(string='Sutarties numeris', required=False)
    employee_id = fields.Many2one('hr.employee', string='Employee', default=_default_employee_id, readonly=True,
                                  ondelete="cascade")
    department_id = fields.Many2one('hr.department', string='Department')
    type_id = fields.Many2one('hr.contract.type', string='Contract Type', required=False,
                              default=lambda self: self.env['hr.contract.type'].search([], limit=1))
    job_id = fields.Many2one('hr.job', string='Job Title')
    struct_id = fields.Many2one('hr.payroll.structure', string='Salary structure', required=True,
                                default=default_struct_id, ondelete="cascade")
    date_start = fields.Date(string='Start Date', required=True, default=fields.Date.today())
    date_end = fields.Date(string='End Date')
    trial_date_end = fields.Date(string='Bandomojo periodo pabaiga')
    wage = fields.Float(string='Wage', digits=(16, 2), required=True, help='Basic Salary of the employee')
    sodra_papildomai = fields.Boolean(string='Sodra papildomai')
    sodra_papildomai_type = fields.Selection([('full', 'Pilnas (3%)'), ('exponential', 'Palaipsniui (Nuo 2022 - 2.7%)')],
                                             string='Sodros kaupimo būdas', default='full')
    avansu_politika_suma = fields.Float(string='Avanso dydis (neto)', digits=(2, 2), default=0.0)
    avansu_politika = fields.Selection(selection=get_original_avansu_politika_selection, string='Avansų politika',
                                       default='fixed_sum')
    avansu_politika_proc = fields.Float(string='Atlyginimo proc.',
                                        default=lambda self: self.env.user.company_id.avansu_politika_proc)
    antraeiles = fields.Boolean(string='Antraeilės pareigos', default=False)
    schedule_template_id = fields.Many2one('schedule.template', string='Darbo grafikas', required=True,
                                           domain="[('appointment_id', '=', False)]")
    use_npd = fields.Boolean(string='Naudoti NPD')
    rusis = fields.Selection(SUTARTIES_RUSYS, string='Sutarties rūšis', required=False, default='neterminuota')
    invalidumas = fields.Boolean(string='Neįgalumas',
                                 groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager")
    darbingumas = fields.Many2one('darbuotojo.darbingumas', string='Darbingumo lygis',
                                  groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager")
    struct_name = fields.Char(compute='_compute_struct_name')
    freeze_net_wage = fields.Boolean()
    order_date = fields.Date(string='Įsakymo data')
    contract_priority = fields.Selection([('foremost', 'Foremost'), ('secondary', 'Secondary')],
                                         string='Contract Priority', default='foremost')
    educational_institution_company_code = fields.Char(string='Educational institution company code')

    @api.one
    @api.depends('struct_id.code')
    def _compute_struct_name(self):
        self.struct_name = self.struct_id.code

    @api.multi
    def create_contract(self):
        self.ensure_one()
        # Throw an exception on outdated contract type
        if self.rusis == 'nenustatytos_apimties':
            raise exceptions.ValidationError(_('Employment contract type is outdated. Choose a different type.'))

        if not self.name:
            name = self.env['ir.sequence'].next_by_code('DU')
        else:
            name = self.name
        if not self.schedule_template_id:
            self.schedule_template_id = self.env['schedule.template'].create({
                'name': self.employee_id.name + ' 40 val. savaitė',
                'template_type': 'fixed',
                'wage_calculated_in_days': True,
                'shorter_before_holidays': True,
            })
            self.schedule_template_id.set_default_fixed_attendances()
        self.employee_id.sodra_papildomai = self.sodra_papildomai
        self.employee_id.sodra_papildomai_type = self.sodra_papildomai_type
        contract_values = {'employee_id': self.employee_id.id,
                           'date_start': self.date_start,
                           'date_end': self.date_end,
                           'name': name,
                           'department_id': self.department_id.id,
                           'type_id': self.type_id.id,
                           'struct_id': self.struct_id.id,
                           'rusis': self.rusis,
                           'order_date': self.order_date,
                           'educational_institution_company_code': self.educational_institution_company_code,
                           }
        contract = self.env['hr.contract'].create(contract_values)
        appointment_values = {'name': '1',  # First appointment for contract
                              'contract_id': contract.id,
                              'job_id': self.job_id.id,
                              'date_start': self.date_start,
                              'date_end': self.date_end,
                              'contract_terms_date_end': self.date_end,
                              'avansu_politika_suma': self.avansu_politika_suma,
                              'avansu_politika': self.avansu_politika,
                              'avansu_politika_proc': self.avansu_politika_proc,
                              'wage': self.wage,
                              'antraeiles': self.antraeiles,
                              'sodra_papildomai': self.sodra_papildomai,
                              'sodra_papildomai_type': self.sodra_papildomai_type,
                              'struct_id': self.struct_id.id,
                              'schedule_template_id': self.schedule_template_id.id,
                              'use_npd': self.use_npd,
                              'invalidumas': self.invalidumas,
                              'darbingumas': self.darbingumas.id,
                              'freeze_net_wage': self.freeze_net_wage,
                              'contract_priority': self.contract_priority or 'foremost',
                              }

        num_leaves = self.env['hr.holidays'].get_employee_default_holiday_amount(self.job_id.id,
                                                                                 self.schedule_template_id,
                                                                                 employee_dob=self.employee_id.birthday,
                                                                                 invalidumas=self.invalidumas)
        if self.schedule_template_id.template_type in ('suskaidytos', 'sumine', 'lankstus', 'individualus'):
            num_leaves = num_leaves * 7.0 / 5.0  # P3:DivOK
            appointment_values['leaves_accumulation_type'] = 'calendar_days'
        appointment_values['num_leaves_per_year'] = num_leaves

        if self.trial_date_end and self.trial_date_end >= self.date_start:
            appointment_values.update({'trial_date_start': self.date_start,
                                       'trial_date_end': self.trial_date_end})
            # Set trial dates on contract if first appointment has them
            contract.trial_date_start = self.date_start
            contract.trial_date_end = self.trial_date_end
        appointment = self.env['hr.contract.appointment'].create(appointment_values)

        contract_start_strp = datetime.strptime(self.date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
        contract_start_month_start = (contract_start_strp + relativedelta(day=1)).strftime(
            tools.DEFAULT_SERVER_DATE_FORMAT)
        contract_start_month_end = (contract_start_strp + relativedelta(day=31)).strftime(
            tools.DEFAULT_SERVER_DATE_FORMAT)
        ziniarastis_period = self.env['ziniarastis.period'].search([
            ('date_from', '=', contract_start_month_start),
            ('date_to', '=', contract_start_month_end)
        ])

        prev_date = (contract_start_strp - relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        prev_contract = self.env['hr.contract'].search([
            ('employee_id', '=', contract.employee_id.id),
            ('date_end', '=', prev_date)
        ])
        if not prev_contract:
            HrHolidaysFix = self.env['hr.holidays.fix']
            existing_fix = HrHolidaysFix.search([
                ('employee_id', '=', self.employee_id.id),
                ('date', '=', prev_date),
                ('type', '=', 'set')
            ])
            if not existing_fix:
                HrHolidaysFix.create({
                    'employee_id': self.employee_id.id,
                    'date': prev_date,
                    'type': 'set',
                })

        if ziniarastis_period:
            contract_line = ziniarastis_period.related_ziniarasciai_lines.filtered(
                lambda l: l.contract_id.id == contract.id)
            if not contract_line:
                self.env['ziniarastis.period.line'].create({
                    'ziniarastis_period_id': ziniarastis_period.id,
                    'employee_id': contract.employee_id.id,
                    'contract_id': contract.id,
                    'date_from': ziniarastis_period.date_from,
                    'date_to': ziniarastis_period.date_to,
                    'working_schedule_number': contract.working_schedule_number
                })

            if self.date_start == contract_start_month_start:
                if prev_contract:
                    ziniarastis_period.related_ziniarasciai_lines.filtered(
                        lambda l: l.contract_id.id == prev_contract.id).unlink()

        self.env['hr.holidays'].split_employee_holidays(self.employee_id)

        if self._context.get('no_action', False):
            return contract
        else:
            return {
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'hr.contract.appointment',
                'view_id': False,
                'target': 'self',
                'res_id': appointment.id
            }


HrContractCreate()
