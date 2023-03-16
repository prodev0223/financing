# -*- encoding: utf-8 -*-
from odoo import models, fields


class AccountPayment(models.Model):

    _inherit = 'account.payment'

    def _default_signed_employee_id(self):
        return self.env.user.sudo().company_id.vadovas.id

    signed_employee_id = fields.Many2one('hr.employee', default=_default_signed_employee_id)

