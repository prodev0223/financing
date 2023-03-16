# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, api, tools, exceptions, _


class EDocument(models.Model):
    _inherit = 'e.document'

    # ===================================== Absence (Pravaikstos skyrimas) Document ====================================
    @api.onchange('template_id', 'bool_1', 'date_from', 'date_to', 'employee_id2')
    def _onchange_document_dates_for_absence_set_planned_time(self):
        absence_template = self.env.ref('e_document.pravaikstos_skyrimo_aktas_template')
        for rec in self:
            is_absence_document = not rec.template_id or rec.template_id == absence_template
            if not is_absence_document or not rec.single_absence_day_selected or not rec.bool_1 or not rec.employee_id2:
                continue
            date = rec.date_from
            if not self.env.user.sudo().company_id.with_context(date=date).extended_schedule:
                continue
            planned_lines = self._get_planned_day_lines(rec.employee_id2, date)
            if not planned_lines:
                continue
            rec.time_1 = min(planned_lines.mapped('time_from'))
            rec.time_2 = max(planned_lines.mapped('time_to'))

    @api.multi
    def _check_absence_document_constraints(self):
        for rec in self:
            if not rec.single_absence_day_selected or not rec.bool_1:
                continue
            date = rec.date_from
            if not self.env.user.sudo().company_id.with_context(date=date).extended_schedule:
                continue
            planned_lines = self._get_planned_day_lines(rec.employee_id2, date)
            if not planned_lines:
                continue

            document_time_from, document_time_to = rec.time_1, rec.time_2
            planned_line_time_ranges = planned_lines.get_merged_work_times(combine_potential_break_times=True)
            for planned_time_range in planned_line_time_ranges:
                time_from, time_to = planned_time_range[0], planned_time_range[1]
                if tools.float_compare(time_from, document_time_from, precision_digits=2) > 0 or \
                    tools.float_compare(time_to, document_time_to, precision_digits=2) < 0:
                    raise exceptions.ValidationError(
                        _('Absence time has to be between the planned schedule time for the date ({}-{})').format(
                            self.format_float_to_hours(time_from), self.format_float_to_hours(time_to)
                        )
                    )
        return super(EDocument, self)._check_absence_document_constraints()

    @api.model
    def _get_planned_day_lines(self, employee, date):
        last_of_this_month = (datetime.utcnow() + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        # Get planned days that are either in the past or in the future and not of draft state
        planned_days = self.env['work.schedule.day'].sudo().search([
            ('employee_id', '=', employee.id),
            ('date', '=', date),
            ('work_schedule_line_id.work_schedule_id', '=', self.env.ref('work_schedule.planned_company_schedule').id),
            '|',
            ('state', '!=', 'draft'),
            ('date', '<=', last_of_this_month)
        ])
        return planned_days.mapped('line_ids').filtered(
            lambda l: not l.work_schedule_code_id.is_absence and not l.work_schedule_code_id.is_holiday and
                      not l.holiday_id and not l.matched_holiday_id
        )

    @api.model
    def get_planned_work_time(self, employee, date, force_work_day=False):
        planned_lines = self._get_planned_day_lines(employee, date)
        if not planned_lines or not self.env.user.sudo().company_id.with_context(date=date).extended_schedule:
            return super(EDocument, self).get_planned_work_time(employee, date, force_work_day)
        return min(planned_lines.mapped('time_from')), max(planned_lines.mapped('time_to'))
    # ==================================================================================================================
