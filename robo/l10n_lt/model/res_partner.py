# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    property_account_payable_id = fields.Many2one('account.account',
                                                  default=lambda self: self.env['account.account'].search(
                                                      [('code', '=', '4430')], limit=1).id)
    property_account_receivable_id = fields.Many2one('account.account',
                                                     default=lambda self: self.env['account.account'].search(
                                                         [('code', '=', '2410')], limit=1).id)

    @api.multi
    def name_get(self):
        if self._context.get('special_display_name'):
            return [(record.id, "ID: {0}, {1}".format(str(record.id), str(record.name))) for record in self]
        else:
            return super(ResPartner, self).name_get()

    @api.model
    def default_get(self, field_list):
        res = super(ResPartner, self).default_get(field_list)
        res['property_account_payable_id'] = self.env['account.account'].search([('code', '=', '4430')], limit=1).id
        res['property_account_receivable_id'] = self.env['account.account'].search([('code', '=', '2410')], limit=1).id
        return res
