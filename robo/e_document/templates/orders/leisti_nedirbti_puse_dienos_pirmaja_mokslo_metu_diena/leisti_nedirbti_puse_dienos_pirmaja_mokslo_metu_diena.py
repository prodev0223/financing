# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, api, exceptions, tools


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_leisti_nedirbti_puse_dienos_pirmaja_mokslo_metu_diena_workflow(self):
        self.ensure_one()

        def calc_date(date, hour):
            hour, minute = divmod(hour * 60, 60)
            local_time = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(hour=int(hour),
                                                                                                   minute=int(minute))
            utc_time = local_time
            return utc_time.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

        work_schedule_installed = bool(
            self.env['ir.module.module'].search([('name', '=', 'work_schedule'), ('state', '=', 'installed')],
                                                count=True))

        free_from = 0.0
        free_until = 0.0

        employee_contract = self.env['hr.contract'].search([
            ('employee_id', '=', self.employee_id2.id),
            ('date_start', '<=', self.date_2),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', self.date_2)
        ], limit=1)
        if not employee_contract:
            raise exceptions.Warning(
                ('Nustatytą pirmą mokslo metų dieną (%s), darbuotojas %s neturi aktyvios darbo sutarties') % (
                    self.date_2, self.employee_id2.name))
        app = employee_contract.with_context(date=self.date_2).appointment_id
        if not app:
            raise exceptions.Warning(
                ('Nustatytą pirmą mokslo metų dieną (%s), darbuotojas %s neturi aktyvaus darbo sutarties priedo') % (
                    self.date_2, self.employee_id2.name))

        if work_schedule_installed:
            work_schedule_day_lines = self.env['work.schedule.day'].search([
                ('employee_id', '=', self.employee_id2.id),
                ('date', '=', self.date_2)
            ]).mapped('line_ids')
            planned_day_lines = work_schedule_day_lines.filtered(
                lambda l: l.day_id.work_schedule_id.name == self.env.ref('work_schedule.planned_company_schedule').id)
            factual_day_lines = work_schedule_day_lines.filtered(
                lambda l: l.day_id.work_schedule_id.id == self.env.ref('work_schedule.factual_company_schedule').id)
            lines_to_use = planned_day_lines if planned_day_lines else factual_day_lines
            lines_to_use = lines_to_use.filtered(
                lambda l: not l.work_schedule_code_id.is_holiday and not l.work_schedule_code_id.is_absence)
            if lines_to_use:
                total_work_time = sum(lines_to_use.mapped('worked_time_total'))
                time_free = total_work_time / 2.0  # P3:DivOK
                lines_to_use = lines_to_use.sorted(key=lambda l: l.time_from)
                free_from = lines_to_use[0].time_from

                for line in lines_to_use:
                    if line.worked_time_total < time_free:
                        time_free -= line.worked_time_total
                        free_until = line.time_to
                    else:
                        free_until = line.time_from + time_free
                        time_free = 0
                        break
        else:
            sched_templ_attendance_ids = app.schedule_template_id.fixed_attendance_ids.filtered(
                lambda l: l.dayofweek == str(
                    datetime.strptime(self.date_2, tools.DEFAULT_SERVER_DATE_FORMAT).weekday())).sorted(
                key=lambda l: l.hour_from)
            total_scheduled_time = sum([l.hour_to - l.hour_from for l in sched_templ_attendance_ids])
            if not tools.float_is_zero(total_scheduled_time, precision_digits=2):
                free_from = sched_templ_attendance_ids[0].hour_from
                free_until = free_from
                time_free = total_scheduled_time / 2.0  # P3:DivOK
                for line in sched_templ_attendance_ids:
                    line_time_sum = line.hour_to - line.hour_from
                    if line_time_sum < time_free:
                        time_free -= line_time_sum
                        free_until = line.hour_to
                    else:
                        free_until = line.hour_from + time_free
                        time_free = 0
                        break

        if not tools.float_is_zero(free_until - free_from, precision_digits=2):
            generated_id = self.env['hr.holidays'].create({
                'name': 'Laisvas pusdienis pirmąją mokslo metų dieną',
                'data': self.date_document,
                'employee_id': self.employee_id2.id,
                'holiday_status_id': self.env.ref('hr_holidays.holiday_status_MP').id,
                'date_from': calc_date(self.date_2, free_from),
                'date_to': calc_date(self.date_2, free_until),
                'type': 'remove',
                'numeris': self.document_number,
            })
            generated_id.action_approve()
            self.inform_about_creation(generated_id)
            self.write({
                'record_model': 'hr.holidays',
                'record_id': generated_id.id
            })


EDocument()
