# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountMoveLine(models.Model):

    _inherit = 'account.move.line'

    eksportuota = fields.Boolean(
        string='Eksportuotas mokėjimas',
        default=False, groups='account.group_account_user',
        copy=False
    )
