# -*- coding: utf-8 -*-
from __future__ import division
from odoo import api, models, tools, _
from odoo.tools.misc import formatLang
from datetime import datetime
from six import iteritems
from dateutil.relativedelta import relativedelta
from odoo.addons.l10n_lt_payroll.model.darbuotojai import get_last_work_day

CATEGORY_TO_CODE_MAPPING = {
    'neapmokamas_nedarbingumas': ['N', 'NS'],
    'prastovos': ['PK', 'PN'],
    'atostogos': ['A'],
    'mamadieniai': ['M', 'MP'],
    'kitu_rusiu_atostogos': ['KR', 'MA'],
    'nemokamos_atostogos': ['NA', 'NLL'],
    'ligos': ['L'],
    'kvalifikacijos_kelimas': ['KV'],
    'darbas_nakti': ['DN'],
    'darbas_poilsio_dienomis': ['DP'],
    'neivykdyta_darbo_laiko_norma': ['NDL'],
    'virsyta_darbo_laiko_norma': ['VDL'],
    'darbas_poilsio_nakti': ['SNV'],
    'virsvalandziai': ['VD', 'VDN'],
    'worked_time_actual': ['FD', 'BN', 'BĮ'],
}

regular_amount_codes = ['BM', 'BUD', 'BV']
free_day_worked_codes = ['DP']
night_hour_codes = ['DN']
overtime_codes = ['VD', 'VSS', 'VDN']
holiday_nights_codes = ['SNV']
work_norm_adjustment_codes = ['NDL', 'VDL']
extra_work_codes = overtime_codes + work_norm_adjustment_codes + holiday_nights_codes
downtime_codes = ['PN']
extra_amount_codes_excl_downtime = extra_work_codes + night_hour_codes + free_day_worked_codes
liga_amount_codes = ['L']
tevystes_amount_codes = ['T']
holiday_amount_codes = ['A']
kompensacija_amount_codes = ['AK']
all_holidays_amount_codes = holiday_amount_codes + kompensacija_amount_codes
business_trip_amount_codes = ['KM']
qualification_training_amount_codes = ['KV']
npd_amount_codes = ['NPD']
bonus_amount_codes = ['PR', 'PD', 'PRI', 'PDN', 'PDNM']
dynamic_workplace_compensation_amount_codes = ['KKPD']
compensation_amount_codes = ['KOMP'] + dynamic_workplace_compensation_amount_codes
other_addition_amount_codes = ['P', 'PNVDU', 'KR', 'INV', 'IST', 'V']
other_additions_amount_codes = ['KNDDL', 'MA'] + qualification_training_amount_codes
other_bonuses_amount_codes = other_addition_amount_codes + bonus_amount_codes
all_other_additions_codes = liga_amount_codes + other_addition_amount_codes + extra_work_codes + compensation_amount_codes
total_additions_amount_codes = regular_amount_codes + extra_amount_codes_excl_downtime + downtime_codes + \
                               liga_amount_codes + tevystes_amount_codes + all_holidays_amount_codes + \
                               other_bonuses_amount_codes + other_additions_amount_codes
gpm_amount_codes = ['GPM']
gpm_employer_pays_amount_codes = ['EMPLRGPM']
SODRA_employer_pays_amount_codes = ['EMPLRSDB']
voluntary_SODRA_employer_pays_amount_codes = ['EMPLRSDP']
employer_SODRA_of_benefit_in_kind_codes = ['EMPLRSDDMAIN']
employee_sodra_amount_codes = ['SDB']
employee_extra_sodra_amount_codes = ['SDP']
child_benefit_amount_codes = ['VAIKUI']
total_employer_pays_taxes_codes = gpm_employer_pays_amount_codes + SODRA_employer_pays_amount_codes + \
                                  voluntary_SODRA_employer_pays_amount_codes + employer_SODRA_of_benefit_in_kind_codes
