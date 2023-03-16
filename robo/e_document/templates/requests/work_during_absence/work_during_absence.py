# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, api, tools, _, exceptions, fields

TEMPLATE_REF = 'e_document.work_during_absence_request_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    show_date_table = fields.Boolean(compute='_compute_show_date_table')

    @api.multi
    @api.depends('e_document_time_line_ids.date', 'template_id')
    def _compute_show_date_table(self):
        """
        Computes whether to show the date table on the document. Don't show the table if all of the dates selected are
        in a range.
        """
        work_during_absence_template = self.env.ref(TEMPLATE_REF, False)
        for rec in self.filtered(lambda document: document.template_id == work_during_absence_template):
            requested_dates = rec.e_document_time_line_ids.mapped('date')
            if not requested_dates:
                rec.show_date_table = False
                continue
            min_date, max_date = min(requested_dates), max(requested_dates)
            date_to_test = min_date
            show_date_table = False
            while date_to_test <= max_date:
                if date_to_test not in requested_dates:
                    show_date_table = True
                    break
                date_to_test_dt = datetime.strptime(date_to_test, tools.DEFAULT_SERVER_DATE_FORMAT)
                day_after_dt = date_to_test_dt + relativedelta(days=1)
                day_after = day_after_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                date_to_test = day_after
            rec.show_date_table = show_date_table

    @api.multi
    def work_during_absence_request_workflow(self):
        """
        Creates a related order to be signed confirming this request
        """
        self.ensure_one()
        work_during_absence_order_template = self.env.ref('e_document.work_during_absence_order_template')
        order_document = self.env['e.document'].create({
            'template_id': work_during_absence_order_template.id,
            'document_type': 'isakymas',
            'employee_id2': self.employee_id1.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'date_2': self.date_document,
            'user_id': self.user_id.id,
            'e_document_time_line_ids': [(0, 0, line.read()[0]) for line in self.e_document_time_line_ids],
        })
        self.write({'record_model': 'e.document', 'record_id': order_document.id})

    @api.multi
    def check_workflow_constraints(self):
        res = super(EDocument, self).check_workflow_constraints()
        work_during_absence_template = self.env.ref(TEMPLATE_REF, False)
        for rec in self.filtered(lambda document: work_during_absence_template and
                                                  document.template_id == work_during_absence_template):
            res += self.check_work_during_absence_constraints(
                rec.employee_id1,
                rec.e_document_time_line_ids.mapped('date')
            )
        return res

    @api.multi
    def execute_confirm_workflow_check_values(self):
        res = super(EDocument, self).execute_confirm_workflow_check_values()
        work_during_absence_template = self.env.ref(TEMPLATE_REF, False)
        for rec in self:
            if rec.sudo().skip_constraints_confirm or rec.sudo().template_id != work_during_absence_template:
                continue

            issues = self.check_work_during_absence_constraints(
                rec.employee_id1,
                rec.e_document_time_line_ids.mapped('date')
            )
            if issues:
                raise exceptions.ValidationError(issues)

        return res

    @api.model
    def check_work_during_absence_constraints(self, employee, dates):
        self.ensure_one()

        # Check at least some dates have been selected
        if not dates:
            return _('You must select the dates you wish to work on!')

        # Check for duplicate dates
        if len(set(dates)) != len(dates):
            return _('Some dates have been entered twice. Please check the dates you wish to work on.')

        dates = set(dates)

        # Check for leaves on specified dates
        hr_holidays = self.env['hr.holidays'].sudo().search([
            ('state', '=', 'validate'),
            ('employee_id', '=', employee.id),
            ('date_from_date_format', '<=', max(dates)),
            ('date_to_date_format', '>=', min(dates)),
            ('holiday_status_id', 'in', [
                self.env.ref('hr_holidays.holiday_status_sl').id,
                self.env.ref('hr_holidays.holiday_status_N').id,
                self.env.ref('hr_holidays.holiday_status_NS').id,
            ])
        ])

        dates_not_found = list()

        for date in dates:
            date_hr_holiday = hr_holidays.filtered(lambda h: h.date_from_date_format <= date <= h.date_to_date_format)
            if not date_hr_holiday:
                dates_not_found.append(date)

        if dates_not_found:
            return _('No leaves you can request to work on have been found for the following dates {}').format(
                ', '.join(dates_not_found)
            )

        # Check if specified days are work days
        appointments = self.env['hr.contract.appointment'].sudo().search([
            ('employee_id', '=', employee.id),
            ('date_start', '<=', max(dates)),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', min(dates))
        ])

        days_that_are_not_work_days = list()

        for date in dates:
            appointments_for_date = appointments.filtered(lambda app: app.date_start <= date and
                                                                      (not app.date_end or app.date_end >= date))
            if not appointments_for_date:
                return _('No active work contract appointment found for date {}').format(date)

            is_work_day = False
            for appointment in appointments_for_date:
                schedule_template_id = appointment.schedule_template_id
                is_work_day = schedule_template_id and \
                              schedule_template_id.with_context(force_use_schedule_template=True).is_work_day(date)
                if is_work_day:
                    break

            if not is_work_day:
                days_that_are_not_work_days.append(date)

        if days_that_are_not_work_days:
            # Can always be bypassed with constraints disabled
            return _('The following selected days are not work dates: {}. You should only ask to work during work '
                     'days.').format(', '.join(days_that_are_not_work_days))

        return str()