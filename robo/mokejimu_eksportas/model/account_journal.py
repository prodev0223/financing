# -*- coding: utf-8 -*-
from odoo import models, api, fields, exceptions, _


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    front_name = fields.Char(string='Front-end name', help='This is displayed to user in the bank export wizard')

    @api.multi
    @api.depends('name', 'currency_id', 'company_id', 'company_id.currency_id', 'bank_account_id',
                 'bank_account_id.bank_id', 'bank_account_id.bank_id.name', 'bank_account_id.acc_number')
    def name_get(self):
        res = []
        if self.env.context.get('display_bank_account'):
            for journal in self.filtered(lambda j: j.bank_account_id):
                bank_account = journal.bank_account_id
                currency = journal.currency_id or journal.company_id.currency_id
                name = "%s (%s) %s" % (bank_account.bank_id.name, bank_account.acc_number[-4:],
                                       currency.name)
                if journal.front_name:
                    name += " (%s)" % journal.front_name
                res += [(journal.id, name)]

            res += super(AccountJournal, self.filtered(lambda j: not j.bank_account_id)).name_get()
        else:
            res = super(AccountJournal, self).name_get()
        return res

    @api.multi
    def unlink(self):
        """Ensure that there's no related bank statements / payment exports when trying to unlink the journal"""
        for rec in self:
            if self.env['account.bank.statement'].search_count([('journal_id', '=', rec.id)]) \
                    or self.env['mokejimu.eksportas'].search_count([('journal_id', '=', rec.id)]):
                raise exceptions.ValidationError(
                    _('Negalite ištrinti žurnalo nes jis turi susijusių banko išrašų arba mokėjimo eksportų')
                )
        return super(AccountJournal, self).unlink()