other_deductions_amount_codes = ['IŠSK']
benefit_in_kind_codes = ['NTR']
benefit_in_kind_employee_gpm_codes = ['NTR_GPM']
benefit_in_kind_employee_sodra_codes = ['NTR_SODRA_EMPL']
benefit_in_kind_employer_sodra_codes = ['NTR_SODRA_EMPLR']
# Do not add NTRD to the other_deductions_amount_codes since it's calculated within the NTR code
benefit_in_kind_employer_pays_taxes_codes = ['NTRD']
total_employer_benefit_in_kind_codes = benefit_in_kind_employer_pays_taxes_codes + \
                                       employer_SODRA_of_benefit_in_kind_codes + \
                                       voluntary_SODRA_employer_pays_amount_codes + SODRA_employer_pays_amount_codes + \
                                       gpm_employer_pays_amount_codes
total_deductions_amount_codes = gpm_amount_codes + employee_sodra_amount_codes + employee_extra_sodra_amount_codes + \
                                child_benefit_amount_codes + other_deductions_amount_codes
late_payments_amount_codes = ['PVL']
SODRA_employee_floor_amount_codes = ['SDBGRPADD']
SODRA_employer_floor_amount_codes = ['SDDGRADD']
SODRA_employer_amount_codes = ['SDDMAIN']
SODRA_total_amount_codes = ['SDD']
should_pay_codes = ['NET']
holiday_already_paid_codes = ['AM']
advance_payment_codes = ['AVN']
untaxed_allowance = ['NAKM']
deductions = ['ISSK']
labor_costs_amount_codes = total_additions_amount_codes + SODRA_total_amount_codes

ALL_PAYROLL_CODES = labor_costs_amount_codes + total_deductions_amount_codes + total_additions_amount_codes + \
                    all_other_additions_codes + all_holidays_amount_codes + extra_amount_codes_excl_downtime + \
                    advance_payment_codes + should_pay_codes + SODRA_employer_floor_amount_codes + \
                    SODRA_employee_floor_amount_codes + late_payments_amount_codes + \
                    qualification_training_amount_codes + npd_amount_codes + SODRA_employer_amount_codes + \
                    untaxed_allowance + deductions + holiday_already_paid_codes + tevystes_amount_codes + \
                    business_trip_amount_codes + benefit_in_kind_employer_pays_taxes_codes + benefit_in_kind_codes

