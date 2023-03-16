# -*- coding: utf-8 -*-


from odoo import _, api, exceptions, fields, models


class CashReceiptNumberWizard(models.TransientModel):
    _name = 'cash.receipt.number.wizard'

    def default_number(self):
        active_id = self._context.get('active_id', False)
        if active_id:
            receipt_id = self.env['cash.receipt'].browse(active_id)
            return receipt_id.name
        return False

    number = fields.Char(string='Kvito numeris', default=default_number)

    @api.multi
    def change_number(self):
        self.ensure_one()
        if not self.env.user.is_accountant():
            return False
        active_id = self._context.get('active_id', False)
        if active_id:
            receipt_id = self.env['cash.receipt'].browse(active_id)
            number = self.number
            receipt_id.write({
                'move_name': number,
                'name': number
            })
            move_id = receipt_id.move_line_ids.mapped('move_id')
            if move_id:
                if not number:
                    raise exceptions.UserError(
                        _('Patvirtinto kvito numerio negalima pakeisti į tuščią.\nPirmiau atšaukite kvitą.'))
                move_id.write({
                    'name': number,
                })
                receipt_id.move_line_ids.write({
                    'name': number,
                })
