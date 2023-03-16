# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    depreciation_line_id = fields.Many2one('account.asset.depreciation.line')
    asset_id = fields.Many2one('account.asset.asset', readonly=True, copy=False)


AccountMove()
