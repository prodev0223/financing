# -*- coding: utf-8 -*-
from __future__ import division
import calendar
import logging
import re
import threading
import unicodedata
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo.addons.robo.models.robo_tools import MONTH_TO_STRING_MAPPING
from odoo.addons.robo.models.linksnis import kas_to_ko

import odoo
from odoo import models, fields, api, tools, exceptions, SUPERUSER_ID
from odoo.api import Environment
from odoo.tools import float_is_zero, float_compare
from odoo.tools.translate import _
from .hr_contract import SUTARTIES_RUSYS
from odoo.addons.base_iban.models.res_partner_bank import validate_iban


PROBATION_LAW_CHANGE_DATE = '2022-04-01'  # Date on which the probation attribute is no longer checked

_digits = re.compile('\d')
_logger = logging.getLogger(__name__)


def get_next_sequence_number(s):
    number_string = ''
    len_digits = 0
    for i in range(len(s)):
        char = s[-i-1]
        if char.isdigit():
            number_string = char + number_string
            len_digits += 1
        else:
            break
    if number_string:
        nex_number_int = int(number_string) + 1
        prefix = s[:-len_digits]
    else:
        prefix = s
        nex_number_int = 1
    next_number_str = str(nex_number_int).zfill(len_digits)
    return prefix + next_number_str


def contains_digits(d):
    return bool(_digits.search(d))


def remove_numbers(d):
    mas = []
    if d is not None and isinstance(d, (str, unicode)):
        for raide in d:
            if not raide.isdigit():
                mas.append(raide)
    return ''.join(mas)


def remove_letters(d):
    mas = []
    if d is not None and isinstance(d, (str, unicode)):
        for raide in d:
            if raide.isdigit():
                mas.append(raide)
    return ''.join(mas)


def remove_other(d):
    mas = []
    if d is not None and isinstance(d, (str, unicode)):
        for raide in d:
            if raide != ' ' and raide != ',' and raide != '-':
                mas.append(raide)
    return ''.join(mas)


def remove_accents(input_str):
    nkfd_form = unicodedata.normalize('NFKD', input_str)
    only_ascii = nkfd_form.encode('ASCII', 'ignore')
    return only_ascii


def is18(birth_date):
    age = 18
    end_date = datetime.today()
    years = end_date.year - birth_date.year
    if years == age:
        return birth_date.month < end_date.month or (birth_date.month == end_date.month and birth_date.day <= end_date.day)
    return years > age


def suma(self, employee_id, code, from_date, to_date=None):
    if to_date is None:
        to_date = datetime.utcnow().strftime('%Y-%m-%d')
    self._cr.execute("SELECT sum(case when hp.credit_note = False then (pl.total) else (-pl.total) end)\
                FROM hr_payslip as hp, hr_payslip_line as pl \
                WHERE hp.employee_id = %s AND hp.state = 'done' \
                AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pl.slip_id AND pl.code = %s",
                     (employee_id, from_date, to_date, code))
    res = self._cr.fetchone()
    return res and res[0] or 0.0


def suma_dd(self, employee_id, codes, from_date, to_date=None):
    if to_date is None:
        to_date = datetime.utcnow().strftime('%Y-%m-%d')
    self._cr.execute("SELECT sum(case when hp.credit_note = False then (pl.number_of_days) else (-pl.number_of_days) end)\
                FROM hr_payslip AS hp, hr_payslip_worked_days AS pl \
                WHERE hp.employee_id = %s AND hp.state = 'done' \
                AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pl.payslip_id AND pl.code IN %s ",
                     (employee_id, from_date, to_date, tuple(codes)))
    res = self._cr.fetchone()
    return res and res[0] or 0.0


def suma_dv(self, employee_id, codes, from_date, to_date=None):
    if to_date is None:
        to_date = datetime.utcnow().strftime('%Y-%m-%d')
    self._cr.execute("SELECT sum(case when hp.credit_note = False then (pl.number_of_hours) else (-pl.number_of_hours) end)\
                FROM hr_payslip AS hp, hr_payslip_worked_days AS pl \
                WHERE hp.employee_id = %s AND hp.state = 'done' \
                AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pl.payslip_id AND pl.code IN %s",
                     (employee_id, from_date, to_date, tuple(codes)))
    res = self._cr.fetchone()
    return res and res[0] or 0.0


def skaiciuoti_atostogu_dienas(self, datefrom, dateto):  # todo pagal appointmentą?
    try:
        date1 = datetime.strptime(datefrom, tools.DEFAULT_SERVER_DATE_FORMAT)
    except:
        date1 = datetime.strptime(datefrom, tools.DEFAULT_SERVER_DATETIME_FORMAT)
    try:
        date2 = datetime.strptime(dateto, tools.DEFAULT_SERVER_DATE_FORMAT)
    except:
        date2 = datetime.strptime(dateto, tools.DEFAULT_SERVER_DATETIME_FORMAT)
    daygenerator = (date1 + timedelta(x) for x in xrange((date2 - date1).days))
    darbo_dienos = sum(1 for day in daygenerator if day.weekday() < 5)
    atostogu_ids = self.env['sistema.iseigines'].search([('date', '>=', datefrom), ('date', '<=', dateto)])
    atostogu_skaicius = len(atostogu_ids)
    for aid in atostogu_ids:
        savaites_diena = datetime.strptime(aid.date, tools.DEFAULT_SERVER_DATE_FORMAT).weekday()
        if savaites_diena in (5, 6):
            atostogu_skaicius -= 1
    if date2.weekday() in (5, 6):
        darbo_dienos -= 1
    atostogu_dienos = darbo_dienos - atostogu_skaicius + 1
    return atostogu_dienos


