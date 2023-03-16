# -*- coding: utf-8 -*-
from odoo import api, fields, models


class EDocumentTimeLine(models.Model):
    _name = 'e.document.time.line'
    _inherit = ['robo.time.line']

    e_document_id = fields.Many2one('e.document', required=True, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', compute='_compute_employee_id')

    @api.multi
    @api.depends('e_document_id', 'e_document_id.document_type', 'e_document_id.employee_id2',
                 'e_document_id.employee_id1')
    def _compute_employee_id(self):
        for rec in self:
            if rec.e_document_id.document_type == 'prasymas':
                rec.employee_id = rec.e_document_id.employee_id1
            else:
                rec.employee_id = rec.e_document_id.employee_id2

    @api.multi
    @api.onchange('e_document_id', 'date')
    def _onchange_set_employee_working_hours(self):
        """
        Gets working ranges based on appointment schedule template and sets it as the line time
        """
        employees = self.mapped('employee_id')
        for employee in employees:
            employee_lines = self.filtered(lambda rec: rec.employee_id == employee)
            dates = employee_lines.mapped('date')
            min_date, max_date = min(dates), max(dates)
            contract_appointments = self.env['hr.contract.appointment'].sudo().search([
                ('employee_id', '=', employee.id),
                ('date_start', '<=', max_date),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', min_date)
            ])
            for employee_line in employee_lines:
                date = employee_line.date
                date_appointment = contract_appointments.filtered(
                    lambda app: app.date_start <= date and (not app.date_end or app.date_end >= date)
                )
                if date_appointment:
                    schedule_template = date_appointment.schedule_template_id
                    if schedule_template.is_work_day(date):
                        working_ranges = schedule_template.get_working_ranges([date])
                        working_ranges = working_ranges.get(str(date), list())
                        if working_ranges:
                            working_range = working_ranges[0]
                            employee_line.time_from, employee_line.time_to = working_range[0], working_range[1]


EDocumentTimeLine()
