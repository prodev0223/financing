# -*- coding: utf-8 -*-


from odoo import fields, models


class AccountInvoiceTagsDetails(models.Model):
    _name = 'account.invoice.tags.details'

    invoice_id = fields.Many2one('account.invoice')
    tag_id = fields.Many2one('account.invoice.tags')
    details = fields.Html('Details')