def get_vdu(env, date_from,  employee, contract_id=None, include_last=False, vdu_type=False):
    res = {
        'vdu': 0.0,
        'vdu_date': date_from,
        'employee': employee,
    }
    calculation_info = {}
    salary_info = {'vdu_record_data': {}}

    coefficient_2019 = 1.289
    vdu_precision_digits = 3

    # Determine dates ==================================================================================================
    if not date_from:
        return res
    try:
        date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATETIME_FORMAT)
    except ValueError:
        date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)

    date_vdu_to_dt = (date_from_dt + relativedelta(day=1))
    date_vdu_prev_year_dt = date_vdu_to_dt + relativedelta(years=-1)
    date_vdu_from_dt = (date_from_dt + relativedelta(months=-3, day=1))
    if include_last:
        date_vdu_from_dt += relativedelta(months=+1)
        date_vdu_to_dt += relativedelta(months=+1)
    date_vdu_from = date_vdu_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
    date_vdu_prev_year = date_vdu_prev_year_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
    date_vdu_to = date_vdu_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
    # ==================================================================================================================

    # Find the appointment =============================================================================================
    appointment_domain = [('employee_id', '=', employee.id)]
    dates_domain = [
        ('date_start', '<=', date_from),
        '|',
        ('date_end', '=', False),
        ('date_end', '>=', date_from)
    ]
    if contract_id:
        appointment_domain.append(('contract_id', '=', contract_id))
    appointment = env['hr.contract.appointment'].search(appointment_domain + dates_domain,
                                                        order='date_start desc', limit=1)
    if not appointment:
        appointment_date_end = date_vdu_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        appointment_date_start = (date_vdu_to_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        dates_domain = [('date_start', '<=', appointment_date_start),
                        '|', ('date_end', '=', False),
                        ('date_end', '>=', appointment_date_end)]
        appointment = env['hr.contract.appointment'].search(appointment_domain + dates_domain,
                                                            order='date_start desc', limit=1)
    if not appointment:
        appointment = env['hr.contract.appointment'].search(appointment_domain, order='date_start desc', limit=1)
    # ==================================================================================================================

    # Find the contract ================================================================================================
    contract = None
    if appointment:
        contract = appointment.contract_id
    elif contract_id:
        contract = env['hr.contract'].sudo().browse(contract_id)
    #  =================================================================================================================

    # Get VDU records ==================================================================================================
    vdu_records = env['employee.vdu'].search([
        ('employee_id', '=', employee.id),
        ('date_from', '>=', date_vdu_from),
        ('date_from', '<', date_vdu_to)
    ])
    if contract:
        related_contracts = contract.get_contracts_related_to_work_relation()
        vdu_records = vdu_records.filtered(lambda r: not r.contract_id or r.contract_id.id in related_contracts.ids)
    # ==================================================================================================================

    # Find out the type if it's not set ================================================================================
    if vdu_records and not vdu_type:
        newest_vdu_records = vdu_records.sorted(lambda r: r.date_from, reverse=True)[0]
        vdu_type = 'h' if newest_vdu_records.type == 'val' else 'd'
    # ==================================================================================================================

    # Get data from the VDU records ====================================================================================
    total_amount = 0.0
    num_hours_worked = num_days_worked = 0.0
    for vdu_rec in vdu_records:
        amount = vdu_rec.amount
        date = vdu_rec.date_from
        if date < '2019-01-01' <= appointment.date_start:
            amount *= coefficient_2019

        total_amount += amount
        num_hours_worked += vdu_rec.hours_worked
        num_days_worked += vdu_rec.days_worked

        salary_info['vdu_record_data'].update({
            date: {
                'hours': vdu_rec.hours_worked,
                'days': vdu_rec.days_worked,
                'amount': amount
            }
        })
    # ==================================================================================================================

    # Get quarterly bonus amounts ======================================================================================
    bonuses = env['hr.employee.bonus'].search([('employee_id', '=', employee.id),
                                               ('payment_date_from', '<', date_vdu_to),
                                               ('payment_date_to', '>', date_vdu_from),
                                               ('state', '=', 'confirm')])

    payslips = env['hr.payslip'].search([('employee_id', '=', employee.id),
                                         ('date_from', '>=', date_vdu_from),
                                         ('date_from', '<', date_vdu_to),
                                         ('state', '=', 'done')
                                         ])

    if not payslips:
        quarterly_bonuses = bonuses.filtered(lambda r: r.bonus_type == '3men')
    else:
        quarterly_bonuses = env['hr.payslip.line'].search([
            ('slip_id', 'in', payslips.ids),
            ('code', '=', 'PR'),
            ('amount', '>', 0)
        ])

    if quarterly_bonuses:
        if not payslips:
            bonus = quarterly_bonuses.sorted(lambda d: d.payment_date_from, reverse=True)[0]
            bonus_date = bonus.payment_date_from
        else:
            bonus = quarterly_bonuses.sorted(lambda r: r.slip_id.date_from, reverse=True)[0]
            bonus_date = bonus.slip_id.date_from
        quarterly_bonus_amount = bonus.amount
        if bonus_date < '2019-01-01' <= date_from:
            quarterly_bonus_amount *= coefficient_2019
    else:
        quarterly_bonus_amount = 0.0
    total_amount += quarterly_bonus_amount
    salary_info.update({'quarterly_bonus_amount': quarterly_bonus_amount})
    # ==================================================================================================================

    # Get long term bonus amounts ======================================================================================
    payslips = env['hr.payslip'].search([
        ('employee_id', '=', employee.id),
        ('date_from', '>=', date_vdu_prev_year),
        ('date_from', '<', date_vdu_to),
        ('state', '=', 'done')
    ])
    if not payslips:
        long_term_bonuses = bonuses.filtered(lambda r: r.bonus_type == 'ilgesne')
    else:
        long_term_bonuses = env['hr.payslip.line'].search([('slip_id', 'in', payslips.ids),
                                                           ('code', '=', 'PRI'),
                                                           ('amount', '>', 0)])
    long_term_bonus_amount = 0.0
    for bonus in long_term_bonuses:
        bonus_date = bonus.payment_date_from if not payslips else bonus.slip_id.date_from
        bonus_amount = bonus.amount
        if bonus_date < '2019-01-01' <= date_from:
            bonus_amount *= coefficient_2019
        long_term_bonus_amount += bonus_amount
    total_amount += long_term_bonus_amount / 4.0  # P3:DivOK
    salary_info.update({'long_term_bonus_amount': long_term_bonus_amount})
    # ==================================================================================================================

    hours_worked_is_set = tools.float_compare(num_hours_worked, 0.0, precision_digits=vdu_precision_digits) > 0
    days_worked_is_set = tools.float_compare(num_days_worked, 0.0, precision_digits=vdu_precision_digits) > 0

    if vdu_type == 'd' and appointment:
        schedule_template = appointment.schedule_template_id
        full_post = tools.float_compare(schedule_template.etatas, 1.0, precision_digits=vdu_precision_digits) == 0
        regular_schedule = schedule_template.template_type == 'fixed'
        if regular_schedule:
            work_days = list(set(schedule_template.fixed_attendance_ids.mapped('dayofweek')))
            if len(work_days) != 5 or any(int(work_day) not in range(0, 5) for work_day in work_days):
                regular_schedule = False

        partial_downtime_exists = env['hr.employee.downtime'].search_count([
            ('date_from_date_format', '<=', date_vdu_to),
            ('date_to_date_format', '>=', date_vdu_from),
            ('employee_id', '=', employee.id),
            ('holiday_id.state', '=', 'validate'),
            ('downtime_type', '!=', 'full')
        ])

        use_hours_for_wage_calculations = appointment.use_hours_for_wage_calculations
        flexible_schedule = schedule_template.template_type == 'lankstus'
        vdu_after_dk_changes = date_vdu_from >= '2020-01-01'

        should_calculate_using_hours = partial_downtime_exists or \
                                       (not full_post and not regular_schedule) or \
                                       (use_hours_for_wage_calculations and
                                        (not flexible_schedule or vdu_after_dk_changes))

        if should_calculate_using_hours and hours_worked_is_set:
            vdu = total_amount / num_hours_worked * schedule_template.avg_hours_per_day  # P3:DivOK

            calculation_info = {
                'formula': _('(Visa priskaičiuota suma) ÷ (Dirbtų valandų skaičius) × (Vidutinis valandų skaičius per '
                          'dieną)'),
                'formula_with_real_values': '{} ÷ {} × {}'.format(round(total_amount, 2),
                                                                  round(num_hours_worked, 2),
                                                                  round(schedule_template.avg_hours_per_day, 2)),
                'amount': vdu
            }
            if partial_downtime_exists:
                calculation_info.update({'reason': _('VDU periode buvo dalinė prastova')})
            elif not full_post and not regular_schedule:
                calculation_info.update({'reason': _('Darbuotojo etatas nėra lygus 1.0 ir darbuotojas dirba ne pagal '
                                                     'standartinį 5d.d./sav. grafiką')})
            else:
                calculation_info.update({'reason': _('Darbo sutarties priedo grafiko šablone nustatyta atlyginimą '
                                                     'skaičiuoti valandomis')})
        elif days_worked_is_set:
            vdu = total_amount / num_days_worked  # P3:DivOK
            calculation_info = {
                'formula': _('(Visa priskaičiuota suma) ÷ (Dirbtų dienų skaičius)'),
                'reason': _('Darbo sutarties priedo grafiko šablone nenustatyta atlyginimą skaičiuoti valandomis, arba '
                            'grafikas yra lankstus'),
                'formula_with_real_values': '{} ÷ {}'.format(round(total_amount, 2), round(num_days_worked, 2)),
                'amount': vdu
            }
        else:
            try:
                appointments_in_vdu_range = env['hr.contract.appointment'].search([
                    ('employee_id', '=', employee.id),
                    ('contract_id', '=', appointment.contract_id.id),
                    ('date_start', '<=', date_vdu_to),
                    '|',
                    ('date_end', '>=', date_vdu_from),
                    ('date_end', '=', False)
                ])

                total_amount = 0.0
                total_hours = 0.0
                total_days = 0.0
                for i in range(0, 3):
                    month_start_dt = datetime.strptime(date_vdu_from, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(months=i)
                    month_start = month_start_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    month_end = (month_start_dt+relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    appointments_for_month = appointments_in_vdu_range.filtered(
                        lambda a: a.date_start <= month_end and (not a.date_end or a.date_end >= month_start))
                    for month_app in appointments_for_month:
                        norm_date_from = max(month_start, month_app.date_start)
                        norm_date_to = min(month_end, month_app.date_end) if month_app.date_end else month_end
                        app_work_norm = env['hr.employee'].with_context(
                            dont_shorten_before_holidays=True
                        ).employee_work_norm(
                            calc_date_from=norm_date_from,
                            calc_date_to=norm_date_to,
                            contract=month_app.contract_id,
                            appointment=month_app)
                        app_work_norm_with_shorter_days = env['hr.employee'].employee_work_norm(
                            calc_date_from=norm_date_from,
                            calc_date_to=norm_date_to,
                            contract=month_app.contract_id,
                            appointment=month_app)
                        month_app_work_norm = env['hr.employee'].with_context(
                            maximum=True, dont_shorten_before_holidays=True
                        ).employee_work_norm(
                            calc_date_from=month_start,
                            calc_date_to=month_end,
                            contract=month_app.contract_id,
                            appointment=month_app)
                        hour_ratio = day_ratio = 0.0
                        if not tools.float_is_zero(month_app_work_norm['hours'], precision_digits=2):
                            hour_ratio = app_work_norm['hours'] / float(month_app_work_norm['hours'])  # P3:DivOK
                        if not tools.float_is_zero(month_app_work_norm['days'], precision_digits=2):
                            day_ratio = app_work_norm['days'] / float(month_app_work_norm['days'])  # P3:DivOK
                        if month_app.struct_id.code == 'MEN':
                            if month_app.use_hours_for_wage_calculations:
                                wage = month_app.wage * hour_ratio
                            else:
                                wage = month_app.wage * day_ratio
                        else:
                            wage = month_app.wage * app_work_norm['hours']
                        total_amount += wage
                        total_hours += app_work_norm_with_shorter_days['hours']
                        total_days += app_work_norm_with_shorter_days['days']
                if appointment.use_hours_for_wage_calculations or appointment.struct_id.code == 'VAL':
                    vdu = total_amount / total_hours * appointment.schedule_template_id.avg_hours_per_day  # P3:DivOK
                    calculation_info = {
                        'formula': _('(Visa priskaičiuota suma) ÷ (Dirbtų valandų skaičius) × (Vidutinis valandų '
                                     'skaičius per dieną)'),
                        'reason': _('Nerasti VDU įrašai, todėl pagal dirbtas valandas ir darbo normą proporcingai '
                                    'priskaičiuotas atlyginimas per VDU laikotarpį dalinamas iš dirbto valandų '
                                    'skaičiaus ir dauginamas iš vidutinio valandų skaičiaus per dieną VDU skaičiavimo '
                                    'pabaigos datai'),
                        'formula_with_real_values': '{} ÷ {} × {}'.format(round(total_amount, 2),
                                                                          round(total_hours, 2),
                                                                          round(appointment.schedule_template_id.avg_hours_per_day, 2)),
                        'amount': vdu
                    }
                else:
                    vdu = total_amount / total_days  # P3:DivOK
                    calculation_info = {
                        'formula': _('(Visa priskaičiuota suma) ÷ (Dirbtų dienų skaičius)'),
                        'reason': _('Nerasti VDU įrašai, todėl pagal dirbtas valandas ir darbo normą proporcingai '
                                    'priskaičiuotas atlyginimas per VDU laikotarpį dalinamas iš dirbtų dienų skaičiaus'),
                        'formula_with_real_values': '{} ÷ {}'.format(round(total_amount, 2), round(total_days, 2)),
                        'amount': vdu
                    }
            except:
                month_date_from = (date_from_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                month_date_to = (date_from_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                num_days = appointment.employee_id.with_context(maximum=True).employee_work_norm(
                    calc_date_from=month_date_from,
                    calc_date_to=month_date_to,
                    appointment=appointment)['days']
                wage = appointment.wage

                if appointment.struct_id.code == 'MEN':
                    vdu = wage / num_days if num_days > 0 else 0.0  # P3:DivOK
                    calculation_info = {
                        'formula': _('(Atlyginimas nustatytas darbo sutarties priede) ÷ (Dirbtų dienų skaičius)'),
                        'reason': _('Nerasti VDU įrašai ir nebuvo įmanoma proporcingai išskaičiuoti pagal dirbtą laiką '
                                    'per VDU periodą'),
                        'formula_with_real_values': '{} ÷ {}'.format(round(wage, 2), round(num_days, 2)),
                        'amount': vdu
                    }
                else:
                    vdu = wage * appointment.schedule_template_id.avg_hours_per_day
                    calculation_info = {
                        'formula': _('(Atlyginimas nustatytas darbo sutarties priede) × (Vidutinis valandų skaičius '
                                     'per dieną)'),
                        'reason': _('Nerasti VDU įrašai ir nebuvo įmanoma proporcingai išskaičiuoti pagal dirbtą '
                                    'laiką per VDU periodą, o atlyginimo struktūra - valandinė'),
                        'formula_with_real_values': '{} × {}'.format(round(wage, 2),
                                                                     round(appointment.schedule_template_id.avg_hours_per_day, 2)),
                        'amount': vdu
                    }
    elif vdu_type == 'h' and appointment:
        if hours_worked_is_set:
            vdu = total_amount / num_hours_worked  # P3:DivOK
            calculation_info = {
                'formula': _('(Visa priskaičiuota suma) ÷ (Dirbtų valandų skaičius)'),
                'reason': _('Egzistuoja VDU įrašai, kuriuose nurodytas dirbtų valandų skaičius'),
                'formula_with_real_values': '{} ÷ {}'.format(round(total_amount, 2), round(num_hours_worked, 2)),
                'amount': vdu
            }
        else:
            try:
                appointments_in_vdu_range = env['hr.contract.appointment'].search([
                    ('employee_id', '=', employee.id),
                    ('contract_id', '=', appointment.contract_id.id),
                    ('date_start', '<=', date_vdu_to),
                    '|',
                    ('date_end', '>=', date_vdu_from),
                    ('date_end', '=', False)
                ])

                total_amount = 0.0
                total_hours = 0.0
                total_days = 0.0
                for i in range(0, 3):
                    month_start_dt = datetime.strptime(date_vdu_from,
                                                       tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(months=i)
                    month_start = month_start_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    month_end = (month_start_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    appointments_for_month = appointments_in_vdu_range.filtered(
                        lambda a: a.date_start <= month_end and (not a.date_end or a.date_end >= month_start))
                    for month_app in appointments_for_month:
                        norm_date_from = max(month_start, month_app.date_start)
                        norm_date_to = min(month_end, month_app.date_end) if month_app.date_end else month_end
                        app_work_norm = env['hr.employee'].with_context(
                            dont_shorten_before_holidays=True
                        ).employee_work_norm(
                            calc_date_from=norm_date_from,
                            calc_date_to=norm_date_to,
                            contract=month_app.contract_id,
                            appointment=month_app)
                        app_work_norm_with_shorter_days = env['hr.employee'].employee_work_norm(
                            calc_date_from=norm_date_from,
                            calc_date_to=norm_date_to,
                            contract=month_app.contract_id,
                            appointment=month_app)
                        month_app_work_norm = env['hr.employee'].with_context(
                            maximum=True, dont_shorten_before_holidays=True
                        ).employee_work_norm(
                            calc_date_from=month_start,
                            calc_date_to=month_end,
                            contract=month_app.contract_id,
                            appointment=month_app)
                        # P3:DivOK
                        hour_ratio = app_work_norm['hours'] / float(
                            month_app_work_norm['hours']) if not tools.float_is_zero(month_app_work_norm['hours'],
                                                                                     precision_digits=2) else 0.0
                        # P3:DivOK
                        day_ratio = app_work_norm['days'] / float(
                            month_app_work_norm['days']) if not tools.float_is_zero(month_app_work_norm['days'],
                                                                                    precision_digits=2) else 0.0
                        if month_app.struct_id.code == 'MEN':
                            if month_app.use_hours_for_wage_calculations:
                                wage = month_app.wage * hour_ratio
                            else:
                                wage = month_app.wage * day_ratio
                        else:
                            wage = month_app.wage * app_work_norm['hours']
                        total_amount += wage
                        total_hours += app_work_norm_with_shorter_days['hours']
                        total_days += app_work_norm_with_shorter_days['days']
                if not tools.float_is_zero(total_hours, precision_digits=2):
                    vdu = total_amount / total_hours  # P3:DivOK
                    calculation_info = {
                        'formula': _('(Visa priskaičiuota suma) ÷ (Dirbtų valandų skaičius)'),
                        'reason': _('VDU įrašuose nenurodytas dirbtų valandų skaičius, todėl priskaičiuotas atlyginimas'
                                    ' proporcingai paskaičiuojamas per VDU laikotarpį'),
                        'formula_with_real_values': '{} ÷ {}'.format(round(total_amount, 2), round(total_hours, 2)),
                        'amount': vdu
                    }
                else:
                    vdu = total_amount / total_days / appointment.schedule_template_id.avg_hours_per_day  # P3:DivOK
                    calculation_info = {
                        'formula': _('(Visa priskaičiuota suma) ÷ (Dirbtų dienų skaičius) ÷ (Vidutinis valandų skaičius'
                                     ' per dieną)'),
                        'reason': _('VDU įrašuose nenurodytas dirbtų valandų skaičius, todėl priskaičiuotas atlyginimas'
                                    ' proporcingai paskaičiuojamas per VDU laikotarpį'),
                        'formula_with_real_values': '{} ÷ {} ÷ {}'.format(round(total_amount, 2), round(total_hours, 2),
                                                                          round(appointment.schedule_template_id.avg_hours_per_day, 2)),
                        'amount': vdu
                    }
            except:
                if appointment.struct_id.code == 'VAL':
                    vdu = appointment.wage
                    calculation_info = {
                        'formula': _('Einamojo mėnesio atlyginimas'),
                        'reason': _('VDU įrašuose nenurodytas dirbtų valandų skaičius ir nustatyta valandinė atlyginimo '
                                    'struktūra'),
                        'formula_with_real_values': str(round(vdu, 2)),
                        'amount': vdu
                    }
                else:
                    month_date_from = (date_from_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    month_date_to = (date_from_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    wage = appointment.wage
                    num_days = appointment.employee_id.with_context(maximum=True).employee_work_norm(
                        calc_date_from=month_date_from,
                        calc_date_to=month_date_to,
                        appointment=appointment)['days']
                    hours_per_day = appointment.schedule_template_id.avg_hours_per_day
                    if num_days > 0:
                        vdu = wage / num_days / hours_per_day  # P3:DivOK
                        calculation_info = {
                            'formula': _('(Atlyginimas nustatytas darbo sutarties priede) ÷ (Dirbtų dienų skaičius) ÷ '
                                         '(Vidutinis valandų skaičius per dieną)'),
                            'reason': _('Nerasti VDU įrašai ir nebuvo įmanoma proporcingai išskaičiuoti pagal dirbtą laiką '
                                        'per VDU periodą, esant mėnesinei atlyginimo struktūrai'),
                            'formula_with_real_values': '{} ÷ {} ÷ {}'.format(round(wage, 2), round(num_days, 2), round(hours_per_day, 2)),
                            'amount': vdu
                        }
                    else:
                        vdu = 0
                        calculation_info = {
                            'formula': _('Neapskaičiuojama'),
                            'reason': _('Nerasti VDU įrašai ir nebuvo įmanoma proporcingai išskaičiuoti pagal dirbtą laiką '
                                        'per VDU periodą, esant mėnesinei atlyginimo struktūrai ir nerasta dirbtų darbo '
                                        'dienų šį mėnesį'),
                            'formula_with_real_values': '0.0',
                            'amount': 0.0
                        }
    else:
        if days_worked_is_set:
            vdu = total_amount / num_days_worked  # P3:DivOK
        else:
            if not appointment:
                vdu = 0
                calculation_info = {
                    'formula': '-',
                    'reason': _('Nerastas darbo sutarties priedas VDU skaičiavimo datai'),
                    'formula_with_real_values': '0.0',
                    'amount': 0.0
                }
            elif appointment.struct_id.code == 'MEN':
                month_date_from = (date_from_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                month_date_to = (date_from_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                wage = appointment.wage
                num_days = appointment.schedule_template_id.num_work_days(month_date_from, month_date_to)
                vdu = wage / num_days if num_days > 0 else 0  # P3:DivOK
            else:
                vdu = appointment.wage

    # Check that VDU is at least the minimum wage ======================================================================
    minimum_wage_adjustment = {}
    mma_date = date_vdu_to
    if include_last:
        mma_date = (date_vdu_to_dt - relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    if contract:
        # Ensure that the mma is calculated based on the contract attributes
        mma_date = max(mma_date, contract.work_relation_start_date)

    minimum_wage_data = employee.get_minimum_wage_for_date(mma_date, date_from)

    if vdu_type == 'd':
        minimum_daily = minimum_wage_data['day']
        if tools.float_compare(vdu, minimum_daily, precision_digits=vdu_precision_digits) < 0:
            vdu = minimum_daily
            minimum_wage_adjustment = {
                'formula': _('Minimalus dienos atlyginimas'),
                'formula_with_real_values': '{}'.format(minimum_daily)
            }
    else:
        minimum_hourly = minimum_wage_data['hour']
        if tools.float_compare(vdu, minimum_hourly, precision_digits=vdu_precision_digits) < 0:
            vdu = minimum_hourly
            minimum_wage_adjustment = {
                'formula': _('Minimalus valandinis atlyginimas'),
                'formula_with_real_values': str(vdu),
            }
    # ==================================================================================================================

    res.update({
        'vdu': vdu,
        'calculation_info': calculation_info,
        'salary_info': salary_info,
        'vdu_type': vdu_type,
        'minimum_wage_adjustment': minimum_wage_adjustment
    })
    return res


def correct_lithuanian_identification(kodas):
    if len(kodas) != 11:
        return False
    if not kodas.isdigit():
        return False
    last_digit = int(kodas[-1])
    coeficients1 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 1]

    remainder_1 = sum(int(a) * b for a, b in zip(kodas, coeficients1)) % 11
    if remainder_1 == last_digit:
        return True
    elif remainder_1 != 10:
        return False
    else:
        coeficients2 = [3, 4, 5, 6, 7, 8, 9, 1, 2, 3]
        remainder_2 = sum(int(a) * b for a, b in zip(kodas, coeficients2)) % 11
        if remainder_2 == 10:
            remainder_2 = 0
        return last_digit == remainder_2


def get_last_work_day(self, date):

    """
    @return DEFAULT_SERVER_DATE_FORMAT
    """

    if isinstance(date, basestring):
        try:
            date = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        except ValueError:
            date = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
    while date.weekday() in [5, 6] or self.env['sistema.iseigines'].search([('date', '=', date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))]):
        date -= timedelta(days=1)
    return date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)


class SeimosNariai(models.Model):

    _name = 'seimos.nariai'

    name = fields.Char(string='Vardas Pavardė', required=True)
    birthday = fields.Date(string='Gimimo data', required=True)
    mokyklos_baigimas = fields.Date(string='Mokyklos baigimo data', required=False)
    nebesimoko = fields.Boolean(string='Nebesimoko', required=False)
    seimos_narys = fields.Selection([('vyras', 'Vyras'), ('zmona', 'Žmona'),
                                    ('sugyventinis', 'Sugyventinis'), ('vaikas', 'Vaikas')],
                                    default='vaikas', string='Šeimos narys', required=True)
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', required=True)


SeimosNariai()


class HrEmployee(models.Model):

    _inherit = 'hr.employee'

    @api.model
    def _generate_order_by(self, order_spec, query):
        """
        Cast tabelio_numeris as integer, so it is sorted normally
        -> (1, 2, 10..) and not (1, 10, 2..)
        """
        if order_spec and 'tabelio_numeris' in order_spec:
            try:
                # Try splitting by field and mode i.e. table_number ASC
                # If there is too many values to unpack (multi order by)
                # Proceed with normal (default) operation
                field, mode = order_spec.split(' ')
                return ' ORDER BY LENGTH({}) {}, {} {}'.format(field, mode, field, mode)
            except ValueError:
                pass
        return super(HrEmployee, self)._generate_order_by(order_spec, query)

    @api.model
    def default_tabelio_numeris(self):
        self._cr.execute('SELECT tabelio_numeris from hr_employee')  # todo main_acc
        res = self._cr.fetchall()
        max_nr = 0
        for item in res:
            if item and item[0]:
                is_numerical = True
                for i in range(len(item[0])):
                    char = item[0][-i - 1]
                    is_numerical = False if not char.isdigit() else is_numerical
                if is_numerical:
                    try:
                        max_nr = max(int(item[0]), max_nr)
                    except:
                        pass
        return str(max_nr + 1)

    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female')
    ], groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager")

    sodra_papildomai = fields.Boolean(string='Sodra papildomai', default=False,
                                      groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager", # todo somehow remove
                                      )
    sodra_papildomai_type = fields.Selection([('full', 'Pilnas (3%)'), ('exponential', 'Palaipsniui (Nuo 2022 - 2.7%)')],
                                             string='Sodros kaupimo būdas', default='full')
    tevystes = fields.Boolean(string='Tėvystės atostogos', compute='onchange_leave_id', readonly=True,
                              groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager")
    invalidumas = fields.Boolean(string='Neįgalumas', related='appointment_id.invalidumas',
                                 groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager")
    darbingumas = fields.Many2one('darbuotojo.darbingumas', related='appointment_id.darbingumas',
                                  string='Darbingumo lygis',
                                  groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager")
    sodra_id = fields.Char(string='Socialinio draudimo nr.',
                           groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager",
                           sequence=100,
                           )
    address_home_id = fields.Many2one('res.partner', string='Partneris', required=False, inverse='_set_bank_account_id')
    identification_id = fields.Char(required=False, inverse='_set_gender',
                                    groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager")
    personal_phone_number = fields.Char(required=False, string="Asmeninis telefonas",
                                        groups="robo_basic.group_robo_free_manager,"
                                               "robo_basic.group_robo_premium_manager,"
                                               "robo_basic.group_robo_hr_manager",
                                        sequence=100,
                                        )
    last_medical_certificate_date = fields.Date(string="Date of last medical examination", required=False,
                                                groups="robo_basic.group_robo_free_manager,"
                                                       "robo_basic.group_robo_premium_manager,"
                                                       "robo_basic.group_robo_hr_manager",
                                                track_visibility='onchange'
                                                )
    next_medical_certificate_date = fields.Date(string="Date of next medical examination", required=False,
                                                groups="robo_basic.group_robo_free_manager,"
                                                       "robo_basic.group_robo_premium_manager,"
                                                       "robo_basic.group_robo_hr_manager",
                                                track_visibility='onchange'
                                                )
    street = fields.Char(compute='_compute_address_fields', inverse='_set_street')
    street2 = fields.Char(compute='_compute_address_fields', inverse='_set_street2')
    zip = fields.Char(compute='_compute_address_fields', inverse='_set_zip')
    city = fields.Char(compute='_compute_address_fields', inverse='_set_city')
    state_id = fields.Many2one('res.country.state', compute='_compute_address_fields', inverse='_set_state_id')
    country_id = fields.Many2one('res.country', compute='_compute_address_fields', inverse='_set_country_id')
    nationality_id = fields.Many2one('res.country', string='Pilietybė',
                                     groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager",
                                     )
    seimos_nariai = fields.One2many('seimos.nariai', 'employee_id', string='Šeimos nariai',
                                    groups='hr.group_hr_user,robo_basic.group_robo_hr_manager', sequence=100)
    atostogu_dienos = fields.Float(string='Priklauso atostogų dienų per metus', default=20.0,
                                   groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager",
                                   sequence=100,
                                   )
    work_location = fields.Char(default='Vilnius') #fixme:should it default to company address
    seimynine_padetis = fields.Many2one('seimynine.padetis', string='Šeimyninė padėtis',
                                        groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager",
                                        sequence=100,
                                        )
    contract_id = fields.Many2one('hr.contract', compute='_compute_contract_id', string='Current Contract',
                                  help='Latest contract of the employee')
    department_id = fields.Many2one('hr.department', required=True, track_visibility='onchange')
    advance_accountancy_partner_id = fields.Many2one('res.partner', string='Advance accountancy partner', sequence=100)
    main_accountant = fields.Boolean(string='Įmonės buhalteris', default=False, inverse='_set_main_accountant',
                                     groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager",
                                     sequence=100,
                                     )
    tabelio_numeris = fields.Char(string='Tabelio numeris', default=default_tabelio_numeris, sequence=100)
    bank_account_id = fields.Many2one('res.partner.bank',
                                      groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager",
                                      track_visibility='onchange',
                                      sequence=100,
                                      )
    bank_account_number = fields.Char(string='Banko sąskaita', sequence=100)
    birthday = fields.Date(groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager")
    leaves_accumulation_type = fields.Selection([('work_days', 'Darbo dienomis'),
                                                 ('calendar_days', 'Kalendorinėmis dienos')],
                                                string='Atostogų kaupimo tipas',
                                                related='appointment_id.leaves_accumulation_type', store=False,
                                                readonly=True,
                                                )
    type = fields.Selection([('employee', 'Darbuotojas'), ('intern', 'Praktikantas'), ('mb_narys', 'MB narys')],
                            string='Tipas', required=True, default='employee')
    # current_leave_id = fields.Many2one('hr.holidays.status',groups="robo_basic.group_robo_premium_manager")
    leave_text = fields.Text(string='Name', compute='_compute_leave_status')
    #country_id = fields.Many2one(default=lambda self: self.env['res.country'].search([('code', '=', 'LT')], limit=1))
    no_taxes_sodra_lubos = fields.Boolean(string='Nebetaikyti mokęsčių pasiekus sodros lubas', default=True,
                                          groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager",
                                          sequence=100,
                                          )
    related_user_archive_date = fields.Date(string='Naudotojo deaktyvavimo data',
                                            groups='robo_basic.group_robo_premium_accountant',
                                            sequence=100,
                                            track_visibility='onchange',
                                            )
    recalculate_num_of_leaves = fields.Boolean(string='Perskaičiuoti atostogas per metus', default=True,
                                     groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager",
                                               sequence=100,
                                               )
    pay_salary_in_cash = fields.Boolean(string='Darbo užmokestį mokėti grynais', default=False,
                                               groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager")
    show_bank_account_id = fields.Boolean(compute='_compute_show_bank_account_id')
    job_id = fields.Many2one('hr.job', store=True, compute='_compute_job_id')
    is_non_resident = fields.Boolean(string='Ne rezidentas', inverse='_set_is_non_resident',
                                 groups='robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager,robo_basic.group_robo_free_manager')
    skip_monthly_income_tax_report = fields.Boolean(string="Don't include in the monthly income tax report",
                                                    inverse='_set_skip_monthly_income_tax_report',
                                                    groups='robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager',
                                                    )

    @api.multi
    def _compute_show_bank_account_id(self):
        """
        Compute //
        Shows bank account ID if record is already created
        compute is not called if record is being created in form view,
        thus bank account is not showed
        :return: None
        """
        for rec in self:
            rec.show_bank_account_id = True

    @api.multi
    @api.depends('contract_ids.job_id', 'contract_ids.date_start', 'contract_ids.date_end')
    def _compute_job_id(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        for rec in self:
            contracts = rec.contract_ids
            contracts_up_to = contracts.filtered(lambda a: a.date_start <= date)
            contract_current = contracts.filtered(
                lambda a: a.date_start <= date and (not a.date_end or date <= a.date_end)
            )
            contracts_upcoming = contracts.filtered(
                lambda a: a.date_start >= date
            ) if contracts_up_to and not contract_current else None
            contracts = contracts_upcoming or contracts_up_to or contracts
            if contracts:
                job = contracts.sorted(key=lambda a: a.date_start, reverse=not contracts_upcoming)[0].job_id
                if job and rec.job_id != job:
                    rec.job_id = job

    def _set_skip_monthly_income_tax_report(self):
        for rec in self.filtered(lambda x: x.address_home_id):
            if rec.sudo().address_home_id.skip_monthly_income_tax_report != rec.skip_monthly_income_tax_report:
                rec.sudo().address_home_id.write({
                    'skip_monthly_income_tax_report': rec.skip_monthly_income_tax_report
                })

    def _set_is_non_resident(self):
        for rec in self.filtered(lambda x: x.address_home_id):
            resident = 'nerezidentas' if rec.is_non_resident else 'rezidentas'
            if rec.sudo().address_home_id.rezidentas != resident:
                rec.sudo().address_home_id.write({
                    'rezidentas': resident
                })

    @api.multi
    def _set_gender(self):
        """
        Inverse //
        Always get and set the gender if it is missing when identification id is set
        :return: None
        """
        for rec in self:
            gender = rec._get_gender_from_identification_id()
            if gender and not rec.gender:
                rec.gender = gender

    @api.multi
    def _set_bank_account_id(self):
        """
        Inverse //
        Create res.partner.bank record from specified IBAN after validating it.
        If new hr.employee record is being created user cannot create corresponding bank account,
        since you can't specify the employee which is not saved yet,
        thus we create the record with inverse
        :return: None
        """
        for rec in self.filtered(lambda x: x.address_home_id):
            if rec.bank_account_number and not rec.bank_account_id:
                validate_iban(rec.bank_account_number)
                account_values = {
                    'partner_id': rec.address_home_id.id,
                    'acc_number': rec.bank_account_number,
                }
                partner_bank = self.env['res.partner.bank'].create(account_values)
                rec.bank_account_id = partner_bank

            # Manually trigger is_employee re-computation
            # since sometimes it's not called correctly (we were not able to pinpoint why)
            rec.address_home_id._is_employee()

    @api.multi
    def _set_street(self):
        user_is_hr_manager = self.env.user.is_hr_manager()
        for rec in self:
            if rec.address_home_id:
                vals = {
                    'street': rec.street
                }
                if user_is_hr_manager:
                    rec.address_home_id.sudo().write(vals)
                else:
                    rec.address_home_id.write(vals)

    @api.multi
    def _set_street2(self):
        user_is_hr_manager = self.env.user.is_hr_manager()
        for rec in self:
            if rec.address_home_id:
                vals = {
                    'street2': rec.street2
                }
                if user_is_hr_manager:
                    rec.address_home_id.sudo().write(vals)
                else:
                    rec.address_home_id.write(vals)

    @api.multi
    def _set_zip(self):
        user_is_hr_manager = self.env.user.is_hr_manager()
        for rec in self:
            if rec.address_home_id:
                vals = {
                    'zip': rec.zip
                }
                if user_is_hr_manager:
                    rec.address_home_id.sudo().write(vals)
                else:
                    rec.address_home_id.write(vals)

    @api.multi
    def _set_city(self):
        user_is_hr_manager = self.env.user.is_hr_manager()
        for rec in self:
            if rec.address_home_id:
                vals = {
                    'city': rec.city
                }
                if user_is_hr_manager:
                    rec.address_home_id.sudo().write(vals)
                else:
                    rec.address_home_id.write(vals)

    @api.multi
    def _set_state_id(self):
        user_is_hr_manager = self.env.user.is_hr_manager()
        for rec in self:
            if rec.address_home_id:
                vals = {
                    'state_id': rec.state_id.id
                }
                if user_is_hr_manager:
                    rec.address_home_id.sudo().write(vals)
                else:
                    rec.address_home_id.write(vals)

    @api.multi
    def _set_country_id(self):
        user_is_hr_manager = self.env.user.is_hr_manager()
        for rec in self:
            if rec.address_home_id:
                vals = {
                    'country_id': rec.country_id.id
                }
                if user_is_hr_manager:
                    rec.address_home_id.sudo().write(vals)
                else:
                    rec.address_home_id.write(vals)

    @api.one
    def _compute_address_fields(self):
        user_is_the_employee = self.env.user.employee_ids and self.id in self.env.user.employee_ids.ids
        user_is_the_manager = self.env.user.is_manager() or self.env.user.is_hr_manager()
        if self.address_home_id and (user_is_the_manager or user_is_the_employee):
            address_home_id = self.sudo().address_home_id
            self.street = address_home_id.street
            self.street2 = address_home_id.street2
            self.zip = address_home_id.zip
            self.city = address_home_id.city
            self.state_id = address_home_id.state_id
            self.country_id = address_home_id.country_id
        if not self.country_id:
            self.country_id = self.env['res.country'].search([('code', '=', 'LT')], limit=1)

    # @api.multi
    # def get_num_sick_days_non_payable(self, date_from, date_to):
    #     '''
    #     @returns: number of days that were not paid
    #     '''
    #     self.ensure_one()
    #     res = 0
    #     date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
    #     date_from_dt_corrected = date_from_dt - relativedelta(months=1)
    #     pholidays = self.env['hr.holidays'].search(
    #         [('date_from_date_format', '>=', date_from_dt_corrected.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)),
    #          ('date_from_date_format', '<=', date_to),
    #          ('type', '=', 'remove'),
    #          ('employee_id', '=', self.id),
    #          ('state', '=', 'validate'),
    #          ('holiday_status_id.kodas', '=', 'L'),
    #          ('sick_leave_continue', '=', False)])
    #     intervals = []
    #     for sick_leave in pholidays:
    #         last_leave = sick_leave
    #         sick_leave_start = sick_leave.date_from_date_format
    #         continuation_from = (datetime.strptime(last_leave.date_to_date_format, tools.DEFAULT_SERVER_DATE_FORMAT) + timedelta(days=1)).\
    #             strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
    #         continuation = self.env['hr.holidays'].search(
    #             [('date_from_date_format', '=', continuation_from),
    #              ('type', '=', 'remove'),
    #              ('employee_id', '=', self.id),
    #              ('state', '=', 'validate'),
    #              ('holiday_status_id.kodas', '=', 'L'),
    #              ('sick_leave_continue', '=', True)], limit=1)
    #         while continuation:
    #             last_leave = continuation
    #             sick_leave_end_temp = last_leave.date_to_date_format
    #             continuation_from = (
    #                     datetime.strptime(sick_leave_end_temp, tools.DEFAULT_SERVER_DATE_FORMAT) + timedelta(days=1)). \
    #                 strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
    #             continuation = self.env['hr.holidays'].search(
    #                 [('date_from_date_format', '=', continuation_from),
    #                  ('type', '=', 'remove'),
    #                  ('employee_id', '=', self.id),
    #                  ('state', '=', 'validate'),
    #                  ('holiday_status_id.kodas', '=', 'L'),
    #                  ('sick_leave_continue', '=', True)], limit=1)
    #         inreval = (sick_leave_start, last_leave.date_to_date_format)
    #         intervals.append(inreval)
    #     for (interval_date_from, interval_date_to) in intervals:
    #         first_date = interval_date_from
    #         second_date = (
    #                 datetime.strptime(first_date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)).strftime(
    #             tools.DEFAULT_SERVER_DATE_FORMAT)
    #         date_str = interval_date_from
    #         date_dt = datetime.strptime(date_str, tools.DEFAULT_SERVER_DATE_FORMAT)
    #         while date_str <= interval_date_to:
    #             if date_str != first_date and date_str != second_date and date_str <= date_to:
    #                 if self.env['hr.employee'].is_work_day(date_str, self.id):
    #                     res += 1
    #             date_dt = date_dt + relativedelta(days=1)
    #             date_str = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
    #     return res

    # @api.multi
    # def write(self, vals):
    #     if 'main_accountant' in vals and not self.env.user.has_group('base.group_system'): # todo main_acc
    #         vals.pop('main_accountant')
    #     return super(HrEmployee, self).write(vals)

    @api.one
    def _compute_contract_id(self):
        """ get the lastest contract """
        date = self._context.get('date') or datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        strict_date_check = self._context.get('strict_date_check', False)
        self._cr.execute('''select id from hr_contract
                                        where employee_id = %s
                                        AND date_start <= %s
                                        ORDER BY date_start desc
                                        limit 1''', (self.id, date))
        res = self._cr.fetchall()
        if res and res[0]:
            self.contract_id = res[0][0]
        elif not strict_date_check:
            self.contract_id = self.sudo().env['hr.contract'].search([('employee_id', '=', self.id)],
                                                                     order='date_start desc', limit=1).id
        else:
            self.contract_id = False

    @api.one
    def _set_main_accountant(self):
        if self.main_accountant and self.env.user.has_group('base.group_system'):
            # self.sudo().company_id.findir = self.id
            pass

    @api.model
    def remove_sql_constraint(self):
        self._cr.execute('''ALTER TABLE hr_employee DROP CONSTRAINT hr_employee_identification_id_uniq;''')

    @api.model
    def create(self, vals):
        job_id = vals.get('job_id')
        saved_partner_vals = {key: vals.get(key) for key in ['zip', 'street', 'street2', 'state_id', 'country_id', 'city'] if vals.get(key)}
        if not vals.get('country_id', False):
            vals['country_id'] = self.env['res.country'].search([('code', '=', 'LT')], limit=1).id
        res = super(HrEmployee, self).create(vals)
        if not res.address_home_id:

            default_partner_vals = {
                'name': res.name,
                'customer': False,
                'supplier': True,
            }
            default_partner_vals.update(saved_partner_vals)
            if res.work_email:
                default_partner_vals['email'] = res.work_email
            if res.work_phone:
                default_partner_vals['phone'] = res.work_phone
            default_partner_vals['rezidentas'] = 'nerezidentas' if res.is_non_resident else 'rezidentas'
            default_partner_vals['skip_monthly_income_tax_report'] = res.skip_monthly_income_tax_report
            if self.env.user.is_hr_manager():
                default_partner = self.env['res.partner'].sudo().create(default_partner_vals)
            else:
                default_partner = self.env['res.partner'].create(default_partner_vals)
            res.address_home_id = default_partner.id

        # if not res.address_home_id and res.main_accountant and res.user_id:
        #     res.address_home_id = res.user_id.partner_id.id
        if job_id:
            res.write({'job_id': job_id})
        if not res.advance_accountancy_partner_id:
            res.advance_accountancy_partner_id = res.address_home_id.id
            # and not res.main_accountant and not self._context.get('dont_create_aa'):  # used in deeper
            # default_advance_accountancy_partner_vals = {'name': 'A.A. ' + res.name, 'advance_payment': True,
            #                                             'supplier': True, 'customer': False}
            # default_advance_partner = self.env['res.partner'].create(default_advance_accountancy_partner_vals)
            # res.advance_accountancy_partner_id = default_advance_partner.id
        return res

    @api.model
    def merge_advance_accountancy_partners(self):
        for employee in self.with_context(active_test=False).env['hr.employee'].search([('advance_accountancy_partner_id', '!=', False),
                                                                                        ('address_home_id', '!=', False)]):
            wiz_vals = {'partner_ids': [(4, employee.address_home_id.id), (4, employee.advance_accountancy_partner_id.id)],
                        'dst_partner_id': employee.address_home_id.id}
            wiz = self.env['base.partner.merge.automatic.wizard'].create(wiz_vals)
            wiz.with_context(ignore_partner_code_duplicates=True).action_merge()

    @api.onchange('seimos_nariai')
    def onchange_seimos_nariai(self):

        if self.seimos_nariai:
            nepilnameciai = 0
            for narys in self.seimos_nariai:
                if narys.seimos_narys == 'vaikas':
                    gimimo_data = narys.birthday
                    gimimo_data_ts = datetime.strptime(gimimo_data, tools.DEFAULT_SERVER_DATE_FORMAT)
                    if not is18(gimimo_data_ts):
                        nepilnameciai += 1
            self.children = nepilnameciai

    # Ranka sutvarkyti CRON vykdymo laika
    @api.model
    def cron_nepilnameciu_tikrinimas(self):
        for darbuotojas in self.env['hr.employee'].search([]):
            if darbuotojas.seimos_nariai:
                nepilnameciai = darbuotojas.children
                for narys in darbuotojas.seimos_nariai:
                    if narys.seimos_narys == 'vaikas' and narys.mokyklos_baigimas and not narys.nebesimoko and \
                            is18(datetime.strptime(narys.birthday, tools.DEFAULT_SERVER_DATE_FORMAT)):
                        data = narys.mokyklos_baigimas
                        data_ts = datetime.strptime(data, tools.DEFAULT_SERVER_DATE_FORMAT)
                        if data_ts < datetime.utcnow():
                            nepilnameciai -= 1
                            narys.nebesimoko = True

                darbuotojas.children = nepilnameciai

    @api.one
    @api.depends('current_leave_id')
    def onchange_leave_id(self):
        if self.current_leave_id:
            if self.current_leave_id.kodas in ['TA']:
                self.tevystes = True

    @api.onchange('sodra_id')
    def onchange_sodra_id(self):
        if self.sodra_id:
            sodra_id = remove_other(self.sodra_id)
            serija = remove_numbers(sodra_id)
            numeris = remove_letters(sodra_id)
            sodra = serija+numeris
            self.sodra_id = sodra

    @api.onchange('name', 'robo_access')
    def onchange_vardas(self):
        if not self._origin.id:
            if self.name and self.robo_access:
                name = self.name
                name = remove_accents(unicode(name))
                splitas = name.split(' ')
                if len(splitas) == 2:
                    domenas = ''
                    if self.company_id.email:
                        domenai = self.company_id.email.split('@')
                        if len(domenai) == 2:
                            domenas = '@' + domenai[1]
                    self.work_email = splitas[0].lower() + '.' + splitas[1].lower() + domenas

    @api.onchange('identification_id', 'country_id')
    def onchange_identification_id(self):
        if not self.country_id or self.country_id.code == 'LT':
            if self.identification_id:
                sid = remove_letters(self.identification_id)
                self.identification_id = sid
                if not correct_lithuanian_identification(sid):
                    raise exceptions.Warning(_('Neteisingas asmens kodas!'))
                if len(sid) != 11:
                    raise exceptions.Warning(_('Neteisingas asmens kodo ilgis!'))
                else:
                    lytis = sid[:1]
                    if lytis == '3' or lytis == '5':
                        self.gender = 'male'
                    elif lytis == '4'or lytis == '6':
                        self.gender = 'female'
                    else:
                        raise exceptions.Warning(_('Neteisingas asmens kodas!'))
                    gimimo_data = sid[1:-4]
                    metai = gimimo_data[:2]
                    if int(metai) <= int(str(datetime.utcnow().year)[-2:]):
                        metai = str(datetime.utcnow().year)[:2] + gimimo_data[:2]
                    else:
                        metai = str(int(str(datetime.utcnow().year)[:2])-1) + gimimo_data[:2]
                    menuo = gimimo_data[2:4]
                    diena = gimimo_data[-2:]
                    data_str = metai + '-' + menuo + '-' + diena
                    try:
                        data = datetime.strptime(data_str, '%Y-%m-%d')
                    except ValueError:
                        raise exceptions.Warning(_('Nurodytas neteisingas asmens kodas'))
                    self.birthday = data.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    def write(self, vals):
        if 'identification_id' in vals:
            sanitized_id = remove_letters(vals.get('identification_id', False))
            vals['identification_id'] = sanitized_id
        return super(HrEmployee, self).write(vals)

    @api.multi
    @api.constrains('identification_id', 'active')
    def constrain_unique_identification_id(self):
        for rec in self:
            if rec.active and rec.identification_id and self.env['hr.employee'].search_count([
                ('identification_id', '=', rec.identification_id),
                ('active', '=', True),
                ('id', '!=', rec.id)]
            ):
                raise exceptions.ValidationError(
                    _('Negali būti daugiau nei vienas darbuotojas su tuo pačiu asmens kodu!')
                )

    @api.multi
    @api.constrains('address_home_id')
    def _check_address_home_id(self):
        for rec in self:
            partner_is_already_related = self.env['hr.employee'].with_context(active_test=False).search_count([
                ('id', '!=', rec.id),
                ('address_home_id', '=', rec.address_home_id.id),
                ('address_home_id', '!=', False),
            ])
            if partner_is_already_related:
                raise exceptions.ValidationError(_('The partner is already related to an existing employee and can not '
                                                   'be related to multiple ones'))

    @api.multi
    def open_leaves_summary_wizard(self):
        action = self.env.ref('l10n_lt_payroll.action_leaves_report_simplified_wizard').read()[0]
        if len(self) == 1:
            action['context'] = {'active_id': self.id}
        return action

    @api.multi
    def _compute_leave_status(self):
        def update_employee_data(employee, leave_data, hide_reason=False):
            employee.leave_date_from = leave_data.get(employee.id, {}).get('leave_date_from')
            employee.leave_date_to = leave_data.get(employee.id, {}).get('leave_date_to')
            employee.current_leave_state = leave_data.get(employee.id, {}).get('current_leave_state')
            employee.current_leave_id = leave_data.get(employee.id, {}).get('current_leave_id')
            if hide_reason and employee.current_leave_id:
                employee.leave_text = _('Neatvykęs (-usi)')
            else:
                employee.leave_text = leave_data.get(employee.id, {}).get('leave_text', '')

        holiday_names = self.env['hr.holidays.report']._get_holiday_names()
        today = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        employee_holidays = self.env['hr.holidays'].sudo().search([('employee_id', 'in', self.ids),
                                                                   ('date_from', '<=', today),
                                                                   ('date_to', '>=', today),
                                                                   ('type', '=', 'remove'),
                                                                   ('state', 'not in', ('cancel', 'refuse'))])

        leave_data = {holiday.employee_id.id: {'leave_date_from': holiday.date_from,
                                               'leave_date_to': holiday.date_to,
                                               'current_leave_state': holiday.state,
                                               'current_leave_id': holiday.holiday_status_id.id,
                                               'leave_text': holiday_names.get(unicode(holiday.holiday_status_id.name),
                                                                               holiday.holiday_status_id.name),
                                               }
                      for holiday in employee_holidays}

        managers = self.env.ref('robo_basic.group_robo_premium_manager')
        hr_manager = self.env.ref('robo_basic.group_robo_hr_manager')
        user_groups = self.env.user.groups_id
        is_manager = managers in user_groups or hr_manager in user_groups

        if is_manager:
            for employee in self:
                update_employee_data(employee, leave_data)

        elif self.env.user.company_id.politika_neatvykimai == "own":
            for employee in self:
                if employee not in self.env.user.employee_ids:
                    continue
                update_employee_data(employee, leave_data)

        elif self.env.user.company_id.politika_neatvykimai == "department":
            dpt_id = self.env.user.employee_ids.department_id.id
            for employee in self:
                if employee.department_id.id != dpt_id:
                    continue
                update_employee_data(employee, leave_data, self.env.user.employee_ids.id != employee.id)

        elif self.env.user.company_id.politika_neatvykimai == "all":
            for employee in self:
                update_employee_data(employee, leave_data, self.env.user.employee_ids.id != employee.id)

    @api.multi
    def get_employee_leaves_num(self, date=None):
        """
        :param date: the date to calculate number of leaves for ; use current date if not provided
        :return: minimum leave days and extra leave days for work experience according to employee's contract
        calculated in work or calendar days
        """

        def _strp(_date):
            return datetime.strptime(_date, tools.DEFAULT_SERVER_DATE_FORMAT)

        self.ensure_one()

        if not date:
            date = datetime.utcnow().date()
        elif isinstance(date, basestring):
            date = _strp(date).date()

        # Check if active contract appointment exists
        active_appointment = self.with_context(date=date).appointment_id
        if not active_appointment:
            return 0, 0

        # Get company logic for extra holiday calculation. Default is 3 extra holidays for first 10
        # years and 1 extra day for every 5 years following that, as stated in the labour code
        ir_config_param = self.env['ir.config_parameter']
        initial_extra_holiday_period = int(ir_config_param.get_param('initial_extra_holiday_period', 10))
        initial_extra_holiday_count = float(ir_config_param.get_param('initial_extra_holiday_count', 3.0))
        repeating_extra_holiday_period = int(ir_config_param.get_param('repeating_extra_holiday_period', 5))
        repeating_extra_holiday_count = float(ir_config_param.get_param('repeating_extra_holiday_count', 1.0))
        company_extra_holiday_period = int(ir_config_param.get_param('company_extra_holiday_period', 0))
        company_extra_holiday_count = float(ir_config_param.get_param('company_extra_holiday_count', 0.0))

        # Calculate work_relation_start and work_relation_end
        employee_contracts = self.contract_ids.sorted(key=lambda c: c.date_start)
        work_relation_start = False
        work_relation_end = False
        for contract in employee_contracts:
            # First loop
            if not work_relation_start:
                work_relation_start = contract.date_start
                work_relation_end = contract.date_end
                continue

            # Has no end (ongoing contract)
            if not work_relation_end:
                break

            starts_next_day = _strp(contract.date_start) == _strp(work_relation_end) + relativedelta(days=1)
            if not starts_next_day:
                work_relation_start = contract.date_start

            # Work relation always end when current contract ends
            work_relation_end = contract.date_end

        # str -> datetime
        # set work relation end if wrong or does not exist
        if work_relation_end:
            work_relation_end = _strp(work_relation_end).date()
        if not work_relation_end or work_relation_end >= date:
            work_relation_end = date
        work_relation_start = _strp(work_relation_start).date()

        # The work relation has to still exist to this day
        if work_relation_end < date:
            return 0, 0

        # Calculate extra holidays
        extra_leave_days = 0
        date_from = work_relation_start
        date_from += relativedelta(years=initial_extra_holiday_period)
        if date_from < work_relation_end:
            extra_leave_days += initial_extra_holiday_count

        date_from += relativedelta(years=repeating_extra_holiday_period)
        while date_from < date:
            extra_leave_days += repeating_extra_holiday_count
            date_from += relativedelta(years=repeating_extra_holiday_period)

        if company_extra_holiday_period and company_extra_holiday_count:
            date_from = work_relation_start + relativedelta(years=company_extra_holiday_period)
            while date_from < date:
                extra_leave_days += company_extra_holiday_count
                date_from += relativedelta(years=company_extra_holiday_period)

        min_leave_days = self.env['hr.holidays'].get_employee_default_holiday_amount(job_id=active_appointment.job_id,
                                                                                     schedule_template=active_appointment.schedule_template_id,
                                                                                     employee_dob=self.birthday,
                                                                                     invalidumas=active_appointment.invalidumas)

        multiplier = 7.0 / 5.0 if active_appointment.leaves_accumulation_type == 'calendar_days' else 1  # P3:DivOK

        return min_leave_days * multiplier, extra_leave_days * multiplier

    @api.multi
    def print_vdu_report(self):
        self.ensure_one()
        action = self.env.ref('l10n_lt_payroll.action_open_vdu_report_wizard_history')
        res = action.read()[0]
        res['context'] = {'employee_ids': self.ids}
        return res


HrEmployee()


class HrContract(models.Model):

    _inherit = 'hr.contract'

    def _default_company_npd(self):
        return self.env.user.company_id.npd_max or 0.0

    rusis = fields.Selection(SUTARTIES_RUSYS, string='Sutarties rūšis', required=True, default='neterminuota', track_visibility='onchange') #TODO: or should we not allow change to it?

    override_taxes = fields.Boolean(string='Naudoti kitus mokesčius', default=False, sequence=100)
    sodra_papild_proc = fields.Float(string='Papildomų sodros įmokų dydis proc.')
    gpm_proc = fields.Float(string='Gyventojų pajamų mokesčio dydis proc.')
    gpm_ligos_proc = fields.Float(string='Gyventojų pajamų mokesčio ligų dydis proc.')
    darbuotojo_pensijos_proc = fields.Float(string='Darbuotojo mokami mokesčiai į pensijų fondą proc.')
    darbuotojo_sveikatos_proc = fields.Float(string='Darbuotojo mokamas sveikatos draudimas proc.')
    darbdavio_sodra_proc = fields.Float(string='Darbdavio sodros dydis proc.')
    npd_max = fields.Float(string='Maksimalus mėnesinių neapmokestinamų pajamų dydis', sequence=100)
    npd_0_25_max = fields.Float(string='Maksimalus mėnesinių neapmokestinamų pajamų 0-25% darbingumo dydis')
    npd_30_55_max = fields.Float(string='Maksimalus mėnesinių neapmokestinamų pajamų 30-55% darbingumo dydis')
    mma = fields.Float(string='Minimalus mėnesinis atlyginimas', sequence=100)
    mma_first_day_of_year = fields.Float(string='Minimalus mėnesinis atlyginimas pirmąją metų dieną', sequence=100)
    min_hourly_rate = fields.Float(string='Minimalus valandinis atlyginimas', sequence=100)
    npd_koeficientas = fields.Float(string='Koeficiento skaičiuojant pritaikomą NPD dydis (0.15)',
                                    help="npd=max_npd-kof*(alga-mma_first_day_of_year)", sequence=100)
    pnpd = fields.Float(string='Priverstinis PNPD', default=0.0, sequence=100)
    npd = fields.Float(string='Priverstinis NPD', inverse='_npd', default=_default_company_npd, sequence=100)
    effective_tax_rate_proc = fields.Float(string='Effective tax rate', compute='_effective_tax_rate_proc',
                                           store=True)
    effective_employer_tax_rate_proc = fields.Float(string='Effective employer tax rate',
                                                    compute='_effective_employer_tax_rate_proc')
    effective_employee_tax_rate_proc = fields.Float(string='Effective employee tax rate',
                                                    compute='_effective_employee_tax_rate_proc')
    effective_employee_tax_rate_proc_sodra = fields.Float(string='Effective employee sodra rate proc.',
                                                          compute='_effective_employee_tax_rate_proc_sodra')
    use_sodra_papild = fields.Boolean(help='Pažymėjus bus naudojama ši reikšmė, o ne nurodyta kompanijos nustatymuose')
    use_gpm = fields.Boolean(help='Pažymėjus bus naudojama ši reikšmė, o ne nurodyta kompanijos nustatymuose')
    use_ligos_gpm = fields.Boolean(help='Pažymėjus bus naudojama ši reikšmė, o ne nurodyta kompanijos nustatymuose')
    use_darbuotojo_pensijos = fields.Boolean(help='Pažymėjus bus naudojama ši reikšmė, o ne nurodyta kompanijos nustatymuose')
    use_darbuotojo_sveikatos = fields.Boolean(help='Pažymėjus bus naudojama ši reikšmė, o ne nurodyta kompanijos nustatymuose')
    use_darbdavio_sodra = fields.Boolean(help='Pažymėjus bus naudojama ši reikšmė, o ne nurodyta kompanijos nustatymuose')
    use_npd_max = fields.Boolean(help='Pažymėjus bus naudojama ši reikšmė, o ne nurodyta kompanijos nustatymuose')
    use_npd_0_25_max = fields.Boolean(help='Pažymėjus bus naudojama ši reikšmė, o ne nurodyta kompanijos nustatymuose')
    use_npd_30_55_max = fields.Boolean(help='Pažymėjus bus naudojama ši reikšmė, o ne nurodyta kompanijos nustatymuose')
    use_mma = fields.Boolean(help='Pažymėjus bus naudojama ši reikšmė, o ne nurodyta kompanijos nustatymuose')
    use_mma_first_day_of_year = fields.Boolean(help='Pažymėjus bus naudojama ši reikšmė, o ne nurodyta kompanijos nustatymuose')
    use_min_hourly_rate = fields.Boolean(help='Pažymėjus bus naudojama ši reikšmė, o ne nurodyta kompanijos nustatymuose')
    use_npd_koeficientas = fields.Boolean(help='Pažymėjus bus naudojama ši reikšmė, o ne nurodyta kompanijos nustatymuose')
    use_npd = fields.Boolean(help='Pažymėjus bus naudojama ši reikšmė, o ne nurodyta kompanijos nustatymuose')
    use_pnpd = fields.Boolean(help='Pažymėjus bus naudojama ši reikšmė, o ne nurodyta kompanijos nustatymuose')
    du_debit_account_id = fields.Many2one('account.account', string='Darbo užmokesčio išlaidų sąskaita')
    sodra_credit_account_id = fields.Many2one('account.account', domain=[('code', '=like', '4%')],
                                              string='SoDra account payable (from salary)')
    gpm_credit_account_id = fields.Many2one('account.account', domain=[('code', '=like', '4%')],
                                            string='GPM liabilities account')
    is_internship_contract = fields.Boolean(compute='_compute_is_internship_contract')

    @api.multi
    def _compute_is_internship_contract(self):
        for rec in self:
            rec.is_internship_contract = rec.rusis in ['voluntary_internship', 'educational_internship']

    @api.one
    def _npd(self):
        appointment = self.get_active_appointment()
        if appointment:
            use_npd = appointment.use_npd
            if not use_npd and not tools.float_is_zero(self.npd, precision_digits=2):
                self.npd = 0

    @api.multi
    def _effective_tax_rate_proc(self):
        for rec in self:
            rec.effective_tax_rate_proc = rec.effective_employer_tax_rate_proc + rec.effective_employee_tax_rate_proc

    @api.one
    def _effective_employer_tax_rate_proc(self):
        employer_taxes = ['darbdavio_sodra_proc']
        tax_rates = self.get_payroll_tax_rates(employer_taxes)
        self.effective_employer_tax_rate_proc = sum(map(float, tax_rates.values()))

    @api.one
    def _effective_employee_tax_rate_proc(self):
        employee_taxes = ['gpm_proc', 'darbuotojo_pensijos_proc', 'darbuotojo_sveikatos_proc']
        if self.appointment_id.sodra_papildomai:
            employee_taxes.append('sodra_papild_proc')
        tax_rates = self.get_payroll_tax_rates(employee_taxes)
        self.effective_employee_tax_rate_proc = sum(map(float, tax_rates.values()))

    @api.one
    def _effective_employee_tax_rate_proc_sodra(self):
        employee_taxes = ['darbuotojo_pensijos_proc', 'darbuotojo_sveikatos_proc']
        if self.appointment_id.sodra_papildomai:
            employee_taxes.append('sodra_papild_proc')
        tax_rates = self.get_payroll_tax_rates(employee_taxes)
        self.effective_employee_tax_rate_proc_sodra = sum(map(float, tax_rates.values()))

    @api.onchange('override_taxes')
    def define_own_taxes(self):
        attributes = [
            'sodra_papild_proc',
            'sodra_papild_exponential_proc',
            'gpm_proc',
            'gpm_ligos_proc',
            'darbuotojo_pensijos_proc',
            'darbuotojo_sveikatos_proc',
            'darbdavio_sodra_proc',
            'npd_max',
            'mma',
            'mma_first_day_of_year',
            'npd_koeficientas',
        ]
        if not self.override_taxes:
            for attr in attributes:
                setattr(self, attr, 0)
            self.npd = 0
        else:
            company = self.company_id or self.env.user.company_id
            if company:
                for attr in attributes:
                    setattr(self, attr, getattr(company, attr))
                self.npd = company.npd_max

    @api.multi
    @api.constrains('date_start', 'date_end', 'employee_id')
    def _check_no_overlap(self):
        for rec in self:
            domain = [
                ('employee_id', '=', rec.employee_id.id),
                ('id', '!=', rec.id),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', rec.date_start)
            ]
            if rec.date_end:
                domain += [('date_start', '<=', rec.date_end)]

            contracts = self.env['hr.contract'].search_count(domain)
            if contracts:
                raise exceptions.ValidationError(_('Negali būti aktyvi daugiau nei viena sutartis vienu metu.'))

    @api.multi
    def get_payroll_tax_rates(self, fields_to_get=None):
        if fields_to_get is None:
            fields_to_get = [
                'darbuotojo_pensijos_proc', 'darbuotojo_sveikatos_proc', 'darbdavio_sodra_proc', 'gpm_proc',
                'gpm_ligos_proc', 'npd_max', 'npd_30_55_max', 'npd_0_25_max', 'mma', 'mma_first_day_of_year',
                'npd_koeficientas', 'sodra_papild_proc', 'sodra_papild_exponential_proc', 'average_wage',
                'under_avg_wage_npd_coefficient', 'under_avg_wage_npd_max', 'under_avg_wage_minimum_wage_for_npd',
                'above_avg_wage_npd_coefficient', 'above_avg_wage_npd_max', 'above_avg_wage_minimum_wage_for_npd'
            ]
        if not self:
            company = self.env.user.company_id
            return {field_name: getattr(company, field_name) or 0.0 for field_name in fields_to_get}
        self.ensure_one()
        overriden_map = {
            'darbuotojo_pensijos_proc': 'use_darbuotojo_pensijos',
            'darbuotojo_sveikatos_proc': 'use_darbuotojo_sveikatos',
            'gpm_proc': 'use_gpm',
            'gpm_ligos_proc': 'use_ligos_gpm',
            'darbdavio_sodra_proc': 'use_darbdavio_sodra',
            'npd_max': 'use_npd_max',
            'npd_30_55_max': 'use_npd_30_55_max',
            'npd_0_25_max': 'use_npd_0_25_max',
            'mma': 'use_mma',
            'mma_first_day_of_year': 'use_mma_first_day_of_year',
            'npd_koeficientas': 'use_npd_koeficientas',
            'min_hourly_rate': 'use_min_hourly_rate',
            'sodra_papild_proc': 'use_sodra_papild',
            'pnpd': 'use_pnpd',
            'npd': 'use_npd',
        }
        company = self.with_context(employee_id=self.employee_id.id).company_id
        res = {}

        if self.override_taxes:
            npd_max_label = 'npd_max'
            override_all_npd_max_fields = False
            for field_name in fields_to_get:
                override_field_name = overriden_map.get(field_name, False)
                if not override_field_name:
                    use_employee_tax = False
                else:
                    use_employee_tax = getattr(self, override_field_name)
                if use_employee_tax:
                    if field_name == npd_max_label:
                        override_all_npd_max_fields = True
                    value = getattr(self, field_name)
                    res[field_name] = value or 0.0
                else:
                    value = getattr(company, field_name)
                    if field_name == 'darbdavio_sodra_proc' and self.is_fixed_term:
                        value += getattr(company, 'term_contract_additional_sodra_proc')
                    res[field_name] = value or 0.0

            # Override all related npd_max fields with the npd_max value. Fields such as under_avg_wage_npd_max etc.
            if override_all_npd_max_fields:
                npd_max_val = res.get(npd_max_label)
                for field_name in fields_to_get:
                    if not field_name[-len(npd_max_label):] == npd_max_label:  # Check if field name ends with 'npd_max'
                        continue
                    res[field_name] = npd_max_val
        else:
            for field_name in fields_to_get:
                value = getattr(company, field_name)
                # TODO: Should this float is zero check happen somewhere else? darbdavio_sodra_proc might be 0 due to
                #  the maximum reached SoDra ceiling
                if field_name == 'darbdavio_sodra_proc' and self.is_fixed_term and \
                        not float_is_zero(value, precision_digits=2):
                    value += getattr(company, 'term_contract_additional_sodra_proc')
                res[field_name] = value or 0.0
        return res

    @api.model
    def cron_archive_employees(self):
        def create_holiday_refusal_bug(exception_message):
            self.env['robo.bug'].sudo().create({
                'user_id': self.env.user.id,
                'error_message': exception_message,
            })
        archived_employees = self.env['hr.employee']
        archived_users = self.env['res.users']
        date_dt = datetime.utcnow()
        date = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        old_contract_ids = self.search([('date_end', '<', date),
                                        ('employee_id.active', '=', True),
                                        ('employee_id.type', '!=', 'mb_narys')])
        for contract_id in old_contract_ids:
            employee_id = contract_id.employee_id
            all_employee_active_contracts = self.search([('employee_id', '=', employee_id.id),
                                                          '|',
                                                            ('date_end', '=', False),
                                                            ('date_end', '>=', date)], count=True)
            if all_employee_active_contracts:
                continue
            if employee_id.user_id:
                to_archive = True
                if employee_id.related_user_archive_date:
                    archive_date_dt = datetime.strptime(employee_id.related_user_archive_date,
                                                        tools.DEFAULT_SERVER_DATE_FORMAT)
                    if date_dt < archive_date_dt:
                        to_archive = False
                if to_archive:
                    employee_id.user_id.write({
                        'active': False,
                    })
                    archived_users |= employee_id.user_id
            employee_id.write({
                'active': False,
            })
            employee_id.inform_accountant_about_work_relation_end_with_delegate_or_department_manager()
            archived_employees |= employee_id

            last_contract = self.search([('employee_id', '=', employee_id.id)], order='date_end desc', limit=1)
            if last_contract:
                date_end = last_contract.date_end
                holidays = self.env['hr.holidays'].search([('employee_id', '=', employee_id.id),
                                                           ('date_from', '>', date_end),
                                                           ('state', 'in', ['confirm', 'validate', 'validate1'])])
                self._cr.commit()
                for holiday in holidays:
                    try:
                        holiday.action_refuse()
                    except Exception as e:
                        self._cr.rollback()
                        msg = _('Failed to cancel holidays on archived employee %s. Error message: %s') % \
                              (employee_id.name, e.args[0] if e.args else e.message)
                        create_holiday_refusal_bug(msg)
                    finally:
                        self._cr.commit()
                intersecting_holidays = self.env['hr.holidays'].search([
                    ('employee_id', '=', employee_id.id),
                    ('date_from_date_format', '<=', date_end),
                    ('date_to_date_format', '>', date_end),
                    ('state', '=', 'validate')
                ])
                for holiday in intersecting_holidays:
                    try:
                        holiday.stop_in_the_middle(date_end)
                    except Exception as e:
                        # Should only break if it's a holiday that requires payment and the payment has already been
                        # reconciled.
                        self._cr.rollback()
                        msg = _('Failed to shorten holidays on archived employee %s. Error message: %s') % \
                              (employee_id.name, e.args[0] if e.args else e.message)
                        create_holiday_refusal_bug(msg)
                    finally:
                        self._cr.commit()

        # Check for users to archive
        employee_ids = self.env['hr.employee'].search([('active', '=', False), ('user_id.active', '=', True)])
        for emp_id in employee_ids.filtered(lambda x: x.user_id.id != SUPERUSER_ID):
            to_archive = True
            if emp_id.related_user_archive_date:
                archive_date_dt = datetime.strptime(emp_id.related_user_archive_date,
                                                    tools.DEFAULT_SERVER_DATE_FORMAT)
                if date_dt < archive_date_dt:
                    to_archive = False
            if to_archive:
                emp_id.user_id.write({
                    'active': False,
                })
                archived_users |= emp_id.user_id

        # Remove partners from mail.channels and default receivers if not linked to any other employee / user
        partners = archived_employees.mapped('address_home_id') + archived_users.mapped('partner_id')
        partners_to_remove = self.env['res.partner']
        for partner in partners:
            if self.env['hr.employee'].search_count([('active', '=', True), ('address_home_id', '=', partner.id)]):
                continue
            if self.env['res.users'].search_count([('active', '=', True), ('partner_id', '=', partner.id)]):
                continue
            partners_to_remove |= partner
        if partners_to_remove:
            self.env.user.company_id.write({'default_msg_receivers': [(3, p.id) for p in partners_to_remove]})
            partners_to_remove.write({'channel_ids': [(5,)]})

    @api.model
    def cron_force_new_jobs(self):
        employees = self.env['hr.employee'].search([('active', '=', True)])
        for employee in employees:
            employee.contract_id._compute_fields()
            employee._compute_job_id()


HrContract()


class ResUsers(models.Model):

    _inherit = 'res.users'

    main_accountant = fields.Boolean(string='Įmonės buhalteris', default=False, inverse='_set_main_accountant',
                                     groups='base.group_system', copy=False)
    substitute_accountant = fields.Boolean(string='Pavaduojantis buhalteris', default=False,
                                           inverse='_set_substitute_accountant', groups='base.group_system', copy=False)
    work_phone = fields.Char(string='Darbo telefonas', copy=False, groups='base.group_system')

    @api.multi
    def _set_main_accountant(self):
        if not self.env.user.has_group('base.group_system'):
            return
        for rec in self:
            if not rec.main_accountant:
                rec.adjust_accountant_mail_channels(subscribe=False)
                continue
            company = rec.sudo().company_id
            rec.adjust_accountant_mail_channels(subscribe=True)
            previous_accountant = self.with_context(active_test=False).search([
                ('id', '!=', rec.id),
                ('main_accountant', '=', True),
            ])
            if previous_accountant:
                previous_accountant.write({'main_accountant': False})
            company_vals = {'findir': rec.id}

            cashier_user = company.cashier_accountant_id.mapped('user_ids')
            if not rec.substitute_accountant and cashier_user and cashier_user[0].is_robo_user():
                company_vals['cashier_accountant_id'] = rec.partner_id.id
            company.write(company_vals)

    @api.multi
    def _set_substitute_accountant(self):
        if self.env.user.has_group('base.group_system'):
            self.filtered(lambda u: not u.main_accountant and not u.substitute_accountant).adjust_accountant_mail_channels(subscribe=False)

    @api.multi
    def write(self, vals):
        if 'main_accountant' in vals and not self.env.user.has_group('base.group_system'):
            vals.pop('main_accountant')
        return super(ResUsers, self).write(vals)

    @api.onchange('partner_id', 'login')
    def onchange_partner_id(self):
        context = dict(self._context or {})
        partneris = context.get('partner_id', False)
        email = context.get('email', False)
        if partneris:
            self.partner_id = partneris
        if email:
            self.login = email

    @api.model
    def get_accountant_mail_channel_ids(self):
        """
        Method to be overridden
        :return: Empty list
        """
        return []

    @api.multi
    def adjust_accountant_mail_channels(self, subscribe=False):
        """
        Add/remove accountants to/from mail channels
        :param subscribe: Indicates if accountants should be added to (True) or removed from (False) mail channels
        :return: None
        """
        accountant_mail_channel_ids = self.get_accountant_mail_channel_ids()
        channels = self.env['mail.channel'].search([('id', 'in', accountant_mail_channel_ids)])
        if subscribe:
            _logger.info('Subscribing users %s to the following channels: %s',
                         ', '.join(r.login for r in self if r.partner_id), ', '.join(channels.mapped('name')))
            channels.sudo().write({'channel_partner_ids': [(4, r.partner_id.id) for r in self if r.partner_id]})
        else:
            _logger.info('Unsubscribing users %s from the following channels: %s',
                         ', '.join(r.login for r in self if r.partner_id), ', '.join(channels.mapped('name')))
            channels.sudo().write({'channel_partner_ids': [(3, r.partner_id.id) for r in self if r.partner_id]})


ResUsers()


class HrPayslip(models.Model):

    _inherit = 'hr.payslip'

    @api.multi
    @api.constrains('date_from', 'date_to')
    def _tikrinti_datas(self):
        for run in self:
            if run.date_from:
                data_nuo = datetime.strptime(run.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                if data_nuo != datetime(data_nuo.year, data_nuo.month, 1):
                    raise exceptions.ValidationError(
                        _('Periodo pradžia ir pabaiga privalo būti pirma ir paskutinė mėnesio dienos!'))
            if run.date_to:
                data_iki = datetime.strptime(run.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_start = run.date_from
                if not date_start:
                    return
                data_nuo = datetime.strptime(run.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                if data_iki != datetime(data_nuo.year, data_nuo.month, calendar.monthrange(data_nuo.year, data_nuo.month)[1]):
                    raise exceptions.ValidationError(
                        _('Periodo pradžia ir pabaiga privalo būti pirma ir paskutinė mėnesio dienos!'))
        return True

    npd_nulis = fields.Boolean(string='NPD = 0', default=False, required=False, states={'verify': [('readonly', True)],
                                                                                    'done': [('readonly', True)]})
    ismoketi_kompensacija = fields.Boolean(string='Išmokėti sukauptų atostoginių kompensaciją',
                                           default=False, required=False, states={'verify': [('readonly', True)],
                                                                                  'done': [('readonly', True)]})
    pnpd_nulis = fields.Boolean(string='PNPD = 0', default=False, required=False, states={'verify': [('readonly', True)],
                                                                                      'done': [('readonly', True)]})
    vdu = fields.Float(string='VDU', compute='_vdu_previous', store=True, digits=(5, 2), group_operator='avg')

    vdu_previous = fields.Float(string='VDU (3 mėn.)', compute='_vdu_previous')

    vdu0 = fields.Float(string='VDU', compute='_vdu_previous', store=False, digits=(5, 2))
    atostogu_likutis = fields.Float(string='Nepanaudotų atostogų likutis periodo pabaigai', compute='_atostogu_likutis', digits=(16, 2), store=True, group_operator='avg')
    isskaitos_ids = fields.Many2many('hr.employee.isskaitos', string='Išskaitos')
    isskaitos_count = fields.Integer(string='Išskaitų skaičius', compute='_isskaitos_count')
    atostogu_praeita_menesi_amount = fields.Float(string='Atostogų suma praeitą mėnesį', compute='_atostogu_praeita_menesi_amount')
    contract_id = fields.Many2one('hr.contract', inverse='_set_holiday_payment_attributes')
    date_from = fields.Date(inverse='_set_holiday_payment_attributes')
    date_to = fields.Date(inverse='_set_holiday_payment_attributes')
    bruto = fields.Float(string='Bruto', compute='_bruto')
    neto = fields.Float(string='Netto', compute='_bruto')
    moketinas = fields.Float(string='Mokėtinas', compute='_bruto')

    # theor_bruto_in_other = fields.Float(compute='_theor_bruto_in_other')
    # theor_gpm_in_other = fields.Float(compute='_theor_bruto_in_other')
    bruto_for_reports = fields.Float(compute='_theor_bruto_in_other')
    neto_for_reports = fields.Float(compute='_theor_bruto_in_other')
    gpm_for_reports = fields.Float(compute='_theor_bruto_in_other')
    amount_paid = fields.Float(string='Išmokėta suma', compute='_amount_paid')
    amount_isskaitos = fields.Float(string='Išskaitos', compute='_amount_paid')
    neto_skirtumas = fields.Float(string='Neto Skirtumas', compute='_neto_diff', store=True)
    neto_5proc_skirtumas = fields.Boolean(string='Skiriasi 5%', compute='_neto_diff', default=False, invisible=True, store=True)
    neto_skirtumas_proc = fields.Float(string='Neto Skirtumas Procentais', compute='_neto_diff', store=True)
    pre_paid = fields.Boolean(string='Suformuotas pavedimas', readonly=True, lt_string='Suformuotas pavedimas')
    closed = fields.Boolean(string='Uždarytas iš suvestinės', readonly=True, default=False)
    payment_ids = fields.Many2many('mokejimu.eksportas')
    busy = fields.Boolean(string='Skaičiuojama', compute='_compute_busy')
    atostogu_likutis_based_on_contract_end = fields.Float(string='Nepanaudotų atostogų likutis periodo pabaigai', compute='_compute_atostogu_likutis_based_on_contract_end')
    # TODO Rename neto_bonuses_added to recompute_bonuses and inverse the checks/places where it is set
    neto_bonuses_added = fields.Boolean(default=True, readonly=True)
    payroll_id = fields.Many2one('hr.payroll', compute='_compute_payroll_id')
    holiday_accumulation_usage_policy = fields.Boolean(
        string='Use holiday accumulation and usage records when calculating holiday payments',
        default=lambda self: self.env.user.company_id.holiday_accumulation_usage_is_enabled
    )

    @api.one
    @api.depends('date_from', 'date_to')
    def _compute_busy(self):
        self.busy = self.payroll_id.busy

    @api.one
    @api.depends('date_from', 'date_to')
    def _compute_payroll_id(self):
        dt_from = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        HrPayroll = self.env['hr.payroll']
        payroll_id = HrPayroll.search([
            ('year', '=', dt_from.year),
            ('month', '=', dt_from.month),
        ], limit=1)
        if not payroll_id:
            payroll_id = HrPayroll.create({
                'year': dt_from.year,
                'month': dt_from.month
            })
        self.payroll_id = payroll_id

    @api.multi
    def form_transfer(self):
        self.ensure_one()
        if self.state != 'done' or self.pre_paid:
            raise exceptions.Warning(_('Algalapis jau turi suformuotą pavedimą arba yra nepatvirtintas!'))
        self.write({'pre_paid': True})
        pay_ids = self.env['hr.payslip.run'].with_context(slips=self,
                                                          return_ids=True,
                                                          date_from=self.date_from,
                                                          date_to=self.date_to).create_bank_statements()
        action = self.env.ref('mokejimu_eksportas.action_mokejimu_eksportas').read()[0]
        action['domain'] = [('id', 'in', pay_ids.ids)]
        return action

    @api.one
    @api.depends('contract_id', 'date_to', 'atostogu_likutis')
    def _compute_atostogu_likutis_based_on_contract_end(self):
        likutis = self.atostogu_likutis
        contract = self.contract_id.sudo()
        if self.date_to and contract:
            other_payslips = self.env['hr.payslip'].search([
                ('employee_id', '=', self.employee_id.id),
                ('date_to', '=', self.date_to),
                ('id', '!=', self.id)
            ])

            curr_slip_contract_ends = False
            if contract.date_end:
                curr_contract_end_dt = datetime.strptime(contract.date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_to_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
                curr_slip_contract_ends = curr_contract_end_dt.year == date_to_dt.year and curr_contract_end_dt.month == date_to_dt.month

            if not curr_slip_contract_ends and other_payslips and any(slip.ismoketi_kompensacija for slip in other_payslips):
                likutis = 0.0

        self.atostogu_likutis_based_on_contract_end = likutis

    @api.multi
    def unlink(self):
        if not self._context.get('ziniarastis_period_line_is_being_cancelled', False) and \
                any(rec.ziniarastis_period_line_id and rec.ziniarastis_period_line_id.state == 'done' for rec in self):
            raise exceptions.UserError(_('Negalima ištrinti algalapio, nes susijusi žiniaraščio eilutė yra patvirtinta'))
        return super(HrPayslip, self).unlink()

    @api.multi
    def cancel_payment(self):
        slips = self.mapped('payment_ids.slip_ids') or self
        slips.write({'pre_paid': False, 'closed': False})
        payments = self.mapped('payment_ids')
        for payment in payments:
            payment.atsaukti()
            payment.unlink()

    @api.model
    def server_action_cancel_payment_func(self):
        action = self.env.ref('l10n_lt_payroll.server_action_cancel_payment')
        if action:
            action.create_action()

    @api.onchange('contract_id', 'date_from', 'date_to', 'employee_id')
    def _should_use_favourable_sdd(self):
        if self.contract_id and self.contract_id.date_start and self.date_from:
            date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            contract_start_date = datetime.strptime(self.contract_id.date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
            self.use_favourable_sdd = True if date_from_dt == (contract_start_date + relativedelta(day=1)) and date_from_dt != contract_start_date else False
        if self.contract_id and self.contract_id.date_end and self.date_to and not self.use_favourable_sdd:
            date_to_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            contract_end_date = datetime.strptime(self.contract_id.date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
            self.use_favourable_sdd = True if contract_end_date <= date_to_dt else False

    @api.multi
    @api.depends('contract_id', 'struct_id', 'date_from', 'date_to', 'moketinas', 'contract_id.appointment_ids', 'contract_id.appointment_ids.neto_monthly', 'line_ids')
    def _neto_diff(self):
        contract_ids = self.mapped('contract_id.id')
        all_payslips = self.env['hr.payslip'].search([('contract_id', 'in', contract_ids)])
        all_appointments = self.env['hr.contract.appointment'].search([('contract_id', 'in', contract_ids)])
        for rec in self:
            if rec.struct_id.code == 'VAL':
                contract_payslips_before_current = all_payslips.filtered(lambda p: p.contract_id.id == rec.contract_id.id and p.date_to <= rec.date_from)
                prev_payslip_id = contract_payslips_before_current.sorted(lambda p: p.date_to, reverse=True)[0] if contract_payslips_before_current else False
                if prev_payslip_id:
                    neto_monthly = prev_payslip_id.moketinas
                    neto_skirtumas = rec.moketinas - neto_monthly
                else:
                    neto_monthly = 0
                    neto_skirtumas = 0
            else:
                try:
                    last_app = all_appointments.filtered(lambda a: a.contract_id.id == rec.contract_id.id and a.date_start <= rec.date_to).sorted(lambda a: a.date_start, reverse=True)[0]
                    neto_monthly = last_app.neto_monthly
                except:
                    neto_monthly = 0.0
                neto_skirtumas = rec.moketinas - neto_monthly
            if float_is_zero(neto_skirtumas, precision_digits=2):
                neto_skirtumas_proc = 0
            elif float_is_zero(neto_monthly, precision_digits=2) or float_is_zero(rec.moketinas, precision_digits=2):
                neto_skirtumas_proc = 100
            else:
                neto_skirtumas_proc = abs(neto_skirtumas / neto_monthly * 100)  # P3:DivOK
            if float_compare(neto_skirtumas_proc, 5, precision_digits=2) >= 0:
                rec.neto_5proc_skirtumas = True
            rec.neto_skirtumas = neto_skirtumas
            rec.neto_skirtumas_proc = neto_skirtumas_proc

    @api.one
    def _amount_paid(self):
        payable_account_id = self.env['account.account'].search([('code', '=', '4480')], limit=1)  # todo get from usual method
        partner_id = self.employee_id.address_home_id
        payable_amls = self.move_id.line_ids.filtered(lambda r: r.account_id == payable_account_id and r.partner_id == partner_id)
        allowance_payments = self.env['hr.employee.payment'].search([('employee_id', '=', self.employee_id.id), ('date_from', '=', self.date_from), ('type', '=', 'allowance')])
        allowance_payment_move_ids = allowance_payments.mapped('account_move_id') | allowance_payments.mapped('account_move_ids')
        allowance_payment_amls = allowance_payment_move_ids.mapped('line_ids').filtered(lambda r: r.account_id.reconcile)
        holidays_payments = self.env['hr.employee.payment'].search([
            ('employee_id', '=', self.employee_id.id),
            ('type', '=', 'holidays'),
            '|',
                '|',
                    '&',
                        ('date_from', '=', self.date_from),
                        '|',
                            '&',
                                ('account_move_id.line_ids.date', '<=', self.date_to),
                                ('account_move_id.line_ids.date', '>=', self.date_from),
                            '&',
                                ('account_move_ids.line_ids.date', '<=', self.date_to),
                                ('account_move_ids.line_ids.date', '>=', self.date_from),
                    '&',
                        ('date_from', '<', self.date_from),
                        ('holidays_ids.ismokejimas', '=', 'before_hand'),
                        ('payment_line_ids.date_from', '<=', self.date_to),
                        ('payment_line_ids.date_to', '>=', self.date_from),
                        '|',
                            '&',
                                ('account_move_id.date', '<=', self.date_to),
                                ('account_move_id.date', '>=', self.date_from),
                            '&',
                                ('account_move_ids.date', '<=', self.date_to),
                                ('account_move_ids.date', '>=', self.date_from),
        ])
        holidays_moves = holidays_payments.mapped('account_move_id') | holidays_payments.mapped('account_move_ids')
        holidays_move_lines = holidays_moves.filtered(lambda r: self.date_from <= r.date <= self.date_to).mapped('line_ids').filtered(lambda r: r.account_id == payable_account_id)
        payable_amls |= holidays_move_lines
        payable_amls |= allowance_payment_amls
        payable_amls_credit = payable_amls.filtered(lambda r: r.credit > 0)  # payable
        payable_amls_debit = payable_amls - payable_amls_credit  # sodra, etc.
        partial_reconciles = payable_amls_credit.mapped('matched_debit_ids')
        debits_reconciled_with = payable_amls_credit.mapped('matched_debit_ids.debit_move_id')
        # moves_reconciled_with = debits_reconciled_with.mapped('move_id')
        isskaitos = self.env['hr.employee.isskaitos'].search([('move_id', 'in', debits_reconciled_with.mapped('move_id.id'))])
        isskaitos_debits_reconciled_with = isskaitos.mapped('move_id.line_ids') & debits_reconciled_with
        paid_amount = sum(
            partial_reconciles.filtered(lambda r: r.debit_move_id not in payable_amls_debit|isskaitos_debits_reconciled_with).mapped('amount'))
        amount_isskaitos = sum(partial_reconciles.filtered(lambda r: r.debit_move_id in isskaitos_debits_reconciled_with).mapped('amount'))
        self.amount_paid = paid_amount
        self.amount_isskaitos = amount_isskaitos

    @api.model
    def message_get_reply_to(self, res_ids, default=None):
        records = self.browse(res_ids)
        return dict((record.id, self.env.user.email or default) for record in records)

    @api.one
    def _theor_bruto_in_other(self):
        neto_in_othr = sum(self.line_ids.filtered(lambda r:r.code in ['AM', 'AVN']).mapped('total'))
        bruto_oth, gpm_oth = self.contract_id.get_theoretical_bruto_gpm(neto_in_othr, self.date_to)
        # P3:DivOK
        gpm_proc = self.contract_id.with_context(date=self.date_to).get_payroll_tax_rates(['gpm_proc'])['gpm_proc'] / 100.0
        natura = sum(self.line_ids.filtered(lambda r: r.code in ['NTR']).mapped('total'))
        # self.theor_bruto_in_other = bruto_oth
        # self.theor_gpm_in_other = gpm_oth
        natur_gpm = natura * gpm_proc

        liga = sum(self.line_ids.filtered(lambda r: r.code in ['L']).mapped('total'))
        liga_gpm = liga * gpm_proc

        eff_bruto = sum(self.line_ids.filtered(lambda r: r.code in ['MEN', 'VAL']).mapped('total')) - bruto_oth - natura - liga
        eff_gpm = sum(self.line_ids.filtered(lambda r: r.code in ['GPM']).mapped('total')) - gpm_oth
        neto = sum(self.line_ids.filtered(lambda r: r.code in ['M']).mapped('total')) - sum(self.line_ids.filtered(lambda r: r.code in ['IŠSK']).mapped('total'))
        self.bruto_for_reports = eff_bruto
        self.gpm_for_reports = eff_gpm
        self.neto_for_reports = neto

    @api.one
    @api.depends('line_ids.amount', 'line_ids.code')
    def _bruto(self):
        self.bruto = sum(self.line_ids.filtered(lambda r: r.code in ['MEN', 'VAL']).mapped('amount'))
        self.neto = sum(self.line_ids.filtered(lambda r: r.code == 'NET').mapped('amount'))
        self.moketinas = sum(self.line_ids.filtered(lambda r: r.code in ['BENDM']).mapped('amount'))

    @api.multi
    def _set_holiday_payment_attributes(self):
        company = self.env.user.company_id
        for rec in self:
            contract = rec.contract_id
            employee = contract.employee_id
            holiday_accumulation_usage_policy = employee.holiday_accumulation_usage_policy or \
                                                company.with_context(date=rec.date_to).holiday_accumulation_usage_is_enabled
            if contract.date_end and rec.date_from <= contract.date_end <= rec.date_to:
                date_end_dt = datetime.strptime(contract.date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
                next_day = (date_end_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                next_contract = employee.contract_ids.filtered(lambda c: c.date_start == next_day)
                if not next_contract:
                    pay_compensation = True

                    # Don't pay compensation if the holiday balance is negative and a deduction for it exists.
                    holiday_balance = rec._get_adjusted_holiday_balance()
                    if tools.float_compare(holiday_balance, 0.0, precision_digits=2) < 0:
                        deduction_exists = self.env['hr.employee.isskaitos'].search_count([
                            ('employee_id', '=', rec.employee_id.id),
                            ('date', '=', contract.date_end),
                            ('state', '=', 'confirm'),
                            ('reason', '=', 'atostoginiai')
                        ])
                        if deduction_exists:
                            pay_compensation = False

                    rec.ismoketi_kompensacija = pay_compensation
            rec.holiday_accumulation_usage_policy = holiday_accumulation_usage_policy

    @api.one
    def _atostogu_praeita_menesi_amount(self):
        if not (self.date_from and self.employee_id):
            self.atostogu_praeita_menesi_amount = 0
            return
        employee = self.employee_id
        date = (datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.atostogu_praeita_menesi_amount = employee.get_vdu(date=date) * employee.with_context(date=date).remaining_leaves

    @api.one
    @api.depends('isskaitos_ids')
    def _isskaitos_count(self):
        self.isskaitos_count = len(self.isskaitos_ids)

    @api.model
    def refresh_info(self, employee_id, date):
        payslips = self.search([('employee_id', '=', employee_id),
                               ('date_from', '<=', date),
                               ('date_to', '>=', date),
                               ('state', '=', 'draft')])
        if len(payslips) > 1:
            payslips = payslips.filtered(lambda p: p.contract_id.date_start <= date and
                                                 (not p.contract_id.date_end or p.contract_id.date_end >= date))
        payslip = payslips and payslips[0]
        if payslip:
            payslip.refresh_inputs()
            payslip.write({'neto_bonuses_added': False})
            payslip.compute_sheet()

    @api.one
    def _vdu_previous(self):
        if self.date_from and self.date_to and self.employee_id:
            include_last = self.contract_id.ends_on_the_last_work_day_of_month and self.ismoketi_kompensacija and \
                           self._context.get('AK', False)

            contract_id = self.contract_id.id
            appointment_domain = [('employee_id', '=', self.employee_id.id)]
            dates_domain = [('date_start', '<=', self.date_from),
                            '|', ('date_end', '=', False),
                            ('date_end', '>=', self.date_from)]
            if contract_id:
                appointment_domain.append(('contract_id', '=', contract_id))
            appointment = self.env['hr.contract.appointment'].search(appointment_domain + dates_domain,
                                                                order='date_start desc', limit=1)
            if not appointment:
                appointment = self.env['hr.contract.appointment'].search(appointment_domain, order='date_start desc',
                                                                    limit=1)
            if self.struct_id.code == 'MEN' and not appointment.use_hours_for_wage_calculations:
                vdu_type = 'd'
            else:
                vdu_type = 'h'
            if self._context.get('vdu_type', False):
                vdu_type = self._context.get('vdu_type', False)
            vdu_date = self._context.get('forced_vdu_date') or self.date_from
            self.vdu = self.vdu_previous = get_vdu(self.env, vdu_date, self.employee_id,
                                                   contract_id=self.contract_id.id, include_last=include_last, vdu_type=vdu_type).get('vdu', 0.0)
            date_from_previous = (datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT) -
                                  relativedelta(months=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

            dates_domain = [('date_start', '<=', date_from_previous),
                            '|', ('date_end', '=', False),
                            ('date_end', '>=', date_from_previous)]
            appointment = self.env['hr.contract.appointment'].search(appointment_domain + dates_domain,
                                                                order='date_start desc', limit=1)
            if not appointment:
                appointment = self.env['hr.contract.appointment'].search(appointment_domain, order='date_start desc',
                                                                    limit=1)

            if self.struct_id.code == 'MEN' and not appointment.use_hours_for_wage_calculations:
                vdu_type = 'd'
            else:
                vdu_type = 'h'
            if self._context.get('vdu_type', False):
                vdu_type = self._context.get('vdu_type', False)
            self.vdu0 = get_vdu(self.env, date_from_previous, self.employee_id, contract_id=self.contract_id.id, vdu_type=vdu_type).get('vdu', 0.0)
        else:
            self.vdu = 0
            self.vdu0 = 0

    @api.one
    @api.depends('date_to', 'employee_id')
    def _atostogu_likutis(self):
        if self.employee_id and self.date_to and not self.imported:
            date_to_use = min(self.contract_id.date_end or self.date_to, self.date_to)
            self.atostogu_likutis = self.employee_id._get_remaining_days(
                date_to_use,
                accumulation_type=self.employee_id.with_context(date=date_to_use).leaves_accumulation_type
            )
        else:
            self.atostogu_likutis = 0.0

    @api.multi
    def _get_adjusted_holiday_balance(self):
        self.ensure_one()
        if self.imported or not self.employee_id or not self.date_to:
            return 0.0
        if not self.holiday_accumulation_usage_policy:
            return self.atostogu_likutis
        accumulation_records = self.env['hr.employee.holiday.accumulation'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('date_from', '>=', self.contract_id.work_relation_start_date),
            '|',
            ('date_to', '=', False),
            ('date_to', '<=', self.date_to)
        ], order='date_from desc')

        balance_date = self.date_to

        # Recompute holiday usages for holidays that are in between contract end
        if self.employee_is_being_laid_off:
            ending_contracts = self.contract_id.get_contracts_related_to_work_relation().filtered(
                lambda contract: contract.date_end
            )
            ending_contract = ending_contracts and ending_contracts[0]
            end_date = balance_date = ending_contract.date_end
            usages = accumulation_records.mapped('holiday_usage_line_ids.usage_id').filtered(
                lambda usage: usage.date_from <= end_date < usage.date_to
            )
            usages._recompute_holiday_usage()

        holiday_balance = 0.0
        for accumulation_record in accumulation_records:
            balance = accumulation_record.with_context(forced_date_to=balance_date).accumulation_work_day_balance
            holiday_balance += balance * accumulation_record.post
        if accumulation_records:
            today = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_calculated_up_to = accumulation_records[0].date_to or today
            if date_calculated_up_to < balance_date:
                date_from_dt = datetime.strptime(date_calculated_up_to, tools.DEFAULT_SERVER_DATE_FORMAT) + \
                               relativedelta(days=1)
                date_from = date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                holiday_balance += self.contract_id.get_leaves_accumulated_at_a_later_date(date_from, balance_date,
                                                                                           adjust_by_post=True)
        return holiday_balance

    @api.one
    @api.depends('date_from', 'date_to', 'employee_id')
    def _vdu(self):
        if self.date_from and self.date_to and self.employee_id:
            self.vdu = self.get_vdu_values()[self.id]['vdu']

    @api.onchange('date_from', 'date_to')
    def onchange_dates_constraint(self):
        if self.date_from:
            data_nuo = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            self.date_from = datetime(data_nuo.year, data_nuo.month, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        if self.date_to:
            data_iki = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            self.date_to = (datetime(data_iki.year, data_iki.month, 1)+relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    def atsaukti(self):
        for rec in self:
            if rec.pre_paid:
                raise exceptions.Warning(_('Negalite atšaukti algalapio kuriam suformuoti pavedimai!'))
            if rec.date_to <= '2017-08-31' and not self.env.user.has_group('base.group_system'):
                raise exceptions.Warning(_('Negalima atšaukti ankstesnių nei 2017-08-31 algalapių'))
            if rec.payslip_run_id and rec.payslip_run_id.state == 'close':
                raise exceptions.Warning(_('Negalima atšaukti algalapio, kurio suvestinė jau patvirtinta'))
            if rec.journal_id.update_posted:
                if rec.move_id:
                    rec.move_id.state = 'draft'
                    rec.move_id.line_ids.remove_move_reconcile()
                    rec.move_id.unlink()
                if rec.employer_benefit_in_kind_tax_move:
                    rec.employer_benefit_in_kind_tax_move.state = 'draft'
                    rec.employer_benefit_in_kind_tax_move.line_ids.remove_move_reconcile()
                    rec.employer_benefit_in_kind_tax_move.unlink()
                rec.state = 'cancel'
            else:
                raise exceptions.Warning(_('Negalima atšaukti jau patvirtinto algalapio. \nSpauskite grąžinti algalapį' +
                                         ' arba uždėkite varnelę žurnale "Leisti atšaukiančius įrašus".'))
            next_contract = False
            if rec.contract_id.date_end and rec.contract_id.date_end <= rec.date_to:
                next_contract_date = datetime.strptime(rec.contract_id.date_end,
                                                       tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)
                next_contract = self.env['hr.contract'].search([
                    ('employee_id', '=', rec.contract_id.employee_id.id),
                    ('date_start', '=', next_contract_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
                ])
            if rec.ismoketi_kompensacija and not next_contract:
                date_to_use = min(rec.contract_id.date_end or rec.date_to, rec.date_to)
                date_dt = datetime.strptime(date_to_use, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)
                date = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                # TODO Search for a holiday fix with 0 work days and 0 calendar days left?
                if rec.employee_id.with_context(date=date).leaves_accumulation_type == 'work_days':
                    accumulation_field = 'work_days_left'
                else:
                    accumulation_field = 'calendar_days_left'
                self.env['hr.holidays.fix'].search([
                    ('date', '=', date),
                    ('employee_id', '=', rec.employee_id.id),
                    '|',
                    ('type', '=', 'set'),
                    '&',
                    ('type', '=', 'add'),
                    (accumulation_field, '=', -rec.atostogu_likutis),
                ]).unlink()
            elif next_contract:
                # TODO Search for a holiday fix with 0 work days and 0 calendar days left?
                self.env['hr.holidays.fix'].search([
                    ('date', '=', next_contract_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)),
                    ('employee_id', '=', rec.employee_id.id),
                    ('type', '=', 'set'),
                ]).unlink()



    @api.multi
    def open_related_isskaitos(self):
        action = self.env.ref('l10n_lt_payroll.action_open_isskaitos')
        return {
            'name': action.name,
            'id': action.id,
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'hr.employee.isskaitos',
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', self.isskaitos_ids.ids)],
        }

    @api.onchange('contract_id')
    def onchange_contract(self):
        super(HrPayslip, self).onchange_contract()
        if not self.journal_id:
            self.journal_id = self.env.user.company_id.salary_journal_id.id

    @api.onchange('contract_id', 'date_from', 'date_to')
    def onchange_get_payments(self):
        if self.date_from and self.date_to and self.employee_id:
            payemnt_line_data = self.get_payslip_payments([self.contract_id.id], self.date_from, self.date_to)
            self.payment_line_ids.unlink()
            self.payment_line_ids = [(0, 0, x) for x in payemnt_line_data]

    @api.model
    def get_contract(self, employee, date_from, date_to):
        res = super(HrPayslip, self).get_contract(employee, date_from, date_to)
        if len(res) > 1:
            res = res[:1]
        return res

    @api.multi
    def print_payslip(self):
        self.ensure_one()
        if not self.env.user.is_manager() and not self.env.user.is_hr_manager():
            raise exceptions.AccessError(_('Negalite atlikti šio veiksmo.'))
        ctx = {
            'active_id': self.id,
            'active_ids': self.ids,
            'active_model': 'hr.payslip',
        }
        return self.env['report'].with_context(ctx).get_action(self, 'l10n_lt_payroll.report_algalapis_sl',
                                                               data={})

    @api.multi
    def print_payslip_note(self):
        self.ensure_one()
        if not self.env.user.is_manager() and not self.env.user.is_hr_manager() and not \
                (self.sudo().employee_id.user_id and self.sudo().employee_id.user_id.id == self.env.user.id):
            raise exceptions.AccessError(_('Negalite atlikti šio veiksmo.'))
        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'payslip.print.language.wizard',
            'context': {'payslip_id': self.id},
            'target': 'new',
        }



HrPayslip()


class ResCompany(models.Model):

    _inherit = 'res.company'

    vadovas = fields.Many2one('hr.employee', string='Vadovas', compute='_vadovas', inverse='_create_vadovas')
    findir = fields.Many2one('res.users', string='Vyr. finansininkas')

    @api.one
    def _create_vadovas(self):
        date = self._context.get('date', datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
        new_employee = self.vadovas
        curr_ceo_recs = self.env['res.company.ceo'].search([('date_from', '<=', date),
                                                            '|',
                                                                ('date_to', '=', False),
                                                                ('date_to', '>=', date)])
        if new_employee.id not in curr_ceo_recs.mapped('employee_id.id'):
            self.env['res.company.ceo'].create({'company_id': self.id,
                                                'employee_id': new_employee.id,
                                                'date_from': date,
                                                })

            curr_ceo_recs.mapped('employee_id').sudo().write({'robo_group': 'employee'})
            new_employee.sudo().write({'robo_group': 'manager'})
            channels = self.get_manager_mail_channels()
            manager = new_employee.user_id.partner_id
            if manager and channels:
                channels.write({'channel_partner_ids': [(4, manager.id)]})
        date_prev = (datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=-1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        curr_ceo_recs.filtered(lambda r: r.employee_id.id != new_employee.id).sudo().write({'date_to': date_prev})

    @api.one
    def _vadovas(self):
        date = self._context.get('date', datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
        self.vadovas = self.env['res.company.ceo'].get_ceo(date)

    @api.model
    def generate_res_company_ceo(self):
        for company in self.search([]):
            self.env['res.company.ceo'].create({'company_id': company.id,
                                                'employee_id': company.vadovas.id,
                                                'date_from': company.vadovas.contract_id.date_start,
                                                })


ResCompany()


class ResCompanyCeo(models.Model):
    _name = 'res.company.ceo'
    _description = 'Company Ceo by date'

    _order = 'date_from desc'

    def default_company_id(self):
        return self.env.ref('base.main_company')

    company_id = fields.Many2one('res.company', string='Kompanija', required=True, default=default_company_id)
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', required=True)
    date_from = fields.Date(string='Data nuo', required=True)
    date_to = fields.Date(string='Data iki')

    @api.model
    def get_ceo(self, date):
        rec = self.search([('date_from', '<=', date),
                           '|', ('date_to', '=', False),
                                ('date_to', '>=', date)], limit=1)
        if not rec:
            rec = self.search([], limit=1)
        return rec.employee_id


ResCompanyCeo()


class HrHolidaysStatus(models.Model):

    _inherit = 'hr.holidays.status'

    kodas = fields.Char(string='Kodas')
    komandiruotes = fields.Boolean(string='Komandiruotės', help='Savaitgaliai užsiskaičiuoja kaip darbo dienos',
                                   default=False)

    @api.onchange('komandiruotes')
    def onchange_komandiruotes(self):
        if self.komandiruotes:
            self.kodas = 'FD'


HrHolidaysStatus()


class HrPayslipRun(models.Model):
    _name = 'hr.payslip.run'
    _inherit = ['hr.payslip.run', 'mail.thread']

    _order = 'date_start DESC'

    def default_journal_id(self):
        return self.env.user.company_id.salary_journal_id

    state = fields.Selection(track_visibility='onchange')
    journal_id = fields.Many2one('account.journal', default=default_journal_id)
    account_move_id = fields.Many2one('account.move', string='Žurnalo įrašas', readonly=True)
    busy = fields.Boolean(string='Skaičiuojama', compute='_compute_busy')
    last_confirm_fail_message = fields.Char(string='Klaidos pranešimas')
    last_confirm_warning_message = fields.Char(string='Įspėjamasis pranešimas')
    payroll_id = fields.Many2one('hr.payroll', compute='_compute_payroll_id')
    business_trip_bank_statement = fields.Many2one(
        'account.bank.statement', string='Dienpinigių išmokėjimo banko išrašas', readonly=True)
    skip_payment_creation = fields.Boolean(string='Neformuoti mokėjimų', track_visibility='onchange')

    @api.one
    @api.depends('date_start', 'date_end')
    def _compute_busy(self):
        self.busy = self.payroll_id.busy

    @api.one
    @api.depends('date_start', 'date_end')
    def _compute_payroll_id(self):
        dt_from = datetime.strptime(self.date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
        HrPayroll = self.env['hr.payroll']
        payroll_id = HrPayroll.search([
            ('year', '=', dt_from.year),
            ('month', '=', dt_from.month),
        ], limit=1)
        if not payroll_id:
            payroll_id = HrPayroll.create({
                'year': dt_from.year,
                'month': dt_from.month
            })
        self.payroll_id = payroll_id

    @api.multi
    def button_export_run_xls(self):
        """
        Generate report, based on value stored in res.company determine
        whether to use threaded calculation or not
        :return: Result of specified method
        """
        if len(self) > 1:
            raise exceptions.Warning(_('Operacija negali būti atlikta keliems įrašams vienu metu'))

        if self.sudo().env.user.company_id.activate_threaded_front_reports:
            date_dt = datetime.strptime(self.date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
            filename = 'Algalapiai %s-%s.xls' % (date_dt.year, date_dt.month)
            report = 'Algalapių suvestinė'
            return self.env['robo.report.job'].generate_report(self, 'export_run_xls', report, returns='base64',
                                                               forced_name=filename, forced_extension='xls')
        else:
            return self.export_run_xls()

    @api.model
    def export_run_xls(self):
        slips = self.mapped('slip_ids')
        return slips.export_payslips()

    @api.model
    def payslip_run_export_xls_action(self):
        action = self.env.ref('l10n_lt_payroll.server_action_payslip_run_xls_export')
        if action:
            action.create_action()

    @api.model
    def cron_reserve_holiday_ticket(self):
        def create_ticket_for_accountant(text):
            ticket_obj = self.env['mail.thread'].sudo()._get_ticket_rpc_object()
            description = '''
                    <p>Sveiki,</p>
                    <p> {}
                    <br/>'''.format(text)
            vals = {
                'ticket_dbname': self.env.cr.dbname,
                'ticket_model_name': self._name,
                'ticket_record_id': self.id,
                'name': _('Sanity Check: Atostogų rezervas'),
                'description': description,
                'ticket_user_login': self.env.user.login,
                'ticket_user_name': self.env.user.name,
                'ticket_type': 'accounting',
                'user_posted': self.env.user.name
            }
            res = ticket_obj.create_ticket(**vals)
            if not res:
                raise exceptions.UserError('Failed to create holiday ticket for accountant')
            return res

        fails = []
        stop = False
        run = self.env['hr.payslip.run'].search([('state', '=', 'close')], order='date_start desc', limit=1)
        date = run.date_end
        if not date:
            return
        mapper = self.env['database.mapper'].search([('database', '=', self.env.cr.dbname)])
        if not mapper.active_client:
            return
            
        skip_dbs = ['kapitalis']
        if self.env.cr.dbname in skip_dbs:
            return
        day = datetime.utcnow().day
        if day not in [15, 16, 20]:
            return

        if not stop:
            employees = self.env['hr.contract'].with_context(active_test=False).search([
                ('date_start', '<=', date), '|', ('date_end', '>=', date)
            ]).mapped('employee_id')
            grand_total = 0.0
            edata = employees.get_holiday_reserve_info(date)
            for employee in employees:
                total = edata.get(employee.id, {}).get('total', 0.0)
                grand_total += total
                partner_id = employee.address_home_id
                saving_account_id = employee.department_id.atostoginiu_kaupiniai_account_id.id or \
                                    employee.company_id.atostoginiu_kaupiniai_account_id.id
                
                lines = self.env['account.move.line'].search([
                    ('date', '<=', date), ('account_id', '=', saving_account_id), ('partner_id', '=', partner_id.id)
                ])
                total2 = sum(lines.mapped('balance')) * -1
                diff = abs(total-total2)
                if tools.float_compare(diff, 10.0, precision_digits=2) > 0:
                    fails.append((employee.name, round(total, 2), round(total2, 2)))
            accounts = self.env.user.company_id.atostoginiu_kaupiniai_account_id + self.env['hr.department'].search([
                ('atostoginiu_kaupiniai_account_id', '!=', False)
            ]).mapped('atostoginiu_kaupiniai_account_id')
            lines = self.env['account.move.line'].search([
                ('date', '<=', date), ('account_id', 'in', accounts.ids)
            ])
            grand_total2 = sum(lines.mapped('balance')) * -1
            diff_total = abs(grand_total-grand_total2)
            if tools.float_compare(diff_total, 10.0, precision_digits=2) > 0:
                fails.append(('Bendra suma', round(grand_total, 2), round(grand_total2, 2)))

        if fails:
            begin_table = lambda headers: '<table border="1"><tr>' + ''.join('<td><b>%s</b></td>' % str(h) for h in headers) + '</tr>'
            add_row = lambda line: '<tr>' + ''.join('<td>%s</td>' % str(l) for l in line) + '</tr>'
            end_table = lambda: '</table>'
            result_details = '''<p>Šių darbuotojų atostogų rezervas (%s) nesutampa:</p>''' % date
            result_details += begin_table(['Detalizacija', 'Teorinis rezervas', 'Apskaitos duomenys'])
            for fail in fails:
                result_details += add_row([fail[0], fail[1], fail[2]])
            result_details += end_table()
            result_details += '''<p>Perskaičiuoti rezervus galima atšaukus ir vėl uždarius atlyginimų suvestinę.</p>'''
            create_ticket_for_accountant(result_details)
            return {}

    def format_transfers_wizard(self):
        if self.busy:
            raise exceptions.Warning(_('Negalite atlikti šio veiksmo kol skaičiuojami algalapiai.'))
        wizard = self.env['hr.payslip.run.transfers.wizard'].create({'parent_id': self.id})
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.payslip.run.transfers.wizard',
            'view_id': self.env.ref('l10n_lt_payroll.payslip_form_transfers_wizard').id,
            'res_id': wizard.id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.onchange('date_start')
    def onchange_date_start(self):
        if self.date_start:
            data_nuo = datetime.strptime(self.date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
            if data_nuo != datetime(data_nuo.year, data_nuo.month, 1):
                raise exceptions.Warning(_('Periodo pradžia privalo būti mėnesio pirmoji diena'))

    @api.onchange('date_end')
    def onchange_date_end(self):
        if self.date_end:
            data_iki = datetime.strptime(self.date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_start = self.date_start
            if not date_start:
                return False
            data_nuo = datetime.strptime(self.date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
            if data_iki != datetime(data_nuo.year, data_nuo.month, calendar.monthrange(data_nuo.year, data_nuo.month)[1]):
                raise exceptions.Warning(_('Periodo pabaiga privalo būti to paties mėnesio paskutinė diena'))

    @api.multi
    @api.constrains('date_start', 'date_end')
    def _tikrinti_datas(self):
        for run in self:
            if run.date_start:
                data_nuo = datetime.strptime(run.date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
                if data_nuo != datetime(data_nuo.year, data_nuo.month, 1):
                    raise exceptions.ValidationError(
                        _('Periodo pradžia ir pabaiga privalo būti pirma ir paskutinė mėnesio dienos!'))
            if run.date_end:
                data_iki = datetime.strptime(run.date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_start = run.date_start
                if not date_start:
                    return True
                data_nuo = datetime.strptime(run.date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
                if data_iki != datetime(data_nuo.year, data_nuo.month, calendar.monthrange(data_nuo.year, data_nuo.month)[1]):
                    raise exceptions.ValidationError(
                        _('Periodo pradžia ir pabaiga privalo būti pirma ir paskutinė mėnesio dienos!'))
        return True

    @api.multi
    def form_business_trip_payments(self):
        if self._context.get('slips', False):
            slips = self._context.get('slips', False)
        else:
            slips = self.mapped('slip_ids') if self else False

        if not slips:
            return

        if not self:
            self = slips.mapped('payslip_run_id')
        for rec in self:
            business_trip_statement = rec.business_trip_bank_statement
            front_statements = business_trip_statement.front_statements
            viewed_front_statements = front_statements.filtered(lambda s: s.state == 'viewed')
            other_front_statements = front_statements.filtered(lambda s: s.state != 'viewed')
            other_front_statements.unlink()
            if not viewed_front_statements and business_trip_statement.state != 'confirm':
                business_trip_statement.unlink()
            else:
                continue

            # Filter done slips where employees get paid by bank transfer only
            payslips = slips.filtered(lambda r: r.state == 'done' and r.payslip_run_id.id == rec.id and not r.employee_id.pay_salary_in_cash)

            business_trips = self.env['hr.holidays'].search([
                ('employee_id', 'in', payslips.mapped('contract_id.employee_id.id')),
                ('state', '=', 'validate'),
                ('holiday_status_id.kodas', '=', 'K'),
                ('date_from_date_format', '>=', rec.date_start),
                ('date_from_date_format', '<=', rec.date_end),
                ('allowance_payout', '=', 'with_salary_payment'),
                ('payment_id', '!=', False)
            ])
            payments = business_trips.mapped('payment_id')
            move_lines = payments.mapped('account_move_id.line_ids') + payments.mapped('account_move_ids.line_ids')
            move_lines = move_lines.filtered(lambda l: (not l.currency_id and float_compare(l.amount_residual, 0.0, precision_rounding=0.01) < 0) or
                          l.currency_id and float_compare(l.amount_residual_currency, 0.0, precision_rounding=0.01) < 0)
            if move_lines and not tools.float_is_zero(sum(move_lines.mapped('bank_export_residual')), precision_digits=2):
                wizard_data = move_lines.call_multiple_invoice_export_wizard()
                wizard_id = wizard_data.get('res_id', False)
                if wizard_id:
                    wizard = self.env['account.invoice.export.wizard'].browse(wizard_id)
                    wizard.write({'journal_id': self.env.ref('base.main_company').payroll_bank_journal_id.id})
                    bank_statement_data = wizard.create_bank_statement()
                    bank_statement_id = bank_statement_data.get('res_id', False)
                    if bank_statement_id:
                        date_dt = datetime.strptime(rec.date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
                        bank_statement = self.env['account.bank.statement'].browse(bank_statement_id)
                        rec.business_trip_bank_statement = bank_statement
                        month_title = kas_to_ko(MONTH_TO_STRING_MAPPING.get(date_dt.month, str(date_dt.month)).decode('utf8'))
                        bank_statement.write({
                            'name': _('Dienpinigiai už {0} metų {1} mėnesį').format(date_dt.year, month_title)
                        })
                        bank_statement.show_front()

    @api.multi
    def create_bank_statements(self):
        if len(self) > 1:  # ensure_one crashes on empty set
            raise exceptions.Warning(_('Ši operacija negalima keliems įrašams'))
        if self._context.get('slips', False):
            slips = self._context.get('slips')
        else:
            slips = self.slip_ids
        closed = self._context.get('closed', False)
        self.form_business_trip_payments()
        company = self.env.user.company_id
        wage_accounts = slips.mapped('employee_id.department_id.saskaita_kreditas') | company.saskaita_kreditas
        gpm_accounts = slips.mapped('employee_id.department_id.saskaita_gpm') | \
                       slips.mapped('contract_id.gpm_credit_account_id') | company.saskaita_gpm
        sodra_accounts = slips.mapped('employee_id.department_id.saskaita_sodra') | \
                         slips.mapped('contract_id.sodra_credit_account_id') | company.saskaita_sodra
        payment_export_obj = self.env['mokejimu.eksportas']
        bank_journal = company.payroll_bank_journal_id
        bank_journal_id = company.payroll_bank_journal_id.id
        date_start = self.date_start or self._context.get('date_from', False)
        date_end = self.date_end or self._context.get('date_to', False)
        if not date_start or not date_end:
            raise exceptions.Warning(_('Nerastos datos formuojant mokėjimą'))
        date = datetime.strptime(date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
        year, month = date.year, date.month
        year = str(year)
        month = str(month) if month >= 10 else '0' + str(month)
        payment_ids = self.env['mokejimu.eksportas']
        if not bank_journal_id:
            raise exceptions.UserError(_('Nenurodytas su DU susijęs banko žurnalas'))
        # Filter done slips where employees get paid by bank transfer only
        payslips = slips.filtered(lambda r: r.state == 'done' and not r.employee_id.pay_salary_in_cash)
        partner_ids = slips.filtered(lambda r: not r.employee_id.pay_salary_in_cash).mapped('employee_id.address_home_id')
        potential_account_move_lines = payslips.mapped('move_id.line_ids').filtered(
            lambda r: r.account_id.reconcile and not r.reconciled)

        for wage_account in wage_accounts:
            account_move_line_ids = potential_account_move_lines.filtered(
                lambda r: r.account_id == wage_account and r.amount_residual != 0.0).ids
            if account_move_line_ids:
                if not closed:
                    name = _('Atlyginimo mokėjimas %s-%s (%s)') % (year, month, str(datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)))
                else:
                    name = _('Atlyginimo mokėjimas %s-%s') % (year, month)
                date_end_dt = datetime.strptime(date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
                search_date_from = (date_end_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                search_date_end = (date_end_dt + relativedelta(days=company.salary_payment_day)).strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT)

                # Prepare line data
                line_data = {
                    'name': name,
                    'account_ids': wage_account.ids,
                    'account_move_line_ids': account_move_line_ids,
                    'slip_ids': payslips.ids,
                    'include_holidays': True,
                    'partner_ids': partner_ids.ids,
                }

                rec = payment_export_obj.with_context(
                    search_in_range=(search_date_from, search_date_end)).create_statement(
                    date_start, date_end, bank_journal_id, line_data
                )
                if rec:
                    payment_ids += rec
        # Filter all done slips
        payslips = slips.filtered(lambda r: r.state == 'done')
        partner_ids = slips.mapped('employee_id.address_home_id')
        potential_account_move_lines_all = self.slip_ids.filtered(lambda r: r.state == 'done').mapped(
            'move_id.line_ids').filtered(
            lambda r: r.account_id.reconcile and not r.reconciled)

        for gpm_account in gpm_accounts:
            gpm_move_lines = potential_account_move_lines_all.filtered(
                lambda r: r.account_id == gpm_account and r.amount_residual != 0.0)
            account_move_line_ids = potential_account_move_lines_all.filtered(
                lambda r: r.account_id == gpm_account and r.amount_residual != 0.0).ids
            if account_move_line_ids and float_compare(-sum(gpm_move_lines.mapped('amount_residual')), 10.0,
                                                       precision_rounding=bank_journal.currency_id.rounding or self.env.user.company_id.currency_id.rounding) >= 0:
                if not closed:
                    name = _('GPM mokėjimas %s-%s (%s)') % (year, month, str(datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)))
                else:
                    name = _('GPM mokėjimas %s-%s') % (year, month)

                # Prepare line data
                line_data = {
                    'name': name,
                    'account_ids': gpm_account.ids,
                    'account_move_line_ids': account_move_line_ids,
                    'slip_ids': payslips.ids,
                    'partner_ids': partner_ids.ids,  # Partner IDs is redefined several times
                }

                rec = payment_export_obj.create_statement(date_start, date_end, bank_journal_id, line_data)
                if rec:
                    payment_ids += rec

        if closed:
            for sodra_account in sodra_accounts:
                account_move_line_ids = potential_account_move_lines_all.filtered(
                    lambda r: r.account_id == sodra_account and r.amount_residual != 0.0).ids
                if account_move_line_ids:
                    name = _('Sodros mokėjimas %s-%s') % (year, month)

                    # Prepare line data
                    line_data = {
                        'name': name,
                        'account_ids': sodra_account.ids,
                        'account_move_line_ids': account_move_line_ids,
                        'slip_ids': payslips.ids,
                        'partner_ids': partner_ids.ids,
                    }

                    rec = payment_export_obj.create_statement(date_start, date_end, bank_journal_id, line_data)
                    if rec:
                        payment_ids += rec
            for deduction_account in slips.mapped('isskaitos_ids.account_id'):
                deduction_move_lines = payslips.mapped('isskaitos_ids.move_id.line_ids').filtered(
                    lambda p: p.account_id == deduction_account and p.amount_residual != 0.0
                )
                partner_ids = deduction_move_lines.mapped('partner_id').ids
                if deduction_move_lines:
                    name = _('Išskaitos %s-%s') % (year, month)

                    line_data = {
                        'name': name,
                        'account_ids': deduction_account.ids,
                        'account_move_line_ids': deduction_move_lines.ids,
                        'partner_ids': partner_ids,
                        'force_split': True,
                    }

                    rec = payment_export_obj.create_statement(date_start, date_end, bank_journal_id, line_data)
                    if rec:
                        payment_ids += rec

        if self._context.get('return_ids', False):
            return payment_ids

    @api.multi
    def close_payslip_run(self):
        if any(state != 'done' for state in self.mapped('slip_ids.state')):
            raise exceptions.UserError(_('Negalite atlikti šio veiksmo, nes yra nepatvirtintų algalapių.'))
        if any(self.mapped('busy')) and not self._context.get('automatic_payroll', False):
            raise exceptions.UserError(_('Negalite atlikti šio veiksmo kol skaičiuojami algalapiai.'))
        if any(run.state != 'draft' for run in self):
            raise exceptions.UserError(_('Negalite atlikti šio veiksmo, perkraukite puslapį'))

        self.mapped('payroll_id').write({
            'busy': True,
            'partial_calculations_running': True,
            'stage': 'payslip_run',
        })
        self._cr.commit()
        if self._context.get('no_thread'):
            self.close_thread()
        else:
            threaded_calculation = threading.Thread(target=self.close_thread)
            threaded_calculation.start()

    @api.one
    def _create_holiday_fix(self):
        if self._context.get('slips', False):
            slips = self._context.get('slips')
        else:
            slips = self.slip_ids
        for payslip in slips.filtered(lambda s: s.ismoketi_kompensacija and s.state == 'done'):
            date_dt = datetime.strptime(payslip.date_to, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)
            date = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            # TODO Search for a holiday fix with 0 work days and 0 calendar days left?
            if not self.env['hr.holidays.fix'].search([
                ('date', '=', date),
                ('employee_id', '=', payslip.employee_id.id),
                ('type', '=', 'set'),
            ], limit=1):
                self.env['hr.holidays.fix'].create({
                    'employee_id': payslip.employee_id.id,
                    'date': date,
                    'calendar_days_left': 0.0,
                })

    @api.multi
    def create_accumulated_holidays_reserve_entry(self):
        """
        Create holiday obligation reserve for the payslip batch
        :return: account.move record
        """
        self.ensure_one()
        payslips = self._context.get('slips') or self.slip_ids
        move = payslips.create_accumulated_holidays_reserve_entry(date=self.date_end)
        return move

    @api.multi
    def check_holiday_reserve_entries(self):
        """
         Checks that all former employees have 0 amount on holiday reserve at the end of the payslip batch 
        :return: a dict with hr.payslip.run id as key, and recordset of hr.employee with with non-zero balance as value
        """
        res = {}
        for rec in self:
            date_to = rec.date_end
            date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_back = (date_to_dt - relativedelta(months=3)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            # Check only the contracts that have ended in the last 3 months and the employee is archived or all the
            # ones that have ended and the employee is still active.
            contracts = self.env['hr.contract'].search([
                '|',
                '&',
                ('date_end', '>', date_back),
                '&',
                ('date_end', '<=', date_to),
                ('employee_id.active', '=', False),
                '&',
                ('date_end', '<=', date_to),
                ('employee_id.active', '=', True),
            ])
            employees = contracts.mapped('employee_id')
            error_employees = self.env['hr.employee']
            for employee in employees:
                domain = [('employee_id', '=', employee.id), '|', ('date_end', '>', date_to), ('date_end', '=', False)]
                if self.env['hr.contract'].search_count(domain):
                    continue
                account_id = employee.department_id.atostoginiu_kaupiniai_account_id.id or employee.company_id.atostoginiu_kaupiniai_account_id.id
                balance = employee.get_aml_balance_by_account(account_id, date_to)

                if not tools.float_is_zero(balance, precision_digits=2):
                    error_employees |= employee
            if error_employees:
                message = 'Šie darbuotojai nebedirba datai %s, bet jų atostogų likutis nėra nulis:\n' % rec.date_end
                message += ', '.join(error_employees.mapped('name'))
                rec.message_post(subtype='mt_comment', body=message)
                warn = rec.last_confirm_warning_message or ''
                rec.write({'last_confirm_warning_message': warn + ('\n' if warn else '') + message})
            res[rec.id] = error_employees
        return res

    @api.multi
    def create_atostoginiu_kaupiniu_irasas(self):
        for rec in self:
            rec.account_move_id.button_cancel()
            rec.account_move_id.unlink()
            move_ids = rec.create_accumulated_holidays_reserve_entry()
            rec.account_move_id = move_ids
        self.check_holiday_reserve_entries()

    @api.multi
    def button_cancel(self):
        if self.payroll_id.busy:
            raise exceptions.Warning(_('Negalite atlikti šio veiksmo kol skaičiuojami algalapiai.'))
        if self.state == 'close':
            slips = self.mapped('slip_ids').filtered(lambda x: x.closed)
            slips.cancel_payment()
        else:
            slips = self.mapped('slip_ids').filtered(lambda x: not x.pre_paid)
        slips.atsaukti()
        self.draft_payslip_run()

    @api.multi
    def draft_payslip_run(self):
        for rec in self:
            if rec.payroll_id.busy:
                raise exceptions.Warning(_('Negalite atlikti šio veiksmo kol skaičiuojami algalapiai.'))
            # if rec.state != 'close':
            #     raise exceptions.Warning(_('Negalite atlikti šio veiksmo, perkraukite puslapį'))
            rec.account_move_id.button_cancel()
            rec.account_move_id.unlink()
            slip_ids = rec.slip_ids.filtered(lambda x: x.closed)
            slip_ids.cancel_payment()
        super(HrPayslipRun, self).draft_payslip_run()

    @api.multi
    def open_journal_entries(self):
        action = self.env.ref('account.action_move_journal_line')
        return {
            'id': action.id,
            'name': action.name,
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.move',
            # 'view_id': False,
            'target': 'self',
            'domain': [('id', 'in', self.account_move_id.ids)],
        }

    @api.multi
    def patvirtinti_visus(self):
        if self.payroll_id.busy:
            raise exceptions.Warning(_('Negalite atlikti šio veiksmo kol skaičiuojami algalapiai.'))
        self.ensure_one()
        self.payroll_id.write({
            'busy': True,
            'partial_calculations_running': True,
            'stage': 'payslip',
        })
        self._cr.commit()
        threaded_calculation = threading.Thread(target=self.confirm_all_thread, kwargs={'slip_ids': self.mapped('slip_ids')})
        threaded_calculation.start()

    @api.multi
    def confirm_all_thread(self, slip_ids):
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, odoo.SUPERUSER_ID, {'lang': 'lt_LT'})
            slips = env['hr.payslip'].browse(slip_ids.ids)
            runs = slips.mapped('payslip_run_id')
            try:
                runs.write({'last_confirm_fail_message': False})
                for slip in slips:
                    if slip.state not in ['done']:
                        slip.action_payslip_done()
            except Exception as exc:
                new_cr.rollback()
                exception_arguments = exc.args
                error_message = exception_arguments and exception_arguments[0]
                if error_message:
                    runs.write({
                        'last_confirm_fail_message': _('Algalapių užvėrimas nepavyko, klaidos pranešimas: {}').format(
                            error_message
                        )
                    })
                run = runs and runs[0]
                run.send_bug('Background thread failed | Confirm all payslips | run id: %s | error msg: %s' %
                             (str(run.id), str(exception_arguments)))
            finally:
                slips.mapped('payroll_id').write({
                    'busy': False,
                    'partial_calculations_running': False,
                    'stage': False,
                })
                new_cr.commit()
                new_cr.close()

    @api.multi
    def close_thread(self):
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, odoo.SUPERUSER_ID, {'lang': 'lt_LT'})
            runs = env['hr.payslip.run'].browse(self.ids)
            try:
                for rec in runs.sorted('date_start'):
                    slips = rec.slip_ids.filtered(lambda x: not x.pre_paid)
                    slips.write({'pre_paid': True, 'closed': True})
                    employees_paid_by_cash = slips.filtered(lambda r: r.employee_id.pay_salary_in_cash).mapped('employee_id')
                    if employees_paid_by_cash:
                        empl_list = ', '.join(employees_paid_by_cash.mapped('name'))
                        rec.write({'last_confirm_warning_message': _('Šiems darbuotojams nebuvo sukurti mokėjimai, nes jiems darbo užmokestis yra mokamas grynais: %s') % str(
                                           empl_list)})
                    else:
                        rec.write({'last_confirm_warning_message': False})
                    if not rec.skip_payment_creation:
                        rec.with_context(slips=slips, closed=True).create_bank_statements()
                    rec.with_context(slips=slips)._create_holiday_fix()
                    rec.create_atostoginiu_kaupiniu_irasas()
                runs.recompute_later_holiday_reserve()
            except Exception as exc:
                import traceback
                new_cr.rollback()
                _logger.info('Background thread failed | close payslip run | ids: %s | error: %s \nTraceback: %s' %
                             (str(runs.ids), tools.ustr(exc), traceback.format_exc()))
                runs.write({'last_confirm_fail_message': _('Algalapio užvėrimas nepavyko, klaidos pranešimas: %s') % tools.ustr(exc)})
            else:
                runs.write({
                    'state': 'close',
                    'last_confirm_fail_message': False,
                })

            runs.mapped('payroll_id').write({
                'busy': False,
                'partial_calculations_running': False,
                'stage': False,
            })
            new_cr.commit()
            new_cr.close()

    @api.multi
    def recompute_later_holiday_reserve(self):
        if not self:
            return
        date_min = min(self.mapped('date_start'))
        later_runs = self.env['hr.payslip.run'].search([('state', '=', 'close'),
                                                        ('date_start', '>', date_min)], order='date_start ASC')
        later_runs_not_done = later_runs - self
        if later_runs_not_done:
            date_min = later_runs_not_done[0].date_start
            for run in later_runs_not_done.filtered(lambda r: r.date_start >= date_min):
                run.cancel_holiday_reserve()
                run.create_atostoginiu_kaupiniu_irasas()

    @api.multi
    def cancel_holiday_reserve(self):
        for rec in self:
            rec.account_move_id.button_cancel()
            rec.account_move_id.unlink()

    @api.multi
    def unlink(self):
        if any(rec.payroll_id.busy for rec in self):
            raise exceptions.Warning(_('Negalite atlikti šio veiksmo kol skaičiuojami algalapiai.'))
        self.mapped('slip_ids').unlink()
        return super(HrPayslipRun, self).unlink()

    @api.multi
    def spausdinti_algalapius(self):

        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.payslip.run.payslip.print',
            'view_id': self.env.ref('l10n_lt_payroll.hr_payslip_run_payslip_print_view_form').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': {'default_payslip_run_id': self.id},
        }

    @api.multi
    def send_bug(self, msg):
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'error_message': msg,
        })


HrPayslipRun()


class HrPayslipRunTransfersWizard(models.TransientModel):
    _name = 'hr.payslip.run.transfers.wizard'

    parent_id = fields.Many2one('hr.payslip.run')
    payslip_ids = fields.Many2many('hr.payslip', string='Algalapiai')

    def form_transfers(self):
        if not self.payslip_ids:
            raise exceptions.Warning(_('Pasirinkite bent vieną algalapį!'))
        self.payslip_ids.write({'pre_paid': True})
        self.parent_id.with_context(slips=self.payslip_ids).create_bank_statements()


HrPayslipRunTransfersWizard()


class MokejimuEksportas(models.Model):

    _inherit = 'mokejimu.eksportas'

    slip_ids = fields.Many2many('hr.payslip')

    @api.model
    def create_statement(self, date_from, date_to, journal_id, data=None):

        # Sanitize default args
        data = data if data else {}

        # Get values from passed data set
        name = data.get('name')
        partner_ids = data.get('partner_ids')
        account_ids = data.get('account_ids')
        account_move_line_ids = data.get('account_move_line_ids')
        slip_ids = data.get('slip_ids')
        include_holidays = data.get('include_holidays')
        show_front = data.get('show_front')
        structured_payment_ref = data.get('structured_payment_ref')
        if not self._context.get('skip_payment_reconciliation'):
            self.auto_reconcile_everything(date_to)
        vals = {'data_nuo': date_from,
                'data_iki': date_to,
                'journal_id': journal_id,
                'structured_payment_ref': structured_payment_ref}
        partner_ids = partner_ids or []
        account_ids = account_ids or []
        if slip_ids is not None:
            vals['slip_ids'] = [(6, 0, slip_ids)]
        if partner_ids:
            vals['partneriai'] = [(6, 0, partner_ids)]
        if account_ids:
            vals['saskaitos'] = [(6, 0, account_ids)]
        if account_move_line_ids:
            vals['eilutes'] = [(6, 0, account_move_line_ids)]
            if 'search_in_range' in self._context:
                search_date_from, search_date_to = self._context['search_in_range']
                account_move_lines = self.env['account.move.line'].search([('partner_id', 'in', partner_ids),
                                                                           ('account_id', 'in', account_ids),
                                                                           ('date_maturity', '>=', search_date_from),
                                                                           ('date_maturity', '<=', search_date_to),
                                                                           ('reconciled', '=', False)])
                vals['eilutes'] += [(4, aml.id,) for aml in account_move_lines]
        else:
            account_move_lines = self.env['account.move.line'].search([('partner_id', 'in', partner_ids),
                                                                       ('account_id', 'in', account_ids),
                                                                       ('date_maturity', '>=', date_from),
                                                                       ('date_maturity', '<=', date_to),
                                                                       ('reconciled', '=', False)])
            vals['eilutes'] = [(6, 0, account_move_lines.ids)]
        if name:
            vals['name'] = name
        if include_holidays:
            date_from = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(day=1)
            date_to = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(day=15, months=1)
            holiday_lines = self.env['hr.holidays'].search([
                ('date_from_date_format', '<=', date_to),
                ('date_to_date_format', '>=', date_from),
                ('ismokejimas', '=', 'before_hand'),
                ('employee_id.address_home_id', 'in', partner_ids)
            ]).mapped('payment_id.account_move_ids.line_ids').filtered(
                lambda l: not l.reconciled and l.move_id.state == 'posted'
                          and not l.eksportuota and l.account_id.reconcile and l.account_id.id in account_ids)
            if holiday_lines:
                extra_names = set(holiday_lines.mapped('name'))
                vals['name'] += ', ' + ', '.join(extra_names)
                vals['eilutes'] += [(4, aml.id,) for aml in holiday_lines]
        export_rec = self.create(vals)
        export_rec.with_context(force_split=data.get('force_split')).patvirtinti()
        if show_front:
            # If we receive show front flag, we also always
            # try to send the payment to bank (from this part of the code)
            export_rec.bank_statement.with_context(auto_send_to_bank=True).show_front()
        if self._context.get('return_ids'):
            return export_rec

    @api.model
    def auto_reconcile_everything(self, date_to):
        partner_ids = self.env['hr.employee'].search([]).mapped('address_home_id.id')
        move_lines = self.env['account.move.line'].search([('reconciled', '=', False),
                                                           ('move_id.state', '=', 'posted'),
                                                           '|',
                                                               ('partner_id', 'in', partner_ids),
                                                               ('account_id.structured_code', '!=', False),
                                                           ('account_id.reconcile', '=', True),
                                                           ('account_id.code', '=ilike', '448%'),
                                                           ('date', '<=', date_to)])
        accounts = move_lines.mapped('account_id')
        for account in accounts:
            acc_move_lines = move_lines.filtered(lambda r: r.account_id == account)
            relevant_partners = acc_move_lines.mapped('partner_id')
            for partner in relevant_partners:
                lines_to_reconcile = acc_move_lines.filtered(lambda r: r.partner_id == partner)
                vmi = partner.kodas == '188659752'
                lines_to_reconcile.with_context(skip_full_reconcile_check=vmi, check_move_validity=False).auto_reconcile_lines_v2()

    # @api.model
    # def cron_auto_create_statements(self, date=None):
    #     if date is None:
    #         date_dt = datetime.now()
    #     else:
    #         date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
    #     date_from = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
    #     date_to_dt = date_dt
    #     while date_to_dt.weekday() in (5, 6) or self.env['sistema.iseigines'].search([('date', '=', date_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))]):
    #         date_to_dt += timedelta(days=1)
    #     amls_to_pay = self.env['account.move.line'].search([('move_id.state', '=', 'posted'),
    #                                                         ('account_id.reconcile', '=', True),
    #                                                         ('amount_residual', '<', 0),
    #                                                         ('date_maturity', '<=', date_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)),
    #                                                         '|', ('invoice_id', '=', False),
    #                                                              ('invoice_id.exported_sepa', '=', False)]).filtered(lambda r: float_compare(r.amount_residual, 0, precision_digits=2) < 0)
    #     employee_partner_ids = self.env['hr.employee'].search([]).mapped('address_home_id.id')
    #     gpm_account = self.env.user.company_id.saskaita_gpm
    #     amount_gpm = sum(amls_to_pay.filtered(lambda r: r.account_id == gpm_account).mapped('amount_residual'))
    #     if amount_gpm < 10.0:  #TODO:where does that 10.0 value come from ? Should it be a setting ?
    #         amls_to_pay = amls_to_pay.filtered(lambda r: r.account_id != gpm_account)
    #     amls_not_employee = amls_to_pay.filtered(lambda r: r.partner_id.id not in employee_partner_ids)
    #     payment_export_obj = self.env['mokejimu.eksportas']
    #     account_ids = amls_not_employee.mapped('account_id.id')
    #     bank_journal_id = self.env['account.journal'].search([('type', '=', 'bank'), ('display_on_footer', '=', True)], limit=1).id
    #     if bank_journal_id:
    #         payment_export_obj.create_statement(date_from, date_from, bank_journal_id, name=None,
    #                                             partner_ids=amls_not_employee.mapped('partner_id.id'),
    #                                             account_ids=account_ids,
    #                                             account_move_line_ids=amls_not_employee.ids)
    #         amls_employee = amls_to_pay - amls_not_employee
    #         account_ids = amls_employee.mapped('account_id.id')
    #         payment_export_obj.create_statement(date_from, date_from, bank_journal_id, name=None,
    #                                             partner_ids=amls_employee.mapped('partner_id.id'),
    #                                             account_ids=account_ids,
    #                                             account_move_line_ids=amls_employee.ids)
    #         amls_to_pay.mapped('invoice_id').write({'exported_sepa': True})


MokejimuEksportas()


class HrPayslipWorkedDays(models.Model):

    _inherit = 'hr.payslip.worked_days'

    amount = fields.Float(string='Amount', compute='_amount', store=False, readonly=True, default=0.0)

    @api.multi
    def _amount(self):
        for rec in self:
            if rec.code != 'L':
                rec.amount = 0.0
                continue
            payslip = payslip_id = rec.payslip_id
            employee = payslip.employee_id
            contract = payslip.contract_id
            date_to = min(payslip_id.date_to, contract.date_end or payslip_id.date_to)
            date_from = max(payslip_id.date_from, contract.date_start)
            date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_from_dt_corrected = date_from_dt - relativedelta(months=1)
            koeficientas = payslip.company_id.with_context(date=payslip.date_to).ligos_koeficientas
            amount = 0.0
            pholidays = self.env['hr.holidays'].search([
                ('date_from_date_format', '>=', date_from_dt_corrected.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)),
                ('date_from_date_format', '<=', date_to),
                ('type', '=', 'remove'),
                ('employee_id', '=', employee.id),
                ('state', '=', 'validate'),
                ('holiday_status_id.kodas', '=', 'L'),
                ('sick_leave_continue', '=', False),
                '|',
                ('on_probation', '=', False),
                ('date_to_date_format', '>=', PROBATION_LAW_CHANGE_DATE),
            ])
            intervals = []
            for sick_leave in pholidays:
                continuation_from = (datetime.strptime(sick_leave.date_to_date_format, tools.DEFAULT_SERVER_DATE_FORMAT) + timedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                continuation = self.env['hr.holidays'].search(
                    [('date_from_date_format', '=', continuation_from),
                     ('type', '=', 'remove'),
                     ('employee_id', '=', employee.id),
                     ('state', '=', 'validate'),
                     ('holiday_status_id.kodas', '=', 'L'),
                     ('sick_leave_continue', '=', True)], limit=1)
                if continuation:
                    # two days are paid so so we don't need to look at other continuations
                    inreval = (sick_leave.date_from_date_format, continuation.date_to_date_format)
                else:
                    inreval = (sick_leave.date_from_date_format, sick_leave.date_to_date_format)
                intervals.append(inreval)
            intervals = [r for r in intervals if r[1] >= date_from]
            for (date_from, date_to) in intervals:
                first_date = date_from
                second_date = (datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                potential_dates = [first_date, second_date]
                total_days_current_month = 0
                total_days_previous_month = 0
                first_day_previous_month = first_day_this_month = None
                for date in potential_dates:
                    # Skip dates where the employee is on probation before the probation period law change date
                    related_holiday = pholidays.filtered(
                        lambda h: h.date_from_date_format <= date <= h.date_to_date_format
                    )
                    if related_holiday and related_holiday.on_probation and date < PROBATION_LAW_CHANGE_DATE:
                        continue
                    if self.env['hr.employee'].is_work_day(date, employee.id, contract_id=contract.id) and date <= date_to:
                        if date < payslip.date_from:
                            total_days_previous_month += 1
                            if not first_day_previous_month:
                                first_day_previous_month = date
                        elif date <= payslip.date_to:
                            total_days_current_month += 1
                            if not first_day_this_month:
                                first_day_this_month = date

                if total_days_previous_month == 0 and total_days_current_month > 0:
                    vdu = payslip_id.with_context(vdu_type='d', forced_vdu_date=first_day_this_month).vdu_previous
                elif total_days_previous_month > 0 and total_days_current_month > 0:
                    vdu = payslip_id.with_context(vdu_type='d', forced_vdu_date=first_day_previous_month).vdu0
                else:
                    vdu = 0.0

                pay_per_day = max(koeficientas * vdu, 0.0)
                amount += tools.float_round(pay_per_day * total_days_current_month, precision_digits=2)
            rec.amount = amount


HrPayslipWorkedDays()


class SeimyninePadetis(models.Model):

    _name = 'seimynine.padetis'

    name = fields.Char(string='Pavadinimas', required=True)
    pnpd_uz_vaika = fields.Float(string='PNPD už vieną vaiką', required=True)
    employee = fields.One2many('hr.employee', 'seimynine_padetis')


SeimyninePadetis()


# class Darbingumas(models.Model):
#
#     _name = 'darbuotojo.darbingumas'
#
#     name = fields.Char(string='Pavadinimas', required=True)
#     npd = fields.Float(string='Neapmokestinamų pajamų dydis', required=True)
#     # employee = fields.One2many('hr.employee', 'darbingumas')
#     #TODO ADD TYPE AND SCRIPT
#
# Darbingumas()


class Darbingumas(models.Model):

    _name = 'darbuotojo.darbingumas'

    name = fields.Selection([('0_25', '0% - 25%'), ('30_55', '30% - 55%')], string='Pavadinimas', required=True)
    npd = fields.Float(string='Neapmokestinamų pajamų dydis', compute='_npd')

    @api.one
    def _npd(self):
        company = self.env.user.company_id
        if self.name == '0_25':
            self.npd = company.get_historical_field_value(self._context.get('date'), 'npd_0_25_max') if self._context.get('date', False) else getattr(company, 'npd_0_25_max')
        elif self.name == '30_55':
            self.npd = company.get_historical_field_value(self._context.get('date'), 'npd_30_55_max') if self._context.get('date',False) else getattr(company, 'npd_30_55_max')


Darbingumas()


class ResPartner(models.Model):

    _inherit = 'res.partner'

    is_employee = fields.Boolean(string='Yra darbuotojas', store=True, compute='_is_employee')
    is_active_employee = fields.Boolean(string='Yra aktyvus darbuotojas', store=True, compute='_is_employee')
    employee_ids = fields.One2many('hr.employee', 'address_home_id', string='Employee')
    rezidentas = fields.Selection([('rezidentas', 'Rezidentas'), ('nerezidentas', 'Ne rezidentas')],
                                  default='rezidentas', inverse='_set_rezidentas', groups='account.group_account_manager')
    skip_monthly_income_tax_report = fields.Boolean("Don't include in the monthly income tax report",
                                                    groups='account.group_account_manager',
                                                    inverse='_set_skip_monthly_income_tax_report')
    email = fields.Char(required=False)
    advance_payment = fields.Boolean(string='Atskaitingas asmuo', default=False, copy=False)

    @api.depends('employee_ids', 'employee_ids.active')
    def _is_employee(self):
        for rec in self:
            employee_ids = rec.with_context(active_test=False).employee_ids
            active_employee_ids = employee_ids.filtered(lambda e: e.active)
            rec.is_employee = True if employee_ids else False
            rec.is_active_employee = True if active_employee_ids else False

    def _set_rezidentas(self):
        if not self.env.user.has_group('account.group_account_manager'):
            return
        for rec in self:
            employees = rec.with_context(active_test=False).employee_ids
            non_resident = rec.rezidentas == 'nerezidentas'
            for employee in employees:
                if employee.is_non_resident != non_resident:
                    employee.write({
                        'is_non_resident': non_resident
                    })

    def _set_skip_monthly_income_tax_report(self):
        for rec in self:
            employees = rec.with_context(active_test=False).employee_ids
            skip_report = rec.skip_monthly_income_tax_report
            employees = employees.filtered(lambda e: e.skip_monthly_income_tax_report != skip_report)
            employees.write({'skip_monthly_income_tax_report': skip_report})


ResPartner()


class HrPayslipEmployees(models.TransientModel):

    _inherit = 'hr.payslip.employees'

    @api.multi
    def compute_sheet(self):
        payslips = self.env['hr.payslip']
        [data] = self.read()
        active_id = self.env.context.get('active_id')
        if active_id:
            [run_data] = self.env['hr.payslip.run'].browse(active_id).read(['date_start', 'date_end', 'credit_note'])
        from_date = run_data.get('date_start')
        to_date = run_data.get('date_end')
        if not data['employee_ids']:
            raise exceptions.UserError(_('Turite pasirinkti bent vieną darbuotoją, kad galėtumėte sukurti algalapius.'))
        for employee in self.env['hr.employee'].browse(data['employee_ids']):
            slip_data = self.env['hr.payslip'].onchange_employee_id(from_date, to_date, employee.id, contract_id=False)
            res = {
                'employee_id': employee.id,
                'name': slip_data['value'].get('name'),
                'struct_id': slip_data['value'].get('struct_id'),
                'contract_id': slip_data['value'].get('contract_id'),
                'payslip_run_id': active_id,
                'input_line_ids': [(0, 0, x) for x in slip_data['value'].get('input_line_ids')],
                'worked_days_line_ids': [(0, 0, x) for x in slip_data['value'].get('worked_days_line_ids')],
                'isskaitos_ids': slip_data['value'].get('isskaitos_ids', []),
                'payment_line_ids': [(0, 0, x) for x in slip_data['value'].get('payment_line_ids')],
                'date_from': from_date,
                'date_to': to_date,
                'credit_note': run_data.get('credit_note'),
            }
            payslips += self.env['hr.payslip'].create(res)
        for slip in payslips:
            slip.compute_sheet()
        return {'type': 'ir.actions.act_window_close'}


HrPayslipEmployees()


class HrHolidaysPaymentLine(models.Model):

    _name = 'hr.holidays.payment.line'

    holiday_id = fields.Many2one('hr.holidays', string='Atostogos', required=True)
    amount = fields.Float(string='Suma')
    vdu = fields.Float(string='VDU')
    num_work_days = fields.Float(string='Darbo dienos')
    holiday_coefficient = fields.Float(string='Holiday coefficient')
    period_date_from = fields.Date(string='Periodo data nuo', help='Pirma mėnesio diena', required=True)
    period_date_to = fields.Date(string='Periodo data iki', help='Paskutinė mėnesio diena', required=True)

    amount_recomputed = fields.Float(string='Suma*', compute='_compute_amounts_based_on_system')
    vdu_recomputed = fields.Float(string='VDU*', compute='_compute_amounts_based_on_system')
    num_work_days_recomputed = fields.Float(string='Darbo dienos*', compute='_compute_amounts_based_on_system')
    holiday_coefficient_recomputed = fields.Float(string='Holiday coefficient*',
                                                  compute='_compute_amounts_based_on_system')

    recomputed_values_match = fields.Boolean(string='Parametrai paskaičiuoti pagal sistemą sutampa su įrašu',
                                             compute='_compute_recomputed_values_match')

    @api.multi
    @api.depends('period_date_from', 'period_date_to', 'holiday_id.type', 'holiday_id.holiday_status_id',
                 'holiday_id.date_vdu_calc', 'holiday_id.date_from_date_format',
                 'holiday_id.employee_id.holiday_coefficient', 'holiday_id.holiday_accumulation_usage_policy')
    def _compute_recomputed_values_match(self):
        for rec in self:
            match = True
            if rec.holiday_id.show_allocated_payments:
                rec = rec.with_prefetch()
                amounts_match = tools.float_compare(rec.amount, rec.amount_recomputed, precision_digits=2) == 0
                vdu_match = tools.float_compare(rec.vdu, rec.vdu_recomputed, precision_digits=2) == 0
                num_work_days_match = tools.float_compare(
                    rec.num_work_days, rec.num_work_days_recomputed, precision_digits=2
                ) == 0
                holiday_coefficient_match = tools.float_compare(
                    rec.holiday_coefficient, rec.holiday_coefficient_recomputed, precision_digits=2
                ) == 0
                match = amounts_match and vdu_match and num_work_days_match and holiday_coefficient_match
            rec.recomputed_values_match = match

    @api.multi
    @api.depends('period_date_from', 'period_date_to', 'holiday_id.type', 'holiday_id.holiday_status_id',
                 'holiday_id.date_vdu_calc', 'holiday_id.date_from_date_format',
                 'holiday_id.employee_id.holiday_coefficient', 'holiday_id.holiday_accumulation_usage_policy')
    def _compute_amounts_based_on_system(self):
        for rec in self:
            holiday = rec.holiday_id
            if not holiday.show_allocated_payments or not holiday.filtered(lambda h: h.id):
                continue
            dt_from = max(rec.period_date_from, holiday.date_from)
            dt_to = min(rec.period_date_to, holiday.date_to)
            vdu_date = holiday.date_vdu_calc or holiday.date_from_date_format
            amount_bruto, vdu, num_work_days = holiday.with_context(
                period_date_from=dt_from, period_date_to=dt_to, vdu_date=vdu_date).get_holiday_pay_data()
            holiday_coefficient = 1.0  #self.holiday_id.employee_id.sudo().holiday_coefficient or 1.0
            rec.holiday_coefficient_recomputed = holiday_coefficient
            rec.amount_recomputed = amount_bruto
            rec.vdu_recomputed = vdu
            rec.num_work_days_recomputed = num_work_days


HrHolidaysPaymentLine()


class HolidaysChangeWizard(models.TransientModel):

    _name = 'holidays.change.wizard'

    def default_holiday_id(self):
        active_ids = self._context.get('active_ids', [])
        if len(active_ids) == 0:
            raise exceptions.Warning(_('Reikia pasirinkti bent vieną įrašą'))
        elif len(active_ids) > 1:
            raise exceptions.Warning(_('Reikia pasirinkti lygiai vieną įrašą'))
        holidays = self.env['hr.holidays'].browse(active_ids)
        if holidays.state != 'validate':
            raise exceptions.Warning(_('Atostogos turi būti patvirtintos'))
        return holidays

    holiday_id = fields.Many2one('hr.holidays', string='Atostogos', required=True, default=default_holiday_id, ondelete='cascade')
    date = fields.Date(string='Nutraukimo data', help='Paskutinė atostogų data', required=True)
    force_shorten = fields.Boolean(
        string='Priverstinai sutrumpintos atostogos',
        help='Atostogos buvo sutrumpintos rankiniu būdu, SoDros robotukai nepratęs jų, jei pažymėsite varnelę',
    )
    show_force_shorten = fields.Boolean(compute='_compute_show_force_shorten')

    @api.multi
    @api.depends('holiday_id.holiday_status_id')
    def _compute_show_force_shorten(self):
        sick_holiday_statuses = self.env['hr.holidays'].get_sick_holiday_statuses()
        for rec in self:
            rec.show_force_shorten = self.holiday_id.holiday_status_id in sick_holiday_statuses

    @api.multi
    @api.onchange('holiday_id')
    def _onchange_holiday_id(self):
        self.ensure_one()
        sick_holiday_statuses = self.env['hr.holidays'].get_sick_holiday_statuses()
        if self.holiday_id and self.holiday_id.holiday_status_id in sick_holiday_statuses:
            self.force_shorten = True
        else:
            self.force_shorten = False

    @api.multi
    def confirm(self):
        self.holiday_id.stop_in_the_middle(self.date)
        self.holiday_id.write({'force_shorten': self.force_shorten})


HolidaysChangeWizard()


class AKlaseKodas(models.Model):

    _name = 'a.klase.kodas'
    _rec_name = 'code'

    def _default_gpm(self):
        return self.env.user.company_id.gpm_proc

    # name = fields.Char(string='Pavadinimas', required=True)
    code = fields.Char(string='Kodas', required=True)
    description = fields.Char(string='Aprašymas')
    gpm_proc = fields.Float(string='Gpm tarifas proc', default=_default_gpm)

    @api.multi
    @api.constrains('code')
    def constrain_unique_code(self):
        for rec in self:
            if self.env['a.klase.kodas'].search_count([('code', '=', rec.code), ('id', '!=', rec.id)]):
                raise exceptions.ValidationError(_('A klasės kodai negali kartotis'))

    @api.multi
    def name_get(self):
        res = []
        for rec in self:
            if len(rec.description or '') > 45:
                descr = (rec.description[:45] or '') + '...'
            else:
                descr = rec.description
            name = '[%s] - %s' % (rec.code or '', descr or '')
            res.append((rec.id, name))
        return res

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):

        if not args:
            args = []
        args = args[:]
        if name:
            recs = self.search(
                ['|', ('code', operator, name), ('description', operator, name)] + args,
                limit=limit)
        else:
            recs = self.search(args, limit=limit)
        return recs.name_get()


AKlaseKodas()


class BKlaseKodas(models.Model):

    _name = 'b.klase.kodas'
    _rec_name = 'code'

    # name = fields.Char(string='Pavadinimas', required=True)
    code = fields.Char(string='Kodas', required=True)
    description = fields.Char(string='Aprašymas')
    # gpm_proc = fields.Float(string="GPM proc", default=0)

    @api.multi
    @api.constrains('code')
    def constrain_unique_code(self):
        for rec in self:
            if self.env['b.klase.kodas'].search_count([('code', '=', rec.code), ('id', '!=', rec.id)]):
                raise exceptions.ValidationError(_('B klasės kodai negali kartotis'))

    @api.multi
    def name_get(self):
        res = []
        for rec in self:
            description = rec.description or ''
            if len(description) > 45:
                descr = (description[:45] or '') + '...'
            else:
                descr = description
            name = '[%s] - %s' % (rec.code or '', descr or '')
            res.append((rec.id, name))
        return res

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not args:
            args = []
        args = args[:]
        if name:
            recs = self.search(
                ['|', ('code', operator, name), ('description', operator, name)] + args,
                limit=limit)
        else:
            recs = self.search(args, limit=limit)
        return recs.name_get()


BKlaseKodas()


class AccountMoveLine(models.Model):

    _inherit = 'account.move.line'

    a_klase_kodas_id = fields.Many2one('a.klase.kodas', string='A klasės kodas')
    b_klase_kodas_id = fields.Many2one('b.klase.kodas', string='B klasės kodas')

    @api.multi
    @api.constrains('a_klase_kodas_id', 'b_klase_kodas_id')
    def _check_only_one_code_is_set(self):
        for rec in self:
            if rec.a_klase_kodas_id and rec.b_klase_kodas_id:
                raise exceptions.UserError(_('Negali būti užstatytas ir A ir B klasės kodas'))


AccountMoveLine()


class AccountInvoice(models.Model):

    _inherit = 'account.invoice'

    b_klase_kodas_id = fields.Many2one('b.klase.kodas', string='B klasės kodas',
                                       states={'open': [('readonly', True)],
                                               'paid': [('readonly', True)],
                                               'cancel': [('readonly', True)]},
                                       )

    @api.model
    def line_get_convert(self, line, part):
        res = super(AccountInvoice, self).line_get_convert(line, part)
        res['b_klase_kodas_id'] = line.get('b_klase_kodas_id', False)
        return res


AccountInvoice()


class HrEmployeeIsskaitos(models.Model):

    _name = 'hr.employee.isskaitos'
    _order = 'date DESC, employee_id'

    def default_date(self):
        return (datetime.now() + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def default_currency_id(self):
        return self.env.user.company_id.currency_id.id

    def default_journal_id(self):
        return self.env.user.company_id.salary_journal_id

    def default_account_id(self):
        return self.env['account.account'].search([('code', '=', '4484')])

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, states={'confirm': [('readonly', True)]})
    state = fields.Selection([('draft', 'Draft'), ('confirm', 'Confirm')],
                             string='State', readonly=True, default='draft', required=True, copy=False)
    date = fields.Date(string='Date', required=True, states={'confirm': [('readonly', True)]}, default=default_date, copy=False)
    reason = fields.Selection([('nepanaudota', 'Grąžinti perduotoms ir darbuotojo nepanaudotoms pagal paskirtį darbdavio pinigų sumoms'),
                               ('sk_klaidos', 'Grąžinti sumoms, permokėtoms dėl skaičiavimo klaidų'),
                               ('zala', 'Atlyginti žalai, kurią darbuotojas dėl savo kaltės padarė darbdaviui'),
                               ('atostoginiai', 'Išieškoti atostoginiams už suteiktas atostogas (nutraukus darbo sutartį)'),
                               ('vykd_r', 'Pagal vykdomuosius raštus'),
                               ('employee_loan', 'Darbuotojo paskola')
                               ], string='Priežastis', states={'confirm': [('readonly', True)]}, required=True)
    move_id = fields.Many2one('account.move', string='Apskaitos įrašas', readonly=True, copy=False)
    partner_id = fields.Many2one('res.partner', string='Partneris', states={'confirm': [('readonly', True)]})
    account_id = fields.Many2one('account.account', string='Išmokėjimo sąskaita', states={'confirm': [('readonly', True)]}, required=True, default=default_account_id)
    amount = fields.Monetary(string='Suma', states={'confirm': [('readonly', True)]})
    date_maturity = fields.Date(string='Išmokėjimo data', required=True, states={'confirm': [('readonly', True)]})
    journal_id = fields.Many2one('account.journal', string='Žurnalas', required=True, states={'confirm': [('readonly', True)]}, default=default_journal_id)
    currency_id = fields.Many2one('res.currency', string='Valiuta', required=True, default=default_currency_id)
    name = fields.Char(readonly=True, string='Name', compute='_name_compute', store=True)
    number = fields.Char(readonly=True, string='Number', copy=False)
    comment = fields.Text(string='Komentaras', states={'confirm': [('readonly', True)]}, copy=False)
    periodic_id = fields.Many2one('hr.employee.deduction.periodic', string='Periodinė išskaita', readonly=True, copy=False)
    limit_deduction_amount = fields.Boolean('Limit deduction amount to 20% under and 50% over the minimum wage',
                                            states={'confirm': [('readonly', True)]})
    can_be_limited = fields.Boolean('Deduction can be limited', compute='_compute_can_be_limited')

    @api.multi
    @api.depends('reason')
    def _compute_can_be_limited(self):
        for rec in self:
            rec.can_be_limited = rec.reason == 'atostoginiai'

    @api.one
    @api.depends('number', 'state')
    def _name_compute(self):
        if self.state == 'confirm':
            self.name = self.number
        else:
            self.name = 'New'

    @api.multi
    def unlink(self):
        if any(rec.state == 'confirm' for rec in self):
            raise exceptions.UserError(_('Negalima trinti patvirtinto įrašo. Pirmiau atšaukite.'))
        return super(HrEmployeeIsskaitos, self).unlink()

    @api.multi
    def confirm(self):
        payslip_data = list()
        deductions_to_reconcile = self.env['hr.employee.isskaitos']
        for rec in self:
            if rec.state == 'confirm':
                raise exceptions.Warning(_('Įrašas jau patvirtintas'))
            if rec.limit_deduction_amount:
                rec.write({'state': 'confirm'})
                continue  # Entries should be created when payslip is computed
            rec.create_move_entry()
            payslip_data.append((rec.employee_id.id, rec.date))
            deductions_to_reconcile |= rec
            rec.write({'state': 'confirm'})
        for payslip_info in set(payslip_data):
            self.env['hr.payslip'].refresh_info(payslip_info[0], payslip_info[1])
        for rec in deductions_to_reconcile:
            rec._reconcile_with_payslip()

    @api.multi
    def create_move_entry(self, amount=None):
        self.ensure_one()
        if not self.number:
            self.number = self.env['ir.sequence'].next_by_code('IŠSK')
        employee = self.employee_id
        date = self.date
        contract = self.env['hr.contract'].search([
            ('employee_id', '=', employee.id),
            ('date_start', '<=', date),
            '|',
            ('date_end', '>=', date),
            ('date_end', '=', False)
        ], limit=1)
        amount = amount or self.amount
        amount = tools.float_round(amount, precision_digits=2)
        if tools.float_compare(amount, 0.0, precision_digits=2) < 0:
            raise exceptions.Warning(_('Suma turi būti teigiama'))
        account_credit = self.account_id.id
        account_debit = self.env['hr.salary.rule'].search([('code', '=', 'BRUTON')], limit=1).get_account_credit_id(
            employee, contract)
        partner_id = credit_partner_id = employee.address_home_id.id
        if self.account_id.code != '4480' and self.partner_id:
            credit_partner_id = self.partner_id.id
        if not partner_id:
            raise exceptions.UserError(_('Nenurodytas darbuotojo %s partneris') % employee.name)
        if not credit_partner_id:
            raise exceptions.UserError(_('Nenurodytas partneris'))
        aml_credit = {'partner_id': credit_partner_id,
                      'debit': 0.0,
                      'credit': amount,
                      'date_maturity': self.date_maturity,
                      'account_id': account_credit,
                      'name': self.comment or '/',
                      }
        maturity_dt = datetime.strptime(self.date_maturity, tools.DEFAULT_SERVER_DATE_FORMAT)
        employee_maturity_dt = maturity_dt + relativedelta(months=1, day=employee.company_id.salary_payment_day)
        employee_maturity = employee_maturity_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        aml_debit = {'partner_id': partner_id,
                     'debit': amount,
                     'credit': 0.0,
                     'account_id': account_debit,
                     'date_maturity': employee_maturity,
                     'name': self.comment or '/',
                     }
        move_vals = {'date': date,
                     'journal_id': self.journal_id.id,
                     'line_ids': [(0, 0, aml_credit), (0, 0, aml_debit)],
                     'ref': self.comment or '/',
                     }
        move = self.env['account.move'].create(move_vals)
        move.post()
        self.write({'move_id': move.id})

    @api.one
    def _reconcile_with_payslip(self):
        move = self.move_id
        payslips = self.env['hr.payslip'].search([('date_from', '<=', move.date),
                                                  ('date_to', '>=', move.date),
                                                  ('employee_id', '=', self.employee_id.id)])
        curr_rounding = {'precision_rounding': self.env.user.company_id.currency_id.rounding}
        line = move.line_ids.filtered(lambda l: not float_is_zero(l.debit, **curr_rounding))
        for payslip in payslips:
            salary_line = payslip.move_id.line_ids.filtered(lambda r: r.account_id == line.account_id and
                                                                      float_compare(r.credit, 0.0, **curr_rounding) > 0)
            (line + salary_line).reconcile()
            if float_is_zero(line.amount_residual, **curr_rounding):
                break

    @api.multi
    def action_cancel(self):
        payslip_data = set([(rec.employee_id.id, rec.date) for rec in self])
        for rec in self:
            rec._unreconcile_with_payslip()
            move = rec.move_id
            move.button_cancel()
            move.unlink()
            rec.state = 'draft'
        for rec in payslip_data:
            # Recompute payslip only once after all the inputs have been unlinked
            self.env['hr.payslip'].refresh_info(rec[0], rec[1])

    @api.onchange('date')
    def onchange_date(self):
        if self.date and not self.date_maturity:
            date_salary = self.env.user.company_id.salary_payment_day or 14
            date_maturity = datetime.strptime(self.date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(months=1, day=date_salary)
            self.date_maturity = date_maturity.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.one
    def _unreconcile_with_payslip(self):
        move = self.move_id
        payslip_move_ids = self.env['hr.payslip'].search([('date_from', '<=', move.date),
                                                          ('date_to', '>=', move.date),
                                                          ('employee_id', '=', self.employee_id.id)]).mapped('move_id')
        for aml in move.line_ids.filtered(
                lambda r: float_compare(r.debit, 0.0,
                                        precision_rounding=self.env.user.company_id.currency_id.rounding) > 0):
            if all([l.move_id in payslip_move_ids for l in aml.mapped('matched_credit_ids.credit_move_id')]):
                aml.remove_move_reconcile()


HrEmployeeIsskaitos()


class HrEmployeeDeductionPeriodic(models.Model):
    _name = 'hr.employee.deduction.periodic'
    _inherit = 'mail.thread'

    _order = 'reference DESC'

    def default_date(self):
        return (datetime.now() + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def default_currency_id(self):
        return self.env.user.company_id.currency_id.id

    def default_journal_id(self):
        return self.env.user.company_id.salary_journal_id

    def default_account_id(self):
        return self.env['account.account'].search([('code', '=', '4484')])

    name = fields.Char(string='Name', default=_('Nauja periodinė išskaita'), store=True,
                       states={'confirm': [('readonly', True)], 'done': [('readonly', True)]})
    reference = fields.Char(string='Reference', default=False, readonly=True, track_visibility='onchange', copy=False)

    state = fields.Selection([('draft', 'Draft'), ('confirm', 'Confirm'), ('done', 'Completed')],
                             string='State', readonly=True,
                             default='draft', required=True, copy=False, track_visibility='onchange')
    action = fields.Selection([('draft', 'Netvirtinti'),
                               ('confirm', 'Tvirtinti')],
                              string='Automatinis veiksmas', default='draft', required=True,
                              states={'confirm': [('readonly', True)], 'done': [('readonly', True)]})
    reason = fields.Selection(
        [('nepanaudota', 'Grąžinti perduotoms ir darbuotojo nepanaudotoms pagal paskirtį darbdavio pinigų sumoms'),
         ('sk_klaidos', 'Grąžinti sumoms, permokėtoms dėl skaičiavimo klaidų'),
         ('zala', 'Atlyginti žalai, kurią darbuotojas dėl savo kaltės padarė darbdaviui'),
         ('atostoginiai', 'Išieškoti atostoginiams už suteiktas atostogas (nutraukus darbo sutartį)'),
         ('vykd_r', 'Pagal vykdomuosius raštus'),
         ], string='Priežastis', default='vykd_r',
        states={'confirm': [('readonly', True)], 'done': [('readonly', True)]}, required=True)

    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', required=True,
                                  states={'confirm': [('readonly', True)], 'done': [('readonly', True)]},
                                  track_visibility='onchange')
    partner_id = fields.Many2one('res.partner', string='Partneris',
                                 states={'confirm': [('readonly', True)], 'done': [('readonly', True)]})
    account_id = fields.Many2one('account.account', string='Išmokėjimo sąskaita',
                                 required=True, default=default_account_id,
                                 states={'confirm': [('readonly', True)], 'done': [('readonly', True)]})
    journal_id = fields.Many2one('account.journal', string='Žurnalas', required=True, default=default_journal_id,
                                 states={'confirm': [('readonly', True)], 'done': [('readonly', True)]})
    currency_id = fields.Many2one('res.currency', string='Valiuta', required=True, default=default_currency_id)

    deduction_ids = fields.One2many('hr.employee.isskaitos', 'periodic_id', copy=False)

    date = fields.Date(string='Kitos išskaitos data', default=False, track_visibility='onchange',
                       states={'confirm': [('readonly', True)], 'done': [('readonly', True)]})
    date_maturity = fields.Date(string='Kitos išskaitos išmokėjimo data', default=False,
                                states={'confirm': [('readonly', True)], 'done': [('readonly', True)]},
                                lt_string='Kitos išskaitos išmokėjimo data')
    date_first = fields.Date(string='Pirmos išskaitos data', track_visibility='onchange', default=default_date,
                             states={'confirm': [('readonly', True)], 'done': [('readonly', True)]}, required=True)
    date_stop = fields.Date(string='Sustabdyti nuo')

    amount = fields.Monetary(string='Mėnesinės išskaitos dydis', required=True, track_visibility='onchange',
                             default=0.0, states={'confirm': [('readonly', True)], 'done': [('readonly', True)]})
    amount_deducted = fields.Monetary(string='Išskaityta suma', compute='_get_amount_deducted', readonly=True)
    amount_total = fields.Monetary(string='Viso išskaitytina suma', required=True, default=0.0,
                                   states={'confirm': [('readonly', True)], 'done': [('readonly', True)]},
                                   track_visibility='onchange')

    comment = fields.Text(string='Komentaras',
                          states={'confirm': [('readonly', True)], 'done': [('readonly', True)]})

    deduction_count = fields.Integer(string='Išskaitų kiekis', compute='_count_deduction')
    show_gap_warning = fields.Boolean(string='Rodyti įspėjimą', compute='_show_gap_warning',
                                      help=('Įspėjimas rodomas kai laikotarpis nuo paskutinių'
                                            ' išskaitų iki sekančios datos yra ilgesnis nei mėnuo'))

    slip_ids = fields.Many2many('hr.payslip', compute='_compute_slip_ids')

    @api.one
    @api.depends('employee_id', 'date')
    def _compute_slip_ids(self):
        HrPayslip = self.env['hr.payslip']
        payslips = HrPayslip
        if self.date:
            payslips = HrPayslip.search([
                ('employee_id', '=', self.employee_id.id),
                ('date_from', '<=', self.date),
                ('date_to', '>=', self.date)
            ])
        self.slip_ids = payslips.ids

    @api.one
    @api.depends('deduction_ids.date', 'date')
    def _show_gap_warning(self):
        if self.date and self.deduction_count > 0:
            last_date = max(self.deduction_ids.mapped('date'))
            date = datetime.strptime(self.date, tools.DEFAULT_SERVER_DATE_FORMAT)
            if (date + relativedelta(months=-1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT) > last_date:
                self.show_gap_warning = True

    @api.one
    @api.depends('deduction_ids')
    def _count_deduction(self):
        self.deduction_count = len(self.deduction_ids)

    @api.one
    @api.depends('deduction_ids.amount')
    def _get_amount_deducted(self):
        self.amount_deducted = sum(d.amount for d in self.deduction_ids)

    @api.one
    def check_completion(self):
        if self.deduction_count > 0:
            if float_compare(self.amount_deducted, self.amount_total,
                             precision_rounding=self.currency_id.rounding) >= 0:
                self.state = 'done'

    @api.multi
    def set_next_date(self):
        self.ensure_one()
        if self.deduction_ids:
            date = self.deduction_ids.sorted(lambda d: d.date)[0].date
        else:
            date = self.date
        date = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        new_day = 31 if date.day == (date + relativedelta(day=31)).day else date.day
        next_date = datetime.strptime(self.date, tools.DEFAULT_SERVER_DATE_FORMAT)
        next_date += relativedelta(months=1, day=new_day)
        self.date = next_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        if self.date_stop and next_date > datetime.strptime(self.date_stop, tools.DEFAULT_SERVER_DATE_FORMAT):
            self.date = False

    @api.multi
    def set_next_date_maturity(self):
        self.ensure_one()
        if self.deduction_ids:
            date = self.deduction_ids.sorted(lambda d: d.date)[0].date_maturity
        else:
            date = self.date_maturity
        date = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        new_day = 31 if date.day == (date + relativedelta(day=31)).day else date.day
        next_date = datetime.strptime(self.date_maturity, tools.DEFAULT_SERVER_DATE_FORMAT)
        next_date += relativedelta(months=1, day=new_day)
        self.date_maturity = next_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    def run(self):
        cdate = datetime.utcnow()
        for rec in self:
            stop_date = datetime.strptime(rec.date_stop, tools.DEFAULT_SERVER_DATE_FORMAT) if rec.date_stop else False
            if datetime.strptime(rec.date, tools.DEFAULT_SERVER_DATE_FORMAT) > cdate:
                continue
            if stop_date and stop_date < cdate:
                continue
            deduction_vals = {
                'employee_id': rec.employee_id.id,
                'periodic_id': rec.id,
                'journal_id': rec.journal_id.id,
                'reason': rec.reason,
                'account_id': rec.account_id.id,
                'partner_id': rec.partner_id.id,
                'currency_id': rec.currency_id.id,
                'date': rec.date,
                'date_maturity': rec.date_maturity,
            }
            amount = min(rec.amount, rec.amount_total - rec.amount_deducted)

            if float_compare(amount, 0.0, precision_rounding=rec.currency_id.rounding) > 0:
                deduction_vals.update({'amount': amount})
                deduction = self.env['hr.employee.isskaitos'].create(deduction_vals)
                deduction.periodic_id = rec.id
                if rec.action == 'confirm':
                    deduction.confirm()

            rec.check_completion()
            if rec.state != 'done':
                rec.set_next_date()
                if rec.date:
                    rec.set_next_date_maturity()

    @api.multi
    def action_view_deduction(self):
        deductions = self.mapped('deduction_ids')
        action = self.env.ref('l10n_lt_payroll.action_deduction_tree1').read()[0]
        if len(deductions) > 1:
            action['domain'] = [('id', 'in', deductions.ids)]
        elif len(deductions) == 1:
            action['views'] = [(self.env.ref('l10n_lt_payroll.isskaitos_form_view').id, 'form')]
            action['res_id'] = deductions.ids[0]
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    @api.multi
    def unlink(self):
        payslips = self.mapped('slip_ids')
        for rec in self:
            if len(rec.deduction_ids) > 0:
                raise exceptions.UserError(_('Periodinė išskaita turi susijusių įrašų (%s).')
                                           % rec.reference or rec.name)
        res = super(HrEmployeeDeductionPeriodic, self).unlink()
        payslips._compute_planned_periodic_deductions_exist()
        return res

    @api.multi
    def confirm(self):
        for rec in self:
            if not rec.employee_id.with_context(date=rec.date, strict_date_check=True).contract_id:
                raise exceptions.ValidationError(
                    _('Cannot create a periodic deduction for employee without a contract'))
            if rec.amount <= 0.0:
                raise exceptions.Warning(_('Nenurodyta mėnesinė suma.'))
            if rec.amount_total <= 0.0:
                raise exceptions.Warning(_('Nenurodyta bendra suma.'))
            if not rec.reference:
                rec.reference = self.env['ir.sequence'].next_by_code('PIŠSK')
            if not rec.date:
                rec.date = rec.date_first
            if not rec.date_maturity:
                rec.date_maturity = rec.date_first
            rec.state = 'confirm'
            rec.slip_ids._compute_planned_periodic_deductions_exist()

    @api.one
    def set_to_draft(self):
        self.state = 'draft'

    @api.one
    def mark_done(self):
        self.state = 'done'

    @api.model
    def cron_create_periodic_deduction(self):
        cdate = (datetime.utcnow() + relativedelta(weeks=2)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        periodic_ids = self.search([
            ('state', '=', 'confirm'),
            ('date', '<=', cdate),
            '|',
            ('date_stop', '=', False),
            ('date_stop', '>', cdate),
        ])
        periodic_ids.run()

    @api.multi
    def name_get(self):
        return [(rec.id, rec.reference or rec.name) for rec in self]


HrEmployeeDeductionPeriodic()
