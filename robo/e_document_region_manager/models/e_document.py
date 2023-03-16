# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import api, models, tools, fields


class EDocument(models.Model):
    _inherit = 'e.document'

    current_user_region_manager = fields.Boolean(compute='_compute_current_user_region_manager',
                                                 search='_search_current_user_region_manager')
    department_employee_ids = fields.Many2many('hr.employee', compute='_compute_department_ids')
    department_ids = fields.Many2many('hr.department', compute='_compute_department_ids')

    @api.multi
    def _compute_current_user_region_manager(self):
        """
        Field 'current_user_region_manager' is used only in the filter for now, this compute method is not triggered
        :return: None
        """
        pass

    def _search_current_user_region_manager(self, operator, value):
        if operator == '=' and value is True:
            EDocument = self.sudo()
            user = self.env.user
            document_ids = []
            if user.is_region_manager():
                EDocumentRegionManager = self.env['e.document.region.manager']
                region_manager_domain = EDocumentRegionManager.get_region_manager_domain(user.id)
                region_managers = EDocumentRegionManager.sudo().search(region_manager_domain)
                for manager in region_managers:
                    region_manager_document_domain = self.get_region_manager_e_document_domain(manager)
                    document_ids += EDocument.search(region_manager_document_domain).ids
            return [('id', 'in', list(set(document_ids)))]
        return [('current_user_region_manager', operator, value)]

    @api.multi
    @api.depends('template_id', 'date_document')
    def _compute_department_ids(self):
        HrEmployee = self.env['hr.employee']
        HrDepartment = self.env['hr.department']
        EDocumentRegionManager = self.env['e.document.region.manager']
        for rec in self.filtered('template_id.is_signable_by_region_manager'):
            employee_domain = []
            department_domain = []
            document_user = rec.sudo().user_id
            # If the document was created by a region manager, constrain its employee domain to the region
            user = document_user if document_user and document_user.is_region_manager() else self.env.user
            if user.is_region_manager():
                document_date = rec.date_document or datetime.today().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                region_manager_domain = EDocumentRegionManager.get_region_manager_domain(user.id, document_date)
                department_ids = EDocumentRegionManager.sudo().search(region_manager_domain). \
                    mapped('department_ids').ids
                employee_domain = [('department_id', 'in', department_ids)]
                department_domain = [('id', 'in', department_ids)]
            employees = HrEmployee.search(employee_domain)
            departments = HrDepartment.search(department_domain)
            rec.department_employee_ids = [(6, 0, employees.ids)]
            rec.department_ids = [(6, 0, departments.ids)]

    @api.onchange('template_id', 'date_document')
    def _onchange_date_document(self):
        employee_domain = []
        department_domain = []
        document_user = self.sudo().user_id
        # If the document was created by a region manager, constrain its employee domain to the region
        user = document_user if document_user and document_user.is_region_manager() else self.env.user
        if self.template_id.is_signable_by_region_manager and user.is_region_manager():
            document_date = self.date_document or datetime.today().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            EDocumentRegionManager = self.env['e.document.region.manager']
            region_manager_domain = EDocumentRegionManager.get_region_manager_domain(user.id, document_date)
            department_ids = EDocumentRegionManager.sudo().search(region_manager_domain).\
                mapped('department_ids').ids
            employee_domain = [('department_id', 'in', department_ids)]
            department_domain = [('id', 'in', department_ids)]
        return {'domain': {'employee_id2': employee_domain, 'department_id2': department_domain}}

    @api.model
    def get_region_manager_e_document_domain(self, manager):
        company = self.env.user.company_id.sudo()
        domain = [('reikia_pasirasyti_iki', '>=', manager.date_start),
                  ('reikia_pasirasyti_iki', '<=', manager.date_stop),
                  ('template_id.is_signable_by_region_manager', '=', True),
                  ('template_id', 'not in', company.manager_restricted_document_templates.ids)]
        # Skip documents that may have a combination of employees from different departments not all of them
        # accessible to the region manager
        documents_to_skip_ids = self.env['e.document'].sudo().search(
            [('e_document_line_ids.employee_id2.department_id', 'not in', manager.department_ids.ids)] + domain).ids
        domain += ['|',
                   ('employee_id2.department_id', 'in', manager.department_ids.ids),
                   '&',
                   ('e_document_line_ids.employee_id2.department_id', 'in', manager.department_ids.ids),
                   ('id', 'not in', documents_to_skip_ids)]
        return domain

    @api.multi
    def check_user_can_sign(self, raise_if_false=True):
        self.ensure_one()
        user = self.env.user
        company = user.company_id.sudo()
        is_cancel_order = self.template_id.id == \
                          self.env.ref('e_document.isakymas_del_ankstesnio_vadovo_isakymo_panaikinimo_template').id
        # If it is a cancel order, the cancellable document should be checked instead
        document = self.cancel_id if is_cancel_order else self
        template = document.template_id

        is_signable_by_region_manager = template and template.is_signable_by_region_manager and template \
                                        not in company.manager_restricted_document_templates
        if self.env.user.is_region_manager() and is_signable_by_region_manager:
            employee_data_is_accessible = True
            # If there are document lines, check each employee data access by line
            if document.e_document_line_ids:
                for line in document.e_document_line_ids:
                    employee_data_is_accessible = employee_data_is_accessible and line.employee_data_is_accessible()
            else:
                employee_data_is_accessible = document.employee_data_is_accessible()
            if employee_data_is_accessible:
                return True
        # Make further checks if user is not able to sign as a region manager
        return super(EDocument, self).check_user_can_sign(raise_if_false)

    @api.multi
    def _set_reikia_pasirasyti_iki(self):
        EDocumentRegionManager = self.env['e.document.region.manager'].sudo()
        for rec in self.filtered('template_id.is_signable_by_region_manager'):
            EDocumentRegionManager.search([
                ('date_start', '<=', rec.reikia_pasirasyti_iki),
                ('date_stop', '>=', rec.reikia_pasirasyti_iki)
            ]).mapped('employee_id.user_id')._compute_region_manager_document_ids()

    @api.model
    def create(self, vals):
        res = super(EDocument, self).create(vals)
        res._set_reikia_pasirasyti_iki()
        return res

    @api.multi
    def write(self, vals):
        res = super(EDocument, self).write(vals)
        if set(('template_id', 'date_from', 'date_time_from', 'date_1', 'date_2', 'date_3', 'date_4', 'date_5',
                 'document_type', 'state', 'reikia_pasirasyti_iki')).intersection(vals):
            self._set_reikia_pasirasyti_iki()
        return res

    @api.multi
    def employee_data_is_accessible(self):
        """
        Method to specify if employee data should be accessible for the current user
        :return: Indication if employee data may be accessible for the user
        """
        self.ensure_one()
        user = self.env.user
        if user.is_manager() or user.is_hr_manager():
            return True
        if not self.template_id.is_signable_by_region_manager or not self.employee_id2.department_id or not \
                user.employee_ids or not user.is_region_manager():
            return False
        date = self.date_document or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        return user.employee_ids[0].is_region_manager_at_date(self.employee_id2.department_id.id,
                                                              self.template_id.id, date)

    @api.multi
    def get_partners_to_inform_about_orders_waiting_for_signature(self):
        self.ensure_one()

        # Get base partners to inform
        partner_ids = super(EDocument, self).get_partners_to_inform_about_orders_waiting_for_signature()

        # Find related departments of the document
        document_employees = self.sudo().related_employee_ids
        related_departments = document_employees.mapped('department_id')

        # Find region managers for those departments as of today
        today = datetime.today().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        region_managers = self.env['e.document.region.manager'].sudo().search([
            ('date_start', '<=', today),
            ('date_stop', '>=', today),
            ('department_ids', 'in', related_departments.ids),
            ('e_document_template_ids', 'in', [self.template_id.id]),
        ])

        managers_to_inform = self.env['e.document.region.manager']
        for manager in region_managers:
            # Check if a document falls under the manager domain.
            manager_domain = self.get_region_manager_e_document_domain(manager)
            inform_about_document = manager_domain and self.id in self.sudo().search(manager_domain).ids
            if inform_about_document:
                managers_to_inform |= manager

        # Add region managers to the partner list
        region_manager_partners = managers_to_inform.mapped('employee_id.address_home_id')
        partner_ids += region_manager_partners.ids

        partner_ids = list(set(partner_ids))
        return partner_ids
