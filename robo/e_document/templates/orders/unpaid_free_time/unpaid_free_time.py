# -*- coding: utf-8 -*-
from odoo import models, api, fields, _, exceptions, tools
from odoo.addons.l10n_lt_payroll.model.schedule_template import merge_time_ranges

UNPAID_FREE_TIME_ORDER_TEMPLATE = 'e_document.unpaid_free_time_order_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    is_unpaid_free_time_order = fields.Boolean(compute='_compute_is_unpaid_free_time_order')

    @api.multi
    def _compute_is_unpaid_free_time_order(self):
        unpaid_free_time_order_template = self.env.ref(UNPAID_FREE_TIME_ORDER_TEMPLATE, False)
        for rec in self:
            rec.is_unpaid_free_time_order = rec.template_id and rec.template_id == unpaid_free_time_order_template

    @api.multi
    @api.depends(lambda self: self._min_max_date_dependencies())
    def _compute_min_max_dates(self):
        unpaid_free_time_documents = self.filtered(lambda document: document.is_unpaid_free_time_order)
        other_documents = self.filtered(lambda document: not document.is_unpaid_free_time_order)
        for rec in unpaid_free_time_documents:
            time_lines = rec.mapped('e_document_time_line_ids')
            dates = time_lines.mapped('date')
            if not dates:
                rec.min_date_from = rec.max_date_to = False
            else:
                rec.min_date_from, rec.max_date_to = min(dates), max(dates)
        return super(EDocument, other_documents)._compute_min_max_dates()

    @api.multi
    def _min_max_date_dependencies(self):
        current_dependencies = super(EDocument, self)._min_max_date_dependencies()
        additional_dependencies = ['e_document_time_line_ids.date']
        return list(set(current_dependencies + additional_dependencies))

    @api.multi
    def execute_confirm_workflow_check_values(self):
        super(EDocument, self).execute_confirm_workflow_check_values()
        for rec in self.filtered(lambda d: d.is_unpaid_free_time_order):
            if rec.sudo().skip_constraints_confirm:
                continue
            rec.check_free_time_document_constraints(rec.employee_id2)

    @api.multi
    def check_free_time_document_constraints(self, employee):
        self.ensure_one()

        def times_overlap(start_time_1, end_time_1, start_time_2, end_time_2):
            return tools.float_compare(start_time_1, end_time_2, precision_digits=2) < 0 and \
                   tools.float_compare(start_time_2, end_time_1, precision_digits=2) < 0

        lines = self.e_document_time_line_ids
        if not lines:
            raise exceptions.UserError(_('Free time to be granted is not specified'))

        times = [(line.date, line.time_from, line.time_to) for line in lines]

        self.sudo()._check_employee_should_work_on_specified_days(employee, times, show_times_employee_should_work=True)

        dates = list(set([x[0] for x in times]))

        employee_holidays = self.env['hr.holidays'].sudo().search([
            ('state', '=', 'validate'),
            ('type', '=', 'remove'),
            ('employee_id', '=', employee.id),
            ('date_from_date_format', '<=', max(dates)),
            ('date_to_date_format', '>=', min(dates))
        ])

        existing_forced_work_times = self.env['hr.employee.forced.work.time'].sudo().search([
            ('employee_id', '=', employee.id),
            ('date', 'in', dates)
        ])

        # Get dates that have existing hr.holiday records
        dates_with_holidays = [
            date for date in dates if
            employee_holidays.filtered(lambda h: h.date_from_date_format <= date <= h.date_to_date_format)
        ]
        # Get dates that have forced work time set that overlaps the requested times
        dates_with_overlapping_times = [date for date in dates if any(
            any(
                times_overlap(requested_time[1], requested_time[2], existing_time.time_from, existing_time.time_to)
                for requested_time in [time for time in times if time[0] == date]
            )
            for existing_time in existing_forced_work_times if existing_time.date == date
        )]

        if dates_with_holidays:
            raise exceptions.UserError(
                _('Can not request free time because the employee has a confirmed leave for dates {}.').format(
                    ', '.join(dates_with_holidays)
                )
            )

        if dates_with_overlapping_times:
            raise exceptions.UserError(
                _('Can not request free time because the employee has a forced work or absence time set for dates '
                  '{}.').format(
                    ', '.join(dates_with_overlapping_times)
                )
            )

    @api.multi
    def unpaid_free_time_order_workflow(self):
        self.ensure_one()
        # TODO Currently workflow uses hr.employee.forced.work.time object since it's well integrated with work schedule
        #  and payroll. Various e-documents create specific time entries in various places in the payroll therefore all
        #  of these work/absence times set by documents should create one kind of document, similar to HrHolidays but
        #  with a different name such as HrLeave. HrHolidays object is not really suitable because the name implies a
        #  mandatory holiday entry and various workarounds have been implemented through out the system that bypass
        #  setting a single time for an entire day by creating individual lines.
        HrEmployeeForcedWorkTime = self.env['hr.employee.forced.work.time']
        free_time_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_NLL')
        hr_employee_forced_work_times = HrEmployeeForcedWorkTime
        lines = self.e_document_time_line_ids
        dates = list(set(lines.mapped('date')))
        for date in dates:
            date_lines = lines.filtered(lambda l: l.date == date)
            times = [(x.time_from, x.time_to) for x in date_lines]
            times = merge_time_ranges(times)
            for time in times:
                hr_employee_forced_work_times |= HrEmployeeForcedWorkTime.sudo().create({
                    'employee_id': self.employee_id2.id,
                    'date': date,
                    'time_from': time[0],
                    'time_to': time[1],
                    'marking_id': free_time_marking.id
                })

        self.write({
            'record_model': 'hr.employee.forced.work.time',
            'record_ids': self.format_record_ids(hr_employee_forced_work_times.ids),
        })

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        document_to_be_cancelled = self.cancel_id
        if document_to_be_cancelled.is_unpaid_free_time_order:
            leave_times = self.env[document_to_be_cancelled.record_model].sudo().browse(
                document_to_be_cancelled.parse_record_ids()
            ).exists()
            leave_times.unlink()
        else:
            return super(EDocument, self).execute_cancel_workflow()

    @api.model
    def check_employees_who_have_taken_unpaid_time_off(self, employees, date_from, date_to):
        return self.env['e.document.time.line'].sudo().search([
            ('e_document_id.template_id', '=', self.env.ref(UNPAID_FREE_TIME_ORDER_TEMPLATE).id),
            ('e_document_id.state', '=', 'e_signed'),
            ('e_document_id.rejected', '=', False),
            ('date', '<=', date_to),
            ('date', '>=', date_from),
            ('e_document_id.employee_id2', 'in', employees.ids),
        ]).mapped('e_document_id.employee_id2')

    @api.model
    def employee_has_taken_free_time_off(self, employee, date_from, date_to):
        return bool(self.check_employees_who_have_taken_unpaid_time_off(employee, date_from, date_to))