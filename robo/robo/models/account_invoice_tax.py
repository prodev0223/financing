# -*- coding: utf-8 -*-


from odoo import api, models


class AccountInvoiceTax(models.Model):
    _inherit = 'account.invoice.tax'

    @api.multi
    def action_change_line_vals(self):
        self.ensure_one()

        wizard_id = self.env['invoice.change.tax.line.wizard'].with_context(default_amount=self.amount).create({
            'tax_line_id': self.id,
        }).id

        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'invoice.change.tax.line.wizard',
            'res_id': wizard_id,
            'view_id': self.env.ref('robo.wizard_change_tax_line_vals_form').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }
