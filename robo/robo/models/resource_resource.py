# -*- coding: utf-8 -*-


from odoo import api, fields, models


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    name = fields.Char(inverse="_set_user_name")

    @api.one
    def _set_user_name(self):
        if self.env.user.is_manager() or self.env.user.is_hr_manager():
            if self.sudo().user_id and self.sudo().user_id.name != self.name:
                self.sudo().user_id.name = self.name
                if self.sudo().user_id.employee_ids:
                    self.sudo().user_id.employee_ids[0].address_home_id.name = self.name
