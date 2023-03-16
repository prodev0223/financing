# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import models, fields, api, tools


class ResUsers(models.Model):
    _inherit = 'res.users'

    region_manager_document_ids = fields.Many2many('e.document', 'e_document_region_manager_res_user_rel',
                                                   'e_document_id', 'res_users_id', store=True,
                                                   compute='_compute_region_manager_document_ids')

    @api.multi
    @api.depends('employee_ids')
    def _compute_region_manager_document_ids(self):
        EDocument = self.env['e.document']
        for rec in self:
            documents = EDocument
            region_managers = rec.mapped('employee_ids.region_manager_ids')
            for manager in region_managers:
                region_manager_document_domain = EDocument.get_region_manager_e_document_domain(manager)
                documents |= EDocument.search(region_manager_document_domain)
            rec.region_manager_document_ids = documents
        self.env['ir.rule'].clear_cache()

    @api.multi
    def is_region_manager(self):
        self.ensure_one()
        return self.has_group('e_document_region_manager.group_e_document_region_manager')

    @api.multi
    def is_region_manager_at_date(self, department_id, date=None):
        """Find out if user is a manager of a provided department in a region"""
        self.ensure_one()
        if date is None:
            date = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        if not self.is_region_manager() or not department_id:
            return False
        region_managers = self.mapped('employee_ids.region_manager_ids')
        return any([x.date_start <= date <= x.date_stop and department_id in x.department_ids.ids
                    for x in region_managers])

    @api.multi
    def get_accessible_departments(self):
        self.ensure_one()
        EDocumentRegionManager = self.env['e.document.region.manager']
        department_domain = []
        if self.is_region_manager():
            date = datetime.today().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            region_manager_domain = EDocumentRegionManager.get_region_manager_domain(self.id, date)
            departments = EDocumentRegionManager.sudo().search(region_manager_domain). \
                mapped('department_ids')
            department_domain = [('id', 'in', departments.ids)]
        departments = self.env['hr.department'].search(department_domain)
        return departments
