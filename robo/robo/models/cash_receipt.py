# -*- coding: utf-8 -*-


from odoo import api, fields, models


class CashReceipt(models.Model):
    _name = 'cash.receipt'
    _inherit = ['cash.receipt', 'ir.attachment.drop']

    custom_name = fields.Char(string='Custom cash receipt name')
    cash_receipt_name = fields.Char(string='Custom cash receipt header', compute='_compute_cash_receipt_name',
                                    default='Cash receipt')

    @api.multi
    def _compute_cash_receipt_name(self):
        user = self.env.user
        enabled_company_settings_group = user.company_id.custom_cash_receipt_header_enabled
        for rec in self:
            rec.cash_receipt_name = rec.custom_name if enabled_company_settings_group and rec.custom_name else rec.name

    @api.multi
    def action_receipt_change_number(self):
        self.ensure_one()
        ctx = dict(self._context)
        ctx['active_id'] = self.id
        action = self.env.ref('robo.change_cash_receipt_number_wizard').read()[0]
        action['context'] = ctx
        return action
