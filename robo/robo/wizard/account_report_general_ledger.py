# -*- coding: utf-8 -*-
from odoo import _, api, models


class AccountReportGeneralLedger(models.TransientModel):

    _inherit = "account.report.general.ledger"

    @api.multi
    def btn_download_xlsx(self):
        """ Use Fast SQL query to write into XLSX file """
        filename = 'DK_%s_%s_%s.xlsx' % (self.env.user.company_id.name, self.date_from, self.date_to)

        if self.sudo().env.user.company_id.activate_threaded_front_reports:
            return self.env['robo.report.job'].generate_report(
                self, 'generate_xlsx', _('Didžoji knyga'), returns='base64', forced_name=filename, forced_extension='xls')
        else:
            return super(AccountReportGeneralLedger, self).btn_download_xlsx()
