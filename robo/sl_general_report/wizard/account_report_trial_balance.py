# -*- coding: utf-8 -*-

from odoo import models, api, fields


class AccBalanceReport(models.TransientModel):

    _inherit = "account.balance.report"

    display_account = fields.Selection(selection_add=[
        ('movement_or_not_zero', 'With movements or balance not equal to 0')
    ])

    def _print_report(self, data):
        data = self.pre_print_report(data)
        return self.env['report'].get_action(self, 'sl_general_report.report_trialbalance_sl', data=data)

    @api.multi
    def xls_export(self):
        return self.check_report()
