# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, exceptions


class GemmaCashRegister(models.Model):
    _name = 'gemma.cash.register'

    number = fields.Char(string='Kasos aparato numeris', required=True, inverse='base_partner')
    name = fields.Char(string='Kasos/Departamento pavadinimas')
    partner_id = fields.Many2one('res.partner', string='Susietas Partneris')

    location_id = fields.Many2one('stock.location',
                                  default=lambda self: self.env['stock.location'].search(
                                      [('usage', '=', 'internal')], order='create_date desc', limit=1),
                                  domain="[('usage','=','internal')]", string='Kasos aparato lokacija')

    journal_id = fields.Many2one('account.journal', default=lambda self: self.env['account.journal'].search(
        [('type', '=', 'sale')], limit=1), string='Pagrindinis Žurnalas')

    state = fields.Selection([('working', 'Kasos aparatas veikiantis'),
                              ('failed', 'Trūksta konfigūracijos (Žurnalas, Lokacija, Partneris)')],
                             string='Būsena', track_visibility='onchange', compute='compute_state')

    vat_mappers = fields.One2many('gemma.vat.mapper', 'cash_register_id', string='PVM kodų sąrašas')

    @api.one
    @api.depends('journal_id', 'location_id', 'number', 'partner_id')
    def compute_state(self):
        if self.journal_id and self.location_id and self.number and self.partner_id:
            self.state = 'working'
        else:
            self.state = 'failed'

    @api.constrains('number')
    def number_constrain(self):
        for rec in self:
            if rec.number:
                if self.env['gemma.cash.register'].search_count(
                        [('id', '!=', self.id), ('number', '=', rec.number)]):
                    raise exceptions.ValidationError(_('Kasos aparatas jau egzistuoja!'))

    @api.one
    def base_partner(self):
        if self.number:
            self.partner_id = self.env['res.partner'].search([('kodas', '=', 'Gemma ' + self.number)])
            if not self.partner_id:
                country_id = self.env['res.country'].sudo().search([('code', '=', 'LT')], limit=1)
                partner_vals = {
                    'gemma_register': True,
                    'name': self.name if self.name else 'Gemma ' + self.number,
                    'is_company': True,
                    'kodas': 'Gemma ' + self.number,
                    'country_id': country_id.id,
                    'property_account_receivable_id': self.env['account.account'].sudo().search(
                        [('code', '=', '2410')], limit=1).id,
                    'property_account_payable_id': self.env['account.account'].sudo().search(
                        [('code', '=', '4430')], limit=1).id,
                    }
                self.partner_id = self.env['res.partner'].sudo().create(partner_vals)

    @api.multi
    def write(self, vals):
        if 'number' in vals:
            vals.pop('number')
        return super(GemmaCashRegister, self).write(vals)

    @api.multi
    def unlink(self):
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Negalima ištrinti Gemma kasos aparato!'))
        return super(GemmaCashRegister, self).unlink()


GemmaCashRegister()
