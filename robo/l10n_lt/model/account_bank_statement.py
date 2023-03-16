# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AccountBankStatement(models.Model):
    _inherit = 'account.bank.statement'

    journal_type = fields.Selection([('sale', 'Sale'),
                                     ('purchase', 'Purchase'),
                                     ('cash', 'Cash'),
                                     ('bank', 'Bank'),
                                     ('general', 'Miscellaneous'),
                                     ],
                                    compute='_journal_type_compute',
                                    help='Technical field used for usability purposes')

    @api.one
    @api.depends('journal_id')
    def _journal_type_compute(self):
        self.journal_type = self.journal_id.type
