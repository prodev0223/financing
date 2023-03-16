# -*- coding: utf-8 -*-
from odoo import fields, models, api, _, exceptions, tools


class UXInvoiceEmail(models.Model):
    _inherit = 'ux.invoice.email'

    @api.multi
    def _get_logo_src(self):
        return '/web/binary/account_logo/${object.journal_id.id}'


UXInvoiceEmail()
