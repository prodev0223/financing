# -*- coding: utf-8 -*-
from odoo import api, exceptions, models, _

TEMPLATE_REF = 'e_document.work_during_absence_order_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def work_during_absence_order_workflow(self):
        self.ensure_one()

        dates = self.e_document_time_line_ids.mapped('date')
        dates = set(dates)

        working_nights_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_DN')
        regular_work_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_FD')

        appointments = self.env['hr.contract.appointment'].sudo().search([
            ('employee_id', '=', self.employee_id2.id),
            ('date_start', '<=', max(dates)),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', min(dates))
        ])

        schedule_templates = appointments.mapped('schedule_template_id')
        regular_work_times = schedule_templates._get_regular_work_times(dates)

        hr_employee_forced_work_times = self.env['hr.employee.forced.work.time']

        for date in dates:
            appointments_for_date = appointments.filtered(lambda app: app.date_start <= date and
                                                                      (not app.date_end or app.date_end >= date))
            schedule_templates = appointments_for_date.mapped('schedule_template_id')
            regular_times = dict()
            for schedule_template in schedule_templates:
                if schedule_template.template_type == 'sumine':
                    break  # Don't set any time since it will most likely be filled in work schedule.
                regular_times = regular_work_times.get(schedule_template.id, {}).get(date, dict())
                if regular_times:
                    break

            for line in regular_times.get('day_lines', list()):
                hr_employee_forced_work_times |= self.env['hr.employee.forced.work.time'].sudo().create({
                    'employee_id': self.employee_id2.id,
                    'date': date,
                    'time_from': line[0],
                    'time_to': line[1],
                    'marking_id': line[2] or regular_work_marking.id
                })
            for line in regular_times.get('night_lines', list()):
                hr_employee_forced_work_times |= self.env['hr.employee.forced.work.time'].sudo().create({
                    'employee_id': self.employee_id2.id,
                    'date': date,
                    'time_from': line[0],
                    'time_to': line[1],
                    'marking_id': line[2] or working_nights_marking.id
                })

        try:
            subject = _('[{}] Work during absence order has been signed ({})').format(self._cr.dbname, self.id)
            body = _(
                """Work during absence order (ID:{}) has been signed. Leaves have to be shortened manually."""
            ).format(self.id)
            self.create_internal_ticket(subject, body)
        except Exception as exc:
            message = _("""
            [{}] Failed to create a ticket to inform about waiting manual action for work during absence order: {} 
            \nError: {}
            """).format(self._cr.dbname, self.id, str(exc.args))
            self.env['robo.bug'].sudo().create({
                'user_id': self.env.user.id,
                'error_message': message,
            })

        self.write({
            'record_model': 'hr.employee.forced.work.time',
            'record_ids': self.format_record_ids(hr_employee_forced_work_times.ids),
        })

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        template = self.env.ref(TEMPLATE_REF, False)
        if template and self.cancel_id and self.cancel_id.template_id == template:
            cancelled_document = self.cancel_id
            forced_work_times = self.env[cancelled_document.record_model].sudo().browse(
                cancelled_document.parse_record_ids()
            ).exists()
            forced_work_times.unlink()
        else:
            return super(EDocument, self).execute_cancel_workflow()

    @api.multi
    def check_workflow_constraints(self):
        res = super(EDocument, self).check_workflow_constraints()
        work_during_absence_template = self.env.ref(TEMPLATE_REF, False)
        for rec in self.filtered(lambda document: work_during_absence_template and
                                                  document.template_id == work_during_absence_template):
            res += self.check_work_during_absence_constraints(
                    rec.employee_id2,
                    rec.e_document_time_line_ids.mapped('date')
            )
        return res

    @api.multi
    def execute_confirm_workflow_check_values(self):
        res = super(EDocument, self).execute_confirm_workflow_check_values()
        work_during_absence_template = self.env.ref(TEMPLATE_REF, False)
        for rec in self.filtered(lambda rec: not rec.sudo().skip_constraints_confirm):
            if not work_during_absence_template or rec.template_id != work_during_absence_template:
                continue
            issues = self.check_work_during_absence_constraints(
                    rec.employee_id2,
                    rec.e_document_time_line_ids.mapped('date')
            )
            if issues:
                raise exceptions.ValidationError(issues)
        return res
