# -*- coding: utf-8 -*-
from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    balance_reconciliation_date = fields.Datetime(groups='robo_basic.group_robo_premium_manager,'
                                                         'robo.group_robo_see_reconciliation_information_partner_cards')


ResPartner()