DEFAULT_PAYSLIP_RELATED_DOCARGS = {
    'max_laikas_d': lambda payslips: _max_laikas_d_with_contract(payslips),
    'max_laikas_h': lambda payslips: _max_laikas_h(payslips),
    'dirbtas_laikas_d': lambda payslips: _dirbtas_laikas_d(payslips),
    'dirbtas_laikas_h': lambda payslips: _dirbtas_laikas_h(payslips),
    'worked_time_actual_d': lambda payslips: _worked_time_by_code(payslips, ['worked_time_actual'], return_days=True),
    'worked_time_actual_h': lambda payslips: _worked_time_by_code(payslips, ['worked_time_actual']),
    'trumpinimas_pries_sventes_h': lambda payslips: _trumpinimas_pries_sventes_h(payslips),
    'visas_laikas_d': lambda payslips: _visas_laikas_d(payslips),
    'visas_laikas_h': lambda payslips: _visas_laikas_h(payslips),
    'nemokamos_atostogos_d': lambda payslips: _worked_time_by_code(payslips, ['nemokamos_atostogos'], return_days=True),
    'nemokamos_atostogos_h': lambda payslips: _worked_time_by_code(payslips, ['nemokamos_atostogos']),
    'neapmokamas_nedarbingumas_d': lambda payslips: _worked_time_by_code(payslips, ['neapmokamas_nedarbingumas'], return_days=True),
    'neapmokamas_nedarbingumas_h': lambda payslips: _worked_time_by_code(payslips, ['neapmokamas_nedarbingumas']),
    'prastovos_d': lambda payslips: _worked_time_by_code(payslips, ['prastovos'], return_days=True),
    'prastovos_h': lambda payslips: _worked_time_by_code(payslips, ['prastovos']),
    'ligos_d': lambda payslips: _worked_time_by_code(payslips, ['ligos'], return_days=True),
    'ligos_h': lambda payslips: _worked_time_by_code(payslips, ['ligos']),
    'periodas': lambda payslips: _periodas(payslips),
    'atostogos_d': lambda payslips: _worked_time_by_code(payslips, ['atostogos', 'ligos', 'mamadieniai', 'kitu_rusiu_atostogos'], return_days=True),
    'atostogos_h': lambda payslips: _worked_time_by_code(payslips, ['atostogos', 'ligos', 'mamadieniai', 'kitu_rusiu_atostogos']),
    'kasmetines_atostogos_d': lambda payslips: _worked_time_by_code(payslips, ['atostogos'], return_days=True),
    'kasmetines_atostogos_h': lambda payslips: _worked_time_by_code(payslips, ['atostogos']),
    'mamadieniai_tevadieniai_d': lambda payslips: _worked_time_by_code(payslips, ['mamadieniai'], return_days=True),
    'mamadieniai_tevadieniai_h': lambda payslips: _worked_time_by_code(payslips, ['mamadieniai']),
    'kitos_atostogos_d': lambda payslips: _worked_time_by_code(payslips, ['kitu_rusiu_atostogos'], return_days=True),
    'kitos_atostogos_h': lambda payslips: _worked_time_by_code(payslips, ['kitu_rusiu_atostogos']),
    'darbas_nakti_h': lambda payslips: _worked_time_by_code(payslips, ['darbas_nakti']),
    'darbas_nakti_d': lambda payslips: _worked_time_by_code(payslips, ['darbas_nakti'], return_days=True),
    'darbas_poilsio_h': lambda payslips: _worked_time_by_code(payslips, ['darbas_poilsio_dienomis']),
    'darbas_poilsio_d': lambda payslips: _worked_time_by_code(payslips, ['darbas_poilsio_dienomis'], return_days=True),
    'kvalifikacija_h': lambda payslips: _worked_time_by_code(payslips, ['kvalifikacijos_kelimas']),
    'kvalifikacija_d': lambda payslips: _worked_time_by_code(payslips, ['kvalifikacijos_kelimas'], return_days=True),
    'darbas_poilsio_nakti_h': lambda payslips: _worked_time_by_code(payslips, ['darbas_poilsio_nakti']),
    'darbas_poilsio_nakti_d': lambda payslips: _worked_time_by_code(payslips, ['darbas_poilsio_nakti'], return_days=True),
    'virsvalandziai_h': lambda payslips: _worked_time_by_code(payslips, ['virsvalandziai']),
    'virsvalandziai_d': lambda payslips: _worked_time_by_code(payslips, ['virsvalandziai'], return_days=True),
    'neivykdyta_norma_h': lambda payslips: _worked_time_by_code(payslips, ['neivykdyta_darbo_laiko_norma']),
    'neivykdyta_norma_d': lambda payslips: _worked_time_by_code(payslips, ['neivykdyta_darbo_laiko_norma'], return_days=True),
    'virsyta_norma_h': lambda payslips: _worked_time_by_code(payslips, ['virsyta_darbo_laiko_norma']),
    'virsyta_norma_d': lambda payslips: _worked_time_by_code(payslips, ['virsyta_darbo_laiko_norma'], return_days=True),
    'remaining_leaves_label': lambda payslips: _remaining_leaves_label(payslips),
    'replace': lambda string: _replace(string),
    'remove': lambda string: _remove(string),
    'round_time': lambda time: _round_time(time),
    'regular_hours': lambda payslips: _regular_hours(payslips),
    'payslip_amounts': lambda payslips: _payslip_amounts(payslips),
    'float_is_zero': lambda amount: tools.float_is_zero(amount, precision_digits=2),
    'payment_date': lambda payslip: _payment_date(payslip),
}


