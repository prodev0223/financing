# -*- coding: utf-8 -*-
from odoo import models, fields, _, api
from odoo.tools.sql import drop_view_if_exists


class AccountMoveLine(models.Model):

    _inherit = 'account.move.line'

    reconciled_with_a_klase = fields.Boolean(string='Rekonsilijuotas su A klase', compute='_reconciled_with_a_klase', store=True)

    @api.one
    @api.depends('matched_debit_ids.debit_move_id.a_klase_kodas_id', 'matched_credit_ids.credit_move_id.a_klase_kodas_id')
    def _reconciled_with_a_klase(self):
        if any(aml.a_klase_kodas_id for aml in self.matched_debit_ids.mapped('debit_move_id')) or any(aml.a_klase_kodas_id for aml in self.matched_credit_ids.mapped('credit_move_id')):
            self.reconciled_with_a_klase = True
        else:
            self.reconciled_with_a_klase = False

AccountMoveLine()
