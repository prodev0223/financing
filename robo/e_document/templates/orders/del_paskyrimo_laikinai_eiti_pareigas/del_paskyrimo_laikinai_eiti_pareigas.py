# -*- coding: utf-8 -*-
from odoo import models, api, exceptions, fields, _

TEMPLATE = 'e_document.isakymas_del_paskyrimo_laikinai_eiti_pareigas_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    show_extra_interim_work_duties_fields = fields.Boolean(compute='_compute_show_extra_interim_work_duties_fields')

    @api.multi
    @api.depends('employee_id2', 'date_from', 'date_document')
    def _compute_show_extra_interim_work_duties_fields(self):
        """Check whether extra fields (job_id2 / num_work_days) should be shown in the template"""
        # Ref current template
        template = self.env.ref(TEMPLATE, False)
        for rec in self.filtered(lambda x: x.template_id == template):
            # Check if employee has a contract for either date from or date document, if
            # both of them are not set, contract_id compute uses today's date
            contract_date = rec.date_from or rec.date_document
            if rec.employee_id2 and not rec.employee_id2.with_context(date=contract_date).contract_id:
                rec.show_extra_interim_work_duties_fields = True

    @api.multi
    def check_workflow_constraints(self):
        body = super(EDocument, self).check_workflow_constraints()
        template = self.env.ref(TEMPLATE)
        for rec in self.filtered(lambda d: d.template_id == template):
            existing_holiday = self.env['hr.holidays'].search([('employee_id', '=', rec.employee_id3.id),
                                                               ('state', '=', 'validate'),
                                                               ('date_from_date_format', '<=', rec.date_to),
                                                               ('date_to_date_format', '>=', rec.date_from)])
            if existing_holiday:
                body += _('Cannot sign the document - the employee that is being delegated has a leave.')

            is_department_delegate = rec.selection_bool_1 == 'true' and rec.politika_atostogu_suteikimas == 'department'
            company_manager_is_delegated = not is_department_delegate and \
                                           rec.employee_id2.id == rec.env.user.sudo().company_id.vadovas.id
            department_manager_is_delegated = is_department_delegate and rec.department_id2.manager_id and \
                                              rec.employee_id2.id == rec.department_id2.manager_id.id
            if not company_manager_is_delegated and not department_manager_is_delegated:
                body += _('The employee that is being substituted is not manager.')
        return body

    @api.multi
    def isakymas_del_paskyrimo_laikinai_eiti_pareigas_workflow(self):
        self.ensure_one()
        is_department_delegate = self.selection_bool_1 == 'true' and self.politika_atostogu_suteikimas == 'department'

        delegate_values = {
            'employee_id': self.employee_id3.id,
            'date_start': self.date_from,
            'date_stop': self.date_to
        }
        model = 'e.document.department.delegate' if is_department_delegate else 'e.document.delegate'
        if is_department_delegate:
            delegate_values['department_id'] = self.department_id2.id

        employee_all_delegations = self.env[model].search([('employee_id', '=', delegate_values['employee_id'])])
        current_delegation = employee_all_delegations.filtered(
            lambda d: d.date_stop >= delegate_values['date_start'] and d.date_start <= delegate_values['date_stop']
        )
        if not current_delegation:
            self.env[model].create(delegate_values)
        elif len(current_delegation) > 1:
            raise exceptions.ValidationError(_('Chosen employee was delegated {0} times throughout the period chosen '
                                               'on the document').format(len(current_delegation)))
        elif len(current_delegation) == 1:
            if current_delegation.date_start == delegate_values['date_start'] and \
                    current_delegation.date_stop == delegate_values['date_stop']:
                self.write({
                    'record_id': current_delegation.id,
                    'record_model': model,
                })
            else:
                current_delegation.write({
                    'date_start': min(current_delegation.date_start, delegate_values['date_start']),
                    'date_stop': max(current_delegation.date_stop, delegate_values['date_stop']),
                })

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        template = self.env.ref(TEMPLATE, False)
        cancel_document = self.cancel_id
        if cancel_document and cancel_document.template_id == template:
            is_department_delegate = cancel_document.selection_bool_1 == 'true' and \
                                     cancel_document.politika_atostogu_suteikimas == 'department'
            model = 'e.document.department.delegate' if is_department_delegate else 'e.document.delegate'
            domain = [
                ('employee_id', '=', cancel_document.employee_id3.id),
                ('date_start', '=', cancel_document.date_from),
                ('date_stop', '=', cancel_document.date_to)
            ]
            if is_department_delegate:
                domain.append(('department_id', '=', cancel_document.department_id2.id))
            self.env[model].search(domain, limit=1).unlink()
        else:
            return super(EDocument, self).execute_cancel_workflow()


EDocument()
