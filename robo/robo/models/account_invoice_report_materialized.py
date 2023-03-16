# -*- coding: utf-8 -*-


from odoo import api, models


class AccountInvoiceReportMaterialized(models.Model):
    _name = 'account.invoice.report.materialized'
    _inherit = ['account.invoice.report', 'robo.threaded.materialized.view']
    _auto = False

    @api.model_cr
    def init(self):
        self._cr.execute('''
        CREATE MATERIALIZED VIEW IF NOT EXISTS account_invoice_report_materialized AS 
        SELECT * FROM account_invoice_report
        ''')

    @api.model
    def refresh_view(self):
        if super(AccountInvoiceReportMaterialized, self).refresh_view():
            self._cr.execute('REFRESH MATERIALIZED VIEW account_invoice_report_materialized')
