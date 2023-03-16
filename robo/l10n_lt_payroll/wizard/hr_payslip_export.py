# -*- coding: utf-8 -*-
import json

from odoo import models, api, fields


class HrPayslipExportWizard(models.TransientModel):
    _name = 'hr.payslip.export'

    type_of_export = fields.Selection(selection=[('0', 'Darbo užmokesčio pažyma'),
                                                 ('1', 'Atsiskaitymo lapelis')],
                                      string='Eksportavimo tipas', default='0', required=True)

    @api.multi
    def export_payslip(self):
        self.ensure_one()
        payslip_ids = self._context.get('active_ids', [])
        payslips = self.env['hr.payslip'].browse(payslip_ids)
        export_report = 'report_algalapis_israsas_sl' if self.type_of_export == '1' else 'report_algalapis_sl'
        export_report = 'l10n_lt_payroll.%s' % export_report
        return self.env['report'].get_action(payslips, export_report,
                                             data={'context': json.dumps(self._context),
                                                   'doc_ids': self._context.get('active_ids', [])})


HrPayslipExportWizard()
