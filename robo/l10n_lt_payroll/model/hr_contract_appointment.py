# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo.addons.l10n_lt_payroll.model.work_norm import CODES_ABSENCE, CODES_HOLIDAYS

from odoo import _, api, exceptions, fields, models, tools

night_shift_start = 22.0
night_shift_end = 6.0


def get_days_intersection(interv_1, interv_2):
    date_1from = interv_1[0]
    date_1to = interv_1[1]
    date_2from = interv_2[0]
    date_2to = interv_2[1]
    if not date_1from and not date_2from:
        raise exceptions.Warning(_('Nenurodyta periodo pradžia'))
    if not date_1to and not date_2to:
        raise exceptions.Warning(_('Nenurodyta periodo pabaiga'))
    if not date_1from:
        date_from = date_2from
    elif not date_2from:
        date_from = date_1from
    else:
        date_from = max(date_1from, date_2from)
    if not date_1to:
        date_to = date_2to
    elif not date_2to:
        date_to = date_1to
    else:
        date_to = min(date_1to, date_2to)
    return date_from, date_to


class ContractAppointment(models.Model):

    _name = 'hr.contract.appointment'
    _inherit = ['mail.thread']
    _description = 'Contract Appointment'
    _order = 'date_start desc'

    def get_original_avansu_politika_selection(self):
        return self.env['res.company']._fields['avansu_politika'].selection

    def default_struct_id(self):
        return self.env['hr.payroll.structure'].search([('code', '=', 'MEN')])

    def _get_default_advance_payment_day(self):
        company = self.env.user.company_id
        return company.advance_payment_day

    contract_id = fields.Many2one('hr.contract', string='Contract', required=True)
    company_id = fields.Many2one('res.company', string='Kompanija', readonly=True, related='contract_id.company_id', store=True)
    name = fields.Char(string='Appointment Reference', required=True, readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', related='contract_id.employee_id', readonly=True,
                                  store=True, index=True)
    department_id = fields.Many2one('hr.department', string='Department')
    type_id = fields.Many2one('hr.contract.type', string='Contract Type', required=False,
                              default=lambda self: self.env['hr.contract.type'].search([], limit=1))
    job_id = fields.Many2one('hr.job', string='Job Title')
    date_start = fields.Date(string='Start Date', required=True, default=fields.Date.today, index=True, track_visibility='onchange')
    date_end = fields.Date(string='End Date', index=True, track_visibility='onchange')
    trial_date_start = fields.Date(string='Trial Start Date', track_visibility='onchange')
    trial_date_end = fields.Date(string='Trial End Date', track_visibility='onchange')
    wage = fields.Float(string='Wage', digits=(16, 2), required=True, help='Basic Salary of the employee')
    notes = fields.Text(string='Notes')
    state = fields.Selection([
        ('draft', 'New'),
        ('open', 'Running'),
        ('close', 'Expired'),
    ], string='Status', track_visibility=_('onchange'), help='Status of the contract', default='draft')
    struct_id = fields.Many2one('hr.payroll.structure', string='Salary Structure', required=True, default=default_struct_id)
    sodra_papildomai = fields.Boolean(string='Sodra papildomai')
    sodra_papildomai_type = fields.Selection([('full', 'Pilnas (3%)'), ('exponential', 'Palaipsniui (Nuo 2022 - 2.7%)')],
                                             string='Sodros kaupimo būdas', default='full')
    avansu_politika_suma = fields.Float(string='Avanso dydis (neto)', digits=(2, 2), default=0.0)
    avansu_politika = fields.Selection(selection=get_original_avansu_politika_selection, string='Avansų politika',
                                       default='fixed_sum')
    avansu_politika_proc = fields.Float(string='Atlyginimo proc.',
                                        default=lambda self: self.env.user.company_id.avansu_politika_proc)
    advance_payment_day = fields.Integer(string='Avanso mokėjimo diena', default=_get_default_advance_payment_day)
    hypothetical_hourly_wage = fields.Float(string='Menamas valandinis atlygis', compute='_hypothetical_hourly_wage',
                                            store=True)
    antraeiles = fields.Boolean(string='Antraeilės', default=False)
    neto_monthly = fields.Float(string='Neto mėnesinis', compute='_neto_monthly', lt_string='Netto mėnesinis', store=True)
    shorter_before_holidays = fields.Boolean(string='Trumpinti prieš šventes', default=True)
    schedule_template_id = fields.Many2one('schedule.template', string='Darbo grafikas', required=True, domain="['|', ('appointment_id', '=', id), ('appointment_id', '=', False)]", inverse='_set_appointment_on_schedule_template')
    use_npd = fields.Boolean(string='Naudoti NPD')
    employee_identification_id = fields.Char(string='Asmens kodas', store=False, related='employee_id.identification_id', readonly=True)
    tabelio_numeris = fields.Char(string='Tabelio numeris', related='employee_id.tabelio_numeris', store=False, readonly=True)
    contract_date_start = fields.Date(string='Sutarties pradžios data', related='contract_id.date_start', store=False, readonly=True)
    contract_date_end = fields.Date(string='Sutarties pabaigos data', related='contract_id.date_end', store=False, readonly=True)
    contract_terms_date_end = fields.Date(string='Pabaigos data nustatant sutarties sąlygas')
    num_leaves_per_year = fields.Float(string='Atostogų per metus', default=20.0)
    additional_leaves_per_year = fields.Float(string='Additional holidays granted')
    total_leaves_per_year = fields.Float(string='Total holidays per year', compute='_compute_total_leaves_per_year')
    leaves_accumulation_type = fields.Selection([('work_days', 'Darbo dienomis'),
                                    ('calendar_days', 'Kalendorinėmis dienos')], string='Atostogų kaupimo tipas',
                                   required=True, default='work_days')
    invalidumas = fields.Boolean(string='Neįgalumas',
                                 groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager")
    darbingumas = fields.Many2one('darbuotojo.darbingumas', string='Darbingumo lygis',
                                  groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager")
    informed = fields.Boolean(string='Informuota buhalterija dėl sutarties pradžios', readonly=True, copy=False, groups='base.group_system')
    informed_end = fields.Boolean(string='Informuota buhalterija dėl sutarties pabaigos', readonly=True, copy=False, groups='base.group_system')
    informed_trial = fields.Boolean(string='Informuota buhalterija dėl bandomojo pabaigos', readonly=True, copy=False, groups='base.group_system')
    use_hours_for_wage_calculations = fields.Boolean(string='Valandinis atlyginimo skaičiavimas', compute='_should_use_hours_for_wage_calculations')
    struct_name = fields.Char(compute='_compute_struct_name')
    num_work_days_year = fields.Float(string='Darbo dienų skaičius metuose pagal darbo priedą', compute='_num_work_days_year')
    num_regular_work_hours = fields.Float(string='Sisteminis darbo valandų skaičius mėnesyje', compute='_num_regular_work_time')
    num_regular_work_days = fields.Float(string='Sisteminis darbo dienų skaičius mėnesyje', compute='_num_regular_work_time')
    paid_overtime = fields.Boolean(string='Apmokamas papildomas darbas', default=True, copy=True)
    is_voluntary_internship = fields.Boolean(compute='_compute_is_voluntary_internship')
    freeze_net_wage = fields.Boolean('Freeze NET wage',
                                     help="Calculate GROSS wage based on NET wage when a new appointment is created")
    accumulated_holiday_days = fields.Float(compute='_compute_accumulated_holiday_days')
    contract_priority = fields.Selection([('foremost', 'Foremost'), ('secondary', 'Secondary')],
                                         string='Contract Priority', default='foremost')

    @api.one
    @api.depends('contract_id.rusis')
    def _compute_is_voluntary_internship(self):
        self.is_voluntary_internship = self.contract_id.rusis in ['voluntary_internship', 'educational_internship']

    @api.onchange('trial_date_start', 'trial_date_end')
    def _onchange_trial_period(self):
        return {
            'warning':
            {
                'title': _('Warning'),
                'message': _('Make sure to change the trial dates on the contract accordingly'),
            }
        }

    @api.multi
    @api.onchange('num_leaves_per_year', 'additional_leaves_per_year')
    def _compute_total_leaves_per_year(self):
        """
        Method to compute the total leaves (base + additional) for a particular appointment;
        """
        for rec in self:
            rec.total_leaves_per_year = rec.num_leaves_per_year + rec.additional_leaves_per_year

    @api.onchange('use_npd', 'sodra_papildomai', 'leaves_accumulation_type', 'invalidumas', 'darbingumas', 'num_leaves_per_year')
    def _suggest_starting_new_appointment(self):
        if self.date_start <= datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT):
            raise exceptions.Warning(_('Keičiasi NPD/Sodra/Atostogų kaupimo būdas arba darbingumo nustatymai.\n'
                                       'Šių nustatymų pakeitimai įtakoją įvairius skaičiavimus, kurie pasikeis nuo priedo įsigaliojimo datos\n'
                                       'Pagalvokite ar tikrai norite keisti šiuos parametrus visam priedui, nuo jo įsigaliojimo datos\n'
                                       'Rekomenduojama kurti naują priedą, nuo datos, kurios keičiasi šio priedo sąlygos.'))

    @api.one
    def _set_appointment_on_schedule_template(self):
        self.schedule_template_id.appointment_id = self.id

    @api.multi
    def write(self, vals):
        # Get neto monthly for all records so this write overwrite does not impact performance
        neto_monthly = {rec.id: rec.neto_monthly for rec in self}
        res = super(ContractAppointment, self).write(vals)

        now = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        changing_wage = 'wage' in vals
        changing_sodra_params = any(key in vals for key in ['sodra_papildomai', 'sodra_papildomai_type'])
        if changing_sodra_params and not changing_wage:
            # This adjusts the frozen net wage
            for rec in self:
                if not rec.freeze_net_wage:
                    continue

                current_net_wage = neto_monthly.get(rec.id)
                if not current_net_wage:
                    continue

                calculation_date = max(min(rec.date_end or now, now), rec.date_start)
                tax_rates = rec.contract_id.with_context(date=calculation_date).get_payroll_tax_rates()

                # Check if zero npd should apply
                in_zero_npd_period = self.env['zero.npd.period'].sudo().search_count([
                    ('date_start', '<=', calculation_date),
                    ('date_end', '>=', calculation_date)
                ])
                if not rec.use_npd or in_zero_npd_period:
                    forced_tax_free_income = 0.0
                else:
                    forced_tax_free_income = None

                voluntary_pension = rec.sodra_papildomai and rec.sodra_papildomai_type
                disability = rec.employee_id.invalidumas and rec.employee_id.darbingumas.name
                is_foreign_resident = rec.employee_id.is_non_resident

                # Calculate the BRUTO based on frozen NET wage
                bruto = self.env['hr.payroll'].sudo().convert_net_income_to_gross(
                    current_net_wage, date=calculation_date, voluntary_pension=voluntary_pension, disability=disability,
                    is_foreign_resident=is_foreign_resident, forced_tax_free_income=forced_tax_free_income,
                    contract=rec.contract_id, **tax_rates
                )

                # Set the new wage
                rec.write({'wage': bruto})

        return res

    @api.model
    def default_get(self, fields):
        res = super(ContractAppointment, self).default_get(fields)
        if not res.get('job_id', False):
            contract_id = self.env['hr.contract'].browse(res.get('contract_id', False))
            employee_id = self.env['hr.employee'].browse(res.get('employee_id', False))
            if contract_id or employee_id:
                res['job_id'] = contract_id.job_id.id or employee_id.job_id.id
            if self.contract_id or self.employee_id:
                res['job_id'] = self.contract_id.job_id.id or self.employee_id.job_id.id
        return res

    @api.model
    def create(self, vals):
        contract = self.env['hr.contract'].browse(vals.get('contract_id'))[0]
        if not contract:
            raise exceptions.UserError(_('Sutarties priedas privalo turėti susijusią sutartį.'))
        prev_appointments = self.search([('employee_id', '=', contract.employee_id.id)])
        prev_number = max(int(app.name) for app in prev_appointments) if prev_appointments else 0
        vals['name'] = str(prev_number + 1)
        res = super(ContractAppointment, self).create(vals)
        res._create_holiday_accumulation_records()
        return res

    @api.multi
    def unlink(self):
        self._remove_holiday_accumulation_records()
        return super(ContractAppointment, self).unlink()

    @api.multi
    @api.depends('contract_id')
    def _num_regular_work_time(self):
        for rec in self:
            calc_date_from = self._context.get('date', False) or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            calc_date_from_dt = datetime.strptime(calc_date_from, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(day=1)
            calc_date_from = calc_date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            calc_date_to = (calc_date_from_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            appointment = rec
            contract = rec.contract_id
            work_norm = self.env['hr.employee'].employee_work_norm(
                calc_date_from=calc_date_from,
                calc_date_to=calc_date_to,
                contract=contract,
                appointment=appointment)
            rec.num_regular_work_hours = work_norm['hours']
            rec.num_regular_work_days = work_norm['days']

    @api.one
    def _num_work_days_year(self):
        default = 365 * 5.0 / 7.0  # P3:DivOK
        try:
            date_to_use = self._context.get('date') or self.date_start
            six_day_work_week = self.schedule_template_id.six_day_work_week
            employee = self._context.get('employee_id', self.employee_id)
            work_days = employee.company_id.with_context(date=date_to_use, six_day_work_week=six_day_work_week).num_work_days_a_year or default
        except:
            work_days = default
        self.num_work_days_year = work_days

    @api.one
    @api.depends('struct_id')
    def _compute_struct_name(self):
        self.struct_name = self.struct_id.code

    @api.multi
    @api.constrains('num_leaves_per_year')
    def constrain_leaves_per_year(self):
        for rec in self:
            min_leaves = self.env['hr.holidays'].get_employee_default_holiday_amount(
                rec.job_id or rec.employee_id.job_id, rec.schedule_template_id,
                rec.employee_id.birthday, rec.invalidumas
            )
            if rec.leaves_accumulation_type == 'calendar_days':
                if not rec.schedule_template_id:
                    convert_to_calendar_days = True
                elif not rec.schedule_template_id.fixed_attendance_ids or \
                        rec.schedule_template_id.template_type not in ['fixed', 'suskaidytos']:
                    convert_to_calendar_days = False
                else:
                    convert_to_calendar_days = rec.schedule_template_id.num_week_work_days in [5, 6]
                if convert_to_calendar_days:
                    min_leaves = min_leaves * 7.0 / 5.0  # P3:DivOK
                if tools.float_compare(rec.num_leaves_per_year, min_leaves, precision_digits=2) < 0:
                    # P3:DivOK
                    raise exceptions.UserError(
                        _('Kaupiant atostogas kalendorinėmis dienomis, darbuotojas turi gauti ne mažiau %s dienų atostogų per metus.') % (min_leaves * 7.0 / 5.0))
            elif rec.leaves_accumulation_type != 'calendar_days' and \
                    tools.float_compare(rec.num_leaves_per_year, min_leaves, precision_digits=2) < 0:
                raise exceptions.UserError(
                    _('Kaupiant atostogas darbo dienomis, darbuotojas turi gauti ne mažiau %s dienų atostogų per metus.') % (min_leaves))

    @api.onchange('leaves_accumulation_type')
    def _onchange_leaves_accumulation_type(self):
        """
        Method to recompute base and additional leave amounts for appointment when leave accumulation type is changed;
        """
        date = self._context.get('date')
        if not date:
            date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        year = int(date[:4])
        metu_pradzia = datetime(year, 1, 1)
        metu_pabaiga = datetime(year, 12, 31)
        num_work_days_year = self.with_context(date=date, employee_id=self.employee_id).num_work_days_year
        num_calendar_days_year = (metu_pabaiga - metu_pradzia).days + 1
        min_leave_days = self.env['hr.holidays'].get_employee_default_holiday_amount(self.job_id, self.schedule_template_id, self.employee_id.birthday, self.invalidumas)
        if self.leaves_accumulation_type == 'calendar_days':
            if tools.float_is_zero(num_work_days_year, precision_digits=2):
                raise exceptions.UserError(
                    _('Darbo dienų skaičius metuose negali būti nulis, kreipkitės į sistemos administratorių'))
            # P3:DivOK
            calendar_days_conv_to_work = max(self.num_leaves_per_year * num_calendar_days_year / num_work_days_year,
                                             min_leave_days)
            additional_days = self.additional_leaves_per_year * num_calendar_days_year / num_work_days_year  # P3:DivOK
        else:
            if tools.float_is_zero(num_calendar_days_year, precision_digits=2):
                raise exceptions.UserError(
                    _('Darbo dienų skaičius metuose negali būti nulis, kreipkitės į sistemos administratorių'))
            # P3:DivOK
            calendar_days_conv_to_work = max(self.num_leaves_per_year * num_work_days_year / num_calendar_days_year,
                                             min_leave_days)
            additional_days = self.additional_leaves_per_year * num_work_days_year / num_calendar_days_year

        self.num_leaves_per_year = calendar_days_conv_to_work
        self.additional_leaves_per_year = additional_days

    @api.multi
    @api.constrains('trial_date_end', 'trial_date_start')
    def _check_trial_period_dates(self):
        for rec in self:
            if rec.trial_date_start and not rec.trial_date_end or not rec.trial_date_start and rec.trial_date_end:
                raise exceptions.ValidationError(_('Reikia nurodyti išbandymo laikotarpio pradžios ir pabaigos datas.'))
            if rec.trial_date_end and rec.trial_date_end < rec.trial_date_start:
                raise exceptions.ValidationError(_('Bandomajo laikotarpio data nuo negali būti vėliau, nei data iki'))

    @api.multi
    def _should_use_hours_for_wage_calculations(self):
        for rec in self:
            rec.use_hours_for_wage_calculations = False
            if not rec.schedule_template_id.wage_calculated_in_days or rec.schedule_template_id.template_type == 'sumine' or rec.schedule_template_id.men_constraint == 'val_per_men':
                rec.use_hours_for_wage_calculations = True

    @api.multi
    @api.depends('employee_id', 'wage', 'sodra_papildomai', 'sodra_papildomai_type', 'use_npd', 'date_end',
                 'contract_id.override_taxes', 'contract_id.use_npd', 'contract_id.use_pnpd', 'date_start',
                 'contract_id.sodra_papild_proc', 'contract_id.gpm_proc', 'contract_id.gpm_ligos_proc',
                 'contract_id.darbuotojo_pensijos_proc', 'contract_id.darbuotojo_sveikatos_proc',
                 'contract_id.darbdavio_sodra_proc', 'contract_id.npd_max', 'contract_id.npd_0_25_max',
                 'contract_id.npd_30_55_max', 'contract_id.mma', 'contract_id.mma_first_day_of_year',
                 'contract_id.min_hourly_rate', 'contract_id.npd_koeficientas', 'contract_id.pnpd', 'contract_id.npd',
                 'contract_id.use_sodra_papild', 'contract_id.use_gpm', 'contract_id.use_ligos_gpm',
                 'contract_id.use_darbuotojo_pensijos', 'contract_id.use_darbuotojo_sveikatos',
                 'contract_id.use_darbdavio_sodra', 'contract_id.use_npd_max', 'contract_id.use_npd_0_25_max',
                 'contract_id.use_npd_30_55_max', 'contract_id.use_mma', 'contract_id.use_mma_first_day_of_year',
                 'contract_id.use_min_hourly_rate', 'contract_id.use_npd_koeficientas', 'contract_id.use_npd',
                 'contract_id.use_pnpd')
    def _neto_monthly(self):
        for rec in self:
            employee = rec.employee_id
            date = max(rec.date_start, rec.date_end or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
            payroll_values = self.env['hr.payroll'].sudo().get_payroll_values(
                date=date,
                bruto=rec.wage,
                force_npd=None if rec.use_npd else 0.0,
                voluntary_pension=rec.sodra_papildomai and rec.sodra_papildomai_type,
                disability=rec.darbingumas.name if rec.invalidumas else False,
                is_foreign_resident=employee.is_non_resident,
                is_fixed_term=rec.contract_id.is_fixed_term,
                contract=rec.contract_id
            )
            net_wage = payroll_values.get('neto')
            rec.neto_monthly = tools.float_round(net_wage, precision_digits=2)

    @api.one
    @api.depends('struct_id.code', 'schedule_template_id', 'wage')
    def _hypothetical_hourly_wage(self):
        if self.struct_id.code == 'MEN':
            try:
                # P3:DivOK
                hypothetical_hourly_wage = self.wage * 12.0 / self.num_work_days_year / self.schedule_template_id.avg_hours_per_day
            except ZeroDivisionError:
                hypothetical_hourly_wage = 0
        else:
            hypothetical_hourly_wage = self.wage
        self.hypothetical_hourly_wage = hypothetical_hourly_wage

    @api.multi
    @api.constrains('avansu_politika_suma', 'avansu_politika')
    def avansu_politika_rules(self):
        if not self._context.get('constraint_advance', True):
            return
        for rec in self:
            avansas_coef = rec.employee_id.company_id.max_advance_rate_proc / 100.0  # P3:DivOK
            if rec.avansu_politika == 'fixed_sum' and tools.float_compare(
                    rec.avansu_politika_suma, 0, precision_digits=2) < 0:
                raise exceptions.ValidationError(_('Avansas negali būti neigiamas.'))

            if rec.avansu_politika != 'fixed_sum':
                max_advance_proc = avansas_coef * 100
                if tools.float_compare(rec.avansu_politika_proc, 0, precision_digits=2) < 0 or \
                        tools.float_compare(rec.avansu_politika_proc,  max_advance_proc, precision_digits=2) > 1:
                    raise exceptions.ValidationError(
                        _('Avansas negali būti neigiamas ir didesnis už {:.2f}%').format(max_advance_proc))
                continue
            neto_wage = rec.neto_monthly
            if rec.struct_id.code == 'VAL':
                neto_wage *= rec.schedule_template_id.avg_hours_per_day * rec.with_context(
                    date=rec.date_start, maximum=True).num_regular_work_days
            if tools.float_compare(neto_wage * avansas_coef, rec.avansu_politika_suma, precision_digits=2) < 0:
                raise exceptions.ValidationError(
                    _('Avansas negali būti didesnis nei {:4.2f}').format(neto_wage * avansas_coef))

    @api.one
    def set_max_advance(self):
        if self.avansu_politika == 'fixed_sum':
            current_advance = self.avansu_politika_suma
            # P3:DivOK
            max_advance = tools.float_round(self.employee_id.company_id.max_advance_rate_proc / 100.0 * self.neto_monthly, precision_digits=2)
            if tools.float_compare(max_advance, current_advance, precision_digits=2) < 0:
                self.avansu_politika_suma = max_advance

    @api.multi
    @api.constrains('date_start', 'date_end')
    def _constrains_dates(self):
        for rec in self:
            if rec.filtered(lambda c: c.date_end and c.date_start > c.date_end):
                raise exceptions.ValidationError(_('Sutarties priedo neteisingos pradžios ir pabaigos datos.'))
            if rec.date_start < rec.contract_id.date_start:
                raise exceptions.ValidationError(
                    _('Sutarties priedas %s darbuotojui %s negali prasidėti anksčiau nei sutartis %s (%s < %s).')
                    % (rec.name,
                       rec.employee_id.name,
                       rec.contract_id.name,
                       rec.date_start,
                       rec.contract_id.date_start))
            if rec.contract_id.date_end:
                if not rec.date_end:
                    raise exceptions.ValidationError(
                        _('Jei sutartis turi pabaigos datą, ją turi turėti ir sutarties priedas.'))
                elif rec.date_end > rec.contract_id.date_end:
                    raise exceptions.ValidationError(
                        _('Sutarties priedo pabaigos data negali būti vėlesnė už sutarties pabaigos datą.'))

            if self._context.get('allow_appointment_intersection'):
                continue
            if rec.date_end:
                appointments = self.env['hr.contract.appointment'].search_count([
                    ('id', '!=', rec.id),
                    ('contract_id', '=', rec.contract_id.id),
                    '|', '&',
                    ('date_start', '>=', rec.date_start),
                    ('date_start', '<=', rec.date_end),
                    '&',
                    ('date_start', '<', rec.date_start),
                    '|',
                    ('date_end', '=', False),
                    ('date_end', '>=', rec.date_start)
                ])
            else:
                appointments = self.env['hr.contract.appointment'].search_count([
                    ('id', '!=', rec.id),
                    ('contract_id', '=', rec.contract_id.id),
                    '|',
                    ('date_end', '>=', rec.date_start),
                    ('date_end', '=', False),
                ])
            if appointments:
                raise exceptions.ValidationError(_('Priedai negali susikirsti'))

    @api.multi
    def set_as_close(self):
        return self.write({'state': 'close'})

    @api.multi
    def start_new_appointment(self, date_start, **params):
        self.ensure_one()
        default_params = params.copy()
        default_params['date_start'] = date_start
        trial_date_end = default_params.get('trial_date_end') or self.trial_date_end
        if trial_date_end:
            trial_date_dt = datetime.strptime(trial_date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_start_dt = datetime.strptime(date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
            if trial_date_dt <= date_start_dt:
                default_params['trial_date_end'] = default_params['trial_date_start'] = False
            elif trial_date_dt > date_start_dt:
                default_params['trial_date_start'] = date_start
        if not default_params.get('num_leaves_per_year', False) and default_params.get('schedule_template_id', False):
            schedule_template = self.env['schedule.template'].browse(default_params['schedule_template_id'])
            invalidumas = default_params.get('invalidumas', self.employee_id.invalidumas)
            dob = self.employee_id.birthday
            job_id = default_params.get('job_id') or self.employee_id.job_id
            min_holiday_amount = self.env['hr.holidays'].get_employee_default_holiday_amount(job_id, schedule_template,
                                                                                             employee_dob=dob,
                                                                                             invalidumas=invalidumas)
            holiday_amount_from_last_appointment = self.num_leaves_per_year if \
                self.leaves_accumulation_type == 'work_days' else self.num_leaves_per_year * 5.0 / 7.0
            num_leaves = max(min_holiday_amount, holiday_amount_from_last_appointment)
            if num_leaves and default_params.get('leaves_accumulation_type', False) == 'calendar_days':
                default_params['num_leaves_per_year'] = num_leaves * 7.0 / 5.0  # P3:DivOK
            else:
                default_params['num_leaves_per_year'] = num_leaves
                default_params['leaves_accumulation_type'] = 'work_days'
        if not default_params.get('date_end'):
            default_params['date_end'] = self.date_end
        prev_day = datetime.strptime(date_start, tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(days=1)
        self.date_end = prev_day.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        # Update holiday accumulation values
        self.env['hr.employee.holiday.accumulation'].search([
            ('appointment_id', '=', self.id)
        ], limit=1).sudo().set_appointment_values()
        freeze_net_wage = default_params.get('freeze_net_wage')
        if freeze_net_wage is None:
            freeze_net_wage = self.freeze_net_wage
        if not default_params.get('wage') and freeze_net_wage:
            gross = self.calculate_new_gross_wage_based_on_updated_params(**default_params)
            default_params.update({'wage': tools.float_round(gross, precision_digits=2)})
        new_appointment = self.with_context(allow_appointment_intersection=True, constraint_advance=False).copy(default=default_params)
        new_appointment.set_max_advance()
        min_leaves, extra_leaves = new_appointment.employee_id.get_employee_leaves_num(date=new_appointment.date_start)
        num_leaves = max(min_leaves + extra_leaves, new_appointment.num_leaves_per_year)
        new_appointment.num_leaves_per_year = num_leaves
        additional_leaves = default_params.get('additional_leaves_per_year', 0)
        new_appointment.additional_leaves_per_year = self.additional_leaves_per_year + additional_leaves
        new_appointment.with_context(allow_appointment_intersection=False)._constrains_dates()
        return new_appointment

    @api.multi
    def calculate_new_gross_wage_based_on_updated_params(self, date_start, **params):
        self.ensure_one()
        current_net_wage = self.neto_monthly

        tax_rates = self.contract_id.with_context(date=date_start).get_payroll_tax_rates()
        sodra_papildomai = params.get('sodra_papildomai')
        if sodra_papildomai is None:
            sodra_papildomai = self.sodra_papildomai
        sodra_papildomai_type = params.get('sodra_papildomai_type')
        if sodra_papildomai_type is None:
            sodra_papildomai_type = self.sodra_papildomai_type

        in_zero_npd_period = self.env['zero.npd.period'].sudo().search_count([
            ('date_start', '<=', date_start),
            ('date_end', '>=', date_start)
        ])
        use_npd = params.get('use_npd', self.use_npd)
        if not use_npd or in_zero_npd_period:
            forced_tax_free_income = 0.0
        else:
            forced_tax_free_income = None

        voluntary_pension = sodra_papildomai and sodra_papildomai_type
        disability = self.employee_id.invalidumas and self.employee_id.darbingumas.name
        is_foreign_resident = self.employee_id.is_non_resident

        # Calculate the BRUTO based on frozen NET wage
        gross = self.env['hr.payroll'].sudo().convert_net_income_to_gross(
            current_net_wage, date=date_start, voluntary_pension=voluntary_pension, disability=disability,
            is_foreign_resident=is_foreign_resident, forced_tax_free_income=forced_tax_free_income,
            contract=self.contract_id, **tax_rates
        )
        return gross

    @api.model
    def move_npd_to_appointment(self):
        self.env['hr.contract.appointment'].search([]).write({'use_npd': True})
        self._cr.execute('''SELECT id, npd FROM hr_contract
                            WHERE override_taxes = True and use_npd = True''')
        for row in self._cr.dictfetchall():
            npd = row['npd']
            if tools.float_is_zero(npd, precision_digits=2):
                contract = self.env['hr.contract'].browse(row['id'])
                apppointments = contract.appointment_ids
                apppointments.write({'use_npd': False})

    @api.model
    def cron_recalculate_leaves_num(self):
        """
        This method recalculates number of leaves for employees that have recalculate_num_of_leaves set to True in their
        employee record. If the number of leaves is bigger than the one in the appointment, new appointment is created
        for employee starting from system's date. If new appointment is created, email is sent to the accountant
        informing about this. This method can also be set to run only for contracts older than 10 years or created
        exactly 10 years (and the following 5 years) ago.
        :return: None
        """

        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        new_appointments = []
        send_mail = False

        contracts = self.env['hr.contract'].search([])

        employees = contracts.mapped('employee_id').filtered(lambda e: e.recalculate_num_of_leaves is True)

        for employee in employees:

            active_appointment = employee.with_context(date=date).appointment_id

            if not active_appointment:
                continue  # no active contract appointment

            min_leave_days, extra_leaves_num = employee.get_employee_leaves_num(date=date)

            if min_leave_days:
                new_leaves_num = round(min_leave_days + extra_leaves_num, 3)
                current_leaves_num = round(active_appointment.num_leaves_per_year, 3)

                if tools.float_compare(new_leaves_num, current_leaves_num, precision_digits=3) > 0:
                    new_appointment = active_appointment.contract_id.update_terms(date,
                                                                                  num_leaves_per_year=new_leaves_num,
                                                                                  leaves_accumulation_type=active_appointment.leaves_accumulation_type)

                    if not new_appointment:
                        continue

                    if new_appointment.id != active_appointment.id:
                        send_mail = True
                        acc_type = 'd.d.'
                        if new_appointment.leaves_accumulation_type == 'calendar_days':
                            acc_type = 'k.d.'
                        new_appointments.append(
                            {'employee_name': employee.name_related, 'appointment_name': new_appointment.name,
                             'num_leaves_per_year': 'Iš %s į %s %s' %
                                                    (active_appointment.num_leaves_per_year,
                                                     new_appointment.num_leaves_per_year, acc_type)})

        # Send mail
        if send_mail:
            html = _('''<p>Sveiki,</p>
                <p>informuojame, kad šiems darbuotojams buvo sukurti nauji priedai, nes jiems perskaičiuotos atostogos per metus: </p>
                <table border="2" width="100%%">
                <tr>
                <td><b>Darbuotojas</b></td>
                <td><b>Priedo nr.</b></td>
                <td><b>Atostogos per metus</b></td>
                </tr>''')

            for appointment in new_appointments:
                html += '<tr><td>%s</td>' % appointment['employee_name']
                html += '<td>%s</td>' % appointment['appointment_name']
                html += '<td>%s</td></tr>' % appointment['num_leaves_per_year']
            html += _('''</table>
                                            <p>Dėkui,</p>
                                            <p>RoboLabs komanda</p>''')

            findir_email = self.sudo().env.user.company_id.findir.partner_id.email

            if not findir_email:
                findir_email = 'support@robolabs.lt'

            self.env['script'].send_email(emails_to=[findir_email],
                                          subject=_(
                                              'Darbuotojams buvo perskaičiuotos atostogos per metus - %s [%s].') % (
                                                  datetime.now().strftime('%Y-%m-%d'), self.env.cr.dbname),
                                          body=html)

    @api.multi
    def toggle_remote_work(self, working_remotely=False):
        self.mapped('schedule_template_id.fixed_attendance_ids').write({'working_remotely': working_remotely})

    @api.multi
    def split_at_date(self, date):
        previous_day_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(days=1)
        previous_day = previous_day_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        for rec in self:
            if rec.date_start >= date or (rec.date_end and rec.date_end <= date):
                continue
            schedule_template_id = rec.schedule_template_id.copy({'appointment_id': False})
            current_end_date = rec.date_end
            rec.write({'date_end': previous_day})
            rec.copy({
                'schedule_template_id': schedule_template_id.id,
                'date_start': date,
                'date_end': current_end_date
            })

    @api.multi
    def _leaves_accumulated_per_day(self):
        self.ensure_one()
        date = self.date_start
        date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        if self.leaves_accumulation_type == 'calendar_days':
            year_start = date_dt + relativedelta(month=1, day=1)
            year_end = date_dt + relativedelta(month=12, day=31)
            yearly_calendar_days = (year_end - year_start).days + 1
            accumulation_per_day = self.total_leaves_per_year / float(yearly_calendar_days)  # P3:DivOK
        else:
            yearly_work_days = self.with_context(date=date).num_work_days_year
            accumulation_per_day = self.total_leaves_per_year / yearly_work_days  # P3:DivOK
        return accumulation_per_day

    @api.multi
    def _get_accumulated_holiday_days(self):
        """
            Gets how many holiday days have been accumulated for a specific appointment. Ignores used days. If the
            appointment is still running - returns accumulated days to the present date
        """
        accumulated_days = 0.0
        holiday_fixes = self.env['hr.holidays.fix'].search([
            ('employee_id', 'in', self.mapped('employee_id').ids),
            ('type', '=', 'set')
        ])

        for rec in self.sorted(key=lambda app: app.date_start):
            date_from = rec.date_start
            now = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to = min(now, rec.date_end or now)

            # Allow forcing a date to
            forced_date_from = self._context.get('forced_date_from')
            forced_date_to = self._context.get('forced_date_to')
            if forced_date_to:
                date_to = max(date_from, forced_date_to)  # Must be after the start date
                if rec.date_end:
                    date_to = min(date_to, rec.date_end)  # Must be before the end date
            if forced_date_from:
                date_from = max(date_from, forced_date_from)
                if rec.date_end:
                    date_from = min(date_from, rec.date_end)

            work_relation_start_date = rec.contract_id.work_relation_start_date

            # Find the last holiday fix
            employee_holiday_fixes = holiday_fixes.filtered(
                lambda fix: fix.employee_id == rec.employee_id and fix.date >= work_relation_start_date
            )
            app_holiday_fixes = employee_holiday_fixes.filtered(lambda fix: date_from <= fix.date <= date_to).sorted(
                key=lambda fix: fix.date, reverse=True
            )
            last_holiday_fix = app_holiday_fixes and app_holiday_fixes[0]

            schedule_template = rec.schedule_template_id
            week_work_days = schedule_template.num_week_work_days or 5.0

            leaves_accumulation_type = rec.leaves_accumulation_type

            balance_adjustment = 0.0
            if last_holiday_fix:
                if leaves_accumulation_type == 'calendar_days':
                    holiday_fix_balance = last_holiday_fix.get_calendar_days(week_work_days)
                else:
                    holiday_fix_balance = last_holiday_fix.get_work_days(week_work_days)

                previous_accumulation_records = self.env['hr.employee.holiday.accumulation'].search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('date_to', '<=', date_from),
                    ('date_from', '>=', work_relation_start_date)
                ])
                current_accumulation_balance = sum(
                    previous_accumulation_records.mapped('accumulation_work_day_balance'))
                if leaves_accumulation_type == 'calendar_days':
                    try:
                        current_accumulation_balance = current_accumulation_balance * 7.0 / week_work_days  # P3:DivOK
                    except ZeroDivisionError:
                        current_accumulation_balance = current_accumulation_balance * 7.0 / 5.0  # P3:DivOK

                # Find the needed adjustment based on holiday fix
                balance_adjustment = holiday_fix_balance - current_accumulation_balance

                if last_holiday_fix.date != date_to:
                    # Compute start balance from the next day after holiday fix
                    date_from_dt = datetime.strptime(last_holiday_fix.date, tools.DEFAULT_SERVER_DATE_FORMAT)
                    date_from_dt += relativedelta(days=1)
                    date_from = date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                else:
                    balance_adjustment = 0.0

            # Get the balance at the start of the appointment
            start_balance = rec.employee_id.with_context(
                ignore_used_days=True,
                ignore_contract_end=True
            )._get_remaining_days(date=date_from, accumulation_type=leaves_accumulation_type, from_date=date_from)

            # Deduct what is accumulated per day so we get the balance at the start of the day for the start date
            accumulation_per_day = rec._leaves_accumulated_per_day()
            if (rec.leaves_accumulation_type == 'work_days' and not rec.schedule_template_id.with_context(
                    force_use_schedule_template=True, calculating_holidays=True
            ).is_work_day(date_from)) or tools.float_is_zero(start_balance, precision_digits=2):
                # No days are deducted since it's not a work day. Balance is going to be the one at the end of the day
                # before.
                accumulation_per_day = 0.0
            start_balance -= accumulation_per_day
            # Deducting the same amount of days as the start balance yields negative 0 (0.795... - 0.795... = -0.0).
            if tools.float_is_zero(start_balance, precision_digits=3):
                start_balance = abs(start_balance)
            start_balance = tools.float_round(start_balance, precision_digits=3)

            # Get the end balance
            end_balance = rec.employee_id.with_context(
                ignore_used_days=True,
                ignore_contract_end=True
            )._get_remaining_days(
                date=date_to, accumulation_type=rec.leaves_accumulation_type, from_date=date_from
            )

            holiday_balance = end_balance - start_balance + balance_adjustment
            accumulated_days += holiday_balance
        return accumulated_days

    @api.multi
    def _compute_accumulated_holiday_days(self):
        for rec in self:
            rec.accumulated_holiday_days = rec._get_accumulated_holiday_days()

    @api.multi
    def _remove_holiday_accumulation_records(self):
        """
            Removes holiday accumulation records for given records and recomputes holiday usage. Should only be used
            when the appointment is deleted.
        """
        # Remove accumulation records and recompute holiday usage
        accumulations = self.env['hr.employee.holiday.accumulation'].sudo().search([
            ('appointment_id', 'in', self.ids)
        ])
        holiday_usage_lines = accumulations.mapped('holiday_usage_line_ids')
        accumulations.sudo().with_context(bypass_appointments=True).unlink()
        holiday_usage_lines.sudo()._recompute_holiday_usage()

    @api.multi
    def _create_holiday_accumulation_records(self):
        """
            Creates HrEmployeeHolidayAccumulation records for records that do not have them and sets appointment values.
        Returns:
            object: HrEmployeeHolidayAccumulation records
        """
        HrEmployeeHolidayAccumulation = self.env['hr.employee.holiday.accumulation']
        accumulations = HrEmployeeHolidayAccumulation.sudo().search([
            ('appointment_id', 'in', self.ids)
        ])

        appointments_without_accumulation = self.filtered(
            lambda r: r.id not in accumulations.mapped('appointment_id').ids and
                      r.employee_id.type != 'intern' and
                      r.contract_id.rusis not in ['voluntary_internship', 'educational_internship'] and
                      r.schedule_template_id.men_constraint != 'val_per_men'
        )

        # Gather up required appointment data
        uid = self._uid
        appointment_data = [
            {
                'appointment_id': rec.id,
                'employee_id': rec.employee_id.id,
                'date_from': rec.date_start,
                'date_to': rec.date_end if rec.date_end else None,
                'post': rec.schedule_template_id.etatas,
                'accumulated_days': rec.accumulated_holiday_days,
                'accumulation_type': rec.leaves_accumulation_type,
                'create_uid': uid,
                'write_uid': uid,
            }
            for rec in appointments_without_accumulation
        ]

        # Manual multi create. This method can be run on all appointments at once and creating multiple records one by
        # one takes a lot of time.
        if appointment_data:
            columns = appointment_data[0].keys()

            # Converting from dict to list based on keys
            record_values = []
            for record in appointment_data:
                record_values += [record.get(column) for column in columns]

            columns = ['id', 'create_date', 'write_date'] + columns
            formatted_columns = ', '.join('\"{}\"'.format(column) for column in columns)

            # Build the query string
            query = """INSERT INTO "hr_employee_holiday_accumulation" (%s) VALUES""" % (formatted_columns)
            for i in range(len(appointment_data)):
                query += ' (nextval(\'hr_employee_holiday_accumulation_id_seq\'), (now() at time zone \'UTC\'),' \
                         ' (now() at time zone \'UTC\'), '
                for k in range(len(appointment_data[i])):
                    query += '%s'
                    if k != len(appointment_data[i]) - 1:
                        query += ', '
                query += ')'
                if i != len(appointment_data) - 1:
                    query += ','
            query += ';'

            # Only the dict keys are not sanitized, the values are since they are passed as an argument to the execute
            # method
            self._cr.execute(
                query,
                tuple(record_values)
            )

            # Return the created ids
            accumulations = HrEmployeeHolidayAccumulation.sudo().search([
                ('appointment_id', 'in', self.ids)
            ])

        for accumulation in accumulations:
            self.env['hr.employee.holiday.usage'].sudo().search([
                ('employee_id', 'in', self.mapped('employee_id').ids),
                ('date_to', '<=', accumulation.date_from)
            ])._recompute_holiday_usage()
        return accumulations

    @api.multi
    def get_active_appointment_at_date(self, date):
        if not date:
            return self.env['hr.contract.appointment']
        return self.filtered(lambda app: app.date_start <= date and (not app.date_end or app.date_end >= date))

    @api.multi
    def get_shorter_before_holidays_worked_time_data(self, date):
        """ Gets specific work time date for shorter before holidays to determine if the date should be shortened """
        self.ensure_one()
        res = {'some_time_for_period_line_is_set': False, 'worked_time_for_day': 0.0,
               'leave_is_set_in_planned_schedule': False}  # Parameter used in work_schedule
        # Find timesheet day for date
        timesheet_day = self.env['ziniarastis.day'].search([
            ('contract_id', '=', self.contract_id.id),
            ('date', '=', date)
        ], limit=1)
        if not timesheet_day:
            return res
        skipped_codes = CODES_HOLIDAYS + CODES_ABSENCE
        # Check if any of the timesheet days have lines with code not in skipped codes list with work time set
        res['some_time_for_period_line_is_set'] = not tools.float_is_zero(
            sum(timesheet_day.ziniarastis_period_line_id.mapped('ziniarastis_day_ids.ziniarastis_day_lines').filtered(
                lambda l: l.code not in skipped_codes
            ).mapped('total_worked_time_in_hours')),
            precision_digits=2
        )
        # Calculate worked time by timesheet lines for date
        res['worked_time_for_day'] = sum(timesheet_day.ziniarastis_day_lines.filtered(
            lambda l: l.code not in skipped_codes
        ).mapped('total_worked_time_in_hours'))
        return res

    @api.multi
    def get_employee_yearly_leaves(self):
        """
        Method to get amount of employee's leaves (main and additional) for provided appointment.
        :return: int leave amount, int additional leave amount;
        """
        self.ensure_one()
        return self.num_leaves_per_year, self.additional_leaves_per_year


ContractAppointment()
