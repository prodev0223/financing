
# -*- encoding: utf-8 -*-
from odoo import fields, models, _, api, exceptions, tools
from .. import paysera_tools as pt


class PayseraWalletIBAN(models.Model):
    _name = 'paysera.wallet.iban'

    # ID fields
    paysera_wallet_id = fields.Many2one('paysera.wallet', string='Paysera wallet ID', ondelete='cascade')
    journal_id = fields.Many2one('account.journal', string='Related journal')
    currency_id = fields.Many2one('res.currency', string='Currency', required=True)
    iban = fields.Char(string='Bank account (IBAN)', required=True, inverse='_set_wallet_data')

    # Wallet amounts
    api_end_balance = fields.Float(string='API end balance')
    api_reserved_amount = fields.Float(string='API reserved amount')
    api_balance_update_date = fields.Datetime(string='API balance update date', inverse='_set_wallet_data')

    @api.multi
    def _set_wallet_data(self):
        """
        Inverse //
        Find related account journal record based on IBAN,
        if it does not exist yet, create it.
        Force the api_end_balance and api_balance_update_date
        to related account.journal record
        :return: None
        """
        # Base values
        company_currency = self.env.user.company_id.currency_id
        res_bank = self.env['res.bank'].search([('bic', '=', pt.STATIC_PAYSERA_BIC)])
        journal_ob = self.sudo().env['account.journal']

        for rec in self:
            journal = rec.journal_id
            # If journal does not exist, try to search for it
            if not journal:
                # Build a domain, if company currency differs
                # from IBAN currency, add it to search domain
                domain = [('bank_acc_number', '=', rec.iban), ('type', '=', 'bank')]
                if rec.currency_id.id != company_currency.id:
                    domain += [('currency_id', '=', rec.currency_id.id)]
                else:
                    domain += ['|', ('currency_id', '=', company_currency.id), ('currency_id', '=', False)]
                journal = journal_ob.search(domain, limit=1)

                # If journal does not exist, create it
                if not journal:
                    code = journal_ob.get_journal_code_bank()
                    journal_vals = {
                        'name': '%s (%s) %s' % (res_bank.name, rec.iban[-4:], rec.currency_id.name),
                        'code': code,
                        'bank_statements_source': 'file_import',
                        'type': 'bank',
                        'company_id': self.env.user.company_id.id,
                        'bank_acc_number': rec.iban,
                        'bank_id': res_bank.id,
                    }
                    if rec.currency_id.id != company_currency.id:
                        journal_vals.update({'currency_id': rec.currency_id.id})
                    journal = journal_ob.create(journal_vals)

                # Write newly created, or found journal to the record
                rec.write({'journal_id': journal.id})

            # If inverse is triggered, always force end balance and update date
            journal.write({
                'api_end_balance': rec.api_end_balance,
                'api_balance_update_date': rec.api_balance_update_date
            })
            journal._compute_api_integrated_bank()

    @api.multi
    @api.constrains('currency_id')
    def _check_currency_id(self):
        """
        Constraints //
        Ensure that there is no more than 1 IBAN with the
        same currency for the same wallet
        :return: None
        """
        for rec in self:
            if self.env['paysera.wallet.iban'].search_count(
                    [('currency_id', '=', rec.currency_id.id),
                     ('paysera_wallet_id', '=', rec.paysera_wallet_id.id)]) > 1:
                raise exceptions.ValidationError(
                    _('You cannot have two IBAN accounts of the same currency for the same wallet!'))

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(rec.id, rec.iban) for rec in self]


PayseraWalletIBAN()