def _payslip_amounts(payslips):
    def line_sums(codes, subtracted_codes=None):
        if not subtracted_codes:
            subtracted_codes = list()
        additions = sum(payslip_line_ids.filtered(lambda l: l.code in codes).mapped('total'))
        deductions = sum(payslip_line_ids.filtered(lambda l: l.code in subtracted_codes).mapped('total'))
        return additions - deductions

    payslip_line_ids = payslips.mapped('line_ids')

    res = {
        'regular_amount': line_sums(regular_amount_codes),
        'extra_amount_excl_downtime': line_sums(extra_amount_codes_excl_downtime),
        'downtime_amount': line_sums(downtime_codes),
        'night_amount': line_sums(night_hour_codes),
        'free_day_work_amount': line_sums(free_day_worked_codes),
        'liga_amount': line_sums(liga_amount_codes),
        'tevystes_amount': line_sums(tevystes_amount_codes),
        'all_holidays_amount': line_sums(all_holidays_amount_codes),
        'holidays_amount': line_sums(holiday_amount_codes),
        'holidays_compensation_amount': line_sums(kompensacija_amount_codes),
        'business_trip_amount': line_sums(business_trip_amount_codes),
        'untaxed_business_trip_amount': line_sums(untaxed_allowance),
        'qualification_training_amount': line_sums(qualification_training_amount_codes),
        'bonuses_amount': line_sums(bonus_amount_codes),
        'compensation_amount': line_sums(compensation_amount_codes),
        'all_other_additions_amount': line_sums(all_other_additions_codes),
        'overtime_amount': line_sums(overtime_codes),
        'holiday_nights_amount': line_sums(holiday_nights_codes),
        'work_norm_adjustment_amount': line_sums(work_norm_adjustment_codes),
        'other_additions_amount': line_sums(other_additions_amount_codes),
        'other_addition_amount': line_sums(other_addition_amount_codes),
        'other_bonuses_amount': line_sums(other_bonuses_amount_codes),
        'total_additions_amount': line_sums(total_additions_amount_codes),
        'npd_amount': line_sums(npd_amount_codes),
        'gpm_amount': line_sums(gpm_amount_codes),
        'social_security_excl_pension_amount': line_sums(employee_sodra_amount_codes),
        'social_pension_security_amount': line_sums(employee_extra_sodra_amount_codes),
        'child_benefit_amount': line_sums(child_benefit_amount_codes),
        'other_deductions_amount': line_sums(other_deductions_amount_codes),
        'total_deductions_amount': line_sums(total_deductions_amount_codes),
        'late_payments_amount': line_sums(late_payments_amount_codes),
        'SODRA_employee_amount': line_sums(employee_sodra_amount_codes),
        'SODRA_employee_extra_amount': line_sums(employee_extra_sodra_amount_codes),
        'SODRA_employee_floor_amount': line_sums(SODRA_employee_floor_amount_codes),
        'SODRA_employer_floor_amount': line_sums(SODRA_employer_floor_amount_codes),
        'SODRA_employer_amount': line_sums(SODRA_employer_amount_codes),
        'SODRA_total_amount': line_sums(SODRA_total_amount_codes),
        'should_payout_amount': line_sums(should_pay_codes),
        'holiday_already_paid_amount': line_sums(holiday_already_paid_codes),
        'advance_payment_amount': line_sums(advance_payment_codes),
        'labor_costs_amount': line_sums(labor_costs_amount_codes),
        'benefit_in_kind_employer_pays_taxes_amount': line_sums(benefit_in_kind_employer_pays_taxes_codes),
        'benefit_in_kind_amount': line_sums(benefit_in_kind_codes, benefit_in_kind_employer_pays_taxes_codes),
        'benefit_in_kind_employee_gpm_amount': line_sums(benefit_in_kind_employee_gpm_codes),
        'benefit_in_kind_employee_sodra_amount': line_sums(benefit_in_kind_employee_sodra_codes),
        'benefit_in_kind_employer_sodra_amount': line_sums(benefit_in_kind_employer_sodra_codes),
        'gpm_employer_pays_amount_amount': line_sums(gpm_employer_pays_amount_codes),
        'SODRA_employer_pays_amount_amount': line_sums(SODRA_employer_pays_amount_codes),
        'voluntary_SODRA_employer_pays_amount': line_sums(voluntary_SODRA_employer_pays_amount_codes),
        'employer_SODRA_of_benefit_in_kind_amount': line_sums(employer_SODRA_of_benefit_in_kind_codes),
        'dynamic_workplace_compensation_amount': line_sums(dynamic_workplace_compensation_amount_codes),
    }
    return res

