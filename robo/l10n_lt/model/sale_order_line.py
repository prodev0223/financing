# -*- coding: utf-8 -*-
from odoo import models, api

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.onchange('tax_id')
    def onchange_tax_ids(self):
        if self.tax_id and self.tax_id.mapped('child_tax_ids'):
            vals = []
            for tax_id in self.tax_id:
                vals.append((4, tax_id.id))
            for child_id in self.tax_id.mapped('child_tax_ids'):
                vals.append((4, child_id.id))
            self.tax_id = vals

    @api.multi
    def _compute_tax_id(self):
        for line in self:
            fpos = line.order_id.fiscal_position_id or line.order_id.partner_id.property_account_position_id
            # If company_id is set, always filter taxes by the company
            taxes = line.product_id.taxes_id.filtered(lambda r: not line.company_id or r.company_id == line.company_id)
            line.tax_id = fpos.with_context(product_type=line.product_id.acc_product_type).map_tax(
                taxes) if fpos else taxes
            for tax in line.tax_id:
                if not self.env.user.sudo().company_id.with_context({'date': line.order_id.date_order}).vat_payer:
                    line.tax_id = [(3, tax.id,)]
        self._change_taxes_price_included()
