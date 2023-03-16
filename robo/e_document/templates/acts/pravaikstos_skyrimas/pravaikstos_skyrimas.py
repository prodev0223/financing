# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import models, api, exceptions, _, fields, tools

TEMPLATE = 'e_document.pravaikstos_skyrimo_aktas_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    single_absence_day_selected = fields.Boolean(compute='_compute_single_absence_day_selected')

    @api.onchange('time_2')
    def _onchange_times_set_times_to_no_more_than_midnight(self):
        template = self.env.ref(TEMPLATE)
        if self.template_id == template:
            if tools.float_compare(self.time_2, 24.0, precision_digits=2) >= 0 or \
                    tools.float_compare(self.time_2, 0.0, precision_digits=2) < 0:
                self.time_2 = 0.0
            if tools.float_compare(self.time_1, 24.0, precision_digits=2) >= 0 or \
                    tools.float_compare(self.time_1, 0.0, precision_digits=2) < 0:
                self.time_1 = 0.0

    @api.multi
    @api.depends('date_from', 'date_to')
    def _compute_single_absence_day_selected(self):
        for rec in self:
            rec.single_absence_day_selected = rec.date_from and rec.date_from == rec.date_to

    @api.multi
    def _check_absence_document_constraints(self):
        for rec in self:
            if not rec.single_absence_day_selected or not rec.bool_1:
                continue
            time_from, time_to = rec.time_1, rec.time_2
            if tools.float_is_zero(time_to, precision_digits=2):
                time_to = 24.0
            if tools.float_compare(time_from, 0.0, precision_digits=2) < 0:
                raise exceptions.ValidationError(_('Time from must be after midnight (00:00)'))
            if tools.float_compare(time_to, 24.0, precision_digits=2) > 0:
                raise exceptions.ValidationError(_('Time to must be no more than midnight (00:00)'))
            if tools.float_compare(time_from, time_to, precision_digits=2) >= 0:
                raise exceptions.ValidationError(_('Time from must be less than time to'))

            if rec.employee_id2:
                appointment = rec.employee_id2.sudo().with_context(date=rec.date_from).appointment_id
                if not appointment:
                    raise exceptions.ValidationError(_('Employee does not have an active work contract for the '
                                                       'specified date'))
                during_work_hours = appointment.schedule_template_id.is_time_range_during_work_hours(
                    time_from, time_to, datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT).weekday()
                )
                if not during_work_hours:
                    raise exceptions.ValidationError(_('The specified absence time is not during the employees work '
                                                       'hours'))

    @api.multi
    def execute_confirm_workflow_check_values(self):
        res = super(EDocument, self).execute_confirm_workflow_check_values()
        self.filtered(lambda d: d.template_id == self.env.ref(TEMPLATE))._check_absence_document_constraints()
        return res

    @api.model
    def get_planned_work_time(self, employee, date, force_work_day=False):
        """
        Gets the planned work time for an employee on a specific date. Allows force treating date as work day.
        @param employee: (hr.employee) - Employee to get the planned work time for
        @param date: (str) Date to retrieve for
        @param force_work_day: (bool) Even if the employee is not supposed to work for specified date - still treat it
        as work day?
        @return (tuple) (time_from, time_to) - planned work time for the given employee for the given date
        """
        default_time_from, default_time_to = 8.0, 17.0
        appointment = employee.with_context(date=date).appointment_id
        if not appointment:
            if force_work_day:
                return default_time_from, default_time_to
            else:
                return 0, 0
        schedule_template = appointment.schedule_template_id
        is_work_day = force_work_day or schedule_template.is_work_day(date)
        if not is_work_day:
            return 0, 0
        regular_hours = schedule_template.get_regular_hours(date)
        if not regular_hours or tools.float_is_zero(regular_hours, precision_digits=2):
            regular_hours = schedule_template.avg_hours_per_day
        time_from = default_time_from
        time_to = time_from + regular_hours
        return time_from, time_to

    @api.multi
    def pravaikstos_skyrimo_aktas_workflow(self):
        self.ensure_one()
        specific_hours_for_a_single_day = self.single_absence_day_selected and self.bool_1
        if specific_hours_for_a_single_day:
            time_from, time_to = self.time_1, self.time_2
            if tools.float_is_zero(time_to, precision_digits=2):
                time_to = 24.0
            hour, minute = divmod(time_from * 60, 60)
            date_from = self.calc_date_from(self.date_from, hour=int(hour), minute=int(minute))
            hour, minute = divmod(time_to * 60, 60)
            date_to = self.calc_date_to(self.date_to, hour=int(hour), minute=int(minute))
        else:
            time_from, time_to = self.get_planned_work_time(self.employee_id2, self.date_from, force_work_day=True)
            hour, minute = divmod(time_from * 60, 60)
            hour, minute = int(round(hour)), int(round(minute))
            date_from = self.calc_date_from(self.date_from, hour=hour, minute=minute)
            hour, minute = divmod(time_to * 60, 60)
            hour, minute = int(round(hour)), int(round(minute))
            date_to = self.calc_date_to(self.date_to, hour=int(hour), minute=int(minute))
        hol_id = self.env['hr.holidays'].create({
            'name': 'Pravaikšta',
            'data': self.date_document,
            'employee_id': self.employee_id2.id,
            'holiday_status_id': self.env.ref('hr_holidays.holiday_status_PB').id,
            'date_from': date_from,
            'date_to': date_to,
            'type': 'remove'
        })
        # Unlink manually created related records before approving holidays to prevent duplicates in work schedule
        hol_id.unlink_manual_holiday_related_records()
        hol_id.action_approve()
        self.write({
            'record_model': 'hr.holidays',
            'record_id': hol_id.id,
        })

        if not specific_hours_for_a_single_day:
            try:
                subject = 'Pasirašytas pravaikštos skyrimo aktas [%s]' % self._cr.dbname
                body = """Buvo pasirašytas pravaikštos skyrimo aktas (darbuotojas %s). 
                Primename, jog reikia "Sodrai" pateikti 12-SD pranešimą.""" % self.employee_id2.name
                self.create_internal_ticket(subject, body)
            except Exception as exc:
                message = 'Failed to create sign workflow ticket for EDoc ID %s\nException: %s' % (
                    self.id, str(exc.args))
                self.env['robo.bug'].sudo().create({
                    'user_id': self.env.user.id,
                    'error_message': message,
                })

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        if self.template_id == self.env.ref(TEMPLATE):
            if not self.check_user_can_sign(raise_if_false=False):
                raise exceptions.AccessError(_('Negalite atlikti šio veiksmo'))
            HrHolidays = self.env['hr.holidays'].sudo()
            holiday = None
            try:
                holiday_id = self.record_id
                if holiday_id and isinstance(holiday_id, int):
                    holiday = HrHolidays.browse(holiday_id).exists()
            except Exception as e:
                pass
            if not holiday:
                holiday = HrHolidays.search([
                    ('date_from_date_format', '=', self.date_from),
                    ('date_to_date_format', '=', self.date_to),
                    ('employee_id', '=', self.employee_id2.id),
                    ('holiday_status_id', '=', self.env.ref('hr_holidays.holiday_status_PB').id),
                    ('type', '=', 'remove'),
                    ('state', '=', 'validate')
                ], limit=1)
            if not holiday:
                raise exceptions.ValidationError(_('Pravaikštos neatvykimas nerastas. Susisiekite su savo buhalteriu.'))
            holiday.action_refuse()
            holiday.message_post(body=_('Action refused when cancelling ') + self.get_document_link_tag())
            # TODO why isn't it unlinked?
            # holiday.action_draft()
            # holiday.unlink()
        else:
            return super(EDocument, self).execute_cancel_workflow()


EDocument()
