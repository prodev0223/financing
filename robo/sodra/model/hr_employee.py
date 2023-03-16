# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    exclude_from_sam = fields.Boolean(string='Neįtraukti į SAM pranešimą',
                                      groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager",
                                      )
    last_name_split_index = fields.Integer(string='Number of words in last name', default=1)

    @api.multi
    @api.constrains('last_name_split_index')
    def _check_last_name_split_index(self):
        for rec in self:
            if rec.last_name_split_index <= 0:
                raise exceptions.ValidationError(_('The lowest possible number of words in last name is 1'))

    @api.multi
    def get_split_name(self):
        self.ensure_one()
        first_name = last_name = str()
        name = self.name or self.address_home_id.name
        if name:
            split_index = self.last_name_split_index or 1
            names = self.name.split()
            first_name = " ".join(names) if len(names) <= split_index else " ".join(names[0:-split_index])
            last_name = " ".join(names[-split_index:]) if len(names) > split_index else str()

        return {'first_name': first_name, 'last_name': last_name}


HrEmployee()
