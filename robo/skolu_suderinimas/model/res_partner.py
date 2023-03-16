# -*- coding: utf-8 -*-

from odoo import models, fields, _, api


class ResPartner(models.Model):

    _inherit = 'res.partner'

    zero_value = fields.Float(string='Zero', help='used in reports to print value formatted by company localization',
                              default=0, store=False)

    @api.multi
    def multiple_debt_reconciliation(self):
        if self.env.user.is_manager() or self.env.user.has_group('robo.group_debt_reconciliation_reports'):
            ctx = {'partner_ids': self.mapped('id'),
                   'default_all_partners': False, }
            return {
                'context': ctx,
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'debt.act.wizard',
                'view_id': False,
                'type': 'ir.actions.act_window',
                'target': 'new',
            }

    @api.model
    def create_partner_debt_actions(self):
        action = self.env.ref('skolu_suderinimas.multiple_debt_reconciliation')
        if action and not action.menu_ir_values_id:
            action.create_action()

    def get_doc_type(self, doc_type):
        if doc_type == 'invoice':
            return _('Sąskaita faktūra')
        elif doc_type == 'payment':
            return _('Mokėjimas')
        elif doc_type == 'account':
            return _('Sąskaita')
        else:
            return _('Kita operacija')


ResPartner()
