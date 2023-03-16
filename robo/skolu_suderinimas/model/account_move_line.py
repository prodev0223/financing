# -*- coding: utf-8 -*-

from odoo import models, api


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.multi
    def get_cluster_currency_id(self):
        self.ensure_one()
        cluster = self.get_reconcile_cluster()
        invoices = cluster.mapped('invoice_id')
        if invoices:
            return invoices.mapped('currency_id')[0].id
        else:
            currencies = cluster.mapped('currency_id')
            if currencies:
                return currencies[0].id
            else:
                return self.env.user.company_id.currency_id.id


AccountMoveLine()
