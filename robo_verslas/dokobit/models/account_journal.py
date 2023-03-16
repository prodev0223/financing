# -*- encoding: utf-8 -*-
from odoo import fields, models, _, api, exceptions


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    import_file_type = fields.Selection(selection_add=[('islandsbanki', 'Islandsbanki'), ])

    @api.constrains('import_file_type', 'currency_id')
    def _check_icelandic_currency(self):
        for journal in self:
            if journal.import_file_type == 'islandsbanki' and journal.currency_id.name != 'ISK':
                raise exceptions.UserError(
                    _('Negalima importuoti Islandsbanki išrašo į žurnalą, kurio valiuta nėra ISK'))

    @api.multi
    def import_statement(self):
        self.ensure_one()
        if self.import_file_type == 'islandsbanki':
            action_name = 'dokobit.account_bank_statement_import_islandsbanki'
            try:
                [action] = self.env.ref(action_name).read()
            except ValueError:
                raise exceptions.UserError(_('Nenustatytas žurnalo importo tipas'))
            # Note: this drops action['context'], which is a dict stored as a string, which is not easy to update
            action.update({'context': (u"{'default_journal_id': " + str(self.id) + u"}")})
            return action
        else:
            return super(AccountJournal, self).import_statement()
