# -*- coding: utf-8 -*-
import exceptions

from odoo import api, fields, models, _


class ChangeUserPartnerOfEmployeeWizard(models.TransientModel):
    _name = 'change.user.partner.of.employee.wizard'

    user_id = fields.Many2one('res.users', string='User')
    partner_id = fields.Many2one('res.partner', string='Partner')
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)

    @api.multi
    def confirm(self):
        self.ensure_one()
        vals = dict()
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserWarning(_('You do not have permission'))
        if self.partner_id:
            vals['address_home_id'] = self.partner_id.id
        if self.user_id:
            vals['user_id'] = self.user_id.id
        return self.employee_id.write(vals)

