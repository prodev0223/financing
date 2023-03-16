# -*- coding: utf-8 -*-
from odoo import models, api, tools, fields, exceptions, _
from datetime import datetime

TEMPLATE = 'e_document.isakymas_del_neatvykimo_i_darba_darbdaviui_leidus_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    compensate_leave = fields.Boolean(compute='_compute_compensate_leave')

    @api.onchange('employee_id2', 'date_from', 'date_to')
    def _onchange_employee_id2_update_float_1_to_match_vdu(self):
        fields_are_set = bool(self.employee_id2 and self.date_from and self.date_to)
        has_access_rights = self.env.user.is_manager() or self.env.user.is_hr_manager()
        template_is_in_template_list = self.template_id in [self.env.ref(TEMPLATE, raise_if_not_found=False)]
        if not fields_are_set or not has_access_rights or not template_is_in_template_list:
            return
        contract = self.employee_id2.sudo().with_context(date=self.date_from).contract_id
        appointment = contract.with_context(date=self.date_from).appointment_id
        daily_wage = appointment.hypothetical_hourly_wage * 8.0 * appointment.schedule_template_id.etatas
        if contract:
            duration = contract.get_num_work_days(self.date_from, self.date_to)
        else:
            date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            duration = (date_to_dt - date_from_dt).days
        self.float_1 = daily_wage * duration

    @api.depends('float_1')
    def _compute_compensate_leave(self):
        for rec in self:
            if tools.float_compare(abs(rec.float_1), 0.0, precision_digits=2) > 0:
                rec.compensate_leave = True

    @api.multi
    def isakymas_del_neatvykimo_i_darba_darbdaviui_leidus_workflow(self):
        self.ensure_one()

        holiday = self.env['hr.holidays'].create({
            'name': 'Neatvykimas į darbą darbdaviui leidus',
            'data': self.date_document,
            'employee_id': self.employee_id2.id,
            'holiday_status_id': self.env.ref('hr_holidays.holiday_status_ND').id,
            'date_from': self.calc_date_from(self.date_from),
            'date_to': self.calc_date_to(self.date_to),
            'type': 'remove',
            'numeris': self.document_number,
        })

        holiday.action_approve()
        self.inform_about_creation(holiday)

        self.write({
            'record_model': 'hr.holidays',
            'record_id': holiday.id,
        })

        if self.compensate_leave:
            date_to_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            payslip_year_id = self.env['years'].search([('code', '=', date_to_dt.year)], limit=1).id

            compensation = self.env['hr.employee.compensation'].create({
                'employee_id': self.employee_id2.id,
                'date_from': self.date_from,
                'date_to': self.date_to,
                'payslip_year_id': payslip_year_id,
                'payslip_month': str(date_to_dt.month).zfill(2),
                'amount': self.float_1,
                'compensation_type': 'approved_leave',
                'related_document': self.id
            })
            compensation.action_confirm()

        if tools.float_is_zero(self.float_1, precision_digits=2):
            try:
                subject = 'Pasirašytas įsakymas dėl neatvykimo į darbą darbdaviui leidus [%s]' % self._cr.dbname
                body = """Buvo pasirašytas įsakymas dėl neatvykimo į darbą darbdaviui leidus (darbuotojas %s). 
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
        template = self.env.ref(TEMPLATE, raise_if_not_found=False)
        document_to_cancel = self.cancel_id

        if document_to_cancel and document_to_cancel.template_id == template:
            record_model = document_to_cancel.record_model
            record_id = document_to_cancel.record_id
            if record_model and record_id:
                holiday = self.env[record_model].browse(record_id)

                if not holiday or not holiday.exists():
                    raise exceptions.ValidationError(_('Neatvykimas į darbą darbdaviui leidus nerastas. '
                                                       'Susisiekite su savo buhalteriu.'))

                if holiday.state == 'validate' and holiday.date_from:
                    period_lines = self.env['ziniarastis.period.line'].search([
                        ('employee_id', '=', holiday.employee_id.id),
                        ('date_from', '<=', holiday.date_from),
                        ('date_to', '>=', holiday.date_from)], limit=1)
                    if period_lines and period_lines[0].period_state == 'done':
                        raise exceptions.UserError(_('Įsakymo patvirtinti negalima, nes atlyginimai jau buvo '
                                                     'paskaičiuoti. Informuokite buhalterį '
                                                     'parašydami žinutę dokumento apačioje.'))
                    holiday.action_refuse()
                    holiday.action_draft()
                    holiday.unlink()
                elif holiday.state != 'validate' and holiday.date_from:
                    holiday.action_draft()
                    holiday.unlink()

            if document_to_cancel.compensate_leave:
                compensation = self.env['hr.employee.compensation'].search([
                    ('related_document', '=', document_to_cancel.id)], limit=1)

                if not compensation:
                    raise exceptions.ValidationError(_('Kompensacija už neatvykimą į darbą darbdaviui leidus nerasta. '
                                                       'Susisiekite su savo buhalteriu.'))
                compensation.action_draft()
                compensation.unlink()
        else:
            return super(EDocument, self).execute_cancel_workflow()


EDocument()
