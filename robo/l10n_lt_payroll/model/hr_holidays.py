# -*- coding: utf-8 -*-
from __future__ import division
import json
import pytz
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, tools, exceptions, SUPERUSER_ID
from odoo.tools import float_is_zero, float_compare
from odoo.tools.translate import _
from odoo.addons.l10n_lt_payroll.model.darbuotojai import get_vdu, get_last_work_day, PROBATION_LAW_CHANGE_DATE


def get_num_work_days(env, date_from, date_to):  # todo 6 days work week?
    date_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
    date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
    related_national_holidays = env['sistema.iseigines'].search([('date', '>=', date_from),
                                                                 ('date', '<=', date_to)]).mapped('date')
    num_days = 0
    while date_dt <= date_to_dt:
        if date_dt.weekday() not in (5, 6) and date_dt.strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT) not in related_national_holidays:
            num_days += 1
        date_dt += timedelta(days=1)
    return num_days


def check_first_two_days(date_from, date_to, on_probation=False, national_holiday_dates=None, week_days_off=(5, 6)):
    def is_day_off(date_to_check):
        if not isinstance(date_to_check, datetime):
            date_to_check = datetime.strptime(date_to_check, tools.DEFAULT_SERVER_DATE_FORMAT)
        return date_to_check.weekday() in week_days_off

    def is_national_holiday_date(date_to_check):
        if isinstance(date_to_check, datetime):
            date_to_check = date_to_check.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        return date_to_check in national_holiday_dates

    def is_regular_work_day(date_to_check):
        return not is_day_off(date_to_check) and not is_national_holiday_date(date_to_check)

    def is_on_probation(date_to_check):
        if isinstance(date_to_check, datetime):
            date_to_check = date_to_check.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        return on_probation and date_to_check < PROBATION_LAW_CHANGE_DATE

    def is_compensated_day(date_to_check):
        return is_regular_work_day(date_to_check) and not is_on_probation(date_to_check)

    if not national_holiday_dates:
        national_holiday_dates = list()
    delta = date_to - date_from
    if delta.days < 0:
        return 0  # Incorrect date range specified
    days_to_check = [date_from]  # Check the first day
    if delta.days > 0:
        days_to_check.append(date_from+relativedelta(days=1))  # Also check the second day
    return sum(1 if is_compensated_day(date) else 0 for date in days_to_check)


def calc_date_in_datetime_format(date, start=True):
    hour = 8 if start else 16
    local, utc = datetime.now(), datetime.utcnow()
    diff = utc - local
    local_time = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(hour=hour, minute=0)
    utc_time = local_time + diff
    return utc_time.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)


