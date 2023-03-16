# -*- coding: utf-8 -*-

# TODO When dependencies are fixed - move this model to robo_core.

from odoo import api, fields, models, tools, _, exceptions
from datetime import datetime
from dateutil.relativedelta import relativedelta


class RoboTimeLine(models.Model):
    _name = 'robo.time.line'

    date = fields.Date(string='Date', required=True)
    time_from = fields.Float(string='Time from', required=True, default=0.0)
    time_to = fields.Float(string='Time to', required=True, default=0.0)
    duration = fields.Float(string='Duration', compute='_compute_duration', store=True)
    date_is_holiday = fields.Boolean(string='Date is holiday', compute='_compute_date_is_holiday_or_day_before')
    date_is_day_before_holiday = fields.Boolean(string='Date is holiday',
                                                compute='_compute_date_is_holiday_or_day_before')
    adjusted_time_to = fields.Float(string='Time to (adjusted)', compute='_compute_adjusted_time_to')

    @api.multi
    @api.constrains('time_from', 'time_to')
    def _check_correct_times(self):
        errors = ''

        for rec in self:
            time_from = rec.time_from
            time_to = rec.time_to
            if tools.float_compare(time_to, 0.0, precision_digits=2) == 0:
                time_to = 24.0
            
            time_compare = tools.float_compare(time_from, time_to, precision_digits=2)
            if time_compare == 0:
                errors += _('Time from is equal to time to for date {}. Please remove this line or adjust the '
                            'times').format(rec.date) + '\n'
            elif time_compare > 0:
                errors += _('Time from is set to be after the time to for date {}. Please remove this line or adjust '
                            'the times').format(rec.date) + '\n'

            hour_from, minute_from = divmod(time_from * 60, 60)
            hour_from, minute_from = str(int(hour_from)).zfill(2), str(int(minute_from)).zfill(2)
            if tools.float_compare(rec.time_from, 0.0, precision_digits=2) < 0:
                errors += _('Time from has to be on or after midnight (00:00). Time from is {}:{} for date {}.').format(
                    hour_from, minute_from, rec.date
                ) + '\n'

            hour_to, minute_to = divmod(time_to * 60, 60)
            hour_to, minute_to = str(int(hour_to)).zfill(2), str(int(minute_to)).zfill(2)
            if tools.float_compare(rec.time_to, 24.0, precision_digits=2) > 0:
                errors += _('Time to has to be before or on midnight (00:00). Time to is {}:{} for date {}.').format(
                    hour_to, minute_to, rec.date
                ) + '\n'

        if errors != '':
            raise exceptions.UserError(errors)

    @api.multi
    @api.depends('time_from', 'time_to')
    def _compute_duration(self):
        for rec in self:
            time_from = rec.time_from
            time_to = rec.time_to
            if tools.float_compare(time_to, 0.0, precision_digits=2) == 0:
                time_to = 24.0

            rec.duration = round(time_to - time_from, 2)

    @api.multi
    @api.depends('date')
    def _compute_date_is_holiday_or_day_before(self):
        dates = self.mapped('date')
        national_holiday_dates = self.env['sistema.iseigines'].sudo().search([('date', 'in', dates)]).mapped('date')
        for rec in self:
            date = rec.date

            if not date:
                rec.date_is_holiday = False
                rec.date_is_day_before_holiday = False
                continue

            # Check if date is in sistema.iseigines
            rec.date_is_holiday = date in national_holiday_dates

            # Check if day after date is in sistema.iseigines
            date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
            next_day = (date_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            rec.date_is_day_before_holiday = next_day in national_holiday_dates

    @api.multi
    @api.depends('time_to')
    def _compute_adjusted_time_to(self):
        for rec in self:
            time_to = rec.time_to
            rec.adjusted_time_to = 24.0 if tools.float_is_zero(time_to, precision_digits=2) else time_to


RoboTimeLine()
