# -*- encoding: utf-8 -*-
from odoo import fields, models, _, api, exceptions, tools


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    import_file_type = fields.Selection(selection_add=[('braintree_bk', 'Braintree (BK)'),])

    @api.multi
    def import_statement(self):
        self.ensure_one()
        if self.import_file_type == 'braintree_bk':
            action_name = 'bk.account_bank_statement_import_braintree_bk'
            try:
                [action] = self.env.ref(action_name).read()
            except ValueError:
                raise exceptions.UserError(_('Nenustatytas žurnalo importo tipas'))
            # Note: this drops action['context'], which is a dict stored as a string, which is not easy to update
            action.update({'context': (u"{'default_journal_id': " + str(self.id) + u"}")})
            return action
        else:
            return super(AccountJournal, self).import_statement()
