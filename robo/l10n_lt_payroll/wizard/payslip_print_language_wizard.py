# -*- coding: utf-8 -*-

import json

from odoo import models, api, fields


class PayslipPrintLanguageWizard(models.TransientModel):
    _name = 'payslip.print.language.wizard'

    def _get_default_payslip_id(self):
        return self._context.get('payslip_id') or False

    payslip_id = fields.Many2one('hr.payslip', default=_get_default_payslip_id)

    @api.multi
    def render_payslip_note(self):
        if not self.payslip_id:
            return False

        return self.env['report'].get_action(
            self.payslip_id,
            'l10n_lt_payroll.report_algalapis_israsas_v2_sl',
            data={
                'context': json.dumps({'force_lang': self._context.get('lang', False)}),
                'doc_ids': self.payslip_id.id
            }
        )


PayslipPrintLanguageWizard()
