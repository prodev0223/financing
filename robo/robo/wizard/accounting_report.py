# -*- coding: utf-8 -*-


from odoo import _, api, models


class AccountingReport(models.TransientModel):
    _inherit = 'accounting.report'

    @api.multi
    def name_get(self):
        return [(rec.id, _('Finansinė ataskaita')) for rec in self]

    # @api.model
    # def default_get(self, fields_list):
    #     res = super(Report, self).default_get(fields_list)
    #     if 'date_from' in fields_list and self._context.get('default_account_report_id', False) and self._context.get('default_account_report_id', False) == self.env.ref('sl_general_report.balansas0').id:
    #         res['date_from'] = '2016-01-01'
    #     return res
