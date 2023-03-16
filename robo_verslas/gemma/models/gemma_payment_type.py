# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, exceptions


class GemmaPaymentType(models.Model):
    _name = 'gemma.payment.type'

    ext_type_id = fields.Integer(string='Mokėjimo tipo kodas')
    name = fields.Char(string='Mokėjimo tipo pavadinimas')
    is_active = fields.Boolean(string='Aktyvus', default=True)
    do_reconcile = fields.Boolean(string='Automatiškai dengti sąskaitas', default=True)
    journal_id = fields.Many2one('account.journal', string='Susietas žurnalas', inverse='set_state')

    state = fields.Selection([('active', 'Veikiantis'),
                              ('warning', 'Trūksta konfigūracijos')], string='Būsena', default='active')

    @api.one
    def set_state(self):
        if self.journal_id:
            self.state = 'active'
        else:
            self.state = 'warning'

    @api.multi
    def unlink(self):
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Negalima ištrinti Gemma mokėjimo tipo!'))
        return super(GemmaPaymentType, self).unlink()


GemmaPaymentType()
