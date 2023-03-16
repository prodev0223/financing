# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, models, tools


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    @api.multi
    def unlink(self):
        if not self.env.user.is_accountant():
            if any(invoice.state in ['open', 'paid'] for invoice in self.sudo().mapped('invoice_ids')):
                raise exceptions.UserError(_('To daryti negalima. Prašome susiekti su Jūsų buhalteriu'))
        return super(StockPicking, self).unlink()
