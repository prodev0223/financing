# -*- coding: utf-8 -*-


from odoo import api, fields, models


class ApEmployeeSelectWizard(models.TransientModel):
    _name = 'ap.employee.select.wizard'

    invoice_id = fields.Many2one('account.invoice')
    ap_employee_id = fields.Many2one('hr.employee', string='Apmokėjęs darbuotojas', copy=False)

    @api.multi
    def post(self):
        self.ensure_one()
        self.invoice_id.write({'ap_employee_id': self.ap_employee_id.id})
        self.invoice_id.app_inv_own()
