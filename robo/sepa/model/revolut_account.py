# -*- encoding: utf-8 -*-
from odoo import fields, models, _, api, exceptions, tools, exceptions
from odoo.tools.misc import ustr


class RevolutAccount(models.Model):
    _name = 'revolut.account'
    _description = 'Store information relative to Revolut accounts'

    name = fields.Char(string='Pavadinimas', translate=False)
    uuid = fields.Char(string='ID (Revolut)')
    journal_id = fields.Many2one('account.journal', string='Žurnalas') #TODO:  maybe have a way to set it?
    revolut_api_id = fields.Many2one('revolut.api', required=True)
    currency_id = fields.Many2one('res.currency', string='Valiuta')
    is_currency_crypto = fields.Boolean(string='Currency is a cryptocurrency')
    leg_ids = fields.One2many('revolut.api.transaction.leg', 'revolut_account_id')
    bank_account_iban = fields.Char(string='Banko sąskaitos nr.')
    bank_account_bic = fields.Char(string='Bank sąskaitos BIC')

    @api.multi
    def name_get(self):
        names = []
        for rec in self:
            if rec.bank_account_iban:
                names.append((rec.id, '%s (%s) %s' % (rec.name, rec.bank_account_iban[-4:], rec.currency_id.name)))
            else:
                names.append((rec.id, '%s %s' % (rec.name, rec.currency_id.name)))
        return names

    @api.multi
    @api.constrains('uuid')
    def _check_unique_uuid(self):
        for rec in self:
            if rec.uuid and self.env['revolut.account'].search_count([('uuid', '=', rec.uuid), ('id', '!=', rec.id)]):
                raise exceptions.ValidationError(_('Sąskaitos UUID turi būti unikalus'))

    @api.model
    def create(self, vals):
        res = super(RevolutAccount, self).create(vals)
        if not self.env.context.get('skip_journal_creation'):
            domain = []
            if res.bank_account_iban:
                bank_account_id = self.env['res.partner.bank'].search([
                    ('acc_number', '=', res.bank_account_iban),
                ], limit=1).id
                domain.extend([
                    '|', '&',
                    ('import_file_type', '=', 'revolut'),
                    ('bank_account_id', '=', False),
                    ('bank_account_id', '=', bank_account_id)
                ])
            else:
                domain.append(('import_file_type', '=', 'revolut'))

            if res.currency_id.id == self.env.user.company_id.currency_id.id:
                domain.extend([
                    '|',
                    ('currency_id', '=', False),
                    ('currency_id', '=', res.currency_id.id)
                ])
            else:
                domain.append(('currency_id', '=', res.currency_id.id))

            journal = self.env['account.journal'].sudo().search(domain)
            if not journal:
                code = self.env['ir.sequence'].next_by_code('revolut.api.journal')
                while self.env['account.journal'].sudo().search_count([('code', '=', code)]):
                    code = self.env['ir.sequence'].next_by_code('revolut.api.journal')
                journal_vals = {
                    'type': 'bank',
                    'name': 'Revolut %s [%s]' % (code, res.name),
                    'code': code,
                    'currency_id': res.currency_id.id,
                    'import_file_type': 'revolut',
                    'revolut_account_id': res.id,
                }
                self.env['account.journal'].sudo().create(journal_vals)
            elif len(journal) > 1:
                self.inform_about_multiple_revolut_journals_therefore_not_being_able_to_associate(journal=journal)
            elif len(journal) == 1:
                journal.revolut_account_id = res.id
        return res

    @api.multi
    def unlink(self):
        if self.env['revolut.api.transaction.leg'].search([('revolut_account_id', 'in', self.ids)], limit=1):
            raise exceptions.UserError(_('Negalima ištrinti šios sąskaitos, nes ji turi susijusių operacijų dalių'))
        if self.env['account.journal'].search([('revolut_account_id', 'in', self.ids)], limit=1):
            raise exceptions.UserError(_('Negalima ištrinti šios sąskaitos, nes ji turi susijusių žurnalų'))
        return super(RevolutAccount, self).unlink()

    @api.multi
    def set_iban_bic(self):
        for rec in self:
            try:
                api = rec.revolut_api_id
                response = api.get_bank_account_details_response(rec.uuid)
                iban, bic = api.get_bank_account_details(response)
                rec.bank_account_iban = iban
                rec.bank_account_bic = bic
            except Exception as e:
                raise exceptions.UserError(_("Nepavyko gauti IBAN ir BIC:\n %s") % ustr(e))

    @api.model
    def inform_about_multiple_revolut_journals_therefore_not_being_able_to_associate(self, journal):
        """
        Method for creating a ticket if a revolut account could not be associated with a journal because of multiple
        revolut journal entries existing
        """
        subject = _('Multiple Revolut journals found, could not decide which one to use')
        body = _('Multiple revolut journals have been found, could not decide which one to assign: \n{}'
                 ).format('\n'.join(journal.mapped('name')))
        try:
            ticket_obj = self.sudo()._get_ticket_rpc_object()
            vals = {
                'ticket_dbname': self.env.cr.dbname,
                'ticket_model_name': self._name,
                'ticket_record_id': False,
                'name': subject,
                'ticket_user_login': self.env.user.login,
                'ticket_user_name': self.env.user.name,
                'description': body,
                'ticket_type': 'accounting',
                'user_posted': self.env.user.name
            }
            res = ticket_obj.create_ticket(**vals)
            if not res:
                raise exceptions.UserError('The distant method did not create the ticket.')
        except Exception as e:
            message = 'Failed to create ticket for informing about multiple revolut journals failure\nException: %s' % \
                      (str(e.args))
            self.env['robo.bug'].sudo().create({
                'user_id': self.env.user.id,
                'error_message': message,
            })


RevolutAccount()
