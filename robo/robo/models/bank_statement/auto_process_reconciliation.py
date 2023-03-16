# -*- coding: utf-8 -*-

from odoo import models, fields, _, api, exceptions


class AutoProcessReconciliation(models.TransientModel):
    _name = 'auto.process.reconciliation'

    parent_id = fields.Many2one('account.bank.statement')
    line_ids = fields.Many2many('account.bank.statement.line', string='Transakcijos')
    auto_partner_id = fields.Many2one('res.partner', string='Priverstinis partneris', readonly=True)
    auto_account_id = fields.Many2one('account.account', string='Priverstinė sąskaita', readonly=True)

    @api.multi
    def auto_process_reconciliation(self):
        if not self.line_ids:
            raise exceptions.Warning(_('Nėra sudengiamų įrašų!'))
        self.line_ids.write({
            'account_id': self.auto_account_id.id,
            'partner_id': self.auto_partner_id.id
        })
        self.line_ids.fast_counterpart_creation()


AutoProcessReconciliation()
