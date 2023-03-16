# -*- coding: utf-8 -*-
from odoo import fields, exceptions, models, api, _


class HrPayslipRunPayslipPrint(models.TransientModel):
    _name = 'hr.payslip.run.payslip.print'

    employee_ids = fields.Many2many('hr.employee', string='Darbuotojai')
    payslip_run_id = fields.Many2one('hr.payslip.run', required=True)

    @api.multi
    def export_selected_payslip(self):
        self.ensure_one()
        if not self.employee_ids:
            raise exceptions.UserError(_('Nepasirinkote darbuotojo.'))
        return self.env['report'].get_action(self, 'l10n_lt_payroll.report_suvestine_sl',
                                             data={'employee_ids': self.employee_ids.ids,
                                                   'payslip_run_id': self.payslip_run_id.ids})


HrPayslipRunPayslipPrint()
