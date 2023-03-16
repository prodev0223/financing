# -*- coding: utf-8 -*-
from odoo import models, api, exceptions, _


TEMPLATE = 'e_document.isakymas_del_darbo_grafiko_pakeitimo_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_darbo_grafiko_pakeitimo_workflow(self):
        self.ensure_one()

        contract = self.employee_id2.with_context(date=self.date_4).contract_id
        appointment = contract.with_context(date=self.date_4).appointment_id

        # Create a new appointment with the changed schedule
        workday_ids = []
        # Currently this document is used to change work hours for Mon - Fri;
        for day in range(5):
            workday = self.env['fix.attendance.line'].create({
                'dayofweek': str(day),
                'hour_from': self.time_1,
                'hour_to': self.time_2,
            })
            workday_ids.append(workday.id)
        schedule_template = appointment.schedule_template_id
        schedule_template_values = {
            'template_type': schedule_template.template_type,
            'wage_calculated_in_days': schedule_template.wage_calculated_in_days,
            'shorter_before_holidays': schedule_template.shorter_before_holidays,
            'etatas_stored': schedule_template.etatas_stored,
            'work_norm': schedule_template.work_norm,
            'fixed_attendance_ids': [(6, 0, workday_ids)]
        }
        schedule_template_new = self.env['schedule.template'].create(schedule_template_values)
        new_record = contract.update_terms(self.date_4, schedule_template_id=schedule_template_new.id)
        if new_record:
            self.inform_about_creation(new_record)
            self.set_link_to_record(new_record)

    @api.multi
    def check_workflow_constraints(self):
        res = super(EDocument, self).check_workflow_constraints()
        for rec in self.filtered(lambda d: d.template_id == self.env.ref(TEMPLATE)):
            contract = rec.employee_id2.with_context(date=rec.date_4).contract_id
            appointment = contract.with_context(date=rec.date_4).appointment_id
            if not contract:
                raise exceptions.ValidationError(
                    _('Current contract of employee {} could not be found.').format(rec.employee_id2.name_related))
            if not appointment:
                raise exceptions.ValidationError(
                    _('Current appointment of employee {} could not be found').format(rec.employee_id2.name_related))
            schedule_template_type = appointment.schedule_template_id.template_type
            if not schedule_template_type or schedule_template_type not in ['fixed', 'suskaidytos']:
                raise exceptions.ValidationError(
                    _('You cannot {} this order because the employees work time depends on post and work time norm. '
                      'You have to change them first.').format(_('sign')))
        return res

    @api.multi
    def execute_confirm_workflow_check_values(self):
        super(EDocument, self).execute_confirm_workflow_check_values()
        for rec in self.filtered(lambda t: t.template_id == self.env.ref(TEMPLATE)):
            appointment = rec.employee_id2.contract_id.with_context(date=rec.date_4).appointment_id
            if not appointment:
                raise exceptions.ValidationError(
                    _('Current appointment of employee {} could not be found').format(rec.employee_id2.name_related))
            schedule_template_type = appointment.schedule_template_id.template_type
            if not schedule_template_type or schedule_template_type not in ['fixed', 'suskaidytos']:
                raise exceptions.ValidationError(
                    _('You cannot {} this order because the employees work time depends on post and work time norm. '
                      'You have to change them first.').format(_('form')))


EDocument()
