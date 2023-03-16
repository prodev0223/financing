# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, exceptions, fields, models, tools

from odoo.addons.l10n_lt_payroll.model.hr_contract_appointment import get_days_intersection


SUTARTIES_RUSYS = [
    ('neterminuota', 'Neterminuota'),
    ('terminuota', 'Terminuota'),
    ('laikina_terminuota', 'Laikino darbo (terminuota)'),
    ('laikina_neterminuota', 'Laikino darbo (neterminuota)'),
    ('pameistrystes', 'Pameistrystes'),
    ('nenustatytos_apimties', 'Nenustatytos apimties'),
    ('projektinio_darbo', 'Projektinio darbo'),
    ('vietos_dalijimosi', 'Darbo vietos dalinimosi'),
    ('keliems_darbdaviams', 'Darbo keliems darbdaviams'),
    ('sezoninio', 'Sezoninio darbo'),
    ('voluntary_internship', 'Savanoriškos praktikos'),
    ('educational_internship', 'Švietimo įstaigos praktikos'),
]


class HrContract(models.Model):
    _inherit = 'hr.contract'

    def default_kompanija(self):
        return self.env.user.company_id

    ends_on_the_last_work_day_of_month = fields.Boolean(compute='_compute_ends_on_the_last_work_day_of_month')
    ends_the_work_relation = fields.Boolean(compute='_compute_ends_the_work_relation')
    date_start = fields.Date(track_visibility='onchange')
    date_end = fields.Date(track_visibility='onchange')
    trial_date_start = fields.Date(track_visibility='onchange')
    trial_date_end = fields.Date(track_visibility='onchange')
    appointment_ids = fields.One2many('hr.contract.appointment', 'contract_id', string='Appointments')
    appointments_count = fields.Integer(string='Number of appointments', compute='_appointments_count')
    company_id = fields.Many2one('res.company', string='Kompanija', required=True, default=default_kompanija)
    wage = fields.Float(compute='_compute_fields', store=True, required=False)
    sodra_papildomai = fields.Boolean(compute='_compute_sodra_papildomai')
    sodra_papildomai_type = fields.Selection([('full', 'Pilnas (3%)'), ('exponential', 'Palaipsniui (Nuo 2022 - 2.7%)')],
                                             string='Sodros kaupimo būdas', default='full',
                                             compute='_compute_sodra_papildomai_type')
    struct_id = fields.Many2one('hr.payroll.structure', compute='_compute_fields', store=True, required=False)
    working_hours = fields.Many2one('resource.calendar', required=False)
    antraeiles = fields.Boolean(string='Antraeiles', compute='_compute_fields', store=True, required=False)
    job_id = fields.Many2one('hr.job', compute='_compute_fields', store=True)
    department_id = fields.Many2one('hr.department', compute='_compute_fields', store=True)
    avansu_politika_suma = fields.Float(string='Avanso dydis (neto)', digits=(2, 2), compute='_compute_fields',
                                        store=True)
    type_id = fields.Many2one('hr.contract.type', required=False)
    appointment_id = fields.Many2one('hr.contract.appointment', compute='_appointment_id', string='Priedas',
                                     help='Nurodytos datos priedas arba paskutinis galiojęs')
    work_relation_start_date = fields.Date(compute='_compute_work_relation_start_date')
    work_relation_end_date = fields.Date(compute='_compute_work_relation_end_date')
    order_date = fields.Date(string='Įsakymo data')
    is_fixed_term = fields.Boolean(string='Is fixed term', compute='_compute_is_fixed_term')
    educational_institution_company_code = fields.Char(string='Educational institution company code')

    @api.onchange('trial_date_start', 'trial_date_end')
    def _onchange_trial_period(self):
        return {
            'warning':
            {
                'title': _('Warning'),
                'message': _('Make sure to change the trial dates on contract appointment (or appointments if there '
                             'are multiple) accordingly'),
            }
        }

    @api.multi
    @api.depends('rusis')
    def _compute_is_fixed_term(self):
        for rec in self:
            rec.is_fixed_term = rec.rusis in ['terminuota', 'pameistrystes', 'projektinio_darbo']

    @api.one
    @api.depends('date_end', 'appointment_ids', 'appointment_ids.date_start')
    def _compute_ends_on_the_last_work_day_of_month(self):
        """
            Checks if the contract ends on the last working day of the month.
            For accumulative work time accounting the last work day of a month is the last calendar day of the month.
        """
        if not self.date_end:
            self.ends_on_the_last_work_day_of_month = False
        else:
            contract_appointments = self.appointment_ids.sorted(key=lambda a: a.date_start, reverse=True)
            last_appointment = contract_appointments[0] if contract_appointments else None

            if last_appointment and last_appointment.schedule_template_id.template_type == 'sumine':
                last_work_day = datetime.strptime(self.date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
                last_work_day = last_work_day + relativedelta(day=31)
                last_work_day = last_work_day.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            else:
                last_work_day = self.env['hr.payroll'].get_last_work_day(date=self.date_end)
            self.ends_on_the_last_work_day_of_month = self.date_end >= last_work_day

    @api.one
    @api.depends('date_end', 'employee_id.contract_ids')
    def _compute_ends_the_work_relation(self):
        """
            Checks if the current contract ends. If so - checks if there's a contract that starts immediately after this
            one ends. If the contract does end and there's no contract that starts straight after - the work relation is
            terminated.
        """
        if not self.date_end:
            self.ends_the_work_relation = False
        else:
            date_end_dt = datetime.strptime(self.date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
            next_day_after_contract_ends_dt = date_end_dt + relativedelta(days=1)
            next_day_after_contract_ends = next_day_after_contract_ends_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            employee_contracts = self.employee_id.contract_ids
            next_contract = employee_contracts.filtered(lambda c: c.date_start == next_day_after_contract_ends)
            self.ends_the_work_relation = not next_contract

    @api.model
    def closest_work_dates(self, date, include_current=True, contract_id=False):
        try:
            weekday = date.weekday()
            date_dt = date
        except:
            date_dt = False
        if not date_dt:
            try:
                date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
            except:
                date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)

        date_dt = date_dt + relativedelta(hour=0, minute=0, second=0)

        free_weekdays = [5, 6]
        appointments = False
        if contract_id:
            appointments = contract_id.mapped('appointment_id')

        min_date = (date_dt + relativedelta(months=-1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        max_date = (date_dt + relativedelta(months=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        holiday_dates = self.env['sistema.iseigines'].search([
            ('date', '<=', max_date),
            ('date', '>=', min_date)
        ]).mapped('date')

        next_closest_work_day = False
        previous_closest_work_day = False

        curr_date_check = date_dt
        while not next_closest_work_day:
            curr_date_check_strf = curr_date_check.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_is_holiday = curr_date_check_strf in holiday_dates
            if date_is_holiday:
                curr_date_check += relativedelta(days=1)
                continue
            curr_check_weekday = curr_date_check.weekday()
            off_days = free_weekdays
            if appointments:
                appointment = appointments.filtered(lambda a: a.date_start <= curr_date_check_strf and
                                                              (not a.date_end or a.date_end >= curr_date_check_strf))
                if appointment:
                    off_days = appointment.schedule_template_id.off_days()
            if curr_date_check_strf > max_date:
                max_date = (datetime.strptime(max_date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(months=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                holiday_dates = self.env['sistema.iseigines'].search([
                    ('date', '<=', max_date),
                    ('date', '>=', min_date)
                ]).mapped('date')

            weekday_is_free_day = curr_check_weekday not in off_days
            if weekday_is_free_day and (curr_date_check != date_dt or include_current):
                next_closest_work_day = curr_date_check_strf
            else:
                curr_date_check += relativedelta(days=1)

        max_date = (date_dt + relativedelta(months=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        curr_date_check = date_dt
        while not previous_closest_work_day:
            curr_date_check_strf = curr_date_check.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_is_holiday = curr_date_check_strf in holiday_dates
            if date_is_holiday:
                curr_date_check -= relativedelta(days=1)
                continue
            curr_check_weekday = curr_date_check.weekday()
            off_days = free_weekdays
            if appointments:
                appointment = appointments.filtered(lambda a: a.date_start <= curr_date_check_strf and
                                                              (not a.date_end or a.date_end >= curr_date_check_strf))
                if appointment:
                    off_days = appointment.schedule_template_id.off_days()
            if curr_date_check_strf < min_date:
                min_date = (datetime.strptime(min_date, tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(months=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                holiday_dates = self.env['sistema.iseigines'].search([
                    ('date', '<=', max_date),
                    ('date', '>=', min_date)
                ]).mapped('date')

            weekday_is_free_day = curr_check_weekday not in off_days
            if weekday_is_free_day and (curr_date_check != date_dt or include_current):
                previous_closest_work_day = curr_date_check_strf
            else:
                curr_date_check -= relativedelta(days=1)
        return {
            'previous': previous_closest_work_day,
            'next': next_closest_work_day
        }

    @api.multi
    def toggle_remote_work(self, date_from, date_to, working_remotely=False):
        for rec in self:
            appointments_in_period = rec.appointment_ids.filtered(lambda a: not a.date_end or a.date_end >= date_from)
            if date_to:
                appointments_in_period = appointments_in_period.filtered(lambda a: a.date_start <= date_to)
            if not appointments_in_period:
                raise exceptions.UserError(_('Could not find appointments in period {} - {} to toggle remote '
                                             'work').format(date_from, date_to))
            appointment_at_start_date = appointments_in_period.sorted(key=lambda a: a.date_start)[0]
            appointment_at_end_date = appointments_in_period.sorted(key=lambda a: a.date_start, reverse=True)[0]
            appointment_at_end_date_end_date = appointment_at_end_date.date_end

            if appointment_at_start_date.date_start != date_from:
                appointment_at_start_date.split_at_date(date_from)
                appointment_at_start_date = self.with_context(date=date_from).appointment_id

            if appointment_at_end_date_end_date != date_to:
                next_day_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)
                next_day = next_day_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                appointment_at_end_date.split_at_date(next_day)

            appointment_at_start_date.toggle_remote_work(working_remotely)
            if date_to:
                appointment_at_end_date = self.with_context(date=date_to).appointment_id
                appointment_at_end_date.toggle_remote_work(working_remotely)

    def get_theoretical_bruto_gpm(self, neto, date):
        gpm_proc = self.with_context(date=date).get_payroll_tax_rates(fields_to_get=['gpm_proc'])['gpm_proc']
        sodra_proc = self.with_context(date=date).effective_employee_tax_rate_proc_sodra
        neto_proc = 100 - gpm_proc - sodra_proc
        if tools.float_compare(neto_proc, 0, precision_digits=2) > 0:
            bruto = tools.float_round(neto * 100 / neto_proc, precision_digits=2)  # P3:DivOK
        else:
            bruto = 0.0
        gpm = tools.float_round(bruto * gpm_proc / 100.0, precision_digits=2)  # P3:DivOK
        return bruto, gpm

    @api.multi
    def active_appointments(self, date_from=False, date_to=False):
        if not date_from or not date_to:
            date_from = datetime.utcnow().replace(day=1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to = (datetime.utcnow()+relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        return self.appointment_ids.filtered(
            lambda r: r.date_start <= date_to and (not r.date_end or r.date_end >= date_from)
        )

    @api.one
    def _appointment_id(self):
        date = self._context.get('date') or datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self._cr.execute('''select id from hr_contract_appointment
                            where contract_id = %s
                            AND date_start <= %s
                            ORDER BY date_start desc
                            limit 1''', (self.id, date))
        res = self._cr.fetchall()
        if res and res[0]:
            self.appointment_id = res[0][0]
        else:
            self.appointment_id = False

    @api.one
    def end_contract(self, date_end, **kw):
        self.ensure_one()
        # if self.date_end:
        #     raise exceptions.Warning(_('Kontraktas turi pabaigą. Ją galite pakeisti tiesiai iš kotrakto lango'))
        if self.date_start > date_end:
            raise exceptions.Warning(_('Kontraktas negali baigtis anksčiau nei prasideda'))
        appointments = self.appointment_ids
        too_late_appointments = appointments.filtered(lambda r: r.date_start > date_end)
        if too_late_appointments:
            raise exceptions.Warning(
                _('Kai kurie sutarties priedai prasideda vėliau, nei nurodyda data. Pirmiau atšaukite juos'))
        appointments_ending_later = appointments.filtered(lambda r: r.date_end and r.date_end > date_end)
        for appointment in appointments_ending_later:
            appointment.date_end = date_end
        # if appointments_ending_later:
        #     raise exceptions.Warning(
        #         _('Kai kurie sutarties priedai baigiasi vėliau, nei nurodyda data. Pirmiau atšaukite juos'))
        appointments_to_close = appointments.filtered(lambda r: not r.date_end)
        appointments_to_close.write({'date_end': date_end})
        new_vals = {'date_end': date_end}

        nutraukimo_fields = ['priezasties_kodas', 'priezastis', 'priezasties_patikslinimo_kodas',
                             'priezasties_patikslinimas', 'teises_akto_straipsnis', 'teises_akto_straipsnio_dalis',
                             'teises_akto_straipsnio_dalies_punktas', 'num_men_iseitine']
        for nutraukimo_field in nutraukimo_fields:
            if nutraukimo_field in kw:
                new_vals[nutraukimo_field] = kw[nutraukimo_field]
        self.write(new_vals)

        # Cancel, shorten holidays that end after the termination day;
        leaves_ending_after_termination = self.env['hr.holidays'].search([
            ('contract_id', '=', self.id),
            ('date_to_date_format', '>', date_end)
        ])
        if leaves_ending_after_termination:
            try:
                leaves_to_cancel = leaves_ending_after_termination.filtered(
                    lambda d: d.date_from_date_format > date_end)
                if leaves_to_cancel:
                    leaves_to_cancel.action_refuse()
                    leaves_to_cancel.action_draft()
                    leaves_to_cancel.unlink()
                leaves_to_shorten = leaves_ending_after_termination - leaves_to_cancel
                if leaves_to_shorten:
                    leaves_to_shorten.stop_in_the_middle(date=date_end)
            except Exception as e:
                raise exceptions.ValidationError(_('Contract could not be terminated because of existing leaves ending '
                                                   'later than last day of employment.'))

        # Stop periodic payments
        base_domain = ['|', ('date_stop', '=', False), ('date_stop', '>', date_end)]
        bonus_periodic = self.env['hr.employee.bonus.periodic'].search(base_domain + [
            ('employee_id', '=', self.employee_id.id)
        ])
        deduction_periodic = self.env['hr.employee.deduction.periodic'].search(base_domain + [
            ('employee_id', '=', self.employee_id.id)
        ])
        payment_periodic = self.env['hr.employee.payment.periodic'].search(base_domain + [
            ('payment_id.employee_id', '=', self.employee_id.id)
        ])
        for periodic in [bonus_periodic, deduction_periodic, payment_periodic]:
            periodic.write({'date_stop': date_end})
        if not self._context.get('simulate'):
            self.inform_accountant_to_manually_check_periodic()

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not args:
            args = []
        args = args[:]
        if name:
            ids = self.search(
                ['|', ('name', operator, name), ('employee_id.name', operator, name)] + args,
                limit=limit)
        else:
            ids = self.search(args, limit=limit)
        return ids.name_get()

    @api.one
    @api.depends('appointment_ids.date_start', 'appointment_ids.date_end', 'appointment_ids.wage',
                 'appointment_ids.struct_id', 'appointment_ids.job_id', 'appointment_ids.department_id',
                 'appointment_ids.avansu_politika_suma', 'appointment_ids.antraeiles')
    def _compute_fields(self):
        current_date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        last_appointment = self.with_context(up_to_date=current_date).get_last_appointment()
        if last_appointment:
            self.wage = last_appointment.wage
            self.struct_id = last_appointment.struct_id.id
            self.job_id = last_appointment.job_id.id
            self.department_id = last_appointment.department_id.id
            self.avansu_politika_suma = last_appointment.avansu_politika_suma
            self.antraeiles = last_appointment.antraeiles
        else:
            self.wage = 0
            self.struct_id = False
            self.job_id = False
            self.department_id = False
            self.avansu_politika_suma = False
            self.antraeiles = False

    @api.one
    def _compute_sodra_papildomai(self):
        # date = self._context.get('date', datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
        # appointment = self.env['hr.contract.appointment'].search([('contract_id', '=', self.id),
        #                                                  ('date_start', '<=', date),
        #                                                  '|',
        #                                                  ('date_end', '=', False),
        #                                                  ('date_end', '>=', date)], limit=1)
        # if appointment:
        #     sodra_papildomai = appointment.sodra_papildomai
        # else:
        #     sodra_papildomai = self.employee_id.sodra_papildomai
        self.sodra_papildomai = self.appointment_id.sodra_papildomai

    @api.one
    def _compute_sodra_papildomai_type(self):
        if self.id and self.appointment_id:
            self.sodra_papildomai_type = self.appointment_id.sodra_papildomai_type
        else:
            self.sodra_papildomai_type = 'full'

    @api.multi
    @api.depends('appointment_ids')
    def _appointments_count(self):
        for rec in self:
            rec.appointments_count = len(rec.appointment_ids)

    @api.multi
    def get_active_appointment(self):
        self.ensure_one()
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        appointment = self.env['hr.contract.appointment'].search([('contract_id', '=', self.id),
                                                                   ('date_start', '<=', date),
                                                                   '|',
                                                                       ('date_end', '=', False),
                                                                       ('date_end', '>=', date),
                                                                   ], limit=1)
        return appointment

    @api.multi
    def get_last_appointment(self):
        self.ensure_one()
        ContractAppointment = self.env['hr.contract.appointment']
        domain = [('contract_id', '=', self.id)]
        appointment = ContractAppointment
        up_to_date = self._context.get('up_to_date')
        if up_to_date:
            appointment = ContractAppointment.search(domain + [('date_start', '<=', up_to_date)],
                                                     order='date_end desc', limit=1)
        if not appointment:
            appointment = ContractAppointment.search(domain, order='date_end desc', limit=1)
        return appointment

    @api.multi
    def update_terms(self, date_from, **params):
        self.ensure_one()

        existing_duplicate = self.env['hr.contract.appointment'].search([('contract_id', '=', self.id),
                                                                         ('date_start', '=', date_from)
                                                                         ], limit=1)

        if existing_duplicate:
            # Check (and convert) annual holiday leave duration
            leaves_accumulation_type = params.get('leaves_accumulation_type', False)
            num_leaves_per_year = params.get('num_leaves_per_year', False)
            if leaves_accumulation_type and num_leaves_per_year:
                min_leaves = self.env['hr.holidays'].get_employee_default_holiday_amount(
                    existing_duplicate.job_id or existing_duplicate.employee_id.job_id,
                    existing_duplicate.schedule_template_id,
                    existing_duplicate.employee_id.birthday, existing_duplicate.invalidumas) * 7.0 / 5.0  # P3:DivOK
                # P3:DivOK
                if leaves_accumulation_type == 'calendar_days' and tools.float_compare(existing_duplicate.num_leaves_per_year,
                    num_leaves_per_year * 7.0 / 5.0, precision_digits=2) < 0 and tools.float_compare(num_leaves_per_year,
                        min_leaves, precision_digits=2) < 0:
                    params.update({
                        'num_leaves_per_year': num_leaves_per_year * 7.0 / 5.0,  # convert to calendar days  # P3:DivOK
                    })

            # Check if NET wage is frozen and calculate the new BRUTO based on params
            freeze_net_wage = params.get('freeze_net_wage')
            if freeze_net_wage is None:
                freeze_net_wage = existing_duplicate.freeze_net_wage
            if not params.get('wage') and freeze_net_wage:
                default_params = params.copy()
                default_params['date_start'] = date_from
                gross = existing_duplicate.calculate_new_gross_wage_based_on_updated_params(**default_params)
                params.update({'wage': tools.float_round(gross, precision_digits=2)})

            existing_duplicate.write(params)
            return existing_duplicate

        active_appointment = self.env['hr.contract.appointment'].search([('contract_id', '=', self.id),
                                                                         ('date_start', '<', date_from),
                                                                         '|',
                                                                         ('date_end', '=', False),
                                                                         ('date_end', '>=', date_from)], limit=1)

        if not active_appointment and (date_from < self.date_end or not self.date_end):
            date_previous_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(days=1)
            date_previous = date_previous_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            apps = self.appointment_ids
            active_appointment = apps.filtered(lambda a: a.date_end == date_previous)

            if active_appointment:
                next_app = self.env['hr.contract.appointment'].search([
                    ('contract_id', '=', self.id),
                    ('date_start', '>', active_appointment.date_end)
                ], order='date_start asc', limit=1)
                if next_app:
                    date_previous = (datetime.strptime(next_app.date_from, tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    active_appointment.date_end = date_previous
                else:
                    active_appointment.date_end = self.date_end

        if active_appointment:
            if not params.get('schedule_template_id', False):
                schedule_template_id = active_appointment.schedule_template_id.copy({'appointment_id': False})
                params.update({
                    'schedule_template_id': schedule_template_id.id
                })
            if not params.get('leaves_accumulation_type', False) and not params.get('num_leaves_per_year', False):
                params.update({
                    'leaves_accumulation_type': active_appointment.leaves_accumulation_type,
                    # 'num_leaves_per_year': active_appointment.num_leaves_per_year,
                })
            return active_appointment.start_new_appointment(date_from, **params)
        else:
            return False

    @api.multi
    def create_new_appointment(self):
        self.ensure_one()
        context = {'contract_id': self.id}
        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.contract.appointment.create',
            'view_id': False,
            'target': 'new',
            'context': context,
        }

    @api.multi
    def open_contract_end_wizard(self):
        self.ensure_one()
        context = {'active_id': self.id}
        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.contract.terminate',
            'view_id': False,
            'target': 'new',
            'context': context,
        }

    @api.multi
    def get_all_structures(self):
        # structures = self.mapped('appointment_ids.struct_id')
        date = self._context.get('date', datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
        date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_from = (date_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = (date_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        appointments = self.appointment_ids.filtered(lambda r: r.date_start <= date_to and (not r.date_end or r.date_end >= date_from))
        structures = appointments.mapped('struct_id')
        if not structures:
            return []
        return list(set(structures._get_parent_structure().ids))

    @api.multi
    @api.constrains('date_start')
    def constrain_date_start(self):
        for rec in self:
            app_start_before_contract = rec.appointment_ids.filtered(lambda r: r.date_start < rec.date_start)
            if app_start_before_contract:
                app = app_start_before_contract[0]
                raise exceptions.ValidationError(
                    _('Sutarties priedas %s darbuotojui %s negali prasidėti anksčiau nei sutartis %s (%s < %s).')
                    % (app.name, rec.employee_id.name, rec.name, app.date_start, rec.date_start))

    @api.multi
    def get_num_work_days(self, date_from, date_to):
        if len(self) == 0:
            return int(self.env['hr.payroll'].standard_work_time_period_data(date_from, date_to).get('days', 0))
        self.ensure_one()
        res = 0
        appointments = self.env['hr.contract.appointment'].search([
            ('contract_id', '=', self.id),
            ('date_start', '<=', date_to),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', date_from)
        ])
        for appointment in appointments:
            app_date_from, app_date_to = get_days_intersection((date_from, date_to), (appointment.date_start, appointment.date_end))
            date_dt = datetime.strptime(app_date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            app_date_to_dt = datetime.strptime(app_date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            schedule_template = appointment.schedule_template_id
            # Determine if the days should be forced converted to work days. Only applies for schedules that are not
            # fixed when employee time sheets are not used and the appointment leaves accumulation type is calendar days
            force_convert_to_work_days = self._context.get('force_convert_to_work_days') and \
                                         (
                                                 self._context.get('do_not_use_ziniarastis') or
                                                 self._context.get('force_use_schedule_template')
                                         ) and \
                                         schedule_template.template_type not in ['fixed', 'suskaidytos'] and \
                                         appointment.leaves_accumulation_type == 'calendar_days'

            while date_dt <= app_date_to_dt:
                date = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                work_day = appointment.schedule_template_id.is_work_day(date)
                if work_day:
                    days_to_add = 1
                    if force_convert_to_work_days:
                        weekly_work_days = 6.0 if appointment.schedule_template_id.six_day_work_week else 5.0
                        days_to_add *= weekly_work_days / 7.0  # P3:DivOK
                    res += days_to_add
                date_dt += timedelta(days=1)
        return res

    @api.multi
    def get_work_days_for_holidays(self, date_from, date_to):
        self.ensure_one()
        total_days = self.with_context(force_use_schedule_template=True).get_num_work_days(date_from, date_to)
        date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)

        other_holidays = self.env['hr.holidays'].search([('employee_id', '=', self.employee_id.id),
                                                         ('state', '=', 'validate'),
                                                         ('type', '=', 'remove'),
                                                         ('date_to_date_format', '>=', date_from),
                                                         ('date_from_date_format', '<=', date_to),
                                                         ('holiday_status_id.kodas', 'in', ['PB', 'NN', 'TM', 'VP'])])
        other_days = 0
        for hol in other_holidays:
            hol_date_from_dt = datetime.strptime(hol.date_from_date_format, tools.DEFAULT_SERVER_DATE_FORMAT)
            hol_date_to_dt = datetime.strptime(hol.date_to_date_format, tools.DEFAULT_SERVER_DATE_FORMAT)
            overlap = True if hol.date_from_date_format <= date_to and hol.date_to_date_format >= date_from else False
            if overlap:
                min_date_to = min(date_to_dt, hol_date_to_dt).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                max_date_from = max(date_from_dt, hol_date_from_dt).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                other_days += self.get_num_work_days(max_date_from,min_date_to)
        return total_days - other_days

    @api.multi
    def _compute_work_relation_start_date(self):
        for rec in self:
            contract = rec
            relation_start = False
            while contract:
                relation_start = contract.date_start
                start_date_dt = datetime.strptime(relation_start, tools.DEFAULT_SERVER_DATE_FORMAT)
                one_day_before = (start_date_dt - relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                contract = contract.employee_id.contract_ids.filtered(lambda c: c.date_end == one_day_before)
            rec.work_relation_start_date = relation_start

    @api.multi
    def _compute_work_relation_end_date(self):
        for rec in self:
            contract = rec
            relation_end = False
            while contract:
                relation_end = contract.date_end
                if not relation_end:
                    break
                end_date_dt = datetime.strptime(relation_end, tools.DEFAULT_SERVER_DATE_FORMAT)
                one_day_after = (end_date_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                contract = contract.employee_id.contract_ids.filtered(lambda c: c.date_start == one_day_after)
            rec.work_relation_end_date = relation_end

    @api.multi
    def get_contracts_related_to_work_relation(self):
        self.ensure_one()
        work_relation_start = self.work_relation_start_date
        work_relation_end = self.work_relation_end_date
        domain = [
            ('employee_id', '=', self.employee_id.id),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', work_relation_start)
        ]
        if work_relation_end:
            domain.append(('date_start', '<=', work_relation_end))
        return self.search(domain)

    @api.multi
    def include_last_month_when_calculating_vdu_for_date(self, date):
        """
        Determines if the month for the given date should be included in the average daily wage calculation based upon
        if it's on or after the last working date of the month.
        Args:
            date (date): Date to check for. Should be the end date for the VDU calculation period.
        Returns:
            boolean: Should include the month for the date in the VDU calculations
        """
        self.ensure_one()

        # Parse and compute the dates
        date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        end_of_month_dt = date_dt + relativedelta(day=31)
        end_of_month = end_of_month_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        if date == end_of_month:
            return True

        # Get the last appointment of the month
        related_contracts = self.get_contracts_related_to_work_relation()
        appointments = related_contracts.mapped('appointment_id').filtered(
            lambda app: app.date_start <= end_of_month and (not app.date_end or app.date_end >= date)
        ).sorted(key=lambda app: app.date_start, reverse=True)
        last_appointment = appointments and appointments[0]
        schedule_template = last_appointment.schedule_template_id if last_appointment else None
        # Check the schedule_template is set
        if not schedule_template:
            return False

        # Determine the date to calculate from backwards
        end_of_work_month = end_of_month_dt
        if last_appointment.date_end:
            end_of_work_month = min(
                end_of_work_month,
                datetime.strptime(last_appointment.date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
            )

        include_last = True
        date_to_check = end_of_work_month
        while date_to_check > date_dt:
            date_to_check_str = date_to_check.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            # Special context (calculating_holidays) that checks the template type and returns the work day by schedule
            # template if the schedule is not regular
            is_work_day = schedule_template.with_context(calculating_holidays=True).is_work_day(date_to_check_str)
            if is_work_day:
                # If at least one of the dates that are greater than the provided date is a work date - don't include
                include_last = False
                break
            date_to_check -= relativedelta(days=1)

        return include_last

    @api.multi
    def inform_accountant_to_manually_check_periodic(self):
        """
        Method to send a ticket to accountant if there are payment records starting after the planned work relation end
        informing that they need to be reviewed and removed if they're not necessary anymore;
        """
        self.ensure_one()
        bonuses = self.env['hr.employee.bonus'].search_count([
            ('employee_id', '=', self.employee_id.id),
            ('payment_date_from', '>', self.date_end),
        ])
        deductions = self.env['hr.employee.isskaitos'].search_count([
            ('employee_id', '=', self.employee_id.id),
            ('date', '>', self.date_end),
        ])
        payments = self.env['hr.employee.payment'].search([
            ('employee_id', '=', self.employee_id.id),
            ('date', '>', self.date_end),
        ])
        payments = self.remove_necessary_payments(payments, self.date_end)
        if bonuses or deductions or payments:
            subject = _('Contract with employee terminated, check bonus, payments and deductions')
            body = _('Contract with employee {0} was terminated. There is a need to manually check and cancel any '
                     'bonus, payments or deductions coming later than the last day of '
                     'work').format(self.employee_id.name_related)
            try:
                ticket_obj = self.sudo()._get_ticket_rpc_object()
                vals = {
                    'ticket_dbname': self.env.cr.dbname,
                    'ticket_model_name': self._name,
                    'name': subject,
                    'description': body,
                    'ticket_type': 'accounting',
                    'user_posted': self.env.user.name,
                }
                res = ticket_obj.create_ticket(**vals)
                if not res:
                    raise exceptions.UserError('The distant method did not create the ticket.')
            except Exception as exc:
                message = 'Failed to create ticket informing the accountant about the possible need to delete ' \
                          'periodic deductions coming later than the last day of contract.' \
                          '\nException message: {0}'.format(str(exc.args))
                self.env['robo.bug'].sudo().create({
                    'user_id': self.env.user.id,
                    'error_message': message,
                })

    @api.model
    def remove_necessary_payments(self, payments, work_relation_end=datetime.utcnow()):
        """
        Method to remove payment records from their respective record sets if they're supposed to be paid even after
        work relation end.

        @param payments: recordset of employee's hr.employee.payment records starting after work relation end;
        @param work_relation_end: date string of work relation end;

        :return: Updated record sets, records which should be paid after work relation end removed from them.
        """
        # Remove payments that are granted for holidays that ended before contract end;
        for payment in payments:
            if all(holiday_end <= work_relation_end for holiday_end in payment.holidays_ids.mapped(
                    'date_to_date_format')):
                payments -= payment

        return payments

    @api.multi
    def unlink(self):
        self.ensure_one()
        has_related_holidays = self.env['hr.holidays'].sudo().search_count([('contract_id', 'in', self.ids)])
        if has_related_holidays:
            raise exceptions.ValidationError(_('The contract has related holidays, they need to be canceled first'))
        return super(HrContract, self).unlink()

    @api.multi
    def create_deduction_for_overused_holidays_for_ending_contract(self):
        """
            Create a deduction if the holiday balance for the employee for the contract end date is negative
        """
        self.ensure_one()

        # Determine end date
        date_end = self.date_end
        if not date_end:
            return

        user = self.env.user
        company = user.company_id
        employee = self.employee_id

        # Get holiday balance
        holiday_balance = self.employee_id.with_context(date=date_end).remaining_leaves
        if tools.float_compare(holiday_balance, 0.0 ,precision_digits=2) > 0:
            return

        # Find last appointment
        appointment = self.with_context(date=date_end).appointment_id
        if not appointment:
            appointments = self.appointment_ids.filtered(
                lambda a: a.date_start <= date_end and (not a.date_end or a.date_end >= date_end)
            ).sorted(key=lambda a: a.date_start, reverse=True)
            appointment = appointments and appointments[0]
        if not appointment:
            return

        schedule_template = appointment.schedule_template_id

        # Get employee post
        post = schedule_template.etatas
        if tools.float_is_zero(post, precision_digits=2):
            # This should never happen but copied code from payslip rules has checks that account for this so might
            # as well set the post to 1.0 in this case so that no division operations fail.
            post = 1.0

        work_norm = schedule_template.work_norm

        # Check if holiday accumulation records should be used
        use_holiday_accumulation_records = company.with_context(date=date_end).holiday_accumulation_usage_is_enabled

        # Get VDU values
        include_last = self.include_last_month_when_calculating_vdu_for_date(date_end)
        vdu_kwargs = {'contract_id': self.id, 'include_last': include_last, 'vdu_type': 'd'}
        vdu_d = self.employee_id.get_vdu(date_end, **vdu_kwargs)
        vdu_kwargs['vdu_type'] = 'h'
        vdu_h = self.employee_id.get_vdu(date_end, **vdu_kwargs)

        # Determine the amount to deduct
        if use_holiday_accumulation_records:
            contracts = self.get_contracts_related_to_work_relation()
            related_appointments = contracts.mapped('appointment_id')
            posts = related_appointments.mapped('schedule_template_id.etatas')
            no_post_changes = len(set(posts)) == 1
            use_daily_vdu = no_post_changes

            if use_daily_vdu:
                vdu = vdu_d / post  # P3:DivOK
            else:
                vdu = vdu_h * work_norm * 8.0
            deduction_amount = holiday_balance * vdu
        else:
            if appointment and appointment.leaves_accumulation_type == 'calendar_days':
                work_days_coefficient = 5.0 / 7.0  # P3:DivOK
            else:
                work_days_coefficient = 1.0
            holiday_balance = holiday_balance * work_days_coefficient
            holiday_coefficient = appointment.employee_id.holiday_coefficient or 1.0
            if tools.float_compare(holiday_coefficient, 1.0, precision_digits=2) != 0:
                vdu = vdu_d / post  # P3:DivOK
            else:
                vdu = vdu_d
            holiday_balance *= holiday_coefficient
            deduction_amount = holiday_balance * vdu

        # Create deduction
        if not tools.float_is_zero(deduction_amount, precision_digits=2):
            # Round values for display
            holiday_balance = tools.float_round(holiday_balance, 2.0)
            vdu = tools.float_round(vdu, 2.0)
            HrEmployeeIsskaitos = self.env['hr.employee.isskaitos']
            deduction_account = self.env['account.account'].search([('code', '=', '63041')], limit=1)
            if not deduction_account:
                deduction_account = HrEmployeeIsskaitos.default_account_id()
            deduction = HrEmployeeIsskaitos.create({
                'employee_id': employee.id,
                'reason': 'atostoginiai',
                'comment': _('Panaudotos atostogų dienos: ({} d.d.) * ({} VDU)').format(holiday_balance, vdu),
                'partner_id': employee.address_home_id.id,
                'date': date_end,
                'date_maturity': date_end,
                'amount': abs(deduction_amount),
                'limit_deduction_amount': True,
                'account_id': deduction_account.id
            })
            deduction.confirm()

    @api.multi
    def is_accumulating_holidays(self, date):
        return not self.find_non_accumulative_holidays(date, date, search_count=True)

    @api.multi
    def find_non_accumulative_holidays(self, date_from, date_to, search_count=False):
        non_accumulative_holiday_status_ids = [
            self.env.ref('hr_holidays.holiday_status_VP').id,
            self.env.ref('hr_holidays.holiday_status_PB').id,
            self.env.ref('hr_holidays.holiday_status_NN').id,
            self.env.ref('hr_holidays.holiday_status_TM').id
        ]

        domain = [
            ('contract_id', 'in', self.ids),
            ('date_from_date_format', '<=', date_to),
            ('date_to_date_format', '>=', date_from),
            ('state', '=', 'validate'),
            ('holiday_status_id', 'in', non_accumulative_holiday_status_ids)
        ]

        if search_count:
            return self.env['hr.holidays'].search_count(domain)
        return self.env['hr.holidays'].search(domain)

    @api.multi
    def get_leaves_accumulated_at_a_later_date(self, date_from, date_to, adjust_by_post=False):
        self.ensure_one()
        domain = [('employee_id', '=', self.employee_id.id)]
        if self.work_relation_end_date:
            domain.append(('date_end', '<=', self.work_relation_end_date))
        domain += [
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', date_from)
        ]
        appointments = self.env['hr.contract.appointment'].search(domain)
        balance = 0.0
        for appointment in appointments:
            forced_date_from = max(date_from, appointment.date_start)
            forced_date_to = min(appointment.date_end or date_to, date_to)
            accumulated = appointment.with_context(
                forced_date_from=forced_date_from, forced_date_to=forced_date_to
            )._get_accumulated_holiday_days()
            if appointment.leaves_accumulation_type == 'calendar_days':
                accumulated *= 5.0 / 7.0  # P3:DivOK
            if adjust_by_post:
                accumulated *= appointment.schedule_template_id.etatas
            balance += accumulated
        return balance

    @api.model
    def cron_check_for_employment_contracts_ending_tomorrow(self):
        tomorrow = (datetime.today() + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        contracts_ending_tomorrow = self.search([('date_end', '=', tomorrow)]).filtered(
            lambda c: c.work_relation_end_date == tomorrow
        )
        if not contracts_ending_tomorrow:
            return

        mail_channel = self.env.ref('l10n_lt_payroll.end_of_contract_notification_mail_channel', False)
        if not mail_channel:
            return

        names = ', '.join(contracts_ending_tomorrow.mapped('employee_id.name'))

        channel_partner_ids = mail_channel.sudo().mapped('channel_partner_ids')
        subject = _('One day remained until the end of the employment contract')
        body = _('For employees: %s. One day remained until the end of the employment contract') % (names)

        msg = {
            'body': body,
            'subject': subject,
            'message_type': 'email',
            'subtype': 'mail.mt_comment',
            'priority': 'high',
            'front_message': True,
            'rec_model': 'hr.contract',
            'partner_ids': channel_partner_ids.ids,
        }
        mail_channel.sudo().robo_message_post(**msg)


HrContract()
