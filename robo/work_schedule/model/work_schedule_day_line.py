# -*- coding: utf-8 -*-
from datetime import datetime

from odoo.addons.l10n_lt_payroll.model.schedule_template import merge_time_ranges

from odoo import models, fields, api, tools, exceptions
from odoo.tools import float_compare
from odoo.tools.translate import _
from work_schedule import SCHEDULE_STATES
from dateutil.relativedelta import relativedelta


class WorkScheduleDayLine(models.Model):
    _name = 'work.schedule.day.line'

    _order = 'time_from'

    day_id = fields.Many2one('work.schedule.day', 'Diena', required=True, ondelete='cascade')
    state = fields.Selection(SCHEDULE_STATES, related='day_id.work_schedule_line_id.state')
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', related='day_id.work_schedule_line_id.employee_id', required=True)
    department_id = fields.Many2one('hr.department', string='Padalinys', related='day_id.work_schedule_line_id.department_id', required=True)

    time_from = fields.Float('Laikas nuo', default=8.0, required=True, readonly=True, states={'draft': [('readonly', False)]})
    time_to = fields.Float('Laikas iki', default=16.0, required=True, readonly=True, states={'draft': [('readonly', False)]})
    datetime_from = fields.Datetime('Data ir laikas nuo', compute='_compute_datetime_of_line')
    datetime_to = fields.Datetime('Data ir laikas iki', compute='_compute_datetime_of_line')
    worked_time_hours = fields.Integer(string='Dirbta valandų', compute='_compute_worked_time', store=True)
    worked_time_minutes = fields.Integer(string='Dirbta minučių', compute='_compute_worked_time', store=True)
    worked_time_total = fields.Float(string='Dirbtas laikas', compute='_compute_worked_time', store=True)

    work_schedule_code_id = fields.Many2one('work.schedule.codes', string='Žymėjimas', required=True, readonly=True, states={'draft': [('readonly', False)]})
    tabelio_zymejimas_id = fields.Many2one(related='work_schedule_code_id.tabelio_zymejimas_id', string='Tabelio Žymėjimas')

    code = fields.Char(string='Kodas', related='work_schedule_code_id.code', readonly=True, compute_sudo=True)
    name = fields.Char(string='Pavadinimas', compute='_compute_name', store=True, translate=False)
    date = fields.Date(string='Data', related='day_id.date')

    prevent_deletion = fields.Boolean('Neleisti ištrinti', help='Kaikurios eilutės gali būti sukuriamos iš atostogų įrašų, todėl neturėtų būti ištrinamos')

    matched_holiday_id = fields.Many2one('hr.holidays', string='Matching holiday id',
                                          compute='_compute_matched_holiday_id', compute_sudo=True)
    holiday_id = fields.Many2one('hr.holidays', string='Related holiday id')

    @api.one
    @api.depends('time_from', 'time_to', 'day_id', 'day_id.date')
    def _compute_datetime_of_line(self):
        hours_from, minutes_from = divmod(self.time_from * 60, 60)
        if float_compare(int(round(minutes_from)), 60, precision_digits=3) == 0:
            minutes_from = 0
            hours_from += 1

        hours_to, minutes_to = divmod(self.time_to * 60, 60)
        if float_compare(int(round(minutes_to)), 60, precision_digits=3) == 0:
            minutes_to = 0
            hours_to += 1
        date = datetime.strptime(self.day_id.date, tools.DEFAULT_SERVER_DATE_FORMAT)
        days_to_add = 0
        if hours_from >= 24:
            days_to_add += 1
            hours_from = 0
        self.datetime_from = datetime(date.year, date.month, date.day, int(hours_from), int(minutes_from)) + relativedelta(days=days_to_add)
        days_to_add = 0
        if hours_to >= 24:
            days_to_add += 1
            hours_to = 0
        self.datetime_to = datetime(date.year, date.month, date.day, int(hours_to), int(minutes_to)) + relativedelta(days=days_to_add)

    @api.one
    @api.depends('time_from', 'time_to')
    def _compute_worked_time(self):
        total_h = self.time_to - self.time_from
        hours, minutes = divmod(total_h * 60, 60)
        if float_compare(int(round(minutes)), 60, precision_digits=3) == 0:
            minutes = 0
            hours += 1
        self.worked_time_hours = hours
        self.worked_time_minutes = int(round(minutes))
        self.worked_time_total = total_h

    @api.multi
    @api.depends('time_from', 'time_to', 'work_schedule_code_id')
    def _compute_name(self):
        for rec in self:
            tabelio_zymejimas = rec.work_schedule_code_id
            marks_the_whole_day = rec.work_schedule_code_id.is_whole_day

            if marks_the_whole_day:
                rec.name = tabelio_zymejimas.code
            else:
                t_1 = rec.time_from
                t_2 = rec.time_to
                name = '{0:02.0f}:{1:02.0f} - {2:02.0f}:{3:02.0f}'.format(
                    *(divmod(t_1 * 60, 60) + divmod(t_2 * 60, 60)))
                if tabelio_zymejimas.code and tabelio_zymejimas.code != 'FD':
                    name += ' ' + tabelio_zymejimas.code
                rec.name = name

    @api.multi
    @api.depends('time_from', 'time_to', 'day_id.date', 'employee_id', 'tabelio_zymejimas_id')
    def _compute_matched_holiday_id(self):
        dates = self.mapped('date')
        holidays = self.env['hr.holidays'].sudo().search([
            ('state', '=', 'validate'),
            ('employee_id', 'in', self.mapped('employee_id').ids),
            ('date_from_date_format', '<=', max(dates)),
            ('date_to_date_format', '>=', min(dates)),
            ('holiday_status_id.tabelio_zymejimas_id', 'in', self.mapped('tabelio_zymejimas_id').ids)
        ])
        for rec in self:
            related_holidays = holidays.filtered(
                lambda h: h.employee_id == rec.employee_id and
                          h.date_from_date_format <= rec.date <= h.date_to_date_format and
                          h.holiday_status_id.tabelio_zymejimas_id == rec.tabelio_zymejimas_id
            )
            if related_holidays and not rec.work_schedule_code_id.is_whole_day:
                related_holidays = related_holidays.filtered(
                    lambda h: h.date_from == rec.datetime_from and h.date_to == rec.datetime_to
                )
                rec.matched_holiday_id = related_holidays and related_holidays[0]

    @api.model
    def create(self, vals):
        day_id = vals.get('day_id', False)
        work_schedule_code_id = vals.get('work_schedule_code_id', False)
        new_vals = vals.copy()
        if day_id:
            work_schedule_day_id = self.env['work.schedule.day'].browse(day_id)
            work_schedule_day_id.work_schedule_line_id.ensure_not_busy()
            if work_schedule_day_id.department_id.id in self.env.user.mapped('employee_ids.fill_department_ids.id') or \
                    (work_schedule_day_id.employee_id in self.env.user.employee_ids and work_schedule_day_id.employee_id.sudo().can_fill_own_schedule):
                self = self.sudo()
            if work_schedule_day_id.work_schedule_line_id.prevent_modifying_as_past_planned:
                raise exceptions.ValidationError(_('You can not modify confirmed planned schedule lines'))
        if day_id and work_schedule_code_id:
            date = work_schedule_day_id.date
            is_holiday = self.env['sistema.iseigines'].search_count([('date', '=', date)]) != 0
            fd_zymejimas = self.env.ref('work_schedule.work_schedule_code_FD')
            vd_zymejimas = self.env.ref('work_schedule.work_schedule_code_VD')
            dp_zymejimas = self.env.ref('work_schedule.work_schedule_code_DP')
            dn_zymejimas = self.env.ref('work_schedule.work_schedule_code_DN')
            vss_zymejimas = self.env.ref('work_schedule.work_schedule_code_VSS')
            snv_zymejimas = self.env.ref('work_schedule.work_schedule_code_SNV')
            if is_holiday:
                if work_schedule_code_id == fd_zymejimas.id:
                    new_vals['work_schedule_code_id'] = dp_zymejimas.id
                elif work_schedule_code_id == vd_zymejimas.id:
                    new_vals['work_schedule_code_id'] = vss_zymejimas.id
                elif work_schedule_code_id == dn_zymejimas.id:
                    new_vals['work_schedule_code_id'] = snv_zymejimas.id
        if work_schedule_code_id:
            mp_zymejimas = self.env.ref('work_schedule.work_schedule_code_MP')
            if work_schedule_code_id == mp_zymejimas.id:
                vals.update({'prevent_deletion': True})
        return super(WorkScheduleDayLine, self).create(new_vals)

    @api.multi
    @api.constrains('time_from', 'time_to')
    def _check_worked_time(self):
        for rec in self:
            time_from_is_negative = float_compare(rec.time_from, 0.0, precision_digits=2) < 0
            time_to_is_negative = float_compare(rec.time_to, 0.0, precision_digits=2) < 0
            time_to_is_more_than_midnight = float_compare(rec.time_to, 24.0, precision_digits=2) > 0
            time_from_is_more_than_midnight = float_compare(rec.time_from, 24.0, precision_digits=2) > 0

            if time_from_is_negative or time_to_is_negative or \
                    time_to_is_more_than_midnight or time_from_is_more_than_midnight:
                raise exceptions.ValidationError(_('Darbo pradžios ir pabaigos laikas turi būti tarp 00:00 ir 24:00'))

            if tools.float_compare(rec.time_from, rec.time_to, precision_digits=3) > 0:
                raise exceptions.UserError(_('Darbo pradžia turi būti prieš darbo pabaigą'))

    @api.multi
    def unlink(self):
        if any(line.prevent_modifying_as_past_planned for line in self.mapped('day_id.work_schedule_line_id')):
            raise exceptions.ValidationError(_('You can not modify confirmed planned schedule lines'))
        lines_should_not_be_deleted = any(rec.prevent_deletion or rec.holiday_id or rec.matched_holiday_id for rec in self)
        bypass_deletion_check = self._context.get('allow_delete_special')
        if lines_should_not_be_deleted and not bypass_deletion_check:
            raise exceptions.ValidationError(_('Negalite ištrinti kai kurių eilučių, nes jos sukurtos pagal įsakymus '
                                               'arba neatvykimo įrašus'))
        else:
            days = self.mapped('day_id')
            if not self.env.user.is_schedule_super():
                line_departments = self.mapped('department_id.id')
                fill_departments = self.env.user.mapped('employee_ids.fill_department_ids.id')
                if any(line_department not in fill_departments for line_department in line_departments) and \
                        any(not line_employee.sudo().can_fill_own_schedule or line_employee not in self.env.user.employee_ids for line_employee in self.mapped('employee_id')):
                    res = super(WorkScheduleDayLine, self).unlink()
                else:
                    res = super(WorkScheduleDayLine, self.sudo()).unlink()
            else:
                res = super(WorkScheduleDayLine, self).unlink()
            days.exists().sudo()._reset_schedule_line_constraints()
            return res

    @api.multi
    def write(self, vals):
        if any(line.prevent_modifying_as_past_planned for line in self.mapped('day_id.work_schedule_line_id')):
            raise exceptions.ValidationError(_('You can not modify confirmed planned schedule lines'))
        return super(WorkScheduleDayLine, self).write(vals)

    @api.multi
    def get_merged_work_times(self, combine_potential_break_times=False):
        """
        Merges the work times for the specified lines
        :param combine_potential_break_times: Remove all the gaps between the merged times that do not exceed the
        maximum lunch break duration
        :return: A list of merged times
        """
        merged_times = merge_time_ranges([(line.time_from, line.time_to) for line in self])
        if not combine_potential_break_times:
            return merged_times
        merged_times.sort()
        break_time_duration = self.env.user.company_id.maximum_time_between_breaks
        adjusted_times = list()
        for time_range_index in range(0, len(merged_times)-1):
            current_time_range = merged_times[time_range_index]
            next_time_range = merged_times[time_range_index+1]

            adjusted_times.append(current_time_range)

            time_to_add = min(break_time_duration, next_time_range[0]-current_time_range[1])
            break_time_duration -= time_to_add
            if tools.float_compare(time_to_add, 0.0, precision_digits=2) > 0:
                adjusted_times.append((current_time_range[1], current_time_range[1]+time_to_add))
        adjusted_times.append(merged_times[-1])
        adjusted_times = merge_time_ranges(adjusted_times)
        adjusted_times.sort()
        return adjusted_times
