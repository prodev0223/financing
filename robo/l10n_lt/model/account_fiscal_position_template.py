# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountFiscalPositionTemplate(models.Model):
    _inherit = 'account.fiscal.position.template'

    not_country_id = fields.Many2one('res.country', string='Not Country',
                                     help='Apply only if delivery or invoicing country does not match.')
    not_country_group_id = fields.Many2one('res.country.group', string='Not in Country Group',
                                           help='Apply only if delivery or invoicing country does not match the group.')
    auto_apply = fields.Boolean(string='Detect Automatically', help="Apply automatically this fiscal position.")
    vat_required = fields.Boolean(string='VAT required', help="Apply only if partner has a VAT number.")
