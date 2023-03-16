# -*- coding: utf-8 -*-
from odoo import models, fields, exceptions, api, _


class NsoftCashierMapper(models.Model):
    _name = 'nsoft.cashier.mapper'

    ext_cashier_id = fields.Integer(string='External cashier ID')
    employee_id = fields.Many2one('hr.employee', string='Employee')
    created_automatically = fields.Boolean(string='Created automatically')
    default_mapper = fields.Boolean(
        string='Default mapper',
        help='Default mapper is used when no other mapper is found for specific external ID',
    )

    @api.multi
    @api.constrains('ext_cashier_id')
    def _check_ext_cashier_id(self):
        """Ensure that cashier ID is unique"""
        for rec in self:
            if self.search_count([('ext_cashier_id', '=', rec.ext_cashier_id)]) > 1:
                raise exceptions.ValidationError(
                    _('Record with external ID [{}] already exists!').format(rec.ext_cashier_id)
                )

    @api.multi
    @api.constrains('employee_id')
    def _check_employee_id(self):
        """Ensure that employee ID is unique"""
        for rec in self.filtered(lambda x: x.employee_id):
            if self.search_count([('employee_id', '=', rec.employee_id.id)]) > 1:
                raise exceptions.ValidationError(
                    _('Record with employee {} already exists!').format(rec.employee_id.display_name)
                )

    @api.multi
    @api.constrains('default_mapper', 'employee_id')
    def _check_default_mapper(self):
        """Ensure that only one default mapper is set"""
        for rec in self.filtered(lambda x: x.default_mapper):
            # Ensure that default mapper has employee set
            if rec.default_mapper and not rec.employee_id:
                raise exceptions.ValidationError(
                    _('You cannot set default mapper without employee ID!'))
            # Ensure that only one default mapper exists
            if self.search_count([('default_mapper', '=', True)]) > 1:
                raise exceptions.ValidationError(
                    _('Only one default mapper can be set!')
                )

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(rec.id, '[{}] -> [{}]'.format(
            rec.ext_cashier_id, rec.employee_id.display_name or _('Undefined'))) for rec in self]
