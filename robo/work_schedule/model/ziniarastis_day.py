# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, tools, exceptions
from odoo.tools.translate import _
from work_schedule import execute_multiple_insert_query
from six import iteritems


class ZiniarastisDay(models.Model):
    _inherit = 'ziniarastis.day'

    ziniarastis_day_lines = fields.One2many('ziniarastis.day.line', 'ziniarastis_id',
                                            inverse='update_schedule_from_ziniarastis')

    @api.multi
    def update_schedule_from_ziniarastis(self):
        if not self:
            return
        schedule_enabled = self.env.user.company_id.with_context(date=min(self.mapped('date'))).extended_schedule
        if not schedule_enabled or self._context.get('do_not_fill_schedule', False) or not self.env.user.is_accountant():
            return
        factual_work_schedule= self.env.ref('work_schedule.factual_company_schedule')
        work_schedule_holiday_code_tabelio_zymejimas_ids = self.env['work.schedule.codes'].search([('is_holiday', '=', True)]).mapped('tabelio_zymejimas_id')
        fd_zymejimas_id = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_FD')
        work_schedule_codes = self.env['work.schedule.codes'].search([])

        dates_dt = [datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT) for date in self.mapped('date')]
        periods = set([(date.year, date.month) for date in dates_dt])

        holidays_to_create = list()
        # schedule_day_lines_to_create = list()
        ziniarstis_periods_to_update = {}

        all_work_schedule_lines = self.env['work.schedule.day'].search([('date', 'in', self.mapped('date'))]).mapped('work_schedule_line_id').filtered(lambda l: l.work_schedule_id.id == factual_work_schedule.id)

        for period in periods:
            year = period[0]
            month = period[1]
            period_start_dt = datetime(period[0], period[1], 1)
            period_end_dt = period_start_dt + relativedelta(day=31)
            period_start = period_start_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            period_end = period_end_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

            period_ziniarastis_day_ids = self.filtered(lambda d: period_end >= d.date >= period_start)
            period_work_schedule_lines = all_work_schedule_lines.filtered(lambda l: l.year == period[0] and l.month == period[1])

            missing_employee_ids = set(period_ziniarastis_day_ids.mapped('employee_id.id')) - set(period_work_schedule_lines.mapped('employee_id.id'))
            for employee in missing_employee_ids:
                employee_id = self.env['hr.employee'].browse(employee)
                department_id = employee_id.department_id or self.env['hr.department'].search([], limit=1)
                if not department_id:
                    continue
                bypass_validated_ziniarastis = self._context.get('bypass_validated_ziniarastis', False)
                factual_work_schedule.with_context(do_not_fill_schedule=True).create_empty_schedule(year, month, [employee_id.id], [department_id.id], bypass_validated_time_sheets=bypass_validated_ziniarastis)

            for employee_id in period_ziniarastis_day_ids.mapped('employee_id'):
                employee_schedule_lines = period_work_schedule_lines.filtered(lambda l: l.employee_id.id == employee_id.id)
                ziniarastis_day_ids = period_ziniarastis_day_ids.filtered(lambda d: d.employee_id.id == employee_id.id)

                employee_schedule_line_id = False
                if len(employee_schedule_lines) > 1:
                    employee_department_id = employee_id.department_id
                    employee_schedule_line_id = employee_schedule_lines.filtered(lambda l: l.department_id.id == employee_department_id.id)

                if not employee_schedule_line_id:
                    if not employee_schedule_lines:
                        try:
                            bypass_validated_ziniarastis = self._context.get('bypass_validated_ziniarastis', False)
                            factual_work_schedule.with_context(do_not_fill_schedule=True).create_empty_schedule(year, month, [employee_id.id], [employee_id.department_id.id], bypass_validated_time_sheets=bypass_validated_ziniarastis)
                            employee_schedule_line_id = self.env['work.schedule.line'].search([
                                ('employee_id', '=', employee_id.id),
                                ('department_id', '=', employee_id.department_id.id),
                                ('year', '=', year),
                                ('month', '=', month)
                            ])
                        except:
                            employee_schedule_line_id = False
                    else:
                        employee_schedule_line_id = employee_schedule_lines[0]

                if not employee_schedule_line_id:
                    continue

                work_schedule_day_ids = employee_schedule_line_id.mapped('day_ids')

                for ziniarastis_day_id in ziniarastis_day_ids:
                    date = ziniarastis_day_id.date
                    date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)

                    period_line_id = str(ziniarastis_day_id.ziniarastis_period_line_id.id)
                    if not ziniarstis_periods_to_update.get(period_line_id):
                        ziniarstis_periods_to_update[period_line_id] = [date]
                    else:
                        ziniarstis_periods_to_update[period_line_id].append(date)

                    work_schedule_day_id = work_schedule_day_ids.filtered(lambda d: d.date == ziniarastis_day_id.date)
                    if not work_schedule_day_id:
                        work_schedule_day_id = self.env['work.schedule.day'].create({
                            'work_schedule_line_id': employee_schedule_line_id.id,
                            'date': date,
                            'business_trip': ziniarastis_day_id.business_trip,
                        })
                    work_schedule_day_id.mapped('line_ids').with_context(allow_delete_special=True).unlink()

                    line_ids = ziniarastis_day_id.mapped('ziniarastis_day_lines').filtered(lambda l: l.write_uid)

                    if not line_ids:
                        continue
                    # P3:DivOK
                    total_worked_time = sum(line_ids.mapped('worked_time_hours')) + sum(line_ids.mapped('worked_time_minutes')) / 60.0
                    if tools.float_compare(total_worked_time, 24, precision_digits=2) > 0:
                        raise exceptions.UserError(_('Nustatytų laiko reikšmių suma %s datai viršija 24 valandų limitą') % date)

                    date_appointment = ziniarastis_day_id.contract_id.with_context(date=date).appointment_id
                    fixed_attendance_ids = date_appointment.schedule_template_id.fixed_attendance_ids
                    day_of_week_fixed_attendance_ids = fixed_attendance_ids.filtered(
                        lambda a: a.dayofweek == str(date_dt.weekday())).sorted(key='hour_from')
                    time_start = day_of_week_fixed_attendance_ids[
                        0].hour_from if day_of_week_fixed_attendance_ids else 8.0
                    time_possible_to_add = 24.0 - time_start
                    time_start -= max(total_worked_time - time_possible_to_add, 0.0)

                    for zymejimas in line_ids.mapped('tabelio_zymejimas_id'):
                        zymejimas_lines = line_ids.filtered(lambda l: l.tabelio_zymejimas_id.id == zymejimas.id)
                        zymejimas_time_hours = sum(zymejimas_lines.mapped('worked_time_hours')) + \
                                               sum(zymejimas_lines.mapped('worked_time_minutes')) / 60.0  # P3:DivOK
                        zymejimas_to_use = zymejimas
                        if zymejimas.id in work_schedule_holiday_code_tabelio_zymejimas_ids.mapped('id'):
                            schedule_holiday = work_schedule_day_id.schedule_holiday_id
                            if not schedule_holiday:
                                holidays_to_create.append({
                                    'employee_id': employee_id.id,
                                    'date_from': date,
                                    'date_to': date,
                                    'holiday_status_id': zymejimas.holiday_status_ids.id
                                })
                                zymejimas_to_use = fd_zymejimas_id
                            else:
                                same_type = work_schedule_day_id.schedule_holiday_id.holiday_status_id == \
                                            zymejimas.holiday_status_ids
                                zymejimas_to_use = fd_zymejimas_id
                                if not same_type:
                                    date_from = schedule_holiday.date_from
                                    date_to = schedule_holiday.date_to
                                    date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
                                    day_before_dt = date_dt - relativedelta(days=1)
                                    day_after_dt = date_dt + relativedelta(days=1)
                                    day_before = day_before_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                                    day_after = day_after_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                                    if date_from < date:
                                        schedule_holiday.write({'date_to': day_before})
                                    if date_to > date:
                                        schedule_holiday.copy({'date_from': day_after})
                                    if schedule_holiday.date_to >= date:  # Date from is always before date
                                        schedule_holiday.unlink()  # Will raise error if holiday is confirmed
                                    holidays_to_create.append({
                                        'employee_id': employee_id.id,
                                        'date_from': date,
                                        'date_to': date,
                                        'holiday_status_id': zymejimas.holiday_status_ids.id
                                    })

                        if tools.float_is_zero(zymejimas_time_hours, precision_digits=2):
                            continue

                        zymejimas_to_use = work_schedule_codes.filtered(
                            lambda c: c.tabelio_zymejimas_id.id == zymejimas_to_use.id).id
                        if not zymejimas_to_use:
                            zymejimas_to_use = work_schedule_codes.filtered(
                                lambda c: c.tabelio_zymejimas_id.id == fd_zymejimas_id.id).id

                        self.env['work.schedule.day.line'].create({
                            'day_id': work_schedule_day_id.id,
                            'work_schedule_code_id': zymejimas_to_use,
                            'time_from': time_start,
                            'time_to': time_start + zymejimas_time_hours,
                        })
                        time_start += zymejimas_time_hours

        execute_multiple_insert_query(self, "work_schedule_holidays", holidays_to_create)
        # execute_multiple_insert_query(self, "work_schedule_day_line", schedule_day_lines_to_create)

        for line_id, dates in iteritems(ziniarstis_periods_to_update):
            self.env['ziniarastis.period.line'].browse(int(line_id)).auto_fill_period_line(dates=dates)


ZiniarastisDay()