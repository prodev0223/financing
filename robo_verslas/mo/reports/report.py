# -*- coding: utf-8 -*-
from odoo import models, api


class ReportDebtReconciliationBase(models.AbstractModel):

    """
    Base model that is inherited by debt reconciliation report multi and
    debt reconciliation report multi minimal
    """

    _inherit = 'report.debt.reconciliation.base'

    @api.model
    def get_default_payable_receivable(self, mode='payable_receivable'):
        """
        return default payable receivable accounts (2410/4430)
        :param mode: all/payable_receivable/receivable/payable
        :return: account.account ID's (list)
        """
        default_receivable_account = self.env['account.account'].search([('code', '=', '2410')])
        default_payable_account = self.env['account.account'].search([('code', '=', '4430')])
        if mode in ['payable_receivable', 'all']:
            default_payable_account |= default_receivable_account
            return default_payable_account.ids
        if mode in ['receivable']:
            return default_receivable_account.ids
        if mode in ['payable']:
            return default_payable_account.ids
