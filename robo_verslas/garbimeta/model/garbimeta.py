# -*- coding: utf-8 -*-
from odoo import models


class ReportAgedPartnerBalance(models.AbstractModel):
    _inherit = 'report.sl_general_report.report_agedpartnerbalance_sl'

    @staticmethod
    def _get_account_code_mapping():
        return {'payable': ['4430', '4481', '4482'],
                'receivable': ['2410']}


ReportAgedPartnerBalance()
