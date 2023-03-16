# -*- coding: utf-8 -*-
from odoo import models, api, tools
from datetime import datetime
from dateutil.relativedelta import relativedelta


class AccountInvoice(models.Model):

    _inherit = 'account.invoice'

    @api.multi
    def action_invoice_open(self):
        res = super(AccountInvoice, self).action_invoice_open()
        for rec in self.filtered(lambda x: x.type in ['in_invoice', 'in_refund']):
            if rec.date_invoice and rec.date_due and rec.date_invoice == rec.date_due:
                date_due = (datetime.strptime(rec.date_due, tools.DEFAULT_SERVER_DATE_FORMAT) +
                            relativedelta(weeks=2)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                rec.date_due = date_due
        return res


AccountInvoice()
