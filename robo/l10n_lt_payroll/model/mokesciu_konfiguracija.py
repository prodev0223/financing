# -*- coding: utf-8 -*-
from odoo import models


class AccountVATwizard(models.TransientModel):
    _inherit = 'account.vat.wizard'

    def default_bank_journal_id(self):
        return self.env.user.company_id.payroll_bank_journal_id


AccountVATwizard()
