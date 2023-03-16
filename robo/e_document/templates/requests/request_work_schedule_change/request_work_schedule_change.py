# -*- coding: utf-8 -*-
from odoo import models, api, exceptions, _

TEMPLATE = 'e_document.request_work_schedule_change_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def request_work_schedule_change_workflow(self):
        self.ensure_one()
        attendance_ids = []
        worked_hours = 0
        for line in self.fixed_attendance_ids:
            vals = {
                'hour_from': line.hour_from,
                'hour_to': line.hour_to,
                'dayofweek': line.dayofweek
            }
            attendance_ids.append((0, 0, vals))
            worked_hours += line.hour_to - line.hour_from

        appointment = self.employee_id1.with_context(date=self.date_3).appointment_id
        nedarbingumas = appointment.darbingumas
        nedarbingumas_type = False
        if nedarbingumas:
            if nedarbingumas.id == self.env.ref('l10n_lt_payroll.0_25').id:
                nedarbingumas_type = '0_25'
            elif nedarbingumas.id == self.env.ref('l10n_lt_payroll.30_55').id:
                nedarbingumas_type = '30_55'

        current_wage = appointment.wage
        use_net = appointment.struct_id.code == 'MEN' and appointment.freeze_net_wage

        if use_net:
            payroll_values = self.env['hr.payroll'].sudo().get_payroll_values(
                date=self.date_1,
                bruto=current_wage,
                force_npd=None if appointment.use_npd else 0.0,
                voluntary_pension=appointment.sodra_papildomai and appointment.sodra_papildomai_type,
                disability=appointment.darbingumas.name if appointment.invalidumas else False,
                is_foreign_resident=appointment.employee_id.is_non_resident,
                is_fixed_term=appointment.contract_id.is_fixed_term,
            )
            current_wage = payroll_values.get('neto', 0.0)

        schedule_change_document = self.env['e.document'].with_context(
            bypass_weekly_hours_mismatch_schedule=True,
            recompute=False
        ).create({
            'template_id': self.env.ref('e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template').id,
            'document_type': 'isakymas',
            'date_document': self.date_document,
            'employee_id2': self.employee_id1.id,
            'date_3': self.date_3,
            'job_id': appointment.job_id.id,
            'date_6': appointment.date_end,
            'darbo_rusis': appointment.contract_id.rusis,
            'struct': appointment.contract_id.struct_id.code,
            'npd_type': 'auto' if appointment.use_npd else 'manual',
            'selection_bool_2': 'false' if not nedarbingumas else 'true',
            'selection_nedarbingumas': nedarbingumas_type,
            'darbo_grafikas': appointment.schedule_template_id.template_type,
            'fixed_schedule_template': 'custom',
            'work_norm': appointment.schedule_template_id.work_norm,
            'etatas': worked_hours/40.0, #P3:DivOK
            'du_input_type': 'neto' if use_net else 'bruto',
            'freeze_net_wage': 'true' if use_net else 'false',
            'department_id2': appointment.department_id.id,
            'float_1': current_wage,
            'fixed_attendance_ids': [(5,)] + attendance_ids,
            'date_1': appointment.trial_date_end,
            'date_2': appointment.trial_date_end,
        })
        self.inform_about_creation(schedule_change_document)
        self.write({'record_model': 'e.document', 'record_id': schedule_change_document.id})

    @api.onchange('employee_id1', 'date_3')
    def _onchange_set_appointment_values(self):
        request_work_schedule_change_doc = self.template_id == self.env.ref(TEMPLATE, raise_if_not_found=False)
        if request_work_schedule_change_doc:
            appointment = self.employee_id1.sudo().with_context(date=self.date_3).appointment_id
            if appointment:
                ids = []
                for line in appointment.schedule_template_id.fixed_attendance_ids:
                    vals = {
                        'hour_from': line.hour_from,
                        'hour_to': line.hour_to,
                        'dayofweek': line.dayofweek
                    }
                    ids.append((0, 0, vals))
                self.fixed_attendance_ids = [(5,)] + ids

    @api.multi
    def execute_confirm_workflow_check_values(self):
        super(EDocument, self).execute_confirm_workflow_check_values()
        for rec in self.filtered(lambda t: t.template_id == self.env.ref(TEMPLATE, raise_if_not_found=False)):
            if not rec.fixed_attendance_ids:
                raise exceptions.UserError(_('Work schedule was not set'))
            appointment = rec.employee_id1.contract_id.with_context(date=rec.date_3).appointment_id
            if not appointment:
                raise exceptions.ValidationError(
                    _('Current appointment of employee {} could not be found').format(rec.employee_id1.name_related))
            schedule_template_type = appointment.sudo().schedule_template_id.template_type
            if not schedule_template_type or schedule_template_type not in ['fixed', 'suskaidytos']:
                raise exceptions.ValidationError(
                    _('Request for {} can not be formed because work time depends on post and work time norm. In order to '
                      'change them, please contact your HR manager').format(rec.employee_id1.name_related))


EDocument()
