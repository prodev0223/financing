# -*- coding: utf-8 -*-


from odoo import api, models


class DebtActWizard(models.TransientModel):
    _inherit = 'debt.act.wizard'

    @api.multi
    def generate_debt_act(self):
        if self.env.user.is_manager() or self.env.user.has_group('robo.group_debt_reconciliation_reports'):
            if not self.env.user.is_manager():
                self = self.with_context(limited=True)
            return super(DebtActWizard, self.sudo()).generate_debt_act()
