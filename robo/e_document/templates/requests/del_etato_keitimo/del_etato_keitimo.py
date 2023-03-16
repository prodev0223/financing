# -*- coding: utf-8 -*-
from odoo import models, api, exceptions, _, fields, tools


class EDocument(models.Model):
    _inherit = 'e.document'

    employee_post = fields.Float(compute='_compute_employee_post')

    @api.multi
    @api.onchange('employee_id1', 'date_1')
    def _set_initial_employee_post(self):
        template = self.env.ref('e_document.prasymas_del_etato_keitimo_template', raise_if_not_found=False)
        for rec in self:
            if rec.template_id == template:
                employee = rec.employee_id1
                user_employee_ids = self.env.user.employee_ids
                if rec.template_id == template and rec.date_1 and employee and employee.id in user_employee_ids.ids:
                    contract = rec.employee_id1.with_context(date=rec.date_1).sudo().contract_id
                    appointment = contract.with_context(date=rec.date_1).sudo().appointment_id
                    rec.float_1 = appointment.schedule_template_id.etatas
                else:
                    rec.float_1 = 1.0

    @api.multi
    @api.depends('employee_id1', 'date_1')
    def _compute_employee_post(self):
        template = self.env.ref('e_document.prasymas_del_etato_keitimo_template', raise_if_not_found=False)
        for rec in self:
            if rec.template_id == template and rec.date_1 and rec.employee_id1:
                contract = rec.employee_id1.with_context(date=rec.date_1).contract_id
                appointment = contract.with_context(date=rec.date_1).appointment_id
                rec.employee_post = appointment.schedule_template_id.etatas
            else:
                rec.employee_post = 1.0

    @api.multi
    def prasymas_del_etato_keitimo_workflow(self):
        self.ensure_one()

        appointment = self.employee_id1.with_context(date=self.date_1).appointment_id
        if not appointment:
            raise exceptions.UserError(_('Nurodytai datai neturite galiojančios darbo sutarties'))

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
                contract=appointment.contract_id,
            )
            current_wage = payroll_values.get('neto', 0.0)

        salary_change_document = self.env['e.document'].with_context(
            bypass_weekly_hours_mismatch_schedule=True,
            recompute=False
        ).create({
            'template_id': self.env.ref('e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template').id,
            'document_type': 'isakymas',
            'date_document': self.date_document,
            'employee_id2': self.employee_id1.id,
            'date_3': self.date_1,
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
            'etatas': self.float_1,
            'du_input_type': 'neto' if use_net else 'bruto',
            'freeze_net_wage': 'true' if use_net else 'false',
            'float_1': current_wage,
            'fixed_attendance_ids': [(5,)],
            'date_1': appointment.trial_date_end,
            'date_2': appointment.trial_date_end,
        })
        self.inform_about_creation(salary_change_document)
        self.write({'record_model': 'e.document', 'record_id': salary_change_document.id})

    @api.multi
    def execute_confirm_workflow_check_values(self):
        super(EDocument, self).execute_confirm_workflow_check_values()
        template = self.env.ref('e_document.prasymas_del_etato_keitimo_template', raise_if_not_found=False)
        for rec in self.filtered(lambda d: d.template_id == template):
            date = rec.date_1
            if date and not \
                    rec.sudo().employee_id1.with_context(date=date).contract_id.with_context(date=date).appointment_id:
                raise exceptions.UserError(_('Nurodytai datai neturite galiojančios darbo sutarties'))
            if tools.float_compare(rec.float_1, 0.0, precision_digits=2) <= 0 or \
                tools.float_compare(rec.float_1, 1.5, precision_digits=2) > 0:
                raise exceptions.UserError(_('Etatas privalo būti tarp 0 ir 1.5'))
            if date and rec.employee_id1 and rec.sudo().employee_post == rec.float_1:
                raise exceptions.UserError(_('Etatas nurodytai datai ir etatas, į kurį norite keisti, sutampa.'))


EDocument()
