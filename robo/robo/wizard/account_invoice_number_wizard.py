# -*- coding: utf-8 -*-


from odoo import _, api, exceptions, fields, models


class AccountInvoiceNumberWizard(models.TransientModel):
    _name = 'account.invoice.number.wizard'

    def default_number(self):
        active_id = self._context.get('active_id', False)
        if active_id:
            invoice_id = self.env['account.invoice'].browse(active_id)
            return invoice_id.move_name
        return False

    def default_reference(self):
        active_id = self._context.get('active_id', False)
        if active_id:
            invoice_id = self.env['account.invoice'].browse(active_id)
            return invoice_id.reference
        return False

    number = fields.Char(string='Sąskaitos numeris', default=default_number)
    reference = fields.Char(string='Tiekėjo numeris', default=default_reference)
    show_ref_field = fields.Boolean(compute='compute_view_status')

    @api.one
    @api.depends('number')
    def compute_view_status(self):
        active_id = self._context.get('active_id', False)
        if active_id:
            invoice_id = self.env['account.invoice'].browse(active_id)
            if invoice_id.type in ['in_invoice', 'in_refund']:
                self.show_ref_field = True

    @api.multi
    def change_number(self):
        self.ensure_one()
        if not (self.env.user.is_accountant() or self.env.user.has_group(
                'robo_basic.group_robo_select_invoice_journal')):
            return False
        active_id = self._context.get('active_id', False)
        if active_id:
            invoice_id = self.env['account.invoice'].browse(active_id)
            number = self.number
            reference = self.reference
            invoice_id.write({
                'move_name': number,
                'number': number,
                'reference': reference
            })
            if invoice_id.move_id:
                if not number or (not reference and invoice_id.type in ['in_invoice', 'in_refund']):
                    raise exceptions.UserError(
                        _('Patvirtintos sąskaitos numerio negalima pakeisti į tuščią.\nPirmiau atšaukite sąskaitą.'))
                invoice_id.move_id.write({
                    'name': number,
                })
                if invoice_id.type in ['in_invoice', 'in_refund']:
                    invoice_id.move_id.line_ids.filtered(lambda a: a.name == a.ref).write({
                        'name': reference,
                    })
                    invoice_id.move_id.line_ids.write({
                        'ref': reference,
                    })
