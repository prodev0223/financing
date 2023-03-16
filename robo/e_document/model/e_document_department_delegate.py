# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models


class EDocumentDepartmentDelegate(models.Model):
    _name = 'e.document.department.delegate'
    _rec_name = 'employee_id'
    _order = 'date_stop DESC'

    date_start = fields.Date(string='From', required=True)
    date_stop = fields.Date(string='To', required=True)
    employee_id = fields.Many2one('hr.employee', string='Delegate', required=True)
    department_id = fields.Many2one('hr.department', string='Department', required=True)

    @api.multi
    @api.constrains('date_start', 'date_stop')
    def constraint_intersection(self):
        for rec in self:
            if self.search([('department_id', '=', rec.department_id.id), ('date_stop', '>=', rec.date_start),
                            ('date_start', '<=', rec.date_stop)], count=True) > 1:
                raise exceptions.ValidationError(_('Periods cannot intersect'))
            if rec.date_start > rec.date_stop:
                raise exceptions.ValidationError(_('Start date cannot be later than stop date'))

    @api.model
    def create(self, vals):
        res = super(EDocumentDepartmentDelegate, self).create(vals)
        user = res.employee_id.user_id
        if user:
            user.sudo()._compute_department_delegated_document_ids()
        self.env['ir.rule'].clear_caches()
        return res

    @api.multi
    def unlink(self):
        employees = self.mapped('employee_id')
        res = super(EDocumentDepartmentDelegate, self).unlink()
        employees.mapped('user_id').sudo()._compute_department_delegated_document_ids()
        self.env['ir.rule'].clear_caches()
        return res

    @api.multi
    def write(self, vals):
        employees = self.mapped('employee_id')
        res = super(EDocumentDepartmentDelegate, self).write(vals)
        employee_id = vals.get('employee_id')
        if employee_id:
            employees |= self.env['hr.employee'].browse(employee_id).exists()
        employees.mapped('user_id').sudo()._compute_department_delegated_document_ids()
        self.env['ir.rule'].clear_caches()
        return res


EDocumentDepartmentDelegate()
