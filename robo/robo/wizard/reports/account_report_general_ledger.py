# -*- coding: utf-8 -*-

from odoo import models, api, _


class AccountReportGeneralLedger(models.TransientModel):

    """
    Extend general ledger report in ROBO, so it can inherit robo.threaded.report
    """

    _name = 'account.report.general.ledger'
    _inherit = ['account.report.general.ledger', 'robo.threaded.report']

    @api.multi
    def button_generate_report(self):
        """
        Generate current report. Later method determines the mode -- threaded/normal
        :return: Result of specified method
        """

        forced_xls = self._context.get('xls_report')
        method_name = 'check_report'
        if hasattr(self, method_name):
            return self.env['robo.report.job'].generate_report(
                self, method_name, _('Didžioji knyga'), forced_xls=forced_xls)

    @api.multi
    def button_generate_pdf_report(self):
        return self.button_generate_report()

    @api.multi
    def button_generate_xls_report(self):
        return self.with_context(xls_report=True).button_generate_report()


AccountReportGeneralLedger()
