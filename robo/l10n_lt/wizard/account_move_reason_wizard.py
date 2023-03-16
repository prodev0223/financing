# -*- coding: utf-8 -*-
from odoo import models, fields, api


# TODO: Remove next week
class AccountMoveReasonWizard(models.TransientModel):
    _name = 'account.move.reason.wizard'

    reason_text = fields.Text(string='Keitimo priežastis', required=True)

    @api.multi
    def post(self):
        move_id = self.env['account.move'].browse(self._context.get('move_id'))
        move_id.write({'change_reason_text': self.reason_text})
        move_id.with_context(web_edit=False).post()
