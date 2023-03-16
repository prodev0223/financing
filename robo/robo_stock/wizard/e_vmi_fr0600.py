# -*- coding: utf-8 -*-
from odoo import models, api
from odoo.tools import float_round


class FR0600(models.TransientModel):
    _inherit = 'e.vmi.fr0600'

    @api.multi
    def get_vat_restore_amount(self):
        """
        Return amount to subtract from deductible VAT which is computed
        from inventory write-offs' move lines posted in tax account
        :return: Amount to subtract from deductible VAT
        """
        self.ensure_one()
        tax = self.env['account.tax'].search([('code', '=', 'PVM1'), ('nondeductible', '=', False),
                                              ('type_tax_use', '=', 'purchase'),
                                              ('price_include', '=', False)], limit=1)
        amount = 0.0
        if tax:
            move_lines = self.env['account.move.line'].search([('date', '>=', self.data_nuo),
                                                               ('date', '<=', self.data_iki),
                                                               ('account_id', '=', tax.account_id.id),
                                                               ('move_id.state', '=', 'posted'),
                                                               ('inventory_id', '!=', False)])
            amount = sum(move_lines.mapped(lambda r: r.credit - r.debit))
        amount = int(float_round(amount, precision_digits=0))

        amount += super(FR0600, self).get_vat_restore_amount()
        return amount


FR0600()
