# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models

REGION_MANAGER_GROUP = 'e_document_region_manager.group_e_document_region_manager'


class EDocumentRegionManager(models.Model):
    _name = 'e.document.region.manager'

    employee_id = fields.Many2one('hr.employee', string='Region manager', required=True)
    date_start = fields.Date(string='From', required=True)
    date_stop = fields.Date(string='To', required=True)
    department_ids = fields.Many2many('hr.department', string='Departments', required=True)
    e_document_template_ids = fields.Many2many('e.document.template', string='E-document templates', required=False,
                                               domain=[('is_signable_by_region_manager', '=', True)])

    @api.multi
    @api.constrains('date_start', 'date_stop')
    def _check_intersection(self):
        for rec in self:
            if self.search([('employee_id', '=', rec.employee_id.id), ('date_stop', '>=', rec.date_start),
                            ('date_start', '<=', rec.date_stop)], count=True) > 1:
                raise exceptions.ValidationError(_('Periods cannot intersect'))
            if rec.date_start > rec.date_stop:
                raise exceptions.ValidationError(_('Start date cannot be later than stop date'))

    @api.model
    def create(self, vals):
        res = super(EDocumentRegionManager, self).create(vals)
        user = res.employee_id.sudo().user_id
        if not user:
            raise exceptions.UserError(_('Employee %s has no related user.') % res.employee_id.name)
        # Add user to region manager group and recompute to gain access to related e-documents
        region_manager_group = self.env.ref(REGION_MANAGER_GROUP)
        user.write({'groups_id': [(4, region_manager_group.id,)]})
        user._compute_region_manager_document_ids()
        self.env['ir.rule'].clear_caches()
        return res

    @api.multi
    def unlink(self):
        employees = self.mapped('employee_id')
        res = super(EDocumentRegionManager, self).unlink()
        users = employees.sudo().mapped('user_id')
        # Remove users from region manager group and recompute to remove access to region manager related e-documents
        region_manager_group = self.env.ref(REGION_MANAGER_GROUP)
        users.write({'groups_id': [(3, region_manager_group.id,)]})
        users._compute_region_manager_document_ids()
        self.env['ir.rule'].clear_caches()
        return res

    @api.multi
    def write(self, vals):
        employees = self.mapped('employee_id')
        region_manager_group = self.env.ref(REGION_MANAGER_GROUP)
        res = super(EDocumentRegionManager, self).write(vals)
        employee_id = vals.get('employee_id')
        if employee_id:
            employee_to_write = self.env['hr.employee'].browse(employee_id).exists()
            if not employee_to_write.sudo().user_id:
                raise exceptions.UserError(_('Employee %s has no related user.') % employee_to_write.name)
            # Add user to region manager group
            employee_to_write.sudo().user_id.write({'groups_id': [(4, region_manager_group.id,)]})
            # Remove users from region manager group
            employees.sudo().mapped('user_id').write({'groups_id': [(3, region_manager_group.id,)]})
            employees |= employee_to_write
        # Recompute to gain/remove access to/from region manager related e-documents
        employees.sudo().mapped('user_id')._compute_region_manager_document_ids()
        self.env['ir.rule'].clear_caches()
        return res

    @api.model
    def get_region_manager_domain(self, user_id, date=None):
        domain = [('employee_id.user_id', '=', user_id)]
        if date:
            domain += [('date_start', '<=', date), ('date_stop', '>=', date)]
        return domain
