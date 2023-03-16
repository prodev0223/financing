# -*- coding: utf-8 -*-
from __future__ import division
import threading
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, api, fields, tools, exceptions, SUPERUSER_ID
from odoo.api import Environment
from odoo.tools.translate import _

PAYROLL_EXECUTION_STAGES = [
    ('schedule', 'Grafiko tvirtinimas'),
    ('ziniarastis_checks', 'Žiniarascio neatitikimu tikrinimas'),
    ('ziniarastis_line_validation', 'Žiniaraščio eilučių tvirtinimas'),
    ('ziniarastis_validation', 'Žiniaraščio tvirtinimas'),
    ('payslip', 'Algalapių tikrinimas'),
    ('payslip_run', 'Atlyginimo suvestinės uždarymas'),
    ('transactions', 'Pavedimų rodymas'),
    ('gpm', 'GPM Formavimas'),
    ('done', 'Baigta'),
    ('sam', 'SAM pranešimo siuntimas'),
    ('undefined', 'Nenumatyta')
]


class HrPayroll(models.Model):
    _name = 'hr.payroll'

    year = fields.Integer('Year', required=True)
    month = fields.Integer('Month', required=True)

    date_from = fields.Date('Mėnesio pradžios data', compute='_compute_dates', store=True)
    date_to = fields.Date('Mėnesio pabaigos data', compute='_compute_dates', store=True)

    busy = fields.Boolean('Atlyginimai skaičiuojami', inverse='_set_thread_identification')
    stage = fields.Selection(PAYROLL_EXECUTION_STAGES, 'Kuris atlyginimo skaičiavimų lygmuo dabar vykdomas')
    partial_calculations_running = fields.Boolean('Atliekamas tarpinis skaičiavimas')

    payslip_run_id = fields.Many2one('hr.payslip.run', 'Algalapių suvestinė', compute='_compute_payslip_run_id')
    thread_identification = fields.Text('Thread identification',
                                                help='Identification of thread that started the payroll calculations',
                                                readonly=True)
    thread_is_active = fields.Boolean('Executing thread is active', compute='_compute_thread_is_active')

    @api.multi
    @api.depends('year', 'month')
    def _compute_dates(self):
        self.ensure_one()
        month_start = datetime(self.year, self.month, 1)
        month_end = month_start + relativedelta(day=31)
        self.date_from = month_start.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.date_to = month_end.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    @api.depends('year', 'month')
    def _compute_payslip_run_id(self):
        self.ensure_one()
        self.payslip_run_id = self.env['hr.payslip.run'].search([
            ('date_start', '=', self.date_from),
            ('date_end', '=', self.date_to)
        ], limit=1)

    @api.multi
    @api.depends('thread_identification')
    def _compute_thread_is_active(self):
        for rec in self.filtered(lambda payroll: payroll.thread_identification):
            thread_is_active = False
            try:
                thread_identification = rec.thread_identification
                threads = [x for x in threading.enumerate() if x.ident == int(thread_identification)]
                thread_is_active = bool(threads)
            except Exception as e:
                pass
            rec.thread_is_active = thread_is_active

    @api.multi
    def launch_automatic_payroll(self):
        self.ensure_one()
        if self.busy:
            msg = _('Negalite įjungti automatinio atlyginimo skaičiavimo, nes ')
            if self.partial_calculations_running and self.stage:
                msg += _('vykdomas tarpinis atlyginimų skaičiavimų veiksmas - %s') % self.stage
            else:
                msg += _('atlyginimai jau skaičiuojami')
            raise exceptions.ValidationError(msg)
        self.write({
                    'busy': True,
                    'partial_calculations_running': False,
                    'stage': False,
                })
        self._cr.commit()
        threaded_calculation = threading.Thread(target=self.automatic_payroll_threaded)
        threaded_calculation.start()

    @api.multi
    def stop_automatic_payroll(self):
        self.ensure_one()
        if not self.busy:
            raise exceptions.UserError(_('Payroll calculations are not running anymore. Please reload the page.'))
        if self.thread_is_active:
            raise exceptions.UserError(_('You can not stop payroll calculations at this stage. The calculations are '
                                         'not stuck and are still running. Please wait until the calculations are '
                                         'done'))
        self.write({'busy': False, 'partial_calculations_running': False, 'stage': False})

    @api.multi
    def _set_thread_identification(self):
        try:
            thread_identification = threading.current_thread().ident
        except Exception as e:
            thread_identification = None
        for rec in self:
            if rec.busy:
                rec.thread_identification = thread_identification
            else:
                rec.thread_identification = None

    @api.multi
    def automatic_payroll_threaded(self):
        self.ensure_one()
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, SUPERUSER_ID, {'lang': 'lt_LT'})
            period_obj = env['hr.payroll']
            curr_payroll_obj = period_obj.browse(self.id)
            try:
                period_obj.execute_automatic_payroll(year=self.year, month=self.month)
            except:
                new_cr.rollback()
            finally:
                curr_payroll_obj.write({
                    'busy': False,
                    'partial_calculations_running': False,
                    'stage': False,
                })
                new_cr.commit()
                new_cr.close()

    @api.model
    def get_next_work_day(self, date, weekends=[5, 6]):
        try:
            date.weekday()
            date_dt = date
        except:
            date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        date = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        potential_max_date = (date_dt + relativedelta(months=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        iseigines = self.env['sistema.iseigines'].search([
            ('date', '<=', potential_max_date),
            ('date', '>=', date)
        ]).mapped('date')
        next_work_day_found = False
        current_date_check_dt = date_dt
        while not next_work_day_found:
            current_date_check_dt += relativedelta(days=1)
            current_date_check = current_date_check_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            is_weekend = current_date_check_dt.weekday() in weekends
            is_holiday = current_date_check in iseigines

            if not is_holiday and not is_weekend:
                return current_date_check
            if current_date_check > potential_max_date:
                return False

    @api.model
    def get_last_work_day(self, month=False, year=False, date=False):
        def _strf(date):
            try:
                return date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            except:
                return date.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

        if month and year:
            last_of_month = datetime(year, month, 1) + relativedelta(day=31)
        elif date:
            if isinstance(date, datetime):
                last_of_month = date + relativedelta(day=31)
            else:
                try:
                    last_of_month = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(day=31)
                except Exception as e:
                    last_of_month = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT) + relativedelta(day=31)
        else:
            raise exceptions.ValidationError(_('Nustatant paskutinę mėnesio darbo dieną - privaloma nurodyti mėnesį ir '
                                               'metus arba betkurią mėnesio datą'))

        first_of_month_strf = _strf(last_of_month + relativedelta(day=1))
        last_of_month_strf = _strf(last_of_month)
        holiday_dates = self.env['sistema.iseigines'].search([
            ('date', '>=', first_of_month_strf),
            ('date', '<=', last_of_month_strf)
        ]).mapped('date')
        last_working_day = last_of_month
        while last_working_day.weekday() in [5, 6] or _strf(last_working_day) in holiday_dates:
            last_working_day -= relativedelta(days=1)
        return _strf(last_working_day)

    @api.model
    def get_payroll_values(self, bruto, **kwargs):
        """
            Computes all the payroll values given the date and the bruto amount
        """

        taxes = self.preprocess_tax_rates(**kwargs)
        today = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date = taxes.get('date') or today
        npd_date = taxes.get('npd_date') or date

        forced_tax_free_income = taxes.get('forced_tax_free_income')
        if forced_tax_free_income is None:
            forced_tax_free_income = taxes.get('force_npd')
        voluntary_pension = taxes.get('voluntary_pension')
        disability = taxes.get('disability')
        rounding = taxes.get('rounding', 0.01)
        npd_adjustment = taxes.get('npd_adjustment', 0.0)
        illness_amount = taxes.get('illness_amount', 0.0)
        bruto_from_other_payments = taxes.get('bruto_from_other_payments', 0.0)
        is_fixed_term = taxes.get('is_fixed_term', False)
        is_foreign_resident = kwargs.get('is_foreign_resident', False)

        # Determine which tax rates to use
        pension_percentage_field = 'darbuotojo_pensijos_proc'
        employer_sodra_percentage_field = 'darbdavio_sodra_proc'
        if is_foreign_resident:
            pension_percentage_field = 'employee_tax_fund_foreigner_with_visa_pct'
            employer_sodra_percentage_field = 'employer_sodra_foreigner_with_visa_pct'

        bruto += illness_amount
        bruto = tools.float_round(bruto, precision_rounding=rounding)
        bruto_without_illness = tools.float_round(bruto-illness_amount, precision_rounding=rounding)

        # Check if voluntary pension (and how much) should be paid
        if voluntary_pension:
            sodra_taxes = 'sodra_papild_exponential_proc' if voluntary_pension == 'exponential' else 'sodra_papild_proc'
            sodra_taxes = taxes.get(sodra_taxes, 0.0)
            # P3:DivOK
            voluntary_sodra = tools.float_round(sodra_taxes * bruto_without_illness / 100.0, precision_rounding=rounding)
        else:
            voluntary_sodra = 0.0

        # Calculate the base employee SODRA taxes
        if not is_foreign_resident:
            employee_health_tax = taxes['darbuotojo_sveikatos_proc'] * bruto_without_illness / 100.0  # P3:DivOK
        else:
            employee_health_tax = 0.0
        employee_pension_tax = taxes[pension_percentage_field] * bruto_without_illness / 100.0  # P3:DivOK

        # Calculate the non-taxable income amount (NPD)
        if forced_tax_free_income is None:
            bruto_for_npd_calculations = bruto + bruto_from_other_payments
            npd_coefficient = taxes['npd_koeficientas']
            minimum_wage = taxes['mma']
            if not disability:
                if npd_date < '2022-01-01':
                    npd_max = taxes['npd_max']
                else:
                    average_wage = taxes['average_wage']
                    if tools.float_compare(bruto_for_npd_calculations, average_wage, precision_digits=2) <= 0:
                        npd_max = taxes['under_avg_wage_npd_max']
                        npd_coefficient = taxes['under_avg_wage_npd_coefficient']
                        minimum_wage = taxes['under_avg_wage_minimum_wage_for_npd']
                    else:
                        npd_max = taxes['above_avg_wage_npd_max']
                        npd_coefficient = taxes['above_avg_wage_npd_coefficient']
                        minimum_wage = taxes['above_avg_wage_minimum_wage_for_npd']
            elif disability == '0_25':
                npd_max = taxes['npd_0_25_max']
            else:
                npd_max = taxes['npd_30_55_max']

            bruto_is_more_than_npd_max = tools.float_compare(bruto_for_npd_calculations, npd_max, precision_digits=2) > 0
            bruto_is_less_than_mma = tools.float_compare(bruto_for_npd_calculations, minimum_wage, precision_digits=2) <= 0

            if bruto_is_more_than_npd_max and (bruto_is_less_than_mma or disability):
                npd = npd_max
            else:
                npd = npd_max - (bruto_for_npd_calculations - minimum_wage) * npd_coefficient
                npd = min(npd, npd_max)
        else:
            npd = forced_tax_free_income
        npd += npd_adjustment
        npd = max(npd, 0.0)
        npd = min(npd, bruto)
        npd = tools.float_round(npd, precision_rounding=rounding)

        # Calculate the GPM
        gpm_proc = taxes['gpm_proc']
        gpm_illness_proc = taxes['gpm_ligos_proc']

        npd_illness = 0.0
        if not tools.float_is_zero(illness_amount, precision_digits=2) and \
           not tools.float_is_zero(bruto, precision_digits=2):
            npd_illness = npd * illness_amount / bruto  # P3:DivOK
        npd_regular = npd - npd_illness
        regular_gpm = (bruto - illness_amount - npd_regular) * gpm_proc / 100.0  # P3:DivOK
        illness_gpm = (illness_amount - npd_illness) * gpm_illness_proc / 100.0  # P3:DivOK
        gpm = regular_gpm + illness_gpm

        # Based on the amounts find out the NETO value
        neto = bruto - gpm - employee_health_tax - employee_pension_tax - voluntary_sodra
        neto = tools.float_round(neto, precision_rounding=rounding)

        # Round taxes
        gpm = tools.float_round(gpm, precision_rounding=rounding)
        employee_health_tax = tools.float_round(employee_health_tax, precision_rounding=rounding)
        employee_pension_tax = tools.float_round(employee_pension_tax, precision_rounding=rounding)

        # Finally find out the employer SODRA amount and the total workplace costs
        employer_sodra_percentage = taxes[employer_sodra_percentage_field]
        if is_fixed_term:
            employer_sodra_percentage += self.env.user.company_id.term_contract_additional_sodra_proc
        employer_sodra = employer_sodra_percentage * bruto / 100.0  # P3:DivOK
        employer_sodra = tools.float_round(employer_sodra, precision_rounding=rounding)

        workplace_costs = bruto + employer_sodra

        return {
            'bruto': bruto,
            'npd': npd,
            'gpm': gpm,
            'employee_health_tax': employee_health_tax,
            'employee_pension_tax': employee_pension_tax,
            'voluntary_sodra': voluntary_sodra,
            'neto': neto,
            'darbdavio_sodra': employer_sodra,
            'workplace_costs': workplace_costs,
        }

    @api.model
    def standard_work_time_period_data(self, date_from, date_to, six_day_work_week=False):
        """
            Returns number of days by the standard accountant calendar given date from and date to
        :param date_from: date string
        :param date_to: date string
        :param six_day_work_week: boolean
        :return: {'days': integer, 'hours': float} - number of days and hours by standard accountant calendar in a
        given period
        """
        if date_from > date_to:
            raise exceptions.UserError(_('Data nuo turi būti prieš datą iki'))

        res = {
            'days': 0,
            'hours': 0.0
        }

        date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        holiday_dates_to = (date_to_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        holiday_dates = self.env['sistema.iseigines'].search([
            ('date', '>=', date_from), ('date', '<=', holiday_dates_to)
        ]).mapped('date')

        weekends = [5, 6] if not six_day_work_week else [6]
        if self._context.get('include_weekends'):
            # Allow including weekends in the calculations. Useful for getting calendar days without national holidays
            weekends = []

        while date_from_dt <= date_to_dt:
            date_check = date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            next_day = (date_from_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if date_check not in holiday_dates and date_from_dt.weekday() not in weekends:
                res['days'] = res['days'] + 1
                res['hours'] = res['hours'] + 8
                if next_day in holiday_dates:
                    res['hours'] = res['hours'] - 1

            date_from_dt += relativedelta(days=1)

        res['hours'] = max(res['hours'], 0.0)

        return res

    @api.model
    def preprocess_tax_rates(self, **kwargs):
        """ Preprocess keyword arguments as tax rates and retrieves missing ones from payroll """
        # Determine date
        date = kwargs.get('date', datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))

        is_foreign_resident = kwargs.get('is_foreign_resident')

        # Get all payroll taxes
        contract = kwargs.get('contract')
        if not contract:
            contract = self.env['hr.contract']
        tax_rates = contract.with_context(date=date).get_payroll_tax_rates()

        # Get additional non-taxable amount (NPD) related tax rates based on NPD date
        npd_date = kwargs.get('npd_date')
        npd_rates = dict()
        if npd_date:
            # Determine which fields are not in kwargs yet
            npd_fields = [
                'npd_max', 'npd_0_25_max', 'npd_30_55_max', 'npd_koeficientas', 'mma_first_day_of_year',
                'average_wage', 'mma', 'under_avg_wage_npd_coefficient', 'under_avg_wage_npd_max',
                'under_avg_wage_minimum_wage_for_npd', 'above_avg_wage_npd_coefficient', 'above_avg_wage_npd_max',
                'above_avg_wage_minimum_wage_for_npd'
            ]
            if not self._context.get('force_override_taxes_by_npd_date'):
                npd_fields = [field for field in npd_fields if field not in kwargs]
            # Get fields based on NPD date
            if npd_fields:
                npd_rates = self.env['hr.contract'].with_context(date=npd_date).get_payroll_tax_rates(npd_fields)
                tax_rates.update(npd_rates)

        # Get additional taxes for foreign resident
        if is_foreign_resident:
            foreign_resident_tax_fields = [field for field in [
                'employee_tax_fund_foreigner_with_visa_pct', 'employer_sodra_foreigner_with_visa_pct'
            ] if field not in kwargs]
            if foreign_resident_tax_fields:
                tax_rates.update(self.env['hr.contract'].with_context(date=date).get_payroll_tax_rates(
                    foreign_resident_tax_fields
                ))

        # Update with taxes defined in kwargs
        tax_rates.update(kwargs)

        # Allow force overriding provided taxes with the taxes of the NPD date (usually the taxes are retrieved by
        # regular date)
        if self._context.get('force_override_taxes_by_npd_date'):
            tax_rates.update(npd_rates)

        return tax_rates

    @api.model
    def convert_net_income_to_gross(self, net_amount, **kwargs):
        """
        Convert net amount to gross amount based on Lithuanian payroll rules/the law. Make sure you pass the correct
        payroll values for the correct date because this method does not check them.
        :param net_amount: net amount to be converted to gross amount (float)
        :return: gross amount based on the given payroll values (float)
        """

        # Gross amount will 0 if net amount is 0
        if tools.float_is_zero(net_amount, precision_digits=2):
            return 0.0

        tax_rates = self.preprocess_tax_rates(**kwargs)
        illness_bruto_amount = tax_rates.get('illness_bruto_amount')

        # Currently no easy way to calculate the BRUTO amount given some NET amount plus additional BRUTO that uses a
        # different tax rate so we bruteforce it
        if illness_bruto_amount and not tools.float_is_zero(illness_bruto_amount, precision_digits=2):
            return self.bruteforce_bruto_from_neto(net_amount, **tax_rates)

        # Assign taxes to variables
        tax_free_income_coefficient = tax_rates.get('npd_koeficientas')
        tax_free_income_max = tax_rates.get('npd_max')
        minimum_wage = tax_rates.get('mma')
        income_tax_rate = tax_rates.get('gpm_proc') / 100.0  # P3:DivOK
        is_foreign_resident = tax_rates.get('is_foreign_resident')
        voluntary_pension = tax_rates.get('voluntary_pension')
        disability = tax_rates.get('disability')
        social_security_voluntary_rate = 0.0
        if voluntary_pension:
            # P3:DivOK
            if voluntary_pension == 'full':
                social_security_voluntary_rate = tax_rates.get('sodra_papild_proc', 0.0) / 100.0
            else:
                social_security_voluntary_rate = tax_rates.get('sodra_papild_exponential_proc', 0.0) / 100.0
        forced_tax_free_income = tax_rates.get('forced_tax_free_income')
        if forced_tax_free_income is None:
            forced_tax_free_income = tax_rates.get('force_npd')
        average_wage = tax_rates.get('average_wage', 0.0)
        today = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date = tax_rates.get('date') or today
        npd_date = tax_rates.get('npd_date') or date

        # Determine which tax rates to use
        # P3:DivOK
        if not is_foreign_resident:
            social_security_pension_rate = tax_rates.get('darbuotojo_pensijos_proc') / 100.0
            social_security_health_rate = tax_rates.get('darbuotojo_sveikatos_proc') / 100.0
        else:
            social_security_health_rate = 0.0
            social_security_pension_rate = tax_rates.get('employee_tax_fund_foreigner_with_visa_pct') / 100.0

        # Get the NET average wage and if no amount is returned or if it's zero set it as the NET amount so calculations
        # are following the rules for amounts under the NET average wage
        net_average_wage = self.get_payroll_values(average_wage, **tax_rates).get('neto')
        if not net_average_wage or tools.float_is_zero(net_average_wage, precision_digits=2):
            net_average_wage = net_amount

        social_insurance_rate = social_security_pension_rate + social_security_health_rate + \
                                social_security_voluntary_rate
        if tools.float_is_zero(tax_free_income_coefficient, precision_digits=2):
            if tools.float_is_zero(tax_free_income_max, precision_digits=2):
                tax_free_income_cutoff_gross = 0.0
            else:
                tax_free_income_cutoff_gross = minimum_wage
        else:
            if npd_date >= '2022-01-01' and tools.float_compare(net_amount, net_average_wage, precision_digits=2) > 0:
                tax_free_income_max = tax_rates.get('above_avg_wage_npd_max') or tax_free_income_max
                tax_free_income_coefficient = tax_rates.get('above_avg_wage_npd_coefficient') or tax_free_income_max
                minimum_wage = tax_rates.get('above_avg_wage_minimum_wage_for_npd') or minimum_wage
            # P3:DivOK
            tax_free_income_cutoff_gross = tax_free_income_max / tax_free_income_coefficient + minimum_wage

        tax_free_income_cutoff_net_amount = tax_free_income_cutoff_gross - \
                                            (tax_free_income_cutoff_gross * income_tax_rate +
                                             tax_free_income_cutoff_gross * social_insurance_rate)

        minimum_wage_net_amount = minimum_wage - ((minimum_wage - tax_free_income_max) * income_tax_rate +
                                                  minimum_wage * social_insurance_rate)
        tax_free_income_max_net_amount = tax_free_income_max - tax_free_income_max * social_insurance_rate

        no_income_tax_gross_amount = -1 * (net_amount / (social_insurance_rate - 1))  # P3:DivOK

        if disability:
            if disability == '0_25':
                forced_tax_free_income = tax_rates.get('npd_0_25_max')
            elif disability == '30_55':
                forced_tax_free_income = tax_rates.get('npd_30_55_max')

        if forced_tax_free_income is not None:
            if tools.float_is_zero(forced_tax_free_income, precision_digits=2):
                gross_amount = -1 * (net_amount / (social_insurance_rate + income_tax_rate - 1))  # P3:DivOK
            elif forced_tax_free_income > no_income_tax_gross_amount:
                gross_amount = no_income_tax_gross_amount
            else:
                # P3:DivOK
                gross_amount = (income_tax_rate * forced_tax_free_income - net_amount) / \
                               (social_insurance_rate + income_tax_rate - 1)
        elif net_amount <= tax_free_income_max_net_amount:
            gross_amount = no_income_tax_gross_amount
        elif net_amount <= minimum_wage_net_amount:
            # P3:DivOK
            gross_amount = (income_tax_rate * tax_free_income_max - net_amount) / \
                           (social_insurance_rate + income_tax_rate - 1)
        elif net_amount <= tax_free_income_cutoff_net_amount:
            if npd_date >= '2022-01-01':
                # Different npd_max and npd_coefficient values are possible depending on the average wage for
                # calculations after this date
                if tools.float_compare(net_amount, net_average_wage, precision_digits=2) <= 0:
                    tax_free_income_max = tax_rates.get('under_avg_wage_npd_max') or tax_free_income_max
                    tax_free_income_coefficient = tax_rates.get('under_avg_wage_npd_coefficient') or tax_free_income_max
                    minimum_wage = tax_rates.get('under_avg_wage_minimum_wage_for_npd') or minimum_wage
                else:
                    tax_free_income_max = tax_rates.get('above_avg_wage_npd_max') or tax_free_income_max
                    tax_free_income_coefficient = tax_rates.get('above_avg_wage_npd_coefficient') or tax_free_income_max
                    minimum_wage = tax_rates.get('above_avg_wage_minimum_wage_for_npd') or minimum_wage
            # P3:DivOK
            gross_amount = (tax_free_income_max * income_tax_rate +
                            income_tax_rate * tax_free_income_coefficient * minimum_wage - net_amount) / \
                           (income_tax_rate * tax_free_income_coefficient + income_tax_rate + social_insurance_rate - 1)
        else:
            gross_amount = -1 * (net_amount / (social_insurance_rate + income_tax_rate - 1))  # P3:DivOK

        # Calculate/forecast NET wage from computed BRUTO
        forecast_net = self.get_payroll_values(gross_amount, **tax_rates).get('neto')
        # Create an adjustment if the NET values don't exactly match. They should not differ by more than 0.01
        net_comparison = tools.float_compare(forecast_net, net_amount, precision_digits=2)
        if net_comparison < 0:
            adjustment = 0.01
        elif net_comparison > 0:
            adjustment = -0.01
        else:
            adjustment = 0.0
        gross_amount += adjustment

        return gross_amount

    @api.model
    def bruteforce_bruto_from_neto(self, net_amount, **kwargs):
        """
        Convert net amount to gross amount based on given payroll values. This method does this by using a try-fail
        method, looping and calculating NETO amounts from BRUTO amounts until it gets an amount that's close enough.
        :param net_amount: net amount to be converted to gross amount (float)
        :return: gross amount based on the given payroll values (float)
        """

        tax_rates = self.preprocess_tax_rates(**kwargs)

        # Assign taxes to variables
        tax_free_income_coefficient = tax_rates.get('npd_koeficientas')
        tax_free_income_max = tax_rates.get('npd_max')
        minimum_wage = tax_rates.get('mma')
        income_tax_rate = tax_rates.get('gpm_proc') / 100.0  # P3:DivOK
        illness_bruto_amount = tax_rates.get('illness_bruto_amount', 0.0)
        tax_rates['illness_bruto_amount'] = None  # Reset illness bruto to prevent recursion when converting neto
        voluntary_pension = tax_rates.get('voluntary_pension')
        social_security_voluntary_rate = 0.0
        if voluntary_pension:
            # P3:DivOK
            if voluntary_pension == 'full':
                social_security_voluntary_rate = tax_rates.get('sodra_papild_proc', 0.0) / 100.0
            else:
                social_security_voluntary_rate = tax_rates.get('sodra_papild_exponential_proc', 0.0) / 100.0
        forced_tax_free_income = tax_rates.get('forced_tax_free_income')
        if forced_tax_free_income is None:
            forced_tax_free_income = tax_rates.get('force_npd')
        illness_income_tax_rate = tax_rates.get('gpm_ligos_proc', 0.0) / 100.0
        is_foreign_resident = tax_rates.get('is_foreign_resident')
        today = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date = tax_rates.get('date') or today
        npd_date = tax_rates.get('npd_date') or date
        average_wage = tax_rates.get('average_wage', 0.0)
        disability = tax_rates.get('disability')
        if disability:
            if disability == '0_25':
                forced_tax_free_income = tax_rates.get('npd_0_25_max')
            elif disability == '30_55':
                forced_tax_free_income = tax_rates.get('npd_30_55_max')

        # Determine which tax rates to use
        # P3:DivOK
        if not is_foreign_resident:
            social_security_pension_rate = tax_rates.get('darbuotojo_pensijos_proc') / 100.0
            social_security_health_rate = tax_rates.get('darbuotojo_sveikatos_proc') / 100.0
        else:
            social_security_health_rate = 0.0
            social_security_pension_rate = tax_rates.get('employee_tax_fund_foreigner_with_visa_pct') / 100.0

        # Checks if calculated neto differs from the required neto by less than 0.01
        def close_match_to_expected_neto(neto_calculated, expected_neto=net_amount):
            return tools.float_compare(abs(neto_calculated - expected_neto), 0.01, precision_digits=2) <= 0

        # Checks if calculated neto is exactly the same as the required neto by three digit precision
        def exact_match_to_expected_neto(neto_calculated, expected_neto=net_amount):
            return tools.float_compare(neto_calculated, expected_neto, precision_digits=3) == 0

        # Calculates NET amount from BRUTO based on given params
        def get_neto(bruto, illness_bruto):
            full_bruto = bruto + illness_bruto
            npd = forced_tax_free_income
            if npd is None:
                # Values for current calculation
                tax_free_income_max_cc = tax_free_income_max
                tax_free_income_coefficient_cc = tax_free_income_coefficient
                minimum_wage_cc = minimum_wage
                bruto_is_more_than_npd_max = tools.float_compare(full_bruto, tax_free_income_max_cc, precision_digits=2) > 0
                bruto_is_less_than_mma = tools.float_compare(full_bruto, minimum_wage_cc, precision_digits=2) <= 0
                if bruto_is_more_than_npd_max and bruto_is_less_than_mma:
                    npd = tax_free_income_max_cc
                else:
                    if npd_date >= '2022-01-01':
                        if tools.float_compare(full_bruto, average_wage, precision_digits=2) <= 0:
                            tax_free_income_max_cc = tax_rates.get('under_avg_wage_npd_max') or tax_free_income_max_cc
                            tax_free_income_coefficient_cc = tax_rates.get(
                                'under_avg_wage_npd_coefficient') or tax_free_income_coefficient_cc
                            minimum_wage_cc = tax_rates.get('under_avg_wage_minimum_wage_for_npd') or minimum_wage_cc
                        else:
                            tax_free_income_max_cc = tax_rates.get('above_avg_wage_npd_max') or tax_free_income_max_cc
                            tax_free_income_coefficient_cc = tax_rates.get(
                                'above_avg_wage_npd_coefficient') or tax_free_income_coefficient_cc
                            minimum_wage_cc = tax_rates.get('above_avg_wage_minimum_wage_for_npd') or minimum_wage_cc
                    npd = tax_free_income_max_cc - (full_bruto - minimum_wage_cc) * tax_free_income_coefficient_cc
                    npd = min(npd, tax_free_income_max_cc)
            npd = max(npd, 0.0)
            npd = min(npd, full_bruto)

            if tools.float_compare(full_bruto, 0.0, precision_digits=2) > 0:
                npd_illness = npd * (illness_bruto / full_bruto)  # P3:DivOK
            else:
                npd_illness = 0.0
            npd_regular_bruto = npd - npd_illness
            taxable_regular_bruto = bruto - npd_regular_bruto
            taxable_illness_bruto = illness_bruto - npd_illness

            income_tax_regular_bruto = taxable_regular_bruto * income_tax_rate
            income_tax_illness = taxable_illness_bruto * illness_income_tax_rate

            social_insurance_amount = \
                round(bruto * social_security_pension_rate, 2) + \
                round(bruto * social_security_health_rate, 2) + \
                round(bruto * social_security_voluntary_rate, 2)

            regular_neto = bruto - income_tax_regular_bruto - social_insurance_amount
            illness_neto = illness_bruto - income_tax_illness
            full_neto = regular_neto + illness_neto
            return full_neto

        # Preliminary BRUTO. Will return the correct NET amount every time if no illness BRUTO is specified thus
        # bruteforce will not be needed
        bruto = self.convert_net_income_to_gross(net_amount, **tax_rates)

        # If no illness amount specified - the bruto above will be correct so we can skip bruteforcing, otherwise
        # trigger the bruteforce
        neto = net_amount - illness_bruto_amount
        bruto_adjustment = 0.0
        close_match_count = 0
        iteration = 0

        # Stop bruteforcing if we get an amount that's close to the required NET amount 10 times. Or if the amount is
        # the one we need
        while not exact_match_to_expected_neto(neto) and close_match_count < 10:
            # Adjust BRUTO to be calculated for
            bruto -= bruto_adjustment

            neto = get_neto(bruto, illness_bruto_amount)

            # Check the difference and adjust the BRUTO adjustment for the next iteration.
            neto_difference = neto - net_amount
            if iteration < 15 and tools.float_compare(abs(neto_difference), 0.01, precision_digits=2) > 0:
                # Perform big adjustments first, if the neto difference is quite big and we're still in the early stage
                # of adjusting
                bruto_adjustment = neto_difference * 2
            elif iteration < 15 and tools.float_compare(abs(neto_difference), 0.001, precision_digits=3) > 0:
                # Perform smaller adjustments as we get closer to the required NETO
                bruto_adjustment = neto_difference
            else:
                # If we're still not getting the right value - perform tiny adjustments
                bruto_adjustment = neto_difference / 2.0  # P3:DivOK

            # Track number of close matches so that we're not looping forever and we can settle on 0.01 amount
            # difference
            is_close_match = close_match_to_expected_neto(neto)
            if is_close_match:
                close_match_count += 1

            iteration += 1

            # Prevent endless cycling if something goes wrong, but this should not happen.
            if iteration > 50:
                break
        return bruto + illness_bruto_amount

    @api.model
    def get_salary_adjustment_data(self, change_date, keep_difference=False, minimum_monthly_wage_adjustment=0.0,
                                   minimum_hourly_wage_adjustment=0.0):
        """Gets data for contracts where salary should be changed to meet the minimum wage for that day
        :param change_date: (str) Date of salary change
        :param keep_difference: (bool) Should the difference between the current minimum wage and the wage the employee
        gets be kept? For example if the minimum wage is 642 and an employee gets 650, then after the minimum wage is
        raised to 730 the employee would get 738 (730+650-642). Only applies if the employee earns less than the new
        minimum wage
        :param minimum_hourly_wage_adjustment: (float) Adjusts the minimum hourly wage for the date by the specified
        amount. Useful if the manager wants their employees to get minimum wage + X
        :param minimum_monthly_wage_adjustment: (float) Adjusts the minimum monthly wage for the date by the specified
        amount. Useful if the manager wants their employees to get minimum wage + X
        :return (dict) dict of tuples { contract.id: (current wage, new wage, use net wage) }
        """
        today = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        # Get related tax rates
        tax_rate_keys = ['mma_first_day_of_year', 'min_hourly_rate', 'mma']
        current_tax_rates = self.env['hr.contract'].with_context(date=today).get_payroll_tax_rates(tax_rate_keys)
        new_tax_rates = self.env['hr.contract'].with_context(date=change_date).get_payroll_tax_rates(tax_rate_keys)

        # Assign tax rates to variables
        current_minimum_monthly_wage = current_tax_rates['mma']
        current_minimum_hourly_wage = current_tax_rates['min_hourly_rate']
        new_minimum_monthly_wage = new_tax_rates['mma_first_day_of_year'] + minimum_monthly_wage_adjustment
        new_minimum_hourly_wage = new_tax_rates['min_hourly_rate'] + minimum_hourly_wage_adjustment

        # Find applicable contracts
        contracts = self.env['hr.contract'].search([
            ('employee_id.active', '=', True),
            ('employee_id.type', '!=', 'intern'),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', change_date)
        ])

        salary_adjustment_data = dict()

        for contract in contracts:
            # Find appointment for change date
            appointment = contract.with_context(date=change_date).appointment_id.filtered(
                lambda app: app.date_start < change_date and (not app.date_end or app.date_end >= change_date)
            )
            if not appointment:
                continue

            current_wage = appointment.wage

            schedule_template = appointment.schedule_template_id
            post = schedule_template.etatas

            # Find current and new minimum wage based on terms for each contract
            if appointment.struct_id.code == 'MEN':
                # For monthly appointments - minimum wage should be adjusted by post or hours per month.
                new_minimum_wage = new_minimum_monthly_wage * post
                current_minimum_wage = current_minimum_monthly_wage * post
                freeze_net_wage = appointment.freeze_net_wage
                if freeze_net_wage:
                    voluntary_pension = appointment.sodra_papildomai and appointment.sodra_papildomai_type
                    disability = appointment.invalidumas and appointment.darbingumas.name
                    is_terminated_contract = appointment.contract_id.rusis in [
                        'terminuota', 'pameistrystes', 'projektinio_darbo'
                    ]
                    is_foreign_resident = appointment.employee_id.sudo().is_non_resident
                    forced_npd = None if appointment.use_npd else 0.0

                    # If NET wage is "frozen" - the new salary should be the NET amount
                    new_minimum_wage = self.get_payroll_values(
                        date=change_date, bruto=new_minimum_wage, forced_tax_free_income=forced_npd,
                        voluntary_pension=voluntary_pension, disability=disability,
                        is_fixed_term=is_terminated_contract, is_foreign_resident=is_foreign_resident
                    )['neto']
                    current_minimum_wage = self.get_payroll_values(
                        date=change_date, bruto=current_minimum_wage, forced_tax_free_income=forced_npd,
                        voluntary_pension=voluntary_pension, disability=disability,
                        is_fixed_term=is_terminated_contract, is_foreign_resident=is_foreign_resident
                    )['neto']
                    current_wage = appointment.neto_monthly
            else:
                # Use hourly wage values
                freeze_net_wage = False
                new_minimum_wage = new_minimum_hourly_wage
                current_minimum_wage = current_minimum_hourly_wage

            # Calculate wage difference if we wish to keep it and the employee earns less than the new minimum wage
            if keep_difference and tools.float_compare(current_wage, new_minimum_wage, precision_digits=2) < 0:
                wage_difference = current_wage - current_minimum_wage
                # Subtract the adjustment from the wage difference so that the employee does not get more than his
                # current difference + new minimum wage
                if appointment.struct_id.code == 'MEN':
                    wage_difference -= minimum_monthly_wage_adjustment
                else:
                    wage_difference -= minimum_hourly_wage_adjustment
                if tools.float_compare(wage_difference, 0.0, precision_digits=2) > 0:
                    new_minimum_wage += wage_difference

            # Don't do anything since the current wage is higher than the new minimum wage
            if tools.float_compare(current_wage, new_minimum_wage, precision_digits=2) >= 0:
                continue

            # Add the new wage data to the data dict
            salary_adjustment_data[contract.id] = (current_wage, new_minimum_wage, freeze_net_wage, post)

        return salary_adjustment_data


HrPayroll()