def _worked_time_by_code(payslips, categories, return_days=False):
    codes = []
    for category in categories:
        codes += CATEGORY_TO_CODE_MAPPING.get(category, [])
    lines = payslips.mapped('worked_days_line_ids').filtered(lambda l: l.code in codes)
    return sum(lines.mapped('number_of_days' if return_days else 'number_of_hours'))

def _max_laikas_d(payslips):
    suma_d = sum(payslip.ziniarastis_period_line_id.num_regular_work_days for payslip in payslips)
    return suma_d or 0

def _max_laikas_d_with_contract(payslips):
    suma_d = sum(payslip.ziniarastis_period_line_id.num_regular_work_days_contract_only for payslip in payslips)
    return suma_d or 0


def _max_laikas_h(payslips):
    suma_h = sum(payslip.ziniarastis_period_line_id.num_regular_work_hours for payslip in payslips if payslip.ziniarastis_period_line_id)
    return suma_h or 0


def _dirbtas_laikas_d(payslips):
    return sum(payslip.ziniarastis_period_line_id.days_total for payslip in payslips)


def _dirbtas_laikas_h(payslips):
    return sum(payslip.ziniarastis_period_line_id.hours_worked for payslip in payslips)


def _trumpinimas_pries_sventes_h(payslips):
    lines = payslips.mapped('worked_days_line_ids').filtered(lambda r: r.compensated_time_before_holidays)
    return sum(lines.mapped('number_of_hours'))


def _regular_hours(payslips):
    suma_h = 0
    for payslip in payslips:
        suma_h += payslip.ziniarastis_period_line_id.num_regular_work_hours if payslip.ziniarastis_period_line_id else 0
    return tools.float_round(suma_h, precision_digits=2)


def _visas_laikas_d(payslips):
    suma_d = 0
    additional_codes = ['A', 'MA', 'KR', 'NA']
    for payslip in payslips:
        ziniarastis = payslip.ziniarastis_period_line_id
        suma_d += len(ziniarastis.ziniarastis_day_ids.mapped('ziniarastis_day_lines').filtered(
            lambda r: r.tabelio_zymejimas_id.code in additional_codes and (r.worked_time_hours or r.worked_time_minutes)).mapped('ziniarastis_id'))
        suma_d += ziniarastis.days_total
    return suma_d


def _visas_laikas_h(payslips):
    suma_h = 0
    additional_codes = ['A', 'MA', 'KR', 'NA']
    for payslip in payslips:
        ziniarastis = payslip.ziniarastis_period_line_id
        # P3:DivOK
        suma_h += sum(ziniarastis.ziniarastis_day_ids.mapped('ziniarastis_day_lines').filtered(lambda r: r.tabelio_zymejimas_id.code in additional_codes).mapped(lambda r: r.worked_time_hours + r.worked_time_minutes/60.0))
        suma_h += ziniarastis.hours_worked
    return suma_h

