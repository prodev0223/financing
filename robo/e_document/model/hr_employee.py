# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import api, exceptions, fields, models, tools, _
from odoo.tools import float_compare


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    delegate_ids = fields.One2many('e.document.delegate', 'employee_id')
    department_delegate_ids = fields.One2many('e.document.department.delegate', 'employee_id')
    is_foreign_resident = fields.Boolean(string='Foreign citizen', compute='_compute_is_foreign_resident')

    show_ending_fixed_term_contract_box = fields.Boolean(compute='_compute_show_ending_fixed_term_contract_box')

    @api.multi
    def is_delegate_at_date(self, date):
        self.ensure_one()
        return any([delegate.date_start <= date <= delegate.date_stop for delegate in self.delegate_ids])

    @api.multi
    def is_department_delegate_at_date(self, department_id, date):
        """ Find out if employee is a delegate of a particular (provided) department """
        self.ensure_one()
        return any([delegate.date_start <= date <= delegate.date_stop and delegate.department_id.id == department_id
                    for delegate in self.department_delegate_ids])

    @api.multi
    def is_any_department_delegate_at_date(self, date):
        """ Find out if employee is a delegate of any existing department """
        self.ensure_one()
        return any([delegate.date_start <= date <= delegate.date_stop for delegate in self.department_delegate_ids])

    @api.multi
    def get_departments_where_employee_is_delegate_at_date(self, date):
        """ Get a list of departments where employee is a delegate on provided date"""
        self.ensure_one()
        departments = list()
        for delegate in self.department_delegate_ids:
            if delegate.date_start <= date <= delegate.date_stop:
                departments.append(delegate.department_id.name)
        return departments

    @api.multi
    def get_information_for_ticket(self):
        self.ensure_one()
        positions = super(HrEmployee, self).get_information_for_ticket()
        date = self._context.get('document_date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        if self.is_delegate_at_date(date):
            positions.append(_('Delegate of the company manager'))
        departments = self.get_departments_where_employee_is_delegate_at_date(date)
        if departments:
            positions.append(_('Delegate of following departments: {}').format(', '.join(departments)))
        return positions

    @api.multi
    def _compute_is_foreign_resident(self):
        """ Compute is employee a foreign resident or a native """
        for rec in self:
            rec.is_foreign_resident = rec.nationality_id.code not in ('LT', False) or rec.is_non_resident

    @api.multi
    def unlink(self):
        """ Override unlink to prevent deletion of hr.employee records with existing related eDocs """
        number_of_related_documents = self.env['e.document'].search_count([
            '|',
            '|',
            '|',
            ('employee_id1', 'in', self.ids),
            ('employee_id2', 'in', self.ids),
            ('employee_id3', 'in', self.ids),
            ('e_document_line_ids.employee_id2', 'in', self.ids),
        ])
        if number_of_related_documents:
            raise exceptions.ValidationError(
                _('There are existing documents ( {} occurrences(-e) ) related to the employee, '
                  'remove them, then try to delete the employee again').format(number_of_related_documents))
        return super(HrEmployee, self).unlink()

    @api.multi
    @api.depends('contract_id.rusis', 'contract_id.date_end')
    def _compute_show_ending_fixed_term_contract_box(self):
        """
        Display a box with buttons, when a fixed term contract is nearing its end, buttons redirect to eDoc templates
        that can change the contract (extend, change type, terminate);
        """
        allowed_groups = [
            'robo_basic.group_robo_free_manager',
            'robo_basic.group_robo_premium_manager',
            'robo_basic.group_robo_hr_manager'
        ]
        if not any(self.env.user.has_group(group) for group in allowed_groups):
            return

        days_before_end_to_display = 3
        today = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_limit = (datetime.utcnow()+relativedelta(days=days_before_end_to_display)).strftime(
            tools.DEFAULT_SERVER_DATE_FORMAT)

        for rec in self:
            contract = rec.contract_id.sudo()
            conditions = contract.rusis == 'terminuota' and today <= contract.work_relation_end_date <= date_limit and \
                         not contract.work_relation_end_date > contract.date_end
            if conditions:
                rec.show_ending_fixed_term_contract_box = True

    @api.multi
    def action_after_fixed_term_contract_end(self):
        """
        Method to create a new document/unarchive an old document depending on button clicked by user. Other, related
        documents are archived.
        :return: form view of the requested template
        """
        action = self._context.get('action')
        mapper = {
            'extend': {
                'template': self.env.ref('e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template'),
                'date_field': 'date_3',
            },
            'change_type': {
                'template': self.env.ref('e_document.isakymas_del_terminuotos_darbo_sutarties_pasibaigimo_ir_darbo_santykiu_tesimo_pagal_neterminuota_darbo_sutarti_template'),
                'date_field': 'date_1_computed',
            },
            'terminate': {
                'template': self.env.ref('e_document.isakymas_del_atleidimo_is_darbo_template'),
                'date_field': 'date_1',
            },
        }
        default_article = self.env['dk.nutraukimo.straipsniai'].search([
            ('straipsnis', '=', '69'),
            ('dalis', '=', '1'),
        ])
        for rec in self:
            contract = rec.contract_id
            related_documents = self.env['e.document'].sudo().with_context(active_test=False).search([
                ('employee_id2', '=', rec.id),
                ('state', '!=', 'e_signed'),
                ('record_model', '=', 'hr.contract'),
                ('record_id', '=', contract.id),
                '|', '|',
                ('template_id', '=', mapper['change_type']['template'].id),
                '&',
                ('template_id', '=', mapper['extend']['template'].id),
                (mapper['extend']['date_field'], '=', contract.work_relation_end_date),
                '&',
                ('template_id', '=', mapper['terminate']['template'].id),
                (mapper['terminate']['date_field'], '=', contract.work_relation_end_date),
            ])
            requested_document = related_documents.filtered(lambda d: d.template_id == mapper[action]['template'])
            other_documents = related_documents - requested_document
            requested_document = requested_document[0] if requested_document else False
            if requested_document and not requested_document.sudo().active:
                requested_document.sudo().toggle_active()
            if not requested_document:
                requested_document = self.get_new_document(action, mapper, contract, default_article)
                requested_document.confirm()
            if other_documents:
                for doc in other_documents.filtered(lambda document: document.sudo().active):
                    doc.sudo().toggle_active()
            return {
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'e.document',
                'res_id': requested_document.id,
                'view_id': mapper[action]['template'].view_id.id,
                'type': 'ir.actions.act_window',
                'target': 'current',
            }

    @api.multi
    def get_new_document(self, action, mapper, contract, article):
        """
        Method to create a new document based on the provided values
        :param action: chosen button on employee card for fixed term contract
        :param mapper: dictionary of template and their respective date_field values
        :param contract: current contract of the employee
        :param article: dk.nutraukimo.straipsnis record to set default on termination document
        :return: e.document record
        """
        self.ensure_one()
        contract_end_date = contract.work_relation_end_date
        date_end_field = mapper[action]['date_field']
        doc_values = {
            'template_id': mapper[action]['template'].id,
            'employee_id2': self.id,
            'document_type': 'isakymas',
            'record_model': 'hr.contract',
            'record_id': contract.id,
        }
        doc_values_additional = {}
        if action == 'extend':
            duration = self.env.user.company_id.fixed_term_contract_extension_by_months or 1
            extended_contract_end = (datetime.utcnow() + relativedelta(months=duration)).strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT)
            fixed_attendance_ids = []
            appointment = contract.appointment_id
            for line in appointment.schedule_template_id.fixed_attendance_ids:
                vals = {
                    'hour_from': line.hour_from,
                    'hour_to': line.hour_to,
                    'dayofweek': line.dayofweek
                }
                fixed_attendance_ids.append((0, 0, vals))

            doc_values_additional = {
                'employee_id': self.id,
                'job_id': self.job_id.id,
                'selection_bool_2': 'true' if appointment.invalidumas else 'false',
                'selection_nedarbingumas': '0_25' if appointment.darbingumas.name == '0_25' else '30_55',
                'darbo_rusis': 'terminuota',
                date_end_field: contract_end_date,
                'date_6': extended_contract_end,
                'work_norm': appointment.schedule_template_id.work_norm,
                'float_1': appointment.wage,
                'fixed_attendance_ids': [(5,)] + fixed_attendance_ids,
                'struct': appointment.struct_id.code,
                'darbo_grafikas': appointment.schedule_template_id.template_type,
                'du_input_type': 'bruto' if float_compare(appointment.wage, appointment.neto_monthly,
                                                          precision_digits=2) == 0 else 'neto',
                'etatas': appointment.schedule_template_id.etatas,
                'selection_1': 'twice_per_month' if appointment.avansu_politika else 'once_per_month',
                'advance_amount': appointment.avansu_politika_suma if appointment.avansu_politika else 0.00,
                'npd_type': 'auto' if appointment.use_npd else 'manual',
            }
            if appointment.struct_id.code == 'MEN':
                doc_values_additional['du_input_type'] = 'neto' if appointment.freeze_net_wage else 'bruto'
        elif action == 'terminate':
            doc_values_additional = {
                'dk_nutraukimo_straipsnis': article.id or False,
                date_end_field: contract_end_date,
            }
        doc_values.update(doc_values_additional)
        return self.env['e.document'].create(doc_values)

    @api.multi
    def _set_robo_access(self):
        self.ensure_one()
        super(HrEmployee, self)._set_robo_access()
        if self.robo_access:
            # Invite to sign e-documents
            documents_to_sign = self.env['e.document'].search([
                ('invite_to_sign_new_users', '=', True),
                ('state', 'not in', ['draft', 'cancel'])
            ]).filtered(lambda u: self.user_id.id not in u.user_ids.mapped('user_id.id'))
            for document in documents_to_sign:
                self.env['signed.users'].create({
                    'document_id': document.id,
                    'user_id': self.user_id.id,
                })
                document.inform_users(self.user_id)


HrEmployee()
