# -*- coding: utf-8 -*-
from odoo import models, api, tools


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    @api.multi
    def _compute_tax_id(self):
        for line in self:
            fpos = self.order_id.fiscal_position_id
            if self.env.uid == tools.SUPERUSER_ID:
                company_id = self.env.user.company_id.id
                line.taxes_id = fpos.with_context(product_type=line.product_id.acc_product_type).map_tax(
                    line.product_id.supplier_taxes_id.filtered(lambda r: r.company_id.id == company_id))
            else:
                line.taxes_id = fpos.with_context(product_type=line.product_id.acc_product_type).map_tax(
                    line.product_id.supplier_taxes_id)
            for tax in line.taxes_id:
                if not self.env.user.sudo().company_id.with_context({'date': line.order_id.date_order}).vat_payer:
                    line.taxes_id = [(3, tax.id,)]
