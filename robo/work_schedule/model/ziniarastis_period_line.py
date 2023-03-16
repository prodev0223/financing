# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import datetime

from odoo import api, models, tools


class ZiniarastisPeriodLine(models.Model):
    _inherit = 'ziniarastis.period.line'

    @api.multi
    def _get_auto_fill_data(self, dates):
        if not self.env.user.company_id.with_context(date=self.date_to).extended_schedule:
            return super(ZiniarastisPeriodLine, self)._get_auto_fill_data(dates)
        self.ensure_one()
        full_data_hours_by_date = defaultdict(lambda: defaultdict(lambda: (0.0, 0.0)))
        date_to_use = max(self.date_from, self.contract_id.date_start)
        date_dt = datetime.strptime(date_to_use, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_use = min(self.contract_id.date_end or self.date_to, self.date_to)
        date_to_dt = datetime.strptime(date_to_use, tools.DEFAULT_SERVER_DATE_FORMAT)
        different_dates = [datetime(year=date_dt.year, month=date_dt.month, day=day).strftime(tools.DEFAULT_SERVER_DATE_FORMAT) for day in range(date_dt.day, date_to_dt.day + 1)]
        holiday_status_business_trip = self.env.ref('hr_holidays.holiday_status_K')
        day_ids = self.env['work.schedule.day'].search(
            [('employee_id', '=', self.employee_id.id),
             ('date', 'in', different_dates)])
        force_work_schedule_line_ids = self._context.get('work_schedule_line_ids', False)
        if force_work_schedule_line_ids:
            day_ids.filtered(lambda d: d.work_schedule_line_id.id in force_work_schedule_line_ids)
        factual_work_schedule = self.env.ref('work_schedule.factual_company_schedule')
        main_work_schedule = self.env.ref('work_schedule.planned_company_schedule')

        national_holiday_dates = self.env['sistema.iseigines'].sudo().search([
            ('date', 'in', different_dates),
        ]).mapped('date')

        if different_dates:
            downtimes = self.env['hr.employee.downtime'].sudo().search([
                ('employee_id', '=', self.employee_id.id),
                ('date_from_date_format', '<=', max(different_dates)),
                ('date_to_date_format', '>=', min(different_dates)),
                ('holiday_id.state', '=', 'validate')
            ])
            downtime_status_code = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_PN').id

        # Get forced work times
        forced_work_dates = self.env['hr.employee.forced.work.time'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('date', 'in', different_dates),
        ]).mapped('date')

        # These holidays will show work norm for that day in ziniarastis rather than the planned time.
        holiday_codes_to_show_work_norm_for = [
            self.env.ref('hr_holidays.holiday_status_cl').kodas,
            self.env.ref('hr_holidays.holiday_status_M').kodas
        ]

        for date in different_dates:
            is_date_downtime = bool(downtimes.filtered(lambda downtime: downtime.date_from_date_format <= date and
                                                                        downtime.date_to_date_format >= date))
            date_day_ids = day_ids.filtered(lambda d: d.date == date)
            planned_day_ids = date_day_ids.filtered(lambda d: d.work_schedule_id.id == main_work_schedule.id).filtered(
                lambda d: d.work_schedule_line_id.used_as_planned_schedule_in_calculations
            )
            factual_day_ids = date_day_ids.filtered(lambda d: d.work_schedule_id.id == factual_work_schedule.id and d.work_schedule_line_id.state == 'done')

            factual_day_holidays = factual_day_ids.mapped('schedule_holiday_id')

            is_forced_work_date = date in forced_work_dates

            # If there are any holidays we take the worked time from the schedule that was planned
            if factual_day_holidays and \
                    factual_day_holidays.holiday_status_id.id != holiday_status_business_trip.id and \
                    not is_forced_work_date:
                zymejimas_id = factual_day_holidays.holiday_status_id.tabelio_zymejimas_id.id
                holiday_tabelio_code = factual_day_holidays.holiday_status_id.tabelio_zymejimas_id.code
                total_h = 0.0
                show_work_norm = holiday_tabelio_code in holiday_codes_to_show_work_norm_for
                if not show_work_norm:
                    factual_day_lines = factual_day_ids.mapped('line_ids') if factual_day_ids else False
                    holiday_work_time_lines_for_day = factual_day_lines.filtered(
                        lambda l: l.work_schedule_code_id.code == holiday_tabelio_code) if factual_day_lines else False
                    if planned_day_ids:
                        total_h = sum(planned_day_ids.mapped('line_ids.worked_time_total'))
                    elif holiday_work_time_lines_for_day:
                        total_h = sum(holiday_work_time_lines_for_day.mapped('worked_time_total'))
                if (tools.float_is_zero(total_h, precision_digits=2) and not planned_day_ids) or show_work_norm:
                    if date_day_ids and date not in national_holiday_dates:
                        schedule_template = date_day_ids[0].appointment_id.schedule_template_id
                        off_days = schedule_template.off_days()
                        date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
                        if date_dt.weekday() not in off_days:
                            total_h = schedule_template.avg_hours_per_day or 1.0
                time_hours, time_minutes = divmod(total_h * 60, 60)
                if tools.float_compare(int(round(time_minutes)), 60, precision_digits=3) == 0:
                    time_minutes = 0
                    time_hours += 1
                full_data_hours_by_date[date][zymejimas_id] = (round(time_hours), round(time_minutes))
            else:
                factual_day_line_ids = factual_day_ids.mapped('line_ids')
                # Add zero values for downtime to correctly determine work norm in ziniarastis. It's a special case
                # because downtime is not a holiday, but rather work time line with an unique code in work schedule.
                if not factual_day_line_ids and is_date_downtime:
                    full_data_hours_by_date[date][downtime_status_code] = (0.0, 0.0)
                for zymejimas in set(factual_day_line_ids.mapped('tabelio_zymejimas_id.id')):
                    zymejimas_lines = factual_day_line_ids.filtered(lambda l: l.tabelio_zymejimas_id.id == zymejimas)
                    total_h = sum(l.worked_time_total for l in zymejimas_lines)
                    time_hours, time_minutes = divmod(total_h * 60, 60)
                    if tools.float_compare(int(round(time_minutes)), 60, precision_digits=3) == 0:
                        time_minutes = 0
                        time_hours += 1
                    full_data_hours_by_date[date][zymejimas] = (round(time_hours), round(time_minutes))

        full_data_different_days = full_data_hours_by_date.keys()
        dates_with_appointment = set(full_data_different_days)
        return full_data_hours_by_date, full_data_different_days, dates_with_appointment

    @api.multi
    def auto_fill_period_line(self, dates=None):
        res = super(ZiniarastisPeriodLine,self.with_context(do_not_fill_schedule=True)).auto_fill_period_line(dates)
        date = min(dates) if dates and isinstance(dates, list) else None
        if not date and self.exists():
            dates_from = self.exists().mapped('date_from')
            if dates_from:
                date = min(dates_from)
        if not date:
            date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        schedule_enabled = False
        if date:
            schedule_enabled = self.env.user.company_id.with_context(date=date).extended_schedule
        if not schedule_enabled:
            return res

        for rec in self:
            try:  # Auto fill period line might remove the line completely thus record still in self but without any
                  # values. This part is not super important so we can surround in a try-except clause
                work_schedule_days = self.env['work.schedule.day'].search([
                    ('work_schedule_id.schedule_type', '=', 'planned'),
                    ('employee_id', '=', rec.employee_id.id),
                    ('date', '>=', rec.date_from),
                    ('date', '<=', rec.date_to)
                ])
            except:
                continue
            if dates:
                work_schedule_days = work_schedule_days.filtered(lambda d: d.date in dates)
            for work_schedule_day in work_schedule_days:
                factual_day_lines = work_schedule_day.mapped('line_ids').filtered(lambda l: l.code in ['FD', 'NT', 'DLS'] and not tools.float_is_zero(l.worked_time_hours + l.worked_time_minutes, precision_digits=2))
                ziniarastis_day = rec.ziniarastis_day_ids.filtered(lambda d: d.date == work_schedule_day.date)
                if ziniarastis_day.contract_id:
                    ziniarastis_day.write({'not_by_schedule': False if factual_day_lines else True})
        return res

    @api.multi
    def button_single_done(self):
        res = super(ZiniarastisPeriodLine, self).button_single_done()
        factual_work_schedule = self.env.ref('work_schedule.factual_company_schedule')
        for rec in self:
            date_dt = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            year = date_dt.year
            month = date_dt.month
            line = self.env['work.schedule.line'].search([
                ('employee_id', '=', rec.employee_id.id),
                ('year', '=', year),
                ('month', '=', month),
                ('work_schedule_id', '=', factual_work_schedule.id)
            ])
            line.with_context(modifying_ziniarastis=True).write({'state': 'done'})
        return res


ZiniarastisPeriodLine()





