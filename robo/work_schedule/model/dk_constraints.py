# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, api, tools, exceptions
from odoo.tools.translate import _
from odoo.addons.l10n_lt_payroll.model.payroll_codes import PAYROLL_CODES

factual_work_codes = PAYROLL_CODES['REGULAR'] + PAYROLL_CODES['ALL_EXTRA'] + PAYROLL_CODES['OUT_OF_OFFICE']
active_budejimas_codes = PAYROLL_CODES['WATCH_WORK']  # TODO NOT CORRECT
passive_budejimas_codes = PAYROLL_CODES['WATCH_HOME']  # TODO NOT CORRECT
overtime_codes = PAYROLL_CODES['OVERTIME']


def float_to_hrs_and_mins(total_time):
    hours, minutes = divmod(total_time * 60, 60)
    if tools.float_compare(int(round(minutes)), 60, precision_digits=3) == 0:
        minutes = 0
        hours += 1
    hours = int(hours)
    minutes = int(minutes)
    hours_minutes_formatted = ''
    if not tools.float_is_zero(hours, precision_digits=2):
        hours_minutes_formatted += str(hours) + _(' val.')
    if not tools.float_is_zero(minutes, precision_digits=2):
        hours_minutes_formatted += str(minutes) + _(' min.')
    return hours_minutes_formatted


