# -*- coding: utf-8 -*-
from odoo import api, models


class AccountAssetSellWizardLine(models.TransientModel):
    _inherit = 'account.asset.sell.wizard.line'

    @api.multi
    def _get_invoice_line_vals(self):
        res = super(AccountAssetSellWizardLine, self)._get_invoice_line_vals()
        res.update({
            'secondary_uom_qty': self.quantity,
            'secondary_uom_id': self.env.ref('product.product_uom_unit').id,
            'secondary_uom_price_unit': self.unit_price
        })
        return res


AccountAssetSellWizardLine()
