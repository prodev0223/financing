# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models


class RecomputeAnalyticsEmployeeCardWizard(models.TransientModel):
    _name = 'recompute.analytics.employee.card.wizard'

    employee_id = fields.Many2one('hr.employee', string='Employee')
    date_from = fields.Date(string='Date from')
    date_to = fields.Date(string='Date to')

    @api.multi
    def recompute_analytic_entries(self):
        self.ensure_one()
        if not self.env.user.is_accountant():
            raise exceptions.UserError(_('You do not have sufficient rights'))

        if self.date_from > self.date_to:
            raise exceptions.UserError(_('"Date from" needs to be earlier than "Date to"'))

        payslips = self.env['hr.payslip'].search([
            ('employee_id', '=', self.employee_id.id),
            ('date_from', '<', self.date_to),
            ('date_to', '>', self.date_from),
        ])
        for payslip in payslips:
            if self._context.get('set_default_analytics'):
                payslip.set_default_analytics()
            payslip.create_analytic_entries()


RecomputeAnalyticsEmployeeCardWizard()
