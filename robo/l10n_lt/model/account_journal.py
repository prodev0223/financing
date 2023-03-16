# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    active = fields.Boolean(string='Aktyvus', default=True)
    skip_cash_reports = fields.Boolean(string='Netraukti į ataskaitas susijusias su kasos operacijomis', default=False)
    update_posted = fields.Boolean(default=True)

    @api.constrains('type', 'currency_id', 'name', 'bank_acc_number')
    def _check_bank_currency_unique(self):
        for rec in self:
            if rec.type != 'bank':
                continue
            same_bank_accounts_len = self.search_count([
                ('type', '=', 'bank'),
                ('currency_id', '=', rec.currency_id.id),
                '|',
                ('name', '=', rec.name),
                ('bank_acc_number', '=', rec.bank_acc_number)
            ])
            if same_bank_accounts_len > 1:
                raise exceptions.UserError(
                    _('Bankai su ta pačia banko sąskaita arba žurnalo pavadinimu privalo turėti skirtingas valiutas'))

    @api.model
    def _get_cash_sequence_prefix(self, code, refund=False):
        prefix = code.upper()
        if refund:
            prefix = prefix + '2'
        else:
            prefix = prefix + '1'
        return prefix

    @api.model
    def _create_cash_sequence(self, vals, refund=False):
        prefix = self._get_cash_sequence_prefix(vals['code'], refund)
        seq = {
            'name': vals['name'],
            'implementation': 'no_gap',
            'prefix': prefix,
            'padding': 4,
            'number_increment': 1,
            'use_date_range': False,
            'code': prefix,
        }
        if 'company_id' in vals:
            seq['company_id'] = vals['company_id']
        return self.env['ir.sequence'].create(seq)

    @api.model
    def create(self, vals):
        if not vals.get('code'):
            raise exceptions.Warning(_('Klaida kuriant žurnalą! Žurnalas privalo turėti kodą.'))
        if not vals.get('sequence_id') and vals.get('type') == 'cash':
            vals.update({'sequence_id': self.sudo()._create_cash_sequence(vals).id})
        if not vals.get('refund_sequence_id'):
            if vals.get('type') == 'cash':
                vals.update({'refund_sequence_id': self.sudo()._create_cash_sequence(vals, refund=True).id,
                             'refund_sequence': True})
            elif vals.get('type') == 'sale':
                sequence_id = self.env['ir.sequence'].sudo().search([('code', '=', 'KR')]).id
                if sequence_id:
                    vals.update({'refund_sequence_id': sequence_id,
                                 'refund_sequence': True})
        if 'currency_id' in vals:
            company_currency_id = self.env.user.company_id.sudo().currency_id.id
            if vals.get('currency_id') == company_currency_id:
                vals.pop('currency_id')
        return super(AccountJournal, self).create(vals)

    @api.multi
    def write(self, vals):
        if 'currency_id' in vals:
            company_currency_id = self.env.user.company_id.sudo().currency_id.id
            if vals.get('currency_id') == company_currency_id:
                vals.update(currency_id=False)
        return super(AccountJournal, self).write(vals)

    @api.multi
    def copy(self, default=None):
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.ValidationError(_('Negalima kopijuoti žurnalo. Kurkite naują žurnalo įrašą.'))
        return super(AccountJournal, self).copy(default=default)

    @api.model
    def _prepare_liquidity_account(self, name, company, currency_id, type):
        return super(AccountJournal, self.with_context(show_views=True))._prepare_liquidity_account(name, company, currency_id, type)
