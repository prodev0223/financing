# -*- coding: utf-8 -*-
from odoo import models, fields


class StockReasonLine(models.Model):

    _name = 'stock.reason.line'

    name = fields.Char(string='Write-off reason')
    account_id = fields.Many2one('account.account', string='Write-off account')