class HrHolidays(models.Model):
    _inherit = 'hr.holidays'

    _order = 'date_from DESC'

    def _pradzia(self):
        return datetime(datetime.utcnow().year, 1, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _pabaiga(self):
        return datetime(datetime.utcnow().year, 12, 31).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _default_date_from(self):
        date_from = datetime.now().replace(hour=8, minute=0,
                                           second=0)  # we return time in utc. difference might be 2 or 3
        # hours depending on daylight saving time
        difference = datetime.utcnow() - datetime.now()
        return (date_from + difference).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

    def _default_date_to(self):
        date_to = datetime.now().replace(hour=16, minute=0, second=0)
        difference = datetime.utcnow() - datetime.now()
        return (date_to + difference).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

    def _data(self):
        return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _default_status(self):
        return self.env['hr.holidays.status'].search([('kodas', '=', 'A')], limit=1)

    def _get_default_business_trip_holidays(self):
        return 'double'  # todo iš nustatymų?

    holiday_status_id = fields.Many2one('hr.holidays.status', default=_default_status,
                                        inverse='calculate_holiday_payment_amounts')
    contract_id = fields.Many2one('hr.contract', string='Contract', compute='_compute_contract_id', store=True,
                                  ondelete='restrict')
    date_from = fields.Datetime(default=_default_date_from, inverse='calculate_holiday_payment_amounts')
    date_to = fields.Datetime(default=_default_date_to, inverse='calculate_holiday_payment_amounts')
    data = fields.Date(string='Operacijos data', default=_data, groups='hr.group_hr_manager',
                       states={'validate': [('readonly', True)]}, track_visibility='onchange', )
    data_report = fields.Date(string='Data', compute='_compute_data_report', store=False)
    numeris = fields.Char(string='Įsakymo numeris', groups='hr.group_hr_manager', readonly=True,
                          track_visibility='onchange',)
    number_of_days = fields.Float(compute='_compute_number_of_days2', string='Number of Days', store=True)
    number_of_calendar_days = fields.Float(compute='_compute_number_of_calendar_days', string='Kalendorinių dienų')
    darbo_dienos = fields.Float(compute='_compute_darbo_dienos', string='Number of Days', store=True)
    kalendorines_dienos = fields.Integer(compute='_compute_kalendorines_dienos', string='Kalendorinės dienos',
                                         store=False)
    pavaduoja = fields.Many2one('hr.employee', string='Pavaduoja', required=False)
    ismokejimas = fields.Selection([('before_hand', 'Prieš atostogas'),
                                    ('du', 'Su darbo užmokesčiu')], default='du', string='Išmokėjimas',
                                   required=True, states={'validate': [('readonly', True)]},
                                   track_visibility='onchange', )
    ismokejimas_report = fields.Char(string='Išmokėjimas', compute='_compute_ismokejimas_report', store=False)
    vdu = fields.Float(string='VDU', compute='_compute_vdu', groups='hr.group_hr_user')
    vdu_h = fields.Float(string='VDU (valandinis)', compute='_compute_vdu', groups='hr.group_hr_user')
    neskaidyti = fields.Boolean(string='Neskaidyti', default=False)
    payment_id = fields.Many2one('hr.employee.payment', string='Išmokėjimo įrašas', readonly=True, copy=False)
    show_accounting_info = fields.Boolean(string='Rodyti apskaitos informaciją', store=False)
    accountant_informed = fields.Boolean(string='Accountant informed', groups='hr.group_hr_manager', copy=False)
    date_from_date_format = fields.Date(string='Date from date format', compute='_compute_date_from_date_format',
                                        store=True)
    date_to_date_format = fields.Date(string='Date to date format', compute='_compute_date_to_date_format', store=True)
    date_from_date_format_lt = fields.Date(string='Date from date format (Lithuanian timezone)',
                                           compute='_compute_date_from_date_format', store=True)
    date_to_date_format_lt = fields.Date(string='Date to date format (Lithuanian timezone)',
                                         compute='_compute_date_to_date_format', store=True)
    amount_business_trip = fields.Float(string='Dienpinigių suma', groups='hr.group_hr_manager',
                                        states={'validate': [('readonly', True)]})
    show_busines_trip_amount = fields.Boolean(compute='_compute_show_busines_trip_amount')
    business_trip_holidays_default = fields.Selection([('double', 'Dvigubai'),
                                                       ('extra_day', 'Papildoma diena'),
                                                       ('rest', 'Poilsio diena')],
                                                      default=_get_default_business_trip_holidays,
                                                      string='Komandiruočių apmokėjimas išeiginėmis',
                                                      help=('Nurodoma, kaip automatu pildyti žiniaraštį, jeigu '
                                                            'komandiruotės persidengia su savaitgaliu'),
                                                      states={'validate': [('readonly', True)]})
    country_allowance_id = fields.Many2one('country.allowance', string='Į kur vyksta', groups='hr.group_hr_user',
                                           states={'validate': [('readonly', True)]})
    half_amount = fields.Boolean(string='Mokėti pusę sumos', states={'validate': [('readonly', True)]})
    double_amount = fields.Boolean(string='Mokėti dvigubai (vadovams)', states={'validate': [('readonly', True)]})
    allowance_norm = fields.Float(string='Dienpinigių norma', compute='_compute_allowance_norm')
    allocated_payment_line_ids = fields.One2many('hr.holidays.payment.line', 'holiday_id', string='Atostoginiai',
                                                 states={'validate': [('readonly', True)]})
    mismatched_allocated_payment_line_ids = fields.One2many('hr.holidays.payment.line', 'holiday_id',
                                                            string='Perskaičiuoti atostoginiai',
                                                            compute='_compute_mismatched_allocated_payment_line_ids')
    should_be_recomputed = fields.Boolean(string='Turėtų būti perskaičiuota (nesutapus perskaičiuotiems atostoginiams)',
                                          compute='_compute_should_be_recomputed')
    show_allocated_payments = fields.Boolean(compute='_compute_show_allocated_payments')

    info_json = fields.Text(compute='_compute_info_text', groups='hr.group_hr_manager')
    info_text = fields.Text(compute='_compute_info_text', groups='hr.group_hr_manager')
    sick_leave_continue = fields.Boolean(string='Tęsiamas nedarbingumo lapelis',
                                         states={'validate': [('readonly', True)],
                                                 'cancel': [('readonly', True)],
                                                 'refuse': [('readonly', True)]})
    appointment_id = fields.Many2one('hr.contract.appointment', string='Susijęs sutarties priedas',
                                     compute='_compute_appointment_id')
    leaves_accumulation_type = fields.Selection([('work_days', 'Darbo dienomis'),
                                                 ('calendar_days', 'Kalendorinėmis dienos')],
                                                string='Atostogų kaupimo tipas',
                                                related='appointment_id.leaves_accumulation_type', store=False,
                                                readonly=True)
    informed = fields.Boolean(string='Informuoti buhalteriai', readonly=True, copy=False)

    npsd = fields.Float(compute='_compute_npsd', string='Menamas NP-SD')
    recalculate = fields.Boolean(default=False, string='Perskaičiuoti VDU pasiekus atostogų mėnesį')
    force_recalculate = fields.Boolean(default=False, string='Perskaičiuoti atostogas')
    is_mb = fields.Boolean(compute='_compute_is_mb')
    is_business_trip = fields.Boolean(compute='_compute_is_business_trip')
    business_trip_worked_on_weekends = fields.Boolean(string='Dirbta savaitgaliais', default=True)
    department_id = fields.Many2one('hr.department', compute='_compute_company_id', store=True, related=False,
                                    compute_sudo=False, track_visibility='onchange', )
    user_id = fields.Many2one('res.users', string='User', compute='_compute_company_id', related=False, store=True,
                              compute_sudo=False)
    company_id = fields.Many2one('res.company', compute='_compute_company_id', store=True, readonly=True, related=False,
                                 compute_sudo=False)
    date_vdu_calc = fields.Date('VDU skaičiavimo data', help=_('Naudojama pastūmus atostogas'))
    holiday_status_code = fields.Char(compute='_compute_holiday_status_code')
    gpm_paid = fields.Boolean('GPM sumokėtas', states={'validate': [('readonly', True)]})
    payment_before_15th = fields.Boolean('Išmokėjimo data iki 15d.', compute='_compute_payment_before_15th',
                                         search='_search_payment_before_15th')
    on_probation = fields.Boolean('Neturi stažo', help='Darbuotojas neturi stažo ligos išmokai gauti',
                                  states={'validate': [('readonly', True)]})
    allowance_payout = fields.Selection([
            ('after_signing', _('Pasirašius dokumentą')),
            ('with_salary_payment', _('Su darbo užmokesčio mokėjimu')),
            ('dont_create', _('Kol kas nemokėti'))
        ], string='Dienpinigių išmokėjimas', help='Kada mokami darbuotojų dienpinigiai',
        readonly=True,  states={'draft': [('readonly', False)]}, default='with_salary_payment'
    )
    is_paid_for = fields.Boolean('Apmokama', states={'validate': [('readonly', True)]})  # Only on some special leave types
    ignore_recalculation_warnings = fields.Boolean('Išjungti įspėjimus dėl galimų perskaičiavimų', track_visibility='always')
    allow_recalculation_warnings_to_be_ignored = fields.Boolean('Leisti ignoruoti įspėjimus dėl galimų perskaičiavimų',
                                                                readonly=True)
    holiday_usage_id = fields.Many2one('hr.employee.holiday.usage', readonly=True)
    holiday_usage_line_ids = fields.One2many('hr.employee.holiday.usage.line', related='holiday_usage_id.line_ids',
                                             readonly=True, inverse='_adjust_payments_based_on_holiday_usage')
    holiday_accumulation_usage_policy = fields.Boolean(
        string='Use holiday accumulation and usage records when calculating holiday payments',
        groups='hr.group_hr_manager', inverse='calculate_holiday_payment_amounts', store=True,
        default=lambda self: self.env.user.company_id.holiday_accumulation_usage_is_enabled
    )
    force_shorten = fields.Boolean(
        string='Priverstinai sutrumpintos atostogos',
        help='Atostogos buvo sutrumpintos rankiniu būdu, SoDra robotai nepratęs jų, jei pažymėta varnelė',
        track_visibility='onchange',
    )
    show_force_shorten = fields.Boolean(compute='_compute_show_force_shorten')
    should_have_a_usage_record = fields.Boolean(compute='_compute_should_have_a_usage_record')

    is_sent_to_sodra = fields.Boolean(string='Data about holiday record was sent so SoDra')
    accumulative_work_time_accounting = fields.Boolean(compute='_compute_accumulative_work_time_accounting')
    holiday_payment = fields.Selection(string='Holiday payment', default='paid_half_of_vdu',
                                       selection=[('paid_at_vdu', 'Paid at VDU'),
                                                  ('paid_half_of_vdu', 'Paid half of VDU'),
                                                  ('other_amount', 'Other amount'),
                                                  ('not_paid', 'Not paid')],
                                       states={'validate': [('readonly', True)]})
    payment_amount = fields.Float(string='Payment amount', states={'validate': [('readonly', True)]})

    #####################
    #  COMPUTE METHODS  #
    #####################

    @api.multi
    @api.depends('date_from', 'employee_id', 'employee_id.contract_ids')
    def _compute_contract_id(self):
        for rec in self:
            rec.contract_id = self.env['hr.contract'].search([
                ('employee_id', '=', rec.employee_id.id),
                ('date_start', '<=', rec.date_from_date_format),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', rec.date_from_date_format),
            ], limit=1).exists()

    @api.multi
    @api.depends('data')
    def _compute_data_report(self):
        for rec in self:
            if rec.sudo().data:
                rec.data_report = rec.sudo().data
            else:
                rec.data_report = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    @api.depends('number_of_days_temp', 'date_from', 'date_to')
    def _compute_number_of_days2(self):
        for hol in self:
            if hol.type == 'add':
                hol.number_of_days = hol.number_of_days_temp
            elif hol.date_from and hol.date_to and hol.type != 'add':
                nuo = datetime.strptime(hol.date_from, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                iki = datetime.strptime(hol.date_to, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                # pridetos iseigines
                iseigines = len(self.env['sistema.iseigines'].search([('date', '>=', hol.date_from),
                                                                      ('date', '<=', hol.date_to)]))
                hol.number_of_days = -((iki - nuo).days + 1 - iseigines)
            else:
                hol.number_of_days = hol.get_num_work_days()

    @api.multi
    def _compute_number_of_calendar_days(self):
        for rec in self:
            if rec.date_from_date_format and rec.date_to_date_format:
                date_from_date_format_dt = datetime.strptime(rec.date_from_date_format, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_to_date_format_dt = datetime.strptime(rec.date_to_date_format, tools.DEFAULT_SERVER_DATE_FORMAT)
                rec.number_of_calendar_days = (date_to_date_format_dt - date_from_date_format_dt).days + 1
            else:
                rec.number_of_calendar_days = 0

    @api.multi
    @api.depends('number_of_days', 'date_from', 'date_to', 'employee_id')
    def _compute_darbo_dienos(self):
        for rec in self:
            number_of_days_temp = rec.get_num_work_days()
            rec.number_of_days_temp = number_of_days_temp
            rec.darbo_dienos = -number_of_days_temp

    @api.multi
    @api.depends('number_of_days_temp', 'date_from', 'date_to')
    def _compute_kalendorines_dienos(self):
        for rec in self:
            rec.kalendorines_dienos = -rec.number_of_days

    @api.multi
    @api.depends('ismokejimas')
    def _compute_ismokejimas_report(self):
        for rec in self:
            rec.ismokejimas_report = rec.sudo().ismokejimas if rec.sudo().ismokejimas else 'nenurodyti'

    @api.multi
    @api.depends('date_from', 'date_to', 'employee_id')
    def _compute_vdu(self):
        for rec in self:
            rec.vdu = get_vdu(self.env, rec.date_from_date_format, rec.employee_id, contract_id=rec.contract_id.id,
                               vdu_type='d').get('vdu', 0.0)
            rec.vdu_h = get_vdu(self.env, rec.date_from_date_format, rec.employee_id, contract_id=rec.contract_id.id,
                               vdu_type='h').get('vdu', 0.0)

    @api.depends('date_from')
    def _compute_date_from_date_format(self):
        vilnius_tz = pytz.timezone('Europe/Vilnius')
        for rec in self:
            if rec.date_from:
                rec.date_from_date_format = rec.date_from[:10]
                date_from = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                date_from_local = pytz.utc.localize(date_from).astimezone(vilnius_tz)
                rec.date_from_date_format_lt = date_from_local.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            else:
                rec.date_from_date_format = False
                rec.date_from_date_format_lt = False

    @api.depends('date_to')
    def _compute_date_to_date_format(self):
        vilnius_tz = pytz.timezone('Europe/Vilnius')
        for rec in self:
            if rec.date_to:
                rec.date_to_date_format = rec.date_to[:10]
                date_to = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                date_to_local = pytz.utc.localize(date_to).astimezone(vilnius_tz)
                rec.date_to_date_format_lt = date_to_local.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            else:
                rec.date_to_date_format = False
                rec.date_to_date_format_lt = False

    @api.multi
    @api.depends('holiday_status_id')
    def _compute_show_busines_trip_amount(self):
        for rec in self:
            rec.show_busines_trip_amount = True if rec.holiday_status_id.kodas == 'K' else False

    @api.multi
    def _compute_allowance_norm(self):
        for rec in self:
            if rec.country_allowance_id and rec.date_from_date_format and rec.date_from_date_format:
                amount_norm = rec.country_allowance_id.get_amount(rec.date_from_date_format, rec.date_to_date_format)
                if rec.double_amount and rec.date_to_date_format < '2020-01-01':
                    amount_norm *= 2
            else:
                amount_norm = 0
            rec.allowance_norm = amount_norm

    @api.multi
    @api.depends('allocated_payment_line_ids')
    def _compute_mismatched_allocated_payment_line_ids(self):
        for rec in self:
            rec.mismatched_allocated_payment_line_ids = rec.allocated_payment_line_ids.filtered(
                lambda l: not l.recomputed_values_match)

    @api.multi
    @api.depends('allocated_payment_line_ids')
    def _compute_should_be_recomputed(self):
        for rec in self:
            rec.should_be_recomputed = len(rec.with_prefetch().mismatched_allocated_payment_line_ids) > 0

    @api.multi
    @api.depends('type', 'holiday_status_id')
    def _compute_show_allocated_payments(self):
        for rec in self:
            rec.show_allocated_payments = rec.type == 'remove' and rec.holiday_status_id.kodas == 'A'

    @api.one
    def _compute_info_text(self):
        res = ''
        kodas = self.holiday_status_id.kodas
        if kodas in ['K', 'A']:
            contract = self.contract_id or self.employee_id.contract_id
            vdu_date = self._context.get('vdu_date', self.date_from)
            try:
                vdu_date_dt = datetime.strptime(vdu_date, tools.DEFAULT_SERVER_DATE_FORMAT)
            except ValueError:
                vdu_date_dt = datetime.strptime(vdu_date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            date_from_dt = vdu_date_dt + relativedelta(day=1)
            date_to_dt = vdu_date_dt + relativedelta(day=31)
            standard_work_time_period_data = self.env['hr.payroll'].sudo().standard_work_time_period_data(
                date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                date_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            )
            work_days_in_month = standard_work_time_period_data.get('days', 0.0)
            if tools.float_is_zero(work_days_in_month, precision_digits=2):
                min_daily_wage = 8 * contract.with_context(date=vdu_date).get_payroll_tax_rates(
                    ['min_hourly_rate']
                )['min_hourly_rate']
            else:
                min_daily_wage = contract.employee_id.get_minimum_wage_for_date(vdu_date)['day']
            if kodas == 'K':
                amount_name = _('Dienpinigiai')
                total_amount = self.amount_business_trip
                num_days = abs(self.number_of_days)
            else:  # todo ar žiūrėti sumiškai ar pamėnesiui?
                amount_name = _('Atostoginiai')
                total_amount = sum(self.allocated_payment_line_ids.mapped('amount'))
                num_days = sum(self.allocated_payment_line_ids.mapped('num_work_days'))

            amount_per_day = total_amount / num_days if num_days > 0 else 0.0  # P3:DivOK

            if float_compare(min_daily_wage, amount_per_day, precision_digits=2) > 0:
                res = _('{0} sudaro {1} per dieną, o minimalus atlyginimas yra {2} už 8 valandas'). \
                    format(amount_name, "{0:.2f}".format(amount_per_day), "{0:.2f}".format(min_daily_wage))

        self.info_text = res
        self.info_json = json.dumps({'text': res})

    @api.multi
    @api.depends('date_to_date_format', 'employee_id.appointment_ids')
    def _compute_appointment_id(self):
        for rec in self:
            rec.appointment_id = rec.with_context(date=rec.date_to_date_format).employee_id.appointment_id

    @api.multi
    @api.depends('holiday_status_id', 'employee_id', 'vdu', 'date_from', 'date_to', 'sick_leave_continue', 'on_probation')
    def _compute_npsd(self):
        for rec in self:
            npsd = 0.0
            is_liga = rec.holiday_status_id.kodas == 'L'
            continuation = rec.sick_leave_continue
            fields_are_set = rec.employee_id and rec.vdu and rec.date_from and rec.date_to
            if is_liga and not continuation and fields_are_set and \
                    (not rec.on_probation or rec.date_to_date_format >= PROBATION_LAW_CHANGE_DATE):
                koeficientas = rec.company_id.with_context(date=rec.date_from[:10]).ligos_koeficientas

                date_from = rec.date_from[:10]
                date_to = rec.date_to[:10]

                date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)

                national_holiday_dates = self.env['sistema.iseigines'].search([
                    ('date', '>=', date_from),
                    ('date', '<=', date_to),
                ]).mapped('date')

                payslip_start = date_from_dt + relativedelta(day=1)
                payslip_end = date_to_dt + relativedelta(day=31)

                contract = rec.employee_id.contract_id.with_context(date=payslip_start)
                schedule_template = rec.appointment_id.schedule_template_id

                if contract.struct_id.code == 'MEN':
                    mma = contract.get_payroll_tax_rates(['mma'])['mma']
                    number_work_days = get_num_work_days(
                        self.env,
                        str(payslip_start.date()),
                        str(payslip_end.date())
                    )
                    min_day_pay = mma / number_work_days if number_work_days > 0 else 0.0  # P3:DivOK
                    min_day_pay *= schedule_template.etatas or 1.0
                elif contract.struct_id.code == 'VAL':
                    min_hourly = contract.employee_id.get_minimum_wage_for_date(rec.date_to[:10])['hour']
                    min_day_pay = min_hourly * schedule_template.avg_hours_per_day
                else:
                    min_day_pay = 0.0
                amount_to_use = max(rec.vdu, min_day_pay)
                pay_per_day = koeficientas * amount_to_use
                week_days_off = schedule_template.off_days() if schedule_template else [5, 6]
                number_absence_days = check_first_two_days(date_from_dt, date_to_dt, rec.on_probation,
                                                           national_holiday_dates, week_days_off)
                npsd = round(pay_per_day * number_absence_days, 2)
            rec.npsd = npsd

    @api.multi
    @api.depends('employee_id')
    def _compute_is_mb(self):
        for rec in self:
            rec.is_mb = rec.employee_id and rec.employee_id.type == 'mb_narys'

    @api.multi
    @api.depends('holiday_status_id')
    def _compute_is_business_trip(self):
        for rec in self:
            rec.is_business_trip = rec.holiday_status_id.kodas == 'K'

    @api.multi
    @api.depends('employee_id')
    def _compute_company_id(self):
        for rec in self:
            if rec.employee_id:
                rec.company_id = rec.employee_id.company_id.id
                rec.department_id = rec.employee_id.department_id.id
                rec.user_id = rec.employee_id.user_id.id

    @api.multi
    @api.depends('holiday_status_id.kodas')
    def _compute_holiday_status_code(self):
        for rec in self:
            rec.holiday_status_code = rec.holiday_status_id.kodas

    @api.multi
    @api.depends('payment_id', 'payment_id.date_payment')
    def _compute_payment_before_15th(self):
        for rec in self:
            if not rec.payment_id:
                rec.payment_before_15th = False
            else:
                date_payment_dt = datetime.strptime(rec.payment_id.date_payment, tools.DEFAULT_SERVER_DATE_FORMAT)
                rec.payment_before_15th = date_payment_dt.day <= 15

    @api.multi
    @api.depends('holiday_status_id')
    def _compute_show_force_shorten(self):
        sick_holiday_statuses = self.get_sick_holiday_statuses()
        for rec in self:
            rec.show_force_shorten = self.holiday_status_id in sick_holiday_statuses

    @api.multi
    @api.depends('date_to', 'employee_id', 'holiday_status_id')
    def _compute_should_have_a_usage_record(self):
        """ Determines if a holiday should have an accumulation record based on the holiday dates """
        # Determine the employees
        employees = self.mapped('employee_id')

        annual_leave_holiday_status = self.env.ref('hr_holidays.holiday_status_cl')

        for employee in employees:
            # Find the date when the employee started accumulating holidays using holiday accumulation records
            holiday_accumulation_start_date = employee.holiday_accumulation_usage_start_date
            if not holiday_accumulation_start_date:
                continue  # Employee is not accumulating holidays

            # Filter annual leaves for the employee
            employee_holidays = self.filtered(
                lambda h: h.employee_id == employee and h.holiday_status_id == annual_leave_holiday_status
            )
            for holiday in employee_holidays:
                # Any holiday before the accumulation start date should not have a usage record.
                holiday.should_have_a_usage_record = holiday.date_to_date_format > holiday_accumulation_start_date

    @api.multi
    def _compute_accumulative_work_time_accounting(self):
        for rec in self:
            appointments = rec.contract_id.appointment_ids.filtered(
                lambda app: app.date_start <= rec.date_to_date_format and
                            (not app.date_end or app.date_end >= rec.date_from_date_format)
            )
            template_types = appointments.mapped('schedule_template_id.template_type')
            rec.accumulative_work_time_accounting = 'sumine' in template_types

    @api.multi
    def _search_payment_before_15th(self, operator, value):
        holidays_with_payment = self.search([('payment_id', '!=', False)])
        find_iki_15 = (operator == '=' and value is True) or (operator == '!=' and value is False)
        ids = []
        for hol in holidays_with_payment:
            iki_15 = datetime.strptime(hol.payment_id.date_payment, tools.DEFAULT_SERVER_DATE_FORMAT).day <= 15
            if find_iki_15 != iki_15:
                continue
            else:
                ids.append(hol.id)
        return [('id', 'in', ids)]

    @api.model
    def split_employee_holidays(self, employee_id):
        # If any holiday period has multiple contracts for an employee - this method splits the holiday.
        holiday_ids = self.search([
            ('employee_id', '=', employee_id.id),
            ('state', '=', 'validate')
        ]).filtered(lambda h: not h.payment_id or
                              not any(is_reconciled for is_reconciled in
                                      h.payment_id.mapped('account_move_ids.line_ids.reconciled')))
        if not holiday_ids:
            return

        contract_ids = self.env['hr.contract'].search([('employee_id', '=', employee_id.id)])
        if not contract_ids:
            return

        new_holiday_ids = self.env['hr.holidays']

        for holiday in holiday_ids:
            hol_date_start = holiday.date_from_date_format
            hol_date_end = holiday.date_to_date_format

            holiday_period_contract_ids = contract_ids.filtered(lambda c:
                                                                c.date_start <= hol_date_end and
                                                                (not c.date_end or c.date_end >= hol_date_start))

            if len(holiday_period_contract_ids) < 2:
                continue

            i = -1
            for holiday_period_contract_id in holiday_period_contract_ids.sorted(key=lambda c: c.date_start):
                i += 1
                period_start = max(holiday_period_contract_id.date_start, hol_date_start)
                contract_end = holiday_period_contract_id.date_end or hol_date_end
                period_end = min(contract_end, hol_date_end)

                if i == 0:
                    holiday.write({'date_to': calc_date_in_datetime_format(period_end, False)})
                    new_holiday_ids |= holiday
                else:
                    new_holiday_id = holiday.copy({
                        'date_from': calc_date_in_datetime_format(period_start),
                        'date_to': calc_date_in_datetime_format(period_end, False)
                    })
                    new_holiday_id.action_validate()
                    new_holiday_ids |= new_holiday_id

        new_holiday_ids.recalculate_holiday_payment_amounts()
        for holiday in new_holiday_ids:
            holiday.update_ziniarastis()

    @api.model
    def find_holidays_that_need_to_be_recomputed(self, date_from, date_to, employee_id, contract_id):
        holiday_status_id = self.env.ref('hr_holidays.holiday_status_cl').id
        domain = [
            ('type', '=', 'remove'),
            ('holiday_status_id', '=', holiday_status_id),
            ('date_to_date_format', '>=', date_from),
            ('date_from_date_format', '<=', date_to),
            ('employee_id', '=', employee_id.id),
            ('state', '=', 'validate'),
            '|',
            ('contract_id', '=', contract_id.id),
            ('contract_id', '=', False)
        ]
        hols = self.env['hr.holidays'].search(domain)
        need_recomputing_holidays = self.env['hr.holidays']
        for hol in hols:
            for payment in hol.allocated_payment_line_ids:
                dt_from = max(payment.period_date_from, hol.date_from_date_format)
                dt_to = min(payment.period_date_to, hol.date_to_date_format)
                vdu_date = hol.date_vdu_calc or hol.date_from_date_format
                amount_bruto, vdu, num_work_days = hol.with_context(period_date_from=dt_from, period_date_to=dt_to,
                                                                    vdu_date=vdu_date).get_holiday_pay_data()
                amounts_match = tools.float_compare(payment.amount, amount_bruto, precision_digits=2) == 0
                vdu_match = tools.float_compare(payment.vdu, vdu, precision_digits=2) == 0
                num_work_days_match = tools.float_compare(payment.num_work_days, num_work_days, precision_digits=2) == 0
                if not amounts_match or not vdu_match or not num_work_days_match:
                    need_recomputing_holidays |= hol
                    break
        return need_recomputing_holidays

    @api.multi
    @api.constrains('state', 'payment_id', 'holiday_status_id')
    def _check_validated_has_payment_id(self):
        if self._context.get('skip_from_script'):
            return
        for rec in self:
            if rec.state == 'validate' and \
                    rec.holiday_status_id.tabelio_zymejimas_id.code == 'A' and not rec.payment_id:
                raise exceptions.ValidationError(_('Nesukurtas išmokėjimo įrašas'))

    @api.constrains('contract_id')
    def _check_contract_is_set(self):
        if not all(rec.contract_id or rec.employee_id.type == 'mb_narys' for rec in self):
            raise exceptions.UserError(_('Nenustatyta darbo sutartis'))

    @api.multi
    def action_ignore_recalculation_warnings(self):
        self.write({'ignore_recalculation_warnings': True})

    @api.model
    def generate_num_work_days(self):
        years = range(2015, 2030)
        for year in years:
            num_5_days_week = 0
            num_6_days_week = 0
            date = datetime(year, 1, 1)
            while date.year == year:
                if not self.env['sistema.iseigines'].search(
                        [('date', '=', date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))]):
                    weekday = date.weekday()
                    if weekday != 6:
                        num_6_days_week += 1
                        if weekday != 5:
                            num_5_days_week += 1
                date += timedelta(days=1)
            print 'Year: %s, num reg work days: %s, num work days 6 per week: %s' % (
                year, num_5_days_week, num_6_days_week)

    @api.onchange('employee_id')
    def _onchange_contract_employee(self):
        if not self.holiday_accumulation_usage_policy:
            self.holiday_accumulation_usage_policy = self.employee_id.holiday_accumulation_usage_policy

    @api.onchange('country_allowance_id', 'number_of_days', 'half_amount')
    def onchange_country_allowance_id(self):
        if self.country_allowance_id:
            amount = self.allowance_norm
            if self.half_amount:
                amount *= 0.5
            self.amount_business_trip = amount

    @api.multi
    @api.constrains('contract_id', 'employee_id')
    def constrain_contract_employee(self):
        for rec in self:
            if rec.contract_id and rec.contract_id.employee_id != rec.employee_id:
                raise exceptions.ValidationError(_('Kontraktas %s nepriklauso darbuotojui %s')
                                                 % (self.contract_id.name, self.employee_id.name))

    @api.constrains('date_from', 'date_to', 'holiday_status_id')
    def _check_date(self):
        poilsio_type_id = self.env.ref('hr_holidays.holiday_status_P', raise_if_not_found=False)
        poilsio_type_id = poilsio_type_id and poilsio_type_id.id or False
        for holiday in self.filtered(lambda r: r.type == 'remove' and r.holiday_status_id.id != poilsio_type_id):
            domain = [
                ('date_from', '<=', holiday.date_to),
                ('date_to', '>=', holiday.date_from),
                ('employee_id', '=', holiday.employee_id.id),
                ('id', '!=', holiday.id),
                ('type', '=', 'remove'),
                ('state', 'not in', ['cancel', 'refuse']),
                ('holiday_status_id', '!=', poilsio_type_id),
            ]
            nholidays = self.env['hr.holidays'].search_count(domain)
            if nholidays:
                raise exceptions.ValidationError(_('Negalima turėti persidengiančių neatvykimo įrašų. '
                                                   'Neatvykimo įrašai persidengia {}').format(holiday.employee_id.name))

    @api.multi
    def action_refuse(self):
        res = super(HrHolidays, self).action_refuse()
        for rec in self:
            if rec.payment_id:
                if rec.payment_id.state != 'done':
                    rec.payment_id.unlink()
                else:
                    rec.payment_id.force_unlink()
            rec.update_ziniarastis()
            if rec.type == 'remove' and rec.holiday_status_id.kodas in ['A']:
                self.env['hr.holidays.fix'].auto_change_fix(rec.employee_id.id, rec.date_from_date_format,
                                                            rec.date_to_date_format, 'remove', rec.contract_id.id)
            message = _('Buvęs laikotarpis: %s - %s\n') % (rec.date_from_date_format, rec.date_to_date_format)
            rec.message_post(subtype='mt_comment', body=message)

        if self:
            date_from = min(self.mapped('date_from_date_format'))
            self.with_context(forced_recompute_date=date_from)._recompute_holiday_usage()

        return res

    @api.multi
    def name_get(self):
        return [(leave.id, "%s %s : %.2f d." % (leave.employee_id.name or leave.category_id.name,
                                                leave.holiday_status_id.name,
                                                -leave.number_of_days))
                for leave in self]

    def get_num_work_days(self):
        if not self.date_from or not self.date_to:
            return 0
        appointment = self.employee_id.with_context(date=self.date_to).appointment_id
        if appointment:
            schedule_id = appointment.schedule_template_id
            temp_days = schedule_id.num_work_days(self.date_from_date_format, self.date_to_date_format)
            return temp_days if temp_days > 0 else 0
        else:
            return 0

    @api.multi
    def check_holidays(self):
        return True

    @api.model
    def irasyti_action(self):
        isakymas = self.env['ir.actions.report.xml'].search([('report_name', '=',
                                                              'l10n_lt_payroll.report_atostogu_isakymas_sl')])
        if isakymas:
            isakymas.create_action()

    @api.one
    def stop_in_the_middle(self, date):
        """
        Shorten an existing confirmed leave record
        :param date: last holiday day, type: str, format DEFAULT_SERVER_DATE_FORMAT
        :return: None
        """
        if not self.state == 'validate':
            raise exceptions.Warning(_('Negalima atšaukti nepatvirtintų atostogų'))
        if self.date_from_date_format > date:
            raise exceptions.Warning(_('Negalima atšaukti atostogų ankstesne data nei jos prasidėjo'))
        if self.date_to_date_format < date:
            raise exceptions.Warning(_('Negalima atšaukti atostogų vėlesne data nei jos prasidėjo'))
        message = _('Buvęs laikotarpis: %s - %s') % (self.date_from_date_format, self.date_to_date_format)
        date_to = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        original_date_to_strf = self.date_to_date_format
        original_date_to = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATETIME_FORMAT)
        date_to += relativedelta(hour=original_date_to.hour, minute=original_date_to.minute, second=original_date_to.second)
        self.date_to = date_to.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        change_date_from = (date_to + timedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        change_date_to = original_date_to.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        if self.type == 'remove' and self.holiday_status_id.kodas in ['A']:
            self.env['hr.holidays.fix'].auto_change_fix(self.employee_id.id, change_date_from, change_date_to, 'add',
                                                        self.contract_id.id)
        message += '\n'
        message += _('Naujas laikotarpis: %s - %s') % (self.date_from_date_format, self.date_to_date_format)
        self.message_post(subtype='mt_comment', body=message)
        self.sudo().calculate_holiday_payment_amounts()
        self.sudo().force_recompute_payments()
        self.update_ziniarastis(date_from=self.date_from_date_format, date_to=original_date_to_strf)

    @api.multi
    def create_holiday_payment(self):
        self.ensure_one()
        employee = self.employee_id
        if self.type == 'remove' and self.holiday_status_id.kodas in ['A']:
            company = employee.company_id
            date_str = self.date_from[:10]
            date_payment = self.get_date_of_payment()
            if not date_payment:
                raise exceptions.UserError(_('Nenurodyta atostoginių išmokėjimo data'))
            try:
                date_dt = datetime.strptime(date_str, tools.DEFAULT_SERVER_DATE_FORMAT)
            except ValueError:
                date_dt = datetime.strptime(date_str, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            date_from_dt = date_dt - relativedelta(day=1)
            date_to_dt = date_dt + relativedelta(day=31)
            date_from = date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to = date_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            journal_id = company.salary_journal_id.id
            payments_by_period = []
            for payment_line in self.allocated_payment_line_ids:
                if tools.float_is_zero(payment_line.num_work_days, precision_digits=2) and tools.float_is_zero(payment_line.amount, precision_digits=2):
                    continue
                bruto = payment_line.amount
                contract = self.contract_id or employee.with_context(date=self.date_from_date_format).contract_id

                appointment = contract.with_context(date=self.date_from_date_format).appointment_id
                if not appointment:
                    appointments = contract.appointment_ids.filtered(lambda a:
                                                                     a.date_start <= self.date_to_date_format and
                                                                     (not a.date_end or
                                                                      a.date_end >= self.date_from_date_format)
                                                                     ).sorted(lambda a: a.date_start)
                    appointment = appointments[0] if appointments else False
                if not appointment:
                    appointment = contract.appointment_ids.filtered(lambda a: a.date_end >= self.date_from_date_format).sorted(key=lambda a: a.date_start)

                voluntary_pension = disability = is_foreign_resident = terminated_contract = False
                if appointment:
                    if appointment.sodra_papildomai:
                        voluntary_pension = appointment.sodra_papildomai_type
                    if appointment.invalidumas:
                        disability = appointment.darbingumas.name
                    is_foreign_resident = appointment.employee_id.sudo().is_non_resident
                    terminated_contract = appointment.contract_id.is_fixed_term

                forced_npd = None if appointment.use_npd else 0.0

                existing_payment_lines = self.env['hr.employee.payment.line'].search([
                    ('date_from', '=', payment_line.period_date_from),
                    ('date_to', '=', payment_line.period_date_to),
                    ('payment_id.employee_id', '=', appointment.employee_id.id)
                ])
                used_up_npd = sum(existing_payment_lines.mapped('amount_npd'))
                bruto_from_payments = sum(existing_payment_lines.mapped('amount_bruto'))

                payroll_values = self.env['hr.payroll'].get_payroll_values(
                    date=self.date_from_date_format,
                    bruto=bruto,
                    voluntary_pension=voluntary_pension,
                    disability=disability,
                    force_npd=forced_npd,
                    npd_adjustment=-used_up_npd,
                    bruto_from_other_payments=bruto_from_payments,
                    npd_date=date_payment,
                    is_foreign_resident=is_foreign_resident,
                    is_fixed_term=terminated_contract,
                )

                sodra = payroll_values.get('employee_pension_tax', 0.0) + payroll_values.get('voluntary_sodra', 0.0) + payroll_values.get('employee_health_tax', 0.0)

                payments_by_period.append((0, 0, {'date_from': payment_line.period_date_from,
                                                  'date_to': payment_line.period_date_to,
                                                  'amount_bruto': bruto,
                                                  'amount_paid': payroll_values.get('neto', 0.0),
                                                  'amount_npd': payroll_values.get('npd', 0.0),
                                                  'amount_gpm': payroll_values.get('gpm', 0.0),
                                                  'amount_sodra': sodra,
                                                  'vdu': payment_line.vdu}))
            if not float_is_zero(sum(p[2]['amount_paid'] for p in payments_by_period),
                                 precision_rounding=company.currency_id.rounding):
                # saskaita_debetas = self.employee_id.department_id.saskaita_debetas.id or self.employee_id.company_id.saskaita_debetas.id
                saskaita_debetas = employee.department_id.atostoginiu_kaupiniai_account_id.id or company.atostoginiu_kaupiniai_account_id.id
                saskaita_kreditas = employee.department_id.saskaita_kreditas.id or company.saskaita_kreditas.id
                saskaita_gpm = contract.gpm_credit_account_id.id or employee.department_id.saskaita_gpm.id or \
                               company.saskaita_gpm.id
                vals = {
                    'state': 'draft',
                    'contract_id': self.contract_id.id,
                    'employee_id': employee.id,
                    'partner_id': employee.address_home_id.id,
                    'date': date_to,
                    'date_payment': date_payment,
                    'date_from': date_from,
                    'date_to': date_to,
                    'currency_id': False,
                    'journal_id': journal_id,
                    'type': 'holidays',
                    # 'holidays_id': self.id,
                    'payment_line_ids': payments_by_period,
                    'a_klase_kodas_id': self.env.ref('l10n_lt_payroll.a_klase_kodas_1').id,
                    'saskaita_debetas': saskaita_debetas,
                    'saskaita_kreditas': saskaita_kreditas,
                    'saskaita_gpm': saskaita_gpm,
                }
                holiday_pay = self.env['hr.employee.payment'].with_context(creating_holiday_payments=True).create(vals)
                self.payment_id = holiday_pay.id
                self.payment_id.check_if_holiday_payment_ready()
        elif self.type == 'remove' and self.holiday_status_id.kodas in ['K']:
            company = employee.company_id
            date_str = self.date_from[:10]
            date_payment = self.get_date_of_payment()
            if not date_payment:
                raise exceptions.UserError(_('Nenurodyta atostoginių išmokėjimo data'))
            try:
                date_dt = datetime.strptime(date_str, tools.DEFAULT_SERVER_DATE_FORMAT)
            except ValueError:
                date_dt = datetime.strptime(date_str, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            date_from_dt = date_dt - relativedelta(day=1)
            date_to_dt = date_dt + relativedelta(day=31)
            date_from = date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to = date_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            journal = company.salary_journal_id
            if journal:
                journal_id = journal.id
            else:
                journal_id = False
            amount = self.amount_business_trip
            if float_compare(amount, 0, precision_digits=2) > 0:
                vals = {
                    'state': 'ready',
                    'description': 'Dienpinigiai',
                    'contract_id': self.contract_id.id,
                    'employee_id': employee.id,
                    'partner_id': employee.address_home_id.id,
                    'date': date_to,
                    'date_payment': date_payment,
                    'date_from': date_from,
                    'date_to': date_to,
                    'currency_id': company.currency_id.id,
                    'journal_id': journal_id,
                    'type': 'allowance',
                    'a_klase_kodas_id': self.env.ref('l10n_lt_payroll.a_klase_kodas_4').id,
                }
                # saskaita_komandiruotes = self.company_id.saskaita_komandiruotes
                saskaita_komandiruotes = employee.department_id.saskaita_komandiruotes or company.saskaita_komandiruotes
                if saskaita_komandiruotes:
                    vals['saskaita_debetas'] = saskaita_komandiruotes.id
                saskaita_komandiruotes_credit = employee.department_id.saskaita_komandiruotes_credit or company.saskaita_komandiruotes_credit
                if saskaita_komandiruotes_credit:
                    vals['saskaita_kreditas'] = saskaita_komandiruotes_credit.id
                holiday_pay = self.env['hr.employee.payment'].create(vals)
                holiday_pay.write({'amount_paid': amount,
                                   'amount_bruto': amount})
                # holiday_pay.amount_paid = holiday_pay.amount_bruto = amount
                self.payment_id = holiday_pay.id

    @api.multi
    def recalculate_holiday_payment_amounts(self):
        for rec in self.filtered(lambda r: r.holiday_status_id.kodas == 'A'):
            payment = rec.payment_id
            if not payment:
                rec.calculate_holiday_payment_amounts()
                continue
            if payment.state != 'done':
                payment.unlink()
                rec.with_context(force_recompute=True).calculate_holiday_payment_amounts()
                rec.create_holiday_payment()

    @api.model
    def cron_recompute_holiday_payment_amounts(self, date=None):
        if date is None:
            date = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        for employee in self.env['hr.employee'].search([]):
            last_payslip_date = self.env['hr.payslip'].search([('state', '=', 'done'), ('date_to', '<=', date),
                                                               ('employee_id', '=', employee.id)],
                                                              order='date_to desc', limit=1).date_to
            if not last_payslip_date:
                continue
            holidays_to_recompute = self.env['hr.holidays'].search([('date_to_date_format', '>=', last_payslip_date),
                                                                    ('holiday_status_id.kodas', '=', 'A'),
                                                                    ('employee_id', '=', employee.id)])
            holidays_to_recompute.recalculate_holiday_payment_amounts()

    @api.one
    def calculate_holiday_payment_amounts(self):
        if not self:
            return
        if not (self.type == 'remove' and self.holiday_status_id.kodas in ['A']):
            return
        if self.state == 'validate' and not self._context.get('force_recompute'):
            return
        date_str = self.date_from[:10]
        date_dt = datetime.strptime(date_str, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_from_dt = date_dt - relativedelta(day=1)
        periods_dates_from = []
        period_date_from = date_from_dt
        holiday_end = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATETIME_FORMAT)
        while period_date_from <= holiday_end:
            periods_dates_from.append(period_date_from)
            period_date_from += relativedelta(months=1)
        payments_by_period = []
        for period_date_from in periods_dates_from:
            period_date_to = (period_date_from + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            dt_from = max(period_date_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT), self.date_from)
            dt_to = min((period_date_from + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                        self.date_to)
            vdu_date = self.date_vdu_calc or self.date_from_date_format
            amount_bruto, vdu, num_work_days = self.with_context(period_date_from=dt_from, period_date_to=dt_to,
                                                                 vdu_date=vdu_date).get_holiday_pay_data()
            holiday_coefficient = 1.0  #self.employee_id.sudo().holiday_coefficient or 1.0
            payments_by_period.append({'period_date_from': period_date_from,
                                       'period_date_to': period_date_to,
                                       'amount': amount_bruto,
                                       'holiday_coefficient': holiday_coefficient,
                                       'vdu': vdu,
                                       'num_work_days': num_work_days,
                                       'holiday_id': self.id})
        self.allocated_payment_line_ids.unlink()
        for paym_line in payments_by_period:
            self.env['hr.holidays.payment.line'].create(paym_line)

        self.create_and_recompute_holiday_usage()

        # Have to loop again and recalculate since holiday usage lines get created
        for line in self.allocated_payment_line_ids:
            dt_from = max(line.period_date_from, self.date_from_date_format)
            dt_to = min(line.period_date_to, self.date_to_date_format)
            vdu_date = self.date_vdu_calc or self.date_from_date_format
            amount_bruto, __, __ = self.with_context(period_date_from=dt_from, period_date_to=dt_to,
                                                                vdu_date=vdu_date).get_holiday_pay_data()
            if tools.float_compare(amount_bruto, line.amount, precision_digits=2):
                line.write({'amount': amount_bruto})

    @api.multi
    def unlink(self):
        for rec in self:
            if rec.state == 'validate':
                raise exceptions.UserError(_('Negalima ištrinti patvirtintų atostogų'))
            if rec.payment_id:
                if rec.payment_id.state == 'draft':
                    rec.payment_id.unlink()
                else:
                    raise exceptions.Warning(_('Yra susijusių mokėjimų. Pirmiau atšaukite juos.'))
            rec.allocated_payment_line_ids.unlink()
        super(HrHolidays, self).unlink()

    @api.multi
    def update_ziniarastis(self, date_from=None, date_to=None):
        self.ensure_one()
        if not date_from:
            date_from = self.date_from[:10]
        if not date_to:
            date_to = self.date_to[:10]

        domain = [
            ('employee_id', '=', self.employee_id.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to)
        ]
        if self.contract_id:
            domain.append(('contract_id', '=', self.contract_id.id))

        days = self.env['ziniarastis.day'].search(domain)

        days._check_ziniarastis_day_holiday_match()
        ziniarastis_lines = days.mapped('ziniarastis_period_line_id').filtered(
            lambda l: l.state == 'draft'
        )
        for ziniarastis_line in ziniarastis_lines:
            related_days = days.filtered(lambda d: d.ziniarastis_period_line_id == ziniarastis_line)
            ziniarastis_line.auto_fill_period_line(dates=related_days.mapped('date'))

    @api.multi
    def action_validate(self):
        for rec in self:
            if rec.type == 'remove' and rec.holiday_status_id.kodas in ['A', 'K'] and not rec.payment_id:
                rec.create_holiday_payment()
                rec.payment_id.atlikti()
            if rec.type == 'remove' and rec.holiday_status_id.kodas in ['A']:
                self.env['hr.holidays.fix'].auto_change_fix(rec.employee_id.id, rec.date_from_date_format,
                                                            rec.date_to_date_format, 'add', rec.contract_id.id)
        super(HrHolidays, self).action_validate()
        for rec in self:
            rec.update_ziniarastis()

        if self:
            date_from = min(self.mapped('date_from_date_format'))
            self.remove_incorrect_holiday_usages()
            self.with_context(forced_recompute_date=date_from)._recompute_holiday_usage()

    @api.multi
    def get_date_of_payment(self):
        self.ensure_one()
        date_from = self.date_from
        if self.ismokejimas == 'before_hand':
            try:
                date = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT) - timedelta(days=1)
            except ValueError:
                date = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATETIME_FORMAT) - timedelta(days=1)
            date = get_last_work_day(self, date)
            return date
        elif self.ismokejimas == 'du':
            try:
                date_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            except ValueError:
                date_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            date = date_dt + relativedelta(months=1, day=self.company_id.salary_payment_day)
            return date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        else:
            raise exceptions.Warning(_('Bloga išmokėjimo reikšmė'))

    def get_min_day_wage(self):
        contract = self.contract_id or self.employee_id.contract_id
        min_day_pay = contract.employee_id.get_minimum_wage_for_date(self.date_to_date_format)['day']
        return min_day_pay

    @api.multi
    def should_use_daily_vdu_for_holiday_accumulation_calculations(self):
        """
        Checks if daily VDU should be used for calculating the payment amount and using holiday accumulation records
        @return: (boolean) should daily VDU be used
        """
        self.ensure_one()
        contracts = self.contract_id.get_contracts_related_to_work_relation()
        related_appointments = contracts.mapped('appointment_ids')
        posts = related_appointments.mapped('schedule_template_id.etatas')
        salary_structures = related_appointments.mapped('struct_id.code')
        no_post_changes = len(set(posts)) == 1
        only_monthly_salary = len(set(salary_structures)) == 1 and salary_structures[0] == 'MEN'
        return no_post_changes and only_monthly_salary

    @api.multi
    def _get_leave_days_for_holiday_pay_data(self):
        self.ensure_one()
        date_from = (self._context.get('period_date_from') or self.date_from)[:10]
        date_to = (self._context.get('period_date_to') or self.date_to)[:10]
        leave_days = self.contract_id.with_context(
            force_use_schedule_template=True, calculating_holidays=True, force_convert_to_work_days=True
        ).get_num_work_days(date_from, date_to)

        if not tools.float_is_zero(leave_days, precision_digits=2):
            return leave_days

        usage_lines = self.holiday_usage_line_ids.filtered(lambda l: l.date_from <= date_to and l.date_to >= date_from)
        calculate_based_on_usage_lines = self.holiday_accumulation_usage_policy

        if not usage_lines or not calculate_based_on_usage_lines:
            appointments = self.contract_id.appointment_ids.filtered(
                lambda a: a.date_start <= date_to and (not a.date_end or a.date_end >= date_from) and
                          a.leaves_accumulation_type == 'calendar_days' and
                          a.schedule_template_id.template_type not in ['fixed', 'suskaidytos'])
            for appointment in appointments:
                app_period_start = max(appointment.date_start, date_from)
                app_period_end = min(appointment.date_end or date_to, date_to)
                app_period_start_dt = datetime.strptime(app_period_start, tools.DEFAULT_SERVER_DATE_FORMAT)
                app_period_end_dt = datetime.strptime(app_period_end, tools.DEFAULT_SERVER_DATE_FORMAT)
                national_holiday_amount = self.env['sistema.iseigines'].search_count([
                    ('date', '<=', app_period_end),
                    ('date', '>=', app_period_start)
                ])
                app_period_duration = abs((app_period_end_dt - app_period_start_dt).days) + 1
                total_work_days_to_be_converted = max((app_period_duration - national_holiday_amount), 0.0)
                number_of_days_per_week = appointment.schedule_template_id.num_week_work_days
                leave_days += total_work_days_to_be_converted * number_of_days_per_week / 7.0  # P3:DivOK

        return leave_days

    @api.multi
    def get_holiday_pay_data(self):
        self.ensure_one()
        date_from = (self._context.get('period_date_from') or self.date_from)[:10]
        date_to = (self._context.get('period_date_to') or self.date_to)[:10]
        vdu_date = self._context.get('vdu_date', date_from)
        leave_days = self._get_leave_days_for_holiday_pay_data()
        holiday_coefficient = 1.0

        # Adjust amount based on usage lines
        usage_lines = self.holiday_usage_line_ids.filtered(lambda l: l.date_from <= date_to and l.date_to >= date_from)
        calculate_based_on_usage_lines = self.holiday_accumulation_usage_policy
        if usage_lines and calculate_based_on_usage_lines:
            # Adjust VDU to match full post because it's multiplied by post later
            use_daily_vdu = self.should_use_daily_vdu_for_holiday_accumulation_calculations()
            if use_daily_vdu:
                day_pay = get_vdu(
                    self.env, vdu_date, self.employee_id, contract_id=self.contract_id.id, vdu_type='d'
                ).get('vdu', 0.0)
            else:
                vdu = get_vdu(self.env, vdu_date, self.employee_id, contract_id=self.contract_id.id, vdu_type='h').get(
                    'vdu', 0.0)
                day_pay = vdu * 8.0

            appointments = self.contract_id.appointment_ids.filtered(
                lambda a: a.date_start <= date_to and (not a.date_end or a.date_end >= date_from)
            )
            appointment = appointments and appointments[0]

            schedule_template = appointment.schedule_template_id if appointment else None
            if schedule_template and not use_daily_vdu:
                 day_pay *= schedule_template.work_norm
            amount_bruto = self.env['hr.holidays.payment.line']._get_payment_amount_adjusted_by_usage_lines(
                usage_lines, day_pay, holiday_coefficient, leave_days, self.contract_id.work_relation_start_date
            )
            if schedule_template and not use_daily_vdu:
                day_pay *= appointment.schedule_template_id.etatas
        else:
            day_pay = vdu = get_vdu(
                self.env, vdu_date, self.employee_id, contract_id=self.contract_id.id, vdu_type='d'
            ).get('vdu', 0.0)
            amount_bruto = leave_days * vdu * holiday_coefficient
        amount_bruto = tools.float_round(amount_bruto, precision_digits=2)
        return amount_bruto, day_pay, leave_days

    @api.model
    def cron_warn_accountants_about_payments(self):
        current_date = datetime.utcnow()
        date_to = current_date
        while date_to.weekday() in (5, 6) or self.env['sistema.iseigines'].search([
            ('date', '=', date_to.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))]):
            date_to += relativedelta(days=1)
        relevant_holidays = self.env['hr.holidays'].search(
            [('holiday_status_id.kodas', '=', 'A'), ('type', '=', 'remove'),
             ('payment_id.state', '=', 'draft'),
             ('accountant_informed', '=', False)])
        for holiday in relevant_holidays:
            holiday.payment_id.check_if_holiday_payment_ready()

    @api.multi
    @api.constrains('payment_id')
    def _check_unique_payment_id(self):
        for rec in self:
            if rec.payment_id and self.env['hr.holidays'].search_count([('payment_id', '=', rec.payment_id.id)]) > 1:
                raise exceptions.ValidationError(_('Negalima kurti vieno apmokėjimo kelioms atostogoms'))

    @api.multi
    @api.constrains('holiday_payment', 'payment_amount', 'holiday_status_id')
    def _check_other_amount_is_positive(self):
        for rec in self:
            if rec.holiday_status_id.kodas == 'MA' and rec.holiday_payment == 'other_amount' and \
                    tools.float_compare(rec.payment_amount, 0.0, precision_digits=2) != 1:
                raise exceptions.ValidationError(_('The amount provided cannot be equal to zero or less than zero'))

    @api.multi
    def open_stop_wizard(self):
        return {
            # 'name': _('Sugeneruoti atostoginių dienų priskyrimai'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'holidays.change.wizard',
            'view_id': False,
            'target': 'new',
            'type': 'ir.actions.act_window',
            'context': {'active_ids': self.ids}
        }

    # don't send emails

    def add_follower(self, employee_id):  # we don't want employees to follow followers
        if not self._context.get('add_follower'):
            return True
        else:
            return super(HrHolidays, self).add_follower(employee_id)

    @api.multi
    def message_subscribe(self, partner_ids=None, channel_ids=None, subtype_ids=None, force=True):
        if not self._context.get('message_subscribe'):
            return True
        else:
            super(HrHolidays, self).message_subscribe(partner_ids=partner_ids, channel_ids=channel_ids,
                                                      subtype_ids=subtype_ids, force=force)

    @api.model
    def cron_force_recalculate(self):
        holidays = self.env['hr.holidays'].search([('force_recalculate', '=', True), ('state', '!=', 'refuse')])
        failed_holiday_data = list()
        for holiday in holidays:
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, SUPERUSER_ID, {'lang': 'lt_LT'})
            holiday_to_recompute = env['hr.holidays'].browse(holiday.id)
            try:
                if holiday_to_recompute.state in ['confirm', 'validate', 'validate1']:
                    holiday_to_recompute.with_context(allow_delete_special=True).action_refuse()
                holiday_to_recompute.action_draft()
                holiday_to_recompute.calculate_holiday_payment_amounts()
                holiday_to_recompute.action_confirm()
                holiday_to_recompute.write({'force_recalculate': False})
                new_cr.commit()
            except Exception as exc:
                failed_holiday_data.append((holiday_to_recompute.id, str(exc.args[0])))
                new_cr.rollback()
            finally:
                new_cr.close()
        if failed_holiday_data:
            errors = '\n'
            for failed_holiday_info in failed_holiday_data:
                err = failed_holiday_info[1]
                failed_holiday = holidays.filtered(lambda h: h.id == failed_holiday_info[0])
                errors += '({}) {} - {}'.format(failed_holiday.id, failed_holiday.employee_id.name, err)
            body = _('Nepavyko perskaičiuoti atostogų. Klaidos pranešimai: {}').format(errors)
            subject = _('[%s] Holiday recompute failed') % self.env.cr.dbname
            self.env['script'].send_email(emails_to=['support@robolabs.lt'], body=body, subject=subject)

    @api.model
    def cron_recalculate(self):
        """
            Finds and recalculates annual leaves that either have recalculate flag set to true or values should be
            different than they currently are (in most cases due to VDU changes)

            Informs accountants if the holiday can not be recalculated (due to confirmed payslips or other reasons)
        """
        # Main holidays with recalculate flag set to true
        holidays_to_recompute = self.env['hr.holidays'].search([
            ('recalculate', '=', True),
            ('state', '=', 'validate'),
            ('ignore_recalculation_warnings', '=', False),
            ('holiday_status_id', '=', self.env.ref('hr_holidays.holiday_status_cl').id)
        ])

        # Holidays that should be recomputed because the payment values differ from the current ones
        now = datetime.utcnow()
        date_from = (now - relativedelta(months=1, day=1, hour=0, minute=0)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = (now + relativedelta(months=2, day=1, hour=0, minute=0)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        amount_mismatch_holiday_ids = self.env['hr.holidays'].search([
            ('date_from', '>=', date_from),
            ('date_from', '<', date_to),
            ('ignore_recalculation_warnings', '=', False),
            ('holiday_status_id', '=', self.env.ref('hr_holidays.holiday_status_cl').id),
            ('state', '=', 'validate')
        ]).filtered(lambda r: r.contract_id and
                              (not r.contract_id.date_end or r.contract_id.date_end > r.date_from_date_format) and
                              r.should_be_recomputed)
        holidays_to_recompute |= amount_mismatch_holiday_ids

        holidays_that_could_not_be_recomputed = self.env['hr.holidays']

        for holiday in holidays_to_recompute:
            hol_date = datetime.strptime(holiday.date_from[:10], tools.DEFAULT_SERVER_DATE_FORMAT).date()

            contract_end_date = holiday.contract_id.date_end
            if contract_end_date and contract_end_date <= holiday.date_to_date_format and \
                    contract_end_date < now.strftime(tools.DEFAULT_SERVER_DATE_FORMAT):
                continue

            check_date = hol_date - relativedelta(months=1, day=1)

            domain = [
                ('employee_id', '=', holiday.employee_id.id),
                ('month', '=', check_date.month),
                ('year_id.code', '=', check_date.year)
            ]
            if holiday.contract_id:
                related_contracts = holiday.contract_id.get_contracts_related_to_work_relation()
                domain += [
                    '|',
                    ('contract_id', 'in', related_contracts.ids),
                    ('contract_id', '=', False),
                ]

            vdu = self.env['employee.vdu'].search(domain)

            first_day = hol_date + relativedelta(day=1)
            payslip = self.env['hr.payslip'].search([
                ('date_from', '=', first_day.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)),
                ('state', '=', 'done'),
                ('employee_id', '=', holiday.employee_id.id)
            ], count=True)

            if payslip:
                holiday.write({'recalculate': False})

                msg_partner_ids = self.env.user.sudo().company_id.findir.partner_id.ids + holiday.message_partner_ids.ids
                holiday.message_post(body=_('Neleidžiama perskaičiuoti atostogų nes algalapis jau patvirtintas'), partner_ids=msg_partner_ids)

                holidays_that_could_not_be_recomputed |= holiday
            elif vdu:
                try:
                    holiday.action_refuse()
                    holiday.action_draft()
                    holiday.calculate_holiday_payment_amounts()
                    holiday.action_confirm()
                except:
                    self.env.cr.rollback()
                    holiday.message_post(body=_('Nepavyko perskaičiuoti atostoginių.'))
                    holidays_that_could_not_be_recomputed |= holiday
                finally:
                    holiday.write({'recalculate': False})
                    self.env.cr.commit()

        if holidays_that_could_not_be_recomputed:
            holidays_that_could_not_be_recomputed.write({'allow_recalculation_warnings_to_be_ignored': True})
            msg_company_name = self.env.user.company_id.name or 'ROBO'
            msg_table_rows = ''
            for holiday_that_could_not_be_recomputed in holidays_that_could_not_be_recomputed:
                msg_table_rows += _('''
                <tr>
                    <td style="border: 1px solid black;">{0}</td>
                    <td style="border: 1px solid black;">{1}</td>
                    <td style="border: 1px solid black;">{2}</td>
                    <td style="border: 1px solid black;"><a href="{3}">Atidaryti</a></td>
                </tr>
                ''').format(
                    holiday_that_could_not_be_recomputed.employee_id.name,
                    holiday_that_could_not_be_recomputed.date_from_date_format,
                    holiday_that_could_not_be_recomputed.date_to_date_format,
                    self.env.user.sudo().company_id.get_record_url(holiday_that_could_not_be_recomputed)
                )
            msg_body = _('''
            <p>
                Sveiki,<br/>
                {0} sistemoje buvo rasti kasmetinių atostogų neatvykimai, kuriuos reikėtų perskaičiuoti, tačiau 
                automatiškai to nebuvo įmanoma padaryti:<br/>
            </p>
            <table style="border: 1px solid black; border-collapse: collapse;">
                <tr>
                    <th style="border: 1px solid black;">Darbuotojo Vardas, Pavardė</th>
                    <th style="border: 1px solid black;">Atostogų pradžia</th>
                    <th style="border: 1px solid black;">Atostogų pabaiga</th>
                    <th style="border: 1px solid black;"></th>
                </tr>
                {1}
            </table>
            <br/>
            <br/>
            <p style="color: gray">
                Buvo nustatyta, kad šiuos neatvykimus reikia perskaičiuoti dėl vienos iš šių priežasčių:
            </p>
            <ul style="color: gray">
                <li>Buvo importuotas VDU įrašas</li>
                <li>Atostogų sukūrimo metu nebuvo nustatytas darbuotojo VDU, dabar jam susikūrus galima teisingai 
                    perskaičiuoti atostoginių sumas
                </li>
                <li>Dėl sistemos techninės priežiūros ar patobulinimų keitėsi atostoginių skaičiavimai</li>
                <li>Dėl duomenų pasikeitimų pasikeitė atostogų duomenys (VDU ar atostogų dienų skaičius)</li>
            </ul>
            <br/>
            <p style="color: gray">
                Neatvykimai nebuvo perskaičiuoti automatiškai dėl patvirtintų algalapių atostogų periode ar dėl 
                kitų nenumatytų priežasčių. Jei manote, kad atostogos neturėtų būti perskaičiuotos ir tolimesni 
                pranešimai apie tam tikrus neatvykimus neturėtų būti siunčiami - nueikite į neatvykimo įrašą ir 
                paspauskite mygtuką Veiksmas -> Išjungti įspėjimus dėl galimų perskaičiavimų.
            </p>
            <p style="color: gray">
                Jei manote, kad egzistuoja klaida ar turite kitų sunkumų - apibūdinkite savo problemą persiųsdami 
                šį laišką el. adresu <a href="mailto:support@robolabs.lt">support@robolabs.lt</a>
            </p>
            ''').format(msg_company_name, msg_table_rows)

            findir_email = self.sudo().env.user.company_id.findir.partner_id.email

            if not findir_email:
                findir_email = 'support@robolabs.lt'

            msg_subject = _('Nepavyko automatiškai perskaičiuoti neatvykimų [{0}]').format(msg_company_name)
            self.env['script'].send_email(emails_to=[findir_email],
                                          subject=msg_subject,
                                          body=msg_body)

    @api.model
    def create(self, vals):
        if 'date_from' not in vals:
            raise exceptions.UserError(_('Panašu, kad bandote sukurti persidengiančias atostogas, '
                                         'šis veiksmas neleidžiamas.'))
        date_from_dt = datetime.strptime(vals['date_from'][:10], tools.DEFAULT_SERVER_DATE_FORMAT).date()
        check_date = date_from_dt - relativedelta(months=1, day=1)
        domain = [
            ('employee_id', '=', vals['employee_id']),
            ('month', '=', check_date.month),
            ('year_id.code', '=', check_date.year)
        ]
        contract_id = vals.get('contract_id')
        if contract_id:
            contract = self.env['hr.contract'].browse(contract_id)
            related_contracts = contract.get_contracts_related_to_work_relation()
            domain += [
                '|',
                ('contract_id', '=', False),
                ('contract_id', 'in', related_contracts.ids)
            ]
        vdu = self.env['employee.vdu'].search(domain)
        if not vdu:
            vals.update({'recalculate': True})

        if vals.get('type', False) == 'remove':
            employee_id = vals.get('employee_id', False)
            holiday_status_id = vals.get('holiday_status_id', False)
            date_from = vals.get('date_from', False)
            date_to = vals.get('date_to', False)
            numeris = vals.get('numeris', False)
            payment_type = vals.get('ismokejimas', False)
            department_id = vals.get('department_id', False)

            if employee_id and holiday_status_id and date_from and date_to:
                existing_holidays = self.search([
                    ('employee_id', '=', employee_id),
                    ('holiday_status_id', '=', holiday_status_id),
                    ('date_from', '=', date_from),
                    ('date_to', '=', date_to),
                ])
                hol_status_id = self.env['hr.holidays.status'].browse(holiday_status_id).exists()
                if existing_holidays:
                    if existing_holidays.state == 'refuse':
                        existing_holidays.action_draft()
                    if existing_holidays.state == 'draft':
                        existing_holidays.action_confirm()
                    vals_new = {'data': datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)}
                    if not existing_holidays.numeris and numeris:
                        vals_new['numeris'] = numeris
                    if payment_type:
                        vals_new['ismokejimas'] = payment_type
                    if department_id:
                        vals_new['department_id'] = department_id
                    existing_holidays.write(vals_new)
                    return existing_holidays
                elif hol_status_id.kodas in ['L', 'G', 'NS', 'N'] and self._context.get('creating_ligos', False):
                    self.move_holidays_for_illnesses(date_from, date_to, employee_id, hol_status_id)
        return super(HrHolidays,
                     self.with_context(mail_notify_force_send=False, mail_notify_user_signature=False)).create(vals)

    def move_holidays_for_illnesses(self, date_from, date_to, employee_id, hol_status_id):
        all_existing_holidays = self.search([
            ('employee_id', '=', employee_id),
            ('date_to', '>=', date_from),
            ('date_from', '<=', date_to),
        ])
        if all_existing_holidays:
            if not any(code not in ['A', 'NA'] for code in
                       all_existing_holidays.mapped('holiday_status_id.tabelio_zymejimas_id.code')):
                max_days_to_shift_forward = 365  # Change value to adjust the maximum amount of days possible to shift forward
                this_hol_date_to = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATETIME_FORMAT) + relativedelta(
                    days=1)
                for existing_holiday_to_be_moved in all_existing_holidays:
                    date_from_dt = datetime.strptime(existing_holiday_to_be_moved.date_from,
                                                     tools.DEFAULT_SERVER_DATETIME_FORMAT)
                    max_date_to = date_from_dt + relativedelta(days=max_days_to_shift_forward)
                    max_date_to_strf = max_date_to.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
                    appointments = self.env['hr.employee'].browse(employee_id).mapped(
                        'contract_ids.appointment_ids').filtered(
                        lambda a: not a.date_end or (date_to <= a.date_end <= max_date_to_strf))

                    hol_work_days = []
                    hol_start_dt = datetime.strptime(existing_holiday_to_be_moved.date_from[:10],
                                                     tools.DEFAULT_SERVER_DATE_FORMAT)
                    hol_end_dt = datetime.strptime(existing_holiday_to_be_moved.date_to[:10],
                                                   tools.DEFAULT_SERVER_DATE_FORMAT)
                    while hol_start_dt <= hol_end_dt:
                        check_date_strf = hol_start_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                        date_appointment = appointments.filtered(lambda a: a.date_start <= check_date_strf and (
                                not a.date_end or a.date_end >= check_date_strf))
                        hol_start_dt += relativedelta(days=1)
                        if not date_appointment:
                            continue
                        is_work_day = date_appointment.schedule_template_id.is_work_day(check_date_strf[:10])
                        if is_work_day:
                            hol_work_days.append(check_date_strf)

                    days_between = len(hol_work_days)
                    all_possible_holidays = self.search([
                        ('employee_id', '=', employee_id),
                        ('date_to', '>=', date_from),
                        ('date_from', '<=', max_date_to_strf),
                    ])
                    days_suitable = []
                    date_to_check = this_hol_date_to
                    days_checked = 0
                    while len(days_suitable) < days_between:
                        if days_checked >= max_days_to_shift_forward:
                            break
                        check_date_strf = date_to_check.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
                        check_date_holidays = all_possible_holidays.filtered(
                            lambda h: h.date_from <= check_date_strf <= h.date_to)
                        if check_date_strf > date_to:
                            check_date_holidays = check_date_holidays.filtered(
                                lambda h: h.id != existing_holiday_to_be_moved.id)
                        if check_date_holidays:
                            date_to_check += relativedelta(days=1)
                            days_checked += 1
                            continue
                        date_appointment = appointments.filtered(lambda a: a.date_start <= check_date_strf and (
                                not a.date_end or a.date_end >= check_date_strf))
                        if not date_appointment:
                            date_to_check += relativedelta(days=1)
                            days_checked += 1
                            continue
                        is_work_day = date_appointment.schedule_template_id.is_work_day(check_date_strf[:10])
                        if not is_work_day:
                            date_to_check += relativedelta(days=1)
                            days_checked += 1
                            continue

                        days_suitable.append(check_date_strf[:10])
                        date_to_check += relativedelta(days=1)
                        days_checked += 1

                    if len(days_suitable) == days_between:
                        periods = []
                        days_suitable.sort()
                        for date in days_suitable:
                            prev_date = (datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(
                                days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                            added = False
                            index = -1
                            for period in periods:
                                index += 1
                                if period[1] == prev_date:
                                    periods[index] = (period[0], date)
                                    added = True
                                    break
                            if not added:
                                periods.append((date, date))

                        d1 = existing_holiday_to_be_moved['date_from']
                        d2 = existing_holiday_to_be_moved['date_to']
                        code_to_text_mapping = {'L': _('ligų'),
                                                'G': _('gimdymo atostogų'),
                                                'NS': _('nedarbingumo ligoniams slaugyti'),
                                                'N': _('neapmokamo nedarbingumo')}
                        shortened_holidays = False
                        for period in periods:
                            period_from_dt = (
                                    datetime.strptime(period[0], tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(
                                hour=11)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
                            period_to_dt = (
                                    datetime.strptime(period[1], tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(
                                hour=19)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
                            period_holidays = existing_holiday_to_be_moved
                            if not shortened_holidays and period_holidays:
                                period_holidays.action_refuse()
                                period_holidays.action_draft()
                                period_holidays.write({
                                    'date_from': period_from_dt,
                                    'date_to': period_to_dt
                                })
                                period_holidays.calculate_holiday_payment_amounts()
                                period_holidays.action_confirm()
                                shortened_holidays = True
                            else:
                                period_holidays = existing_holiday_to_be_moved.copy({
                                    'date_from': period_from_dt,
                                    'date_to': period_to_dt,
                                    'payment_id': False,
                                    'payment_ids': False,
                                    'state': 'draft',
                                })
                                period_holidays.calculate_holiday_payment_amounts()
                                period_holidays.action_confirm()
                            message = _('Šis atostogų įrašas buvo pastumtas iš %s - %s laikotarpio, '
                                        'nes atsirado %s įrašas %s - %s laikotarpiu') % (
                                          str(d1), str(d2), str(code_to_text_mapping[str(hol_status_id.kodas)]),
                                          str(date_from), str(date_to))
                            period_holidays.write({'date_vdu_calc': d1})
                            period_holidays.message_post(body=message, message_type='notification',
                                                         subtype='mt_comment',
                                                         partner_ids=[1],
                                                         subject='Paslinktos atostogos', author_id=False)

    @api.multi
    def action_approve(self):
        # OVERRIDDEN FROM ADDONS
        if not self.env.user.has_group('hr_holidays.group_hr_holidays_user'):
            raise exceptions.UserError(_('Tik personalo vadovas gali patvirtinti atostogų prašymus'))

        manager = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
        for holiday in self:
            if holiday.state != 'validate':
                if holiday.state != 'confirm':
                    raise exceptions.UserError(
                        _('Leave request must be confirmed ("To Approve") in order to approve it.'))

                if holiday.double_validation:
                    return holiday.write({'state': 'validate1', 'manager_id': manager.id if manager else False})
                else:
                    holiday.action_validate()

    @api.multi
    def force_recompute_payments(self):  # todo maybe we don't have to delete
        for rec in self:
            if rec.payment_id:
                if rec.payment_id.state != 'done':
                    rec.payment_id.unlink()
                else:
                    rec.payment_id.force_unlink()
                rec.recalculate_holiday_payment_amounts()
                rec.create_holiday_payment()
                rec.payment_id.atlikti()

    @api.multi
    def action_confirm(self):
        res = super(HrHolidays, self).action_confirm()
        if self.env.user.is_accountant():
            return self.action_approve()
        return res

    @api.model
    def get_holidays_intervals(self, employee_id, dates):
        min_date = min(dates)
        max_date = max(dates)
        komandiruotes_status_id = self.env.ref('hr_holidays.holiday_status_K').id
        poilsio_status_id = self.env.ref('hr_holidays.holiday_status_P').id
        holidays = self.env['hr.holidays'].search([('date_from_date_format', '<=', max_date),
                                                   ('date_to_date_format', '>=', min_date),
                                                   ('state', '=', 'validate'),
                                                   ('employee_id', '=', employee_id),
                                                   ('holiday_status_id', '!=', komandiruotes_status_id)])
        poilsio_holidays = holidays.filtered(lambda r: r.holiday_status_id.id == poilsio_status_id)
        if poilsio_holidays:
            days_poilsio = filter(lambda r: any(hol.date_from_date_format <= r <= hol.date_to_date_format
                                                for hol in poilsio_holidays), dates)
        else:
            days_poilsio = []
        detailed_result = []
        for h in holidays:
            if h.holiday_status_id.tabelio_zymejimas_id:
                zymejimo_id = h.holiday_status_id.tabelio_zymejimas_id.id
            else:
                continue
            detailed_result.append((h.date_from_date_format, h.date_to_date_format, zymejimo_id))
        return days_poilsio, detailed_result

    @api.model
    def get_extra_business_trip_dates(self, employee_id, dates):
        min_date = min(dates)
        max_date = max(dates)
        komandiruotes_status_id = self.env.ref('hr_holidays.holiday_status_K').id
        business_trips = self.env['hr.holidays'].search([('date_from_date_format', '<=', max_date),
                                                         ('date_to_date_format', '>=', min_date),
                                                         ('state', '=', 'validate'),
                                                         ('employee_id', '=', employee_id),
                                                         ('holiday_status_id', '=', komandiruotes_status_id)])

        extra_days_worked = []
        if business_trips:
            # TODO Add o2m on hr.holidays that says which extra days have been worked. Write a script to fix all past documents.
            doc_numbers = business_trips.mapped('numeris')
            employee_lines = self.env['e.document'].search([
                ('document_number', 'in', doc_numbers)
            ]).mapped('business_trip_employee_line_ids').filtered(lambda l: l.employee_id.id == employee_id)
            extra_days_worked = employee_lines.mapped('extra_worked_day_ids').filtered(
                lambda d: d.worked and d.date <= max_date and d.date >= min_date).mapped('date')
        return extra_days_worked

    @api.model
    def get_sick_holiday_statuses(self):
        sick_holiday_statuses = [
            self.env.ref('hr_holidays.holiday_status_sl'),
            self.env.ref('hr_holidays.holiday_status_N'),
            self.env.ref('hr_holidays.holiday_status_NS'),
            self.env.ref('hr_holidays.holiday_status_G'),
        ]
        return sick_holiday_statuses

    @api.multi
    def export_gpm_payment(self):
        self = self.filtered(lambda h: not h.gpm_paid)
        return self.env['account.move.line'].with_context(form_gpm_payments_for_holidays=self.mapped('id')).call_multiple_invoice_export_wizard()

    @api.multi
    def _create_holiday_usage_records(self):
        """
            Creates holiday usage records for holidays that do not have them
        Returns:
            object: HrEmployeeHolidayUsage records
        """
        annual_leaves = self.filtered(lambda h: h.type == 'remove' and h.holiday_status_id.kodas == 'A')

        HrEmployeeHolidayUsage = self.env['hr.employee.holiday.usage']
        usage_ids = HrEmployeeHolidayUsage.search([('holiday_id', 'in', annual_leaves.ids)])
        holidays_with_existing_usages = usage_ids.mapped('holiday_id')
        holidays_without_usages = annual_leaves.filtered(
            lambda l: l.id not in holidays_with_existing_usages.ids and l.should_have_a_usage_record
        )

        for rec in holidays_without_usages:
            # Create holiday usage records that don't exist
            new_usage = HrEmployeeHolidayUsage.sudo().create({'holiday_id': rec.id})
            usage_ids |= new_usage
            rec.write({'holiday_usage_id': new_usage.id})

        return usage_ids

    @api.multi
    def create_and_recompute_holiday_usage(self):
        """
            Creates holiday usage records if necessary and recomputes the holiday usage for all given holidays.
        """
        holiday_usages = self.with_context(recompute=False).sudo()._create_holiday_usage_records()
        holiday_usages.with_context(recompute=True).sudo()._recompute_holiday_usage()

    @api.multi
    def _adjust_payments_based_on_holiday_usage(self):
        annual_holidays = self.filtered(lambda h: h.type == 'remove' and h.holiday_status_id.kodas == 'A' and
                                                  h.state == 'draft')
        annual_holidays.sudo().recalculate_holiday_payment_amounts()

    @api.model
    def remove_incorrect_holiday_usages(self):
        self.env['hr.employee.holiday.usage'].search([
            ('holiday_id.holiday_status_id', '!=', self.env.ref('hr_holidays.holiday_status_cl').id)
        ]).sudo().unlink()

    @api.multi
    def _recompute_holiday_usage(self):
        """
            Unlinks holiday usages for given holidays and recomputes any future holiday usage records for holidays that
            do not have a confirmed payslip.
        """
        # Recompute holiday usages
        # Only annual holidays have holiday usages
        annual_holidays = self.filtered(lambda h: h.type == 'remove' and h.holiday_status_id.kodas == 'A')
        if annual_holidays:
            self.env['hr.employee.holiday.usage'].sudo().search([
                ('employee_id', 'in', annual_holidays.mapped('employee_id').ids)
            ])._recompute_holiday_usage()

    @api.multi
    def get_illness_periods(self):
        periods = list()
        current_period_leaves = self.env['hr.holidays']
        for rec in self.sorted(key=lambda holiday: holiday.date_from_date_format):
            if not current_period_leaves:
                current_period_leaves |= rec
                continue

            # Check when the period ends
            current_period_end = max(current_period_leaves.mapped('date_to_date_format'))
            period_end_dt = datetime.strptime(current_period_end, tools.DEFAULT_SERVER_DATE_FORMAT)
            next_day_after = (period_end_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

            # If the next day after the period ends is the start of the current illness record and it's a sick leave
            # continuation then it's the same period
            if next_day_after == rec.date_from_date_format and rec.sick_leave_continue:
                current_period_leaves |= rec
            else:
                periods.append(current_period_leaves)
                current_period_leaves = rec

        if current_period_leaves:
            # Include the last period in the periods
            periods.append(current_period_leaves)
        return periods


HrHolidays()