class WorkScheduleLine(models.Model):
    _inherit = 'work.schedule.line'

    @api.multi
    def check_line_constraints(self):
        '''

        :return: a list of tuples with errors (employee_id, constraint_type, constraint_info_msg, constraint_err_msg)
        '''

        def _strf(datetime_obj):
            return datetime_obj.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        def objects_for_period(object, start, end):
            return object.filtered(lambda o: o.date_start <= end and (not o.date_end or o.date_end >= start))

        def check_yearly_overtime_constraints_for_employee():
            date_from = month_start
            date_to = month_end
            while date_from <= date_to:
                date_period_back = date_from - relativedelta(years=1)
                work_days_for_check = employee_work_schedule_days.filtered(
                    lambda d: _strf(date_from) >= d.date >= _strf(date_period_back))
                overtime_amount = sum(work_days_for_check.mapped('line_ids').filtered(lambda l: l.code in overtime_codes).mapped('worked_time_total'))
                if tools.float_compare(max_overtime_per_year, overtime_amount, precision_digits=2) < 0:
                    errors.append((
                        employee_id,
                        'yearly_overtime_constraint',
                        _('Viršytas %s val. viršvalandžių limitas per metus') % str(max_overtime_per_year),
                        _('Laikotarpiu nuo %s iki %s nustatyta %s viršvalandžių') % (
                            _strf(date_period_back),
                            _strf(date_from),
                            float_to_hrs_and_mins(overtime_amount)
                        )
                    ))
                date_from += relativedelta(days=1)

        def check_any_seven_days_constraints():
            date_from = month_start
            date_to = month_end + relativedelta(days=6)
            apps_for_this_check = objects_for_period(employee_appointments, _strf(date_from-relativedelta(days=6)), _strf(date_to))
            while date_from <= date_to:
                check_from = date_from - relativedelta(days=6)
                check_to = date_from
                check_from_strf = _strf(check_from)
                check_to_strf = _strf(check_to)
                appointments_for_period = objects_for_period(apps_for_this_check, check_from_strf, check_to_strf)
                work_days_for_check = employee_work_schedule_days.filtered(lambda d: check_to_strf >= d.date >= check_from_strf)
                hours_max = 0.0
                regular_hours = sum(work_days_for_check.mapped('line_ids').filtered(lambda l: l.code in factual_work_codes).mapped('worked_time_total'))
                overtime_hours = sum(work_days_for_check.mapped('line_ids').filtered(lambda l: l.code in overtime_codes).mapped('worked_time_total'))
                day_check = check_from
                while day_check <= check_to:
                    day_check_strf = _strf(day_check)
                    app_for_day = objects_for_period(appointments_for_period, day_check_strf, day_check_strf)
                    if app_for_day and tools.float_compare(app_for_day.schedule_template_id.etatas, 1.0, precision_digits=2) > 0:
                        hours_max += extra_contract_hour_limit / 7.0  # P3:DivOK
                    else:
                        # P3:DivOK
                        hours_max += hour_limit / 7.0 if not app_for_day or app_for_day.schedule_template_id.template_type != 'sumine' else sumine_hour_limit / 7.0
                    day_check += relativedelta(days=1)
                if tools.float_compare(regular_hours, hours_max, precision_digits=2) > 0:
                    errors.append((
                        employee_id,
                        'seven_day_constraints',
                        _('Viršyta %s val. darbo norma per 7 dienas') % str(round(hours_max, 3)),
                        _('Laikotarpiu nuo %s iki %s nustatyta %s') % (
                            check_from_strf,
                            check_to_strf,
                            float_to_hrs_and_mins(regular_hours)
                        )
                    ))

                if tools.float_compare(overtime_hours, overtime_hour_limit, precision_digits=2) > 0:
                    errors.append((
                        employee_id,
                        'seven_day_constraints',
                        _('Viršyta %s val. viršvalandžių norma per 7 dienas') % str(overtime_hour_limit),
                        _('Laikotarpiu nuo %s iki %s nustatyta %s viršvalandžių') % (
                            check_from_strf,
                            check_to_strf,
                            float_to_hrs_and_mins(overtime_hours)
                        )
                    ))

                temp_check_from = check_from
                temp_check_to = check_to
                any_day_not_worked = False
                while temp_check_from <= temp_check_to:
                    date_work_day_for_empl = work_days_for_check.filtered(lambda d: d.date == _strf(temp_check_from))
                    if not date_work_day_for_empl or tools.float_is_zero(sum(date_work_day_for_empl.mapped('line_ids').filtered(lambda l: l.code in all_worked_codes).mapped('worked_time_total')), precision_digits=2):
                        any_day_not_worked = True
                        break
                    temp_check_from += relativedelta(days=1)
                if not any_day_not_worked:
                    errors.append((
                        employee_id,
                        'seven_day_constraints',
                        _('Negalima dirbti daugiau nei 6 dienas iš eilės'),
                        _('Laikotarpiu nuo %s iki %s dirbta 7 dienas') % (check_from_strf, check_to_strf)
                    ))

                all_worked_line_ids_for_period = work_days_for_check.mapped('line_ids').filtered(lambda l: l.code in all_worked_codes and l.worked_time_total > 0).sorted(lambda l: l.datetime_from)
                if len(all_worked_line_ids_for_period) > 1:
                    atleast_one_more_than_main_break_time = False
                    for i in range(0, len(all_worked_line_ids_for_period) - 1):
                        curr_line = all_worked_line_ids_for_period[i]
                        curr_line_time_to = datetime.strptime(curr_line.datetime_to,
                                                              tools.DEFAULT_SERVER_DATETIME_FORMAT)
                        if i == 0:
                            curr_line_time_from = datetime.strptime(curr_line.datetime_from,tools.DEFAULT_SERVER_DATETIME_FORMAT)
                            # P3:DivOK
                            break_between_lines_duration = (curr_line_time_from - check_from).total_seconds() / 3600.0
                            if tools.float_compare(break_between_lines_duration, main_7_day_break_length, precision_digits=2) >= 0:
                                atleast_one_more_than_main_break_time = True
                                break
                        elif i == len(all_worked_line_ids_for_period) - 2:
                            # P3:DivOK
                            break_between_lines_duration = (check_to+relativedelta(days=1) - curr_line_time_to).total_seconds() / 3600.0
                            if tools.float_compare(break_between_lines_duration, main_7_day_break_length,
                                                   precision_digits=2) >= 0:
                                atleast_one_more_than_main_break_time = True
                                break

                        next_line = all_worked_line_ids_for_period[i + 1]
                        next_line_time_from = datetime.strptime(next_line.datetime_from, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                        # P3:DivOK
                        break_between_lines_duration = (next_line_time_from - curr_line_time_to).total_seconds() / 3600.0
                        if tools.float_compare(break_between_lines_duration, main_7_day_break_length, precision_digits=2) >= 0:
                            atleast_one_more_than_main_break_time = True
                            break
                    number_of_days = len(set(all_worked_line_ids_for_period.mapped('date')))
                    if not atleast_one_more_than_main_break_time and number_of_days > 5:
                        errors.append((
                            employee_id,
                            'seven_day_constraints',
                            _('Per betkurias 7 paeiliui einančias dienas turi būti suteikta %s pertrauka') % float_to_hrs_and_mins(main_7_day_break_length),
                            _('Laikotarpiu nuo %s iki %s nėra suteikiama pakankamai ilga pertrauka') % (check_from_strf, check_to_strf)
                        ))
                date_from += relativedelta(days=1)

        def check_4_weeks_constraints():
            check_from = month_start
            check_to = month_end
            weeks_between = max(4.0, ((check_to - check_from).days+1) / 7.0)  # P3:DivOK
            budejimas_max = 7 * 24  # TODO COMPANY SETTINGS
            budejimas_max_for_weeks = weeks_between / 4.0 * budejimas_max  # P3:DivOK
            budejimas_time_for_check = sum(employee_work_schedule_days.filtered(lambda d: _strf(check_to) >= d.date >= _strf(check_from)).mapped('line_ids').filtered(lambda l: l.code in active_budejimas_codes + passive_budejimas_codes).mapped('worked_time_total'))
            if tools.float_compare(budejimas_time_for_check, budejimas_max_for_weeks, precision_digits=2) > 0:
                errors.append((
                    employee_id,
                    '4_weeks_constraints',
                    _('Per mėnesį negalima budėti daugiau, nei %s') % float_to_hrs_and_mins(budejimas_max_for_weeks),
                    _('Laikotarpiu budima %s') % float_to_hrs_and_mins(budejimas_time_for_check)
                ))

        def check_overlapping_time_constraints():
            day_ids = employee_work_schedule_days.filtered(lambda d: month_end_strf >= d.date >= month_start_strf)
            dates = day_ids.mapped('date')
            for date in dates:
                date_days = day_ids.filtered(lambda d: d.date == date)
                date_line_ids = date_days.mapped('line_ids').sorted(key=lambda r: (r['time_from'], r['time_to']))
                hours_from = date_line_ids[1:].mapped('time_from')
                hours_to = date_line_ids[:-1].mapped('time_to')
                if any(h_from < h_to for h_from, h_to in zip(hours_from, hours_to)):
                    errors.append((
                        employee_id,
                        'overlapping_line_times',
                        _('Persidengia darbo laikas datomis'),
                        str(date)
                    ))

        def check_3_month_constraints():
            check_from = month_start
            check_from = check_from - relativedelta(days=check_from.weekday())
            check_to = month_end + relativedelta(days=6-month_end.weekday())
            weeks = int(((check_to - check_from).days+1) / 7.0)  # P3:DivOK
            week_vd_sum_more_than_8_hrs = False
            for i in range(0, weeks):
                to_check_from = check_from+relativedelta(days=7.0*i)
                to_check_to = check_from+relativedelta(days=7.0*(i+1)-1)
                overtime_sum = sum(employee_work_schedule_days.filtered(lambda d: _strf(to_check_to) >= d.date >= _strf(to_check_from)).mapped('line_ids').filtered(lambda l: l.code in overtime_codes).mapped('worked_time_total'))
                if tools.float_compare(overtime_sum, 8.0, precision_digits=2) > 0:
                    week_vd_sum_more_than_8_hrs = True
                    break
            if week_vd_sum_more_than_8_hrs:
                check_from = month_start - relativedelta(months=2)
                check_from = check_from - relativedelta(days=check_from.weekday())
                check_to = month_end + relativedelta(days=6 - month_end.weekday())
                weeks = ((check_to - check_from).days+1) / 7.0  # P3:DivOK
                all_time_worked_sum = sum(employee_work_schedule_days.filtered(
                    lambda d: _strf(check_to) >= d.date >= _strf(check_from)).mapped('line_ids').filtered(lambda l: l.code in overtime_codes+factual_work_codes).mapped('worked_time_total'))
                avg_all_time_worked_sum = all_time_worked_sum / float(weeks)  # P3:DivOK
                if tools.float_compare(avg_all_time_worked_sum, 48.0, precision_digits=2) > 0:
                    errors.append((
                        employee_id,
                        '3_month_constraint',
                        _('Jei betkurią savaitę dirbama daugiau nei 8 val. viršvalandžių, per 3 mėnesius vidutis savaitės darbo laikas negali viršyti 48 val.'),
                        _('Laikotarpiu %s-%s dirbama vidutiniškai %s per savaitę') % (
                            _strf(check_from),
                            _strf(check_to),
                            float_to_hrs_and_mins(avg_all_time_worked_sum))
                    ))

        def check_shift_constraints():
            employee_shifts = employee_lines._get_work_shifts_of_employee()
            index = 0
            for shift in employee_shifts:
                next_shift = employee_shifts[index + 1] if len(employee_shifts) > index + 1 else False
                shift_lines = employee_work_schedule_days.mapped('line_ids').filtered(
                    lambda l: datetime.strptime(l.datetime_from, tools.DEFAULT_SERVER_DATETIME_FORMAT) <= shift[1] and datetime.strptime(l.datetime_to, tools.DEFAULT_SERVER_DATETIME_FORMAT) >= shift[0])
                factual_lines = shift_lines.filtered(lambda l: l.code in factual_work_codes)
                active_budejimas_lines = shift_lines.filtered(lambda l: l.code in active_budejimas_codes)
                passive_budejimas_lines = shift_lines.filtered(lambda l: l.code in passive_budejimas_codes)
                budejimas_lines = active_budejimas_lines
                budejimas_lines |= passive_budejimas_lines
                worked_shift_lines = (factual_lines + budejimas_lines).sorted(lambda l: l.datetime_from)
                # shift_start_date = worked_shift_lines[0].date
                # shift_appointment = objects_for_period(employee_appointments, shift_start_date, shift_start_date)
                # is_suskaidytos = shift_appointment.schedule_template_id.template_type == 'suskaidytos' if shift_appointment else False
                # if not budejimas_lines and len(worked_shift_lines) > 1 and not is_suskaidytos:
                #     start_end_times = [(
                #         datetime.strptime(line.datetime_from, tools.DEFAULT_SERVER_DATETIME_FORMAT),
                #         datetime.strptime(line.datetime_to, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                #     ) for line in worked_shift_lines]
                #     range_length = len(start_end_times)
                #     x = 0
                #     while x < range_length:
                #         curr_period = start_end_times[x]
                #         if len(start_end_times) - 1 >= x + 1:
                #             next_period = start_end_times[x + 1]
                #             if next_period[0] == curr_period[1]:
                #                 start_end_times[x + 1] = (curr_period[0], next_period[1])
                #                 start_end_times.pop(x)
                #                 range_length -= 1
                #                 x -= 1
                #         x += 1
                #     if len(start_end_times) > 1:
                #         time_diff = (start_end_times[1][0] - start_end_times[0][1]).total_seconds() / 3600.0
                #     else:
                #         time_diff = 0.0
                #     if not (minimum_time_between_breaks <= time_diff <= maximum_time_between_breaks):
                #         msg_formatting = _('Dieną %s pirmos pertraukos trukmė yra %s') % (shift_start_date, float_to_hrs_and_mins(time_diff)) if not tools.float_is_zero(time_diff, precision_digits=2) else _('Dieną %s darbuotojas neturi pertraukos.') % shift_start_date
                #         errors.append((
                #             employee_id,
                #             'shift_constraints',
                #             _('Pirmos pertraukos trukmė turi būti tarp %s ir %s') % (float_to_hrs_and_mins(minimum_time_between_breaks), float_to_hrs_and_mins(maximum_time_between_breaks)),
                #             msg_formatting
                #         ))
                #
                #     if tools.float_compare((start_end_times[0][1] - start_end_times[0][0]).total_seconds() / 3600.0, maximum_work_time_to_break, precision_digits=2) > 0 and not tools.float_is_zero(time_diff, precision_digits=2):
                #         errors.append((
                #             employee_id,
                #             'shift_constraints',
                #             _('Pirma pertrauka turi prasidėti anksčiau nei %s po darbo pradžios') % (float_to_hrs_and_mins(maximum_work_time_to_break)),
                #             _('Dieną %s pirma pertrauka prasideda po %s') % (shift_start_date, float_to_hrs_and_mins((start_end_times[0][1] - start_end_times[0][0]).total_seconds() / 3600.0))
                #         ))

                if tools.float_compare(sum(factual_lines.mapped('worked_time_total')), daily_hour_limit,precision_digits=2) > 0:
                    errors.append((
                        employee_id,
                        'shift_constraints',
                        _('Darbo laikas per pamainą negali viršyti %s') % float_to_hrs_and_mins(daily_hour_limit),
                        _('Pamainą %s - %s darbuotojas dirba %s') % (shift[0], shift[1], float_to_hrs_and_mins(sum(factual_lines.mapped('worked_time_total'))))
                    ))

                worked_shift_lines_worked_time = sum(worked_shift_lines.mapped('worked_time_total'))
                active_budejimas_lines_worked_time = sum(active_budejimas_lines.mapped('worked_time_total'))
                if bool(tools.float_compare(active_budejimas_lines_worked_time, 11.0, precision_digits=2) > 0 and (passive_budejimas_lines or factual_lines)):
                    # if passive_budejimas_lines or (next_shift and employee_work_schedule_days.mapped('line_ids').filtered(
                    #         lambda l: datetime.strptime(l.datetime_from, tools.DEFAULT_SERVER_DATETIME_FORMAT) <= next_shift[1]
                    #                   and datetime.strptime(l.datetime_to, tools.DEFAULT_SERVER_DATETIME_FORMAT) >= next_shift[0])):
                    errors.append((
                        employee_id,
                        'shift_constraints',
                        _('Esant budėjimui, kuris trunka ilgiau nei 11 valandų, negali būti papildomai nustatomas darbo laikas'),
                        _('Pamainą %s - %s darbuotojui nustatytas papildomas darbo laikas') % (shift[0], shift[1])
                    ))

                if next_shift:
                    min_time_between_shifts = minimum_time_between_shifts_lower if tools.float_compare(
                        worked_shift_lines_worked_time, shift_break_threshold,
                        precision_digits=2) <= 0 else minimum_time_between_shifts_higher
                    time_between_shifts = (next_shift[0] - shift[1]).total_seconds() / 3600.0  # P3:DivOK
                    if tools.float_compare(min_time_between_shifts, time_between_shifts, precision_digits=2) > 0:
                        errors.append((
                            employee_id,
                            'shift_constraints',
                            _('Poilsio laikas tarp pamainų turi trukti ilgiau nei %s') % float_to_hrs_and_mins(min_time_between_shifts),
                            _('Tarp pamainos %s - %s ir %s - %s nustatytas %s poilsio laikas') % (shift[0], shift[1], next_shift[0], next_shift[1], float_to_hrs_and_mins(time_between_shifts))
                        ))

                if tools.float_compare(active_budejimas_lines_worked_time, maximum_active_budejimas_time,
                                       precision_digits=2) > 0:
                    errors.append((
                        employee_id,
                        'shift_constraints',
                        _('Aktyvus budėjimas negali trukti ilgiau nei %s') % float_to_hrs_and_mins(maximum_active_budejimas_time),
                        _('Pamainą %s - %s budėjimas trunka %s') % (shift[0], shift[1], float_to_hrs_and_mins(active_budejimas_lines_worked_time))
                    ))
                index += 1

        def check_correct_downtime_times(lines):
            for line in lines:
                day_ids = line.mapped('day_ids')
                if not day_ids:
                    continue
                full_downtime_records = line.env['hr.employee.downtime'].sudo().search([
                    ('date_from_date_format', '<=', max(day_ids.mapped('date'))),
                    ('date_to_date_format', '>=', min(day_ids.mapped('date'))),
                    ('employee_id', '=', line.employee_id.id),
                    ('downtime_type', '=', 'full'),
                    ('holiday_id.state', '=', 'validate')
                ])
                for downtime_record in full_downtime_records:
                    downtime_from = downtime_record.date_from_date_format
                    downtime_to = downtime_record.date_to_date_format
                    schedule_downtime_days = day_ids.filtered(
                        lambda day: downtime_from <= day.date <= downtime_to
                    )
                    if not schedule_downtime_days:
                        errors.append((
                            line.employee_id.id,
                            'downtime_constraints',
                            _('Egzistuojant pilnai prastovai privaloma nurodyti prastovos laiką'),
                            _('Periode %s - %s nenurodytas prastovos laikas') % (
                            downtime_from, downtime_to))
                        )
                        continue
                    days_with_lines = schedule_downtime_days.filtered(
                        lambda day: any(fcode in day.mapped('line_ids.code') for fcode in factual_work_codes))
                    if days_with_lines:
                        errors.append((
                            line.employee_id.id,
                            'downtime_constraints',
                            _('Pilnos prastovos periode nustatytas darbo laikas'),
                            _('Periode %s - %s nustatytas darbo laikas, kurio neturėtų būti, nes šiame periode yra '
                              'paskelbta prastova') % (
                                downtime_from, downtime_to))
                        )

        errors = []
        if not self:
            return ''
        if len(set(self.mapped('year'))) > 1 or len(set(self.mapped('month'))) > 1 or len(set(self.mapped('work_schedule_id'))) > 1:
            raise exceptions.UserError(_('Šių apribojimų tikrinimas galimas tik vieno periodo eilutėm'))

        year = self.mapped('year')[0]
        month = self.mapped('month')[0]
        month_start = datetime(year, month, 1)
        month_end = month_start + relativedelta(day=31)
        month_start_strf = _strf(month_start)
        month_end_strf = _strf(month_end)
        work_schedule_id = self.mapped('work_schedule_id')[0]
        factual_work_schedule = self.env.ref('work_schedule.factual_company_schedule')
        is_factual_schedule = factual_work_schedule.id == work_schedule_id.id
        employee_ids = self.mapped('employee_id.id')

        company_id = self.env.user.company_id.with_context(date=month_start_strf)
        max_overtime_per_year = company_id.max_overtime_per_year
        hour_limit = company_id.max_7_day_time
        sumine_hour_limit = company_id.max_7_day_sumine_apskaita_time
        extra_contract_hour_limit = company_id.max_7_day_including_extra_time
        overtime_hour_limit = company_id.max_7_day_overtime_time
        main_7_day_break_length = company_id.main_7_day_break_length
        minimum_time_between_breaks = company_id.minimum_time_between_breaks
        maximum_time_between_breaks = company_id.maximum_time_between_breaks
        daily_hour_limit = company_id.max_daily_time
        maximum_active_budejimas_time = company_id.maximum_active_budejimas_time
        maximum_work_time_to_break = company_id.maximum_work_time_to_break
        minimum_time_between_shifts_higher = company_id.minimum_time_between_shifts_higher
        minimum_time_between_shifts_lower = company_id.minimum_time_between_shifts_lower
        shift_break_threshold = company_id.shift_break_threshold

        min_date_for_checks = month_start - relativedelta(years=1)
        max_date_for_checks = month_end + relativedelta(days=6)
        max_date_for_checks_strf = _strf(max_date_for_checks)
        min_date_for_checks_strf = _strf(min_date_for_checks)

        all_worked_codes = active_budejimas_codes + passive_budejimas_codes + factual_work_codes + overtime_codes

        all_lines_to_check = self.search([
            ('work_schedule_id', '=', work_schedule_id.id),
            ('employee_id', 'in', employee_ids),
            ('year', '=', year),
            ('month', '=', month),
            '|',
            ('state', '!=', 'draft'),
            ('id', 'in', self.mapped('id')),
        ])

        all_work_schedule_days_for_checks = self.env['work.schedule.day'].search([
            ('work_schedule_id', '=', work_schedule_id.id),
            ('employee_id', 'in', employee_ids),
            ('date', '<=', max_date_for_checks_strf),
            ('date', '>=', min_date_for_checks_strf),
            '|',
            ('state', '!=', 'draft'),
            ('work_schedule_line_id.id', 'in', self.mapped('id')),
        ])
        if is_factual_schedule:
            all_work_schedule_days_for_checks = all_work_schedule_days_for_checks.filtered(lambda d: not d.schedule_holiday_id)

        all_contracts_for_checks = self.sudo().env['hr.contract'].search([
            ('employee_id', 'in', employee_ids),
            ('date_start', '<=', max_date_for_checks_strf),
            '|',
            ('date_end', '>=', min_date_for_checks_strf),
            ('date_end', '=', False)
        ])

        all_appointments_for_checks = all_contracts_for_checks.mapped('appointment_ids').filtered(lambda a:
            a.date_start <= max_date_for_checks_strf and
            (not a.date_end or a.date_end >= min_date_for_checks_strf))

        for employee_id in employee_ids:
            employee_lines = all_lines_to_check.filtered(lambda l: l.employee_id.id == employee_id)
            employee_work_schedule_days = all_work_schedule_days_for_checks.filtered(lambda d: d.employee_id.id == employee_id)
            employee_appointments = all_appointments_for_checks.filtered(lambda a: a.employee_id.id == employee_id)

            check_yearly_overtime_constraints_for_employee()
            check_any_seven_days_constraints()
            check_overlapping_time_constraints()
            # check_4_weeks_constraints()
            check_3_month_constraints()
            check_correct_downtime_times(employee_lines)
            check_shift_constraints()
        earliest_date = min(all_lines_to_check.mapped('day_ids.date'))
        underage_employee_ids = self.env['hr.employee'].browse(employee_ids).with_context(date=earliest_date).filtered(
            lambda e: e.is_underage
        )
        for employee_id in underage_employee_ids:
            employee_lines = all_lines_to_check.filtered(lambda l: l.employee_id.id == employee_id.id)
            employee_schedule_lines = employee_lines.mapped('day_ids.line_ids')

            date_employee_becomes_18 = employee_id.date_employee_becomes_18
            if date_employee_becomes_18:
                employee_schedule_lines = employee_schedule_lines.filtered(lambda l: l.date < date_employee_becomes_18)

            watch_home_codes = PAYROLL_CODES.get('WATCH_HOME', ['BN'])
            watch_home_lines = employee_schedule_lines.filtered(lambda l: l.code in watch_home_codes)
            watch_home_dates = watch_home_lines.mapped('date')
            for watch_home_date in watch_home_dates:
                errors.append((
                    employee_id.id,
                    'underage_watch_home_constraint',
                    _('Nepilnametis darbuotojas negali būti skiriamas budėjimui namuose'),
                    _('Darbuotojo grafike datai {0} nustatytas budėjimas namuose').format(watch_home_date)
                ))

            night_start = 22  # TODO Create a work schedule setting and take it from there
            night_end = 6
            if employee_id.is_child:
                night_start = 20

            night_lines = employee_schedule_lines.filtered(lambda l: night_start < l.time_to)
            night_lines |= employee_schedule_lines.filtered(lambda l: l.time_from < night_end)

            night_line_dates = list(set(night_lines.mapped('date')))
            for night_line_date in night_line_dates:
                errors.append((
                    employee_id.id,
                    'underage_night_constraint',
                    _('Nepilnametis darbuotojas negali būti skiriamas darbui naktį'),
                    _('Darbuotojo grafike datai {0} nustatytas darbas naktį').format(night_line_date)
                ))

            employee_period_education_schedules = self.env['hr.employee.education.year.schedule'].sudo().search([
                ('employee_id', '=', employee_id.id),
                ('date_from', '<=', month_end.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)),
                ('date_to', '>=', month_start.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
            ])
            schedule_education_days = []
            for employee_period_education_schedule in employee_period_education_schedules:
                education_schedule_start = employee_period_education_schedule.date_from
                education_schedule_end = employee_period_education_schedule.date_to
                start_dt = datetime.strptime(education_schedule_start, tools.DEFAULT_SERVER_DATE_FORMAT)
                end_dt = datetime.strptime(education_schedule_end, tools.DEFAULT_SERVER_DATE_FORMAT)
                schedule_education_weekdays = employee_period_education_schedule.mapped('education_day_ids.dayofweek')
                while start_dt <= end_dt:
                    weekday = str(start_dt.weekday())
                    if weekday in schedule_education_weekdays:
                        schedule_education_days.append(start_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
                    start_dt += relativedelta(days=1)

            morning_start = 6  # TODO Create a work schedule setting and take it from there
            morning_end = 7
            morning_lines = employee_schedule_lines.filtered(lambda l: l.time_from < morning_end and
                                                                       morning_start < l.time_to and
                                                                       l.date in schedule_education_days)
            for morning_line in morning_lines:
                errors.append((
                    employee_id.id,
                    'underage_morning_constraints',
                    _('Nepilnametis darbuotojas negali būti skiriamas dirbti tarp {0} val. ir {1} val. mokslo dienomis').format(morning_start, morning_end),
                    _('Darbuotojo grafike datai {0} nustatytas darbas ryte').format(morning_line.date)
                ))

            start = month_start
            end = month_end
            school_years = self.env['hr.employee.education.year'].sudo().search([
                ('employee_id', '=', employee_id.id),
                ('date_from', '<=', month_end),
                ('date_to', '>=', month_start)
            ])
            while start <= end:
                check_date = start.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                curr_weekday = start.weekday()
                date_lines = employee_schedule_lines.filtered(lambda l: l.date == check_date)
                work_time_total = sum(date_lines.mapped('worked_time_total'))
                date_school_years = school_years.filtered(lambda y: y.date_from <= check_date <= y.date_to)
                school_year_schedules = date_school_years.mapped('education_schedule_ids').filtered(
                    lambda s: s.date_from <= check_date <= s.date_to)
                school_weekdays = list(set(school_year_schedules.mapped('education_day_ids.dayofweek')))
                daily_limit = 8
                if employee_id.is_child:
                    daily_limit = 6
                    if school_weekdays and str(curr_weekday) in school_weekdays:
                        daily_limit = 2
                elif employee_id.is_teenager and school_weekdays:
                    daily_limit -= sum(school_year_schedules.mapped('education_day_ids').filtered(lambda d: d.dayofweek == str(curr_weekday)).mapped('time_total'))
                daily_limit = max(daily_limit, 0.0)
                if tools.float_compare(work_time_total, daily_limit, precision_digits=2) > 0:
                    errors.append((
                        employee_id.id,
                        'underage_daily_work_norm_constraints',
                        _('Nepilnametis darbuotojas šiomis dienomis dirba daugiau, nei leidžia įstatymai'),
                        _('Įstatymai datai {0} šiam darbuotojui leidžia dirbti {1} val., o šis darbuotojas dirba {2} '
                          'val.').format(check_date, daily_limit, work_time_total)
                    ))
                start += relativedelta(days=1)

            check_from = month_start
            check_from = check_from - relativedelta(days=check_from.weekday())
            check_to = month_end + relativedelta(days=6 - month_end.weekday())
            weeks = int(((check_to - check_from).days + 1) / 7.0)  # P3:DivOK
            for i in range(0, weeks):
                to_check_from = check_from + relativedelta(days=7.0 * i)
                to_check_to = check_from + relativedelta(days=7.0 * (i + 1) - 1)
                employee_work_schedule_days = employee_lines.mapped('day_ids')
                work_days = employee_work_schedule_days.filtered(
                    lambda d: _strf(to_check_to) >= d.date >= _strf(to_check_from) and
                              not tools.float_is_zero(sum(d.mapped('line_ids.worked_time_total')),  precision_digits=2)
                )
                if date_employee_becomes_18:
                    work_days = work_days.filtered(lambda d: d.date < date_employee_becomes_18)
                week_dates = [_strf(to_check_from+relativedelta(days=i)) for i in range(0, 7)]
                worked_dates = work_days.mapped('date')
                not_worked_dates = list(set([week_date for week_date in week_dates if week_date not in worked_dates]))
                if len(not_worked_dates) < 2:
                    errors.append((
                        employee_id.id,
                        'underage_weekly_free_days_constraint',
                        _('Nepilnametis darbuotojas privalo turėti bent 2 laisvas dienas per savaitę'),
                        _('Laikotarpiu %s - %s darbuotojas neturi pakankamai laisvų dienų') % (_strf(to_check_from), _strf(to_check_to))
                    ))

                not_worked_week_days = [datetime.strptime(not_worked_date, tools.DEFAULT_SERVER_DATE_FORMAT).weekday() for not_worked_date in not_worked_dates]
                if 6 not in not_worked_week_days:
                    errors.append((
                        employee_id.id,
                        'underage_weekly_sundays_free_constraint',
                        _('Nepilnametis darbuotojas privalo turėti laisvus sekmadienius'),
                        _('%s darbuotojas neturi laisvo sekmadienio') % (_strf(to_check_to))
                    ))

                work_sum = sum(work_days.mapped('line_ids').mapped('worked_time_total'))
                date_school_years = school_years.filtered(lambda y: y.date_from <= _strf(to_check_to) and y.date_to >= _strf(to_check_from))
                school_year_schedules = date_school_years.mapped('education_schedule_ids').filtered(lambda y: y.date_from <= _strf(to_check_to) and y.date_to >= _strf(to_check_from))
                school_weekdays = school_year_schedules.mapped('education_day_ids')
                school_duration = sum(school_weekdays.mapped('time_total'))
                week_limit = 40  # TODO Create a work schedule setting and take it from there
                if employee_id.is_child:
                    week_limit = 30
                    if school_weekdays:
                        week_limit = 12
                elif employee_id.is_teenager and school_weekdays:
                    week_limit -= school_duration
                week_limit = max(week_limit, 0.0)

                if tools.float_compare(work_sum, week_limit, precision_digits=2) > 0:
                    errors.append((
                        employee_id.id,
                        'underage_weekly_constraint',
                        _('Nepilnametis darbuotojas viršija savaitės dirbtų valandų skaičių'),
                        _('Laikotarpiu %s - %s darbuotojas dirba %s per savaitę. (Daugiausia leidžiama dirbti %s val.)') % (_strf(to_check_from), _strf(to_check_to), float_to_hrs_and_mins(work_sum), str(week_limit))
                    ))

            employee_shifts = employee_lines._get_work_shifts_of_employee()
            index = 0
            min_time_between_shifts = 12  # TODO Create a work schedule setting and take it from there
            if employee_id.is_child:
                min_time_between_shifts = 14
            for shift in employee_shifts:
                next_shift = employee_shifts[index + 1] if len(employee_shifts) > index + 1 else False
                if next_shift:
                    time_between_shifts = (next_shift[0] - shift[1]).total_seconds() / 3600.0  # P3:DivOK
                    if tools.float_compare(min_time_between_shifts, time_between_shifts, precision_digits=2) > 0:
                        errors.append((
                            employee_id.id,
                            'underage_shift_constraints',
                            _('Nepilnamečio darbuotojo poilsio laikas tarp pamainų turi trukti ilgiau nei %s') % float_to_hrs_and_mins(min_time_between_shifts),
                            _('Tarp pamainos %s - %s ir %s - %s nustatytas %s poilsio laikas') % (
                            shift[0], shift[1], next_shift[0], next_shift[1],
                            float_to_hrs_and_mins(time_between_shifts))
                        ))
                index += 1

        return self.format_error_tuple_to_string(list(set(errors)))

    def format_error_tuple_to_string(self, errors):
        msg = ''
        if errors:
            employees = self.env['hr.employee'].browse(set([err[0] for err in errors]))
            for employee in employees:
                msg += _('Neatitikimai darbuotojo %s grafike:\n') % employee.name_related
                employee_errors = [err for err in errors if err[0] == employee.id]
                error_types = list(set([err[1] for err in employee_errors]))
                for err_type in error_types:
                    error_type_strings = set([err[2] for err in employee_errors if err[1] == err_type])
                    for error_type_string in error_type_strings:
                        msg += error_type_string + '\n'
                        error_type_string_errors = [err for err in employee_errors if err[1] == err_type and err[2] == error_type_string]
                        error_type_string_errors.sort()
                        for final_error in error_type_string_errors:
                            msg += final_error[3] + '\n'
                        msg += '\n'
                    msg += '\n'
                msg += '\n\n'
        return msg


    @api.multi
    def _get_work_shifts_of_employee(self):
        minimum_time_between_shifts = self.env.user.company_id.minimum_time_between_shifts_lower
        month_start = datetime(self[0].year, self[0].month, 1)
        month_end = month_start + relativedelta(day=31)
        range_from = month_start - relativedelta(days=1)
        range_to = month_end + relativedelta(days=1)
        range_from_strf = range_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        range_to_strf = range_to.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        range_days = self.env['work.schedule.day'].search([
            ('work_schedule_id', 'in', self.mapped('work_schedule_id.id')),
            ('date', '>=', range_from_strf),
            ('date', '<=', range_to_strf),
            ('employee_id', 'in', self.mapped('employee_id.id')),
            '|',
            ('state', '!=', 'draft'),
            ('id', 'in', self.mapped('day_ids.id'))
        ])
        factual_work_schedule = self.env.ref('work_schedule.factual_company_schedule')
        planned_schedule_days = range_days.filtered(lambda d: d.work_schedule_id.id != factual_work_schedule.id)
        factual_schedule_days = range_days.filtered(lambda d: d.work_schedule_id.id == factual_work_schedule.id)
        range_days = planned_schedule_days + factual_schedule_days.filtered(lambda d: not d.schedule_holiday_id)

        worked_time = []

        if not range_days:
            return worked_time

        date_dt = range_from
        while date_dt <= range_to:
            curr_date = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            curr_days = range_days.filtered(lambda rd: rd.date == curr_date)
            curr_days_lines = curr_days.mapped('line_ids').filtered(lambda l: l.code in factual_work_codes+active_budejimas_codes+passive_budejimas_codes+overtime_codes)
            for line in curr_days_lines.sorted(key='time_from'):
                worked_time.append((datetime.strptime(line.datetime_from, tools.DEFAULT_SERVER_DATETIME_FORMAT), datetime.strptime(line.datetime_to, tools.DEFAULT_SERVER_DATETIME_FORMAT)))
            date_dt += relativedelta(days=1)

        range_length = len(worked_time)
        i = 0
        while i < range_length:
            curr_period = worked_time[i]
            if len(worked_time) - 1 >= i + 1:
                next_period = worked_time[i + 1]
                curr_period_end_date_strp = curr_period[1]
                if next_period[0] < curr_period_end_date_strp + relativedelta(hours=minimum_time_between_shifts):
                    worked_time[i + 1] = (curr_period[0], next_period[1])
                    worked_time.pop(i)
                    range_length -= 1
                    i -= 1
            i += 1

        range_length = len(worked_time)
        i = 0
        while i < range_length:
            curr_period = worked_time[i]
            if (curr_period[0] < month_start and curr_period[1] <= month_start) or (
                    curr_period[0] >= month_end + relativedelta(days=1)):
                worked_time.pop(i)
                range_length -= 1
                i -= 1
            i += 1

        return worked_time


WorkScheduleLine()