def _periodas(payslip):
    data = datetime.strptime(payslip.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
    return str(data.year) + '-' + str(data.month)


def _replace(string):
    string = str(string)
    if len(string) > 0 and '.' in string:
        return string.replace('.', ',')
    else:
        return string


def _remove(string):
    string = str(string)
    if len(string) > 0 and '.' in string:
        return string.split('.')[0]
    else:
        return string


def _round_time(time):
    """
    Rounds time and returns as string
    Returns:
        string: Formatted time
    """
    try:
        time = float(time)
    except:
        return time
    time = round(time, 2)
    time = '{:2.2f}'.format(time)
    return time


def _remaining_leaves_label(payslip):
    leaves_accumulation_type = payslip.employee_id.sudo().with_context(
        date=payslip.date_to).leaves_accumulation_type
    label = _(' k.d.') if leaves_accumulation_type == 'calendar_days' else _(' d.d.')
    return label


def _payment_date(payslip):
    # Try to get payment date based on reconciled debit move
    partner = payslip.employee_id.address_home_id
    payslip_moves = payslip.sudo().move_id.filtered(lambda m: m.state == 'posted')
    payment_dates = payslip_moves.mapped('line_ids.matched_debit_ids.debit_move_id').filtered(
        lambda l: l.journal_id.type == 'bank' and l.partner_id == partner
    ).mapped('payment_id.payment_date')
    payment_date = payment_dates and payment_dates[0]
    if payment_date:
        return payment_date

    # If the work relation ends during the payslip period - the payment date is the last working day of the employee
    contract = payslip.sudo().contract_id
    work_relation_ends_during_payslip_period = contract.work_relation_end_date and \
                                               payslip.date_from <= contract.work_relation_end_date <= payslip.date_to
    if payslip.ismoketi_kompensacija and work_relation_ends_during_payslip_period:
        return get_last_work_day(payslip, contract.work_relation_end_date)

    # Return the default salary payment day
    date_to_dt = datetime.strptime(payslip.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
    salary_payment_day = payslip.employee_id.company_id.salary_payment_day
    default_payment_date_dt = date_to_dt + relativedelta(months=1, day=salary_payment_day)
    return default_payment_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)


class Suvestine(models.AbstractModel):

    _name = 'report.l10n_lt_payroll.report_suvestine_sl'

    @api.multi
    def render_html(self, doc_ids, data=None):
        report_obj = self.env['report']
        if self.env.user.is_manager() or self.env.user.is_hr_manager():
            self = self.sudo()
        force_lang = data.get('force_lang', 'lt_LT') if data else False
        force_lang = force_lang or self._context.get('lang') or self.env.user.company_id.partner_id.lang or 'lt_LT'
        employee_ids = data.get('employee_ids', []) if data else ()
        doc_ids = doc_ids if doc_ids else data.get('payslip_run_id', [])

        report = report_obj._get_report_from_name('l10n_lt_payroll.report_suvestine_sl')
        slips = self.env[report.model].browse(doc_ids).mapped('slip_ids')
        if employee_ids:
            slips = slips.filtered(lambda s: s.employee_id.id in employee_ids)
        brotherly_slips = {
            slip.id: slip.search_count([('employee_id', '=', slip.employee_id.id),
                                        ('date_from', '=', slip.date_from),
                                        ('date_to', '=', slip.date_to)])
            for slip in slips
        }
        payslip_runs = self.env[report.model].browse(doc_ids)
        docargs = {
            'doc_ids': doc_ids,
            'doc_model': report.model,
            'docs': payslip_runs,
            'brotherly_slips': brotherly_slips,
            'employee_ids': employee_ids,
            'force_lang': force_lang,
            'formatLang': lambda *a, **kw: formatLang(self.env, *a, **kw)
            }
        docargs.update(DEFAULT_PAYSLIP_RELATED_DOCARGS)
        payments = self.env['hr.employee.payment']
        for payslip_run in payslip_runs:
            payments |= self.env['hr.employee.payment'].search([
                ('type', '!=', 'holidays'),
                ('date', '<=', payslip_run.date_end),
                ('date', '>=', payslip_run.date_start),
                ('state', '=', 'done')
            ])
        if employee_ids:
            payments = payments.filtered(lambda p: p.employee_id.id in employee_ids)
        payments = self.format_payment_data(payments) + self.format_compensation_data(payslip_runs,
                                                                                      employee_ids=employee_ids)
        payments += self._get_benefit_in_kind_employer_pays_taxes_payments(slips)
        payments += self._get_benefit_in_kind_employee_pays_taxes_payments(slips)
        all_payment_types = [payment['type'] for payment in payments]
        payment_types = list(set(all_payment_types))
        docargs.update({
            'payments': payments,
            # Payment types sorted by the amount of entries so that tables with more data appear on the left
            'payment_types': sorted(payment_types, key=lambda p_type: len([x for x in all_payment_types if x == p_type]), reverse=True)
        })
        return report_obj.render('l10n_lt_payroll.report_suvestine_sl', docargs)

    @api.model
    def _get_benefit_in_kind_employer_pays_taxes_payments(self, payslips):
        data = dict()
        payment_type = 'benefit_in_kind_employer_pays_taxes'
        for payslip in payslips:
            payslip_amounts = _payslip_amounts(payslip)
            benefit_in_kind_employer_pays_taxes_amount = payslip_amounts.get(
                'benefit_in_kind_employer_pays_taxes_amount',
                0.0)
            if tools.float_is_zero(benefit_in_kind_employer_pays_taxes_amount, precision_digits=2):
                continue
            employee = payslip.employee_id
            partner = employee.address_home_id
            contract = payslip.contract_id
            key = '{}{}{}'.format(employee.id, partner.id, contract.id)
            existing_data = data.get(key)

            gpm = payslip_amounts.get('gpm_employer_pays_amount_amount', 0.0)
            sodra_main = payslip_amounts.get('SODRA_employer_pays_amount_amount', 0.0)
            additional_sodra = payslip_amounts.get('voluntary_SODRA_employer_pays_amount', 0.0)
            employer_sodra = payslip_amounts.get('employer_SODRA_of_benefit_in_kind_amount', 0.0)
            neto = benefit_in_kind_employer_pays_taxes_amount - gpm - sodra_main - additional_sodra

            if not existing_data:
                data[key] = {
                    'employee': employee.name or partner.name or '-',
                    'contract_id': contract.id,
                    'contract': contract.name if contract else '-',
                    'bruto': benefit_in_kind_employer_pays_taxes_amount,
                    'gpm': gpm,
                    'neto': neto,
                    'type_str': _('Pajamos natūra (mokesčiai iš darbdavio lėšų)'),
                    'type': payment_type,
                    'sodra': sodra_main + additional_sodra + employer_sodra
                }
            else:
                data[key]['bruto'] += benefit_in_kind_employer_pays_taxes_amount
                data[key]['gpm'] += gpm
                data[key]['neto'] += neto
                data[key]['sodra'] += sodra_main + additional_sodra + employer_sodra
        return [data for key, data in sorted(iteritems(data))]  # P3:Ok

    @api.model
    def _get_benefit_in_kind_employee_pays_taxes_payments(self, payslips):
        data = dict()
        payment_type = 'benefit_in_kind_employee_pays_taxes'
        for payslip in payslips:
            payslip_amounts = _payslip_amounts(payslip)
            benefit_in_kind_amount = payslip_amounts.get('benefit_in_kind_amount', 0.0)
            if tools.float_is_zero(benefit_in_kind_amount, precision_digits=2):
                continue

            # Form key
            employee = payslip.employee_id
            partner = employee.address_home_id
            contract = payslip.contract_id
            key = '{}{}{}'.format(employee.id, partner.id, contract.id)
            existing_data = data.get(key)

            # Get related amounts
            benefit_in_kind_gpm = payslip_amounts.get('benefit_in_kind_employee_gpm_amount', 0.0)
            benefit_in_kind_employee_sodra = payslip_amounts.get('benefit_in_kind_employee_sodra_amount', 0.0)
            benefit_in_kind_employer_sodra = payslip_amounts.get('benefit_in_kind_employer_sodra_amount', 0.0)
            total_sodra = benefit_in_kind_employee_sodra  # + benefit_in_kind_employer_sodra
            neto = benefit_in_kind_amount - benefit_in_kind_gpm - benefit_in_kind_employee_sodra

            if not existing_data:
                data[key] = {
                    'employee': employee.name or partner.name or '-',
                    'contract_id': contract.id,
                    'contract': contract.name if contract else '-',
                    'bruto': benefit_in_kind_amount,
                    'gpm': benefit_in_kind_gpm,
                    'neto': neto,
                    'type_str': _('Pajamos natūra (mokesčiai iš darbuotojo lėšų)'),
                    'type': payment_type,
                    'sodra': total_sodra
                }
            else:
                data[key]['bruto'] += benefit_in_kind_amount
                data[key]['gpm'] += benefit_in_kind_gpm
                data[key]['neto'] += neto
                data[key]['sodra'] += total_sodra
        return [data for key, data in sorted(iteritems(data))]  # P3:Ok

    @api.model
    def format_payment_data(self, payments):
        """
        Format payments in a specific way for salary report to render. Payments might not have specific
        fields/attributes so we compute them in this method and return a simple list of data
        :param payments: Employee payments
        :type payments: hr.employee.payment
        :return: list containing formatted payment data
        :rtype: list
        """
        payment_data = {}
        i = -1
        for payment in payments:
            # Get payment basic data
            contract = payment.contract_id
            employee = payment.employee_id
            partner = payment.partner_id
            if not contract:
                if not employee and partner:
                    employee = partner.employee_ids[0] if partner.employee_ids else None
                if employee:
                    contract = employee.with_context(date=payment.date).contract_id
            payment_type = dict(payment._fields.get('type', False)._description_selection(self.env)).get(payment.type,
                                                                                                         '-')

            # Create a key to sum up dictionary values as well as to sort the data later
            if not employee and not partner and not contract:
                i += 1
                key = str(i)
            else:
                key = '{}{}{}{}{}'.format(payment_type,
                                          employee.name if employee else '-',
                                          employee.id if employee else '',
                                          partner.id if partner else '',
                                          contract.id if contract else '')
            existing_data = payment_data.get(key)

            # Append or create data in data dictionary
            if not existing_data:
                payment_data[key] = {
                    'employee': payment.employee_id.name or payment.partner_id.name or '-',
                    'contract_id': payment.contract_id.id,
                    'contract': contract.name if contract else '-',
                    'bruto': payment.amount_bruto,
                    'gpm': payment.amount_gpm,
                    'neto': payment.amount_paid,
                    'type_str': payment_type,
                    'type': payment.type,
                    'sodra': payment.amount_sdb + payment.amount_sdd
                }
            else:
                payment_data[key]['bruto'] += payment.amount_bruto
                payment_data[key]['gpm'] += payment.amount_gpm
                payment_data[key]['neto'] += payment.amount_paid
                payment_data[key]['sodra'] += payment.amount_sdb + payment.amount_sdd

        # Return sorted data
        return [data for key, data in sorted(iteritems(payment_data))]  # P3:Ok

    @api.model
    def format_compensation_data(self, payslip_runs, employee_ids=None):
        """
        Format compensations in a specific way for salary report to render.
        :param payslip_runs: Employee compensations
        :type payslip_runs: hr.payslip.run
        :return: list containing formatted compensation data
        :rtype: list

        Args:
            employee_ids (list): Optional list of employee ids to filter the compensations for
        """
        compensation_data = {}

        compensation_type_map = {
            'KOMP': _('Compensation'),
            'KKPD': _('Dynamic workplace compensation')
        }

        slips = payslip_runs.mapped('slip_ids')
        if employee_ids:
            slips = slips.filtered(lambda s: s.employee_id.id in employee_ids)
        for contract in slips.mapped('contract_id'):
            contract_slips = slips.filtered(lambda s: s.contract_id == contract)
            slip_lines = contract_slips.mapped('line_ids')
            employee = contract.employee_id
            for compensation_type_by_code in compensation_type_map.keys():
                compensation_lines_by_type = slip_lines.filtered(lambda l: l.code == compensation_type_by_code)
                compensation_amount = sum(compensation_lines_by_type.mapped('amount'))
                if tools.float_is_zero(compensation_amount, precision_digits=2):
                    continue
                key = '{}{}{}'.format(employee.name, employee.id, contract.id, compensation_type_by_code)
                existing_data = compensation_data.get(key)
                if not existing_data:
                    compensation_data[key] = {
                        'employee': employee.name,
                        'contract_id': contract.id,
                        'contract': contract.name,
                        'bruto': compensation_amount,
                        'gpm': 0.0,
                        'neto': compensation_amount,
                        'type_str': compensation_type_map.get(compensation_type_by_code),
                        'type': compensation_type_by_code,
                        'sodra': 0.0
                    }
                else:
                    compensation_data[key]['bruto'] += compensation_amount
                    compensation_data[key]['neto'] += compensation_amount

        # Return sorted data
        return [data for key, data in sorted(iteritems(compensation_data))]  # P3:Ok
