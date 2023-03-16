# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, exceptions


class ScoroPaymentType(models.Model):
    _name = 'scoro.payment.type'

    is_active = fields.Boolean(string='Aktyvus', default=True)
    name = fields.Char(string='Mokėjimo tipas')
    internal_code = fields.Char(string='Vidinis sistemos kodas', required=True, readonly=True)
    journal_id = fields.Many2one('account.journal', string='Susietas žurnalas')
    state = fields.Selection([('working', 'Mokėjimo tipas sukonfigūruotas'),
                              ('failed', 'Trūksta konfigūracijos (Pavadinimas, žurnalas)')],
                             string='Būsena', track_visibility='onchange', compute='compute_state')
    create_acc_entries = fields.Boolean(string='Kurti apskaitos įrašus')

    @api.multi
    @api.constrains('internal_code')
    def type_const(self):
        for rec in self.filtered('internal_code'):
            if self.env['scoro.payment.type'].search_count(
                    [('id', '!=', rec.id), ('internal_code', '=', rec.internal_code)]):
                raise exceptions.ValidationError(_('Produkto išorinis identifikatorius negali kartotis!'))

    @api.one
    @api.depends('journal_id', 'name')
    def compute_state(self):
        if self.journal_id and self.name:
            self.state = 'working'
        else:
            self.state = 'failed'

    @api.multi
    def unlink(self):
        if self.mapped('journal_id'):
            raise exceptions.UserError(_('Negalima ištrinti mokėjimo būdo kuris turi susietą žurnalą!'))
        return super(ScoroPaymentType, self).unlink()


ScoroPaymentType()
