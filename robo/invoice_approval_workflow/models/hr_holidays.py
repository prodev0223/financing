# -*- coding: utf-8 -*-

from odoo import api, models


class HrHolidays(models.Model):
    _inherit = 'hr.holidays'

    @api.multi
    def action_validate(self):
        res = super(HrHolidays, self).action_validate()
        self.env['invoice.approval.workflow.step'].sudo().reconfigure_approvers_based_on_holidays()
        return res

    @api.multi
    def action_refuse(self):
        res = super(HrHolidays, self).action_refuse()
        self.env['invoice.approval.workflow.step'].sudo().reconfigure_approvers_based_on_holidays()
        return res
