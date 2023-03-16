# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _


class RasoPaymentType(models.Model):
    _name = 'raso.payment.type'

    payment_type_code = fields.Char(string='Mokėjimo tipo kodas')
    payment_type_name = fields.Char(string='Mokėjimo tipo pavadinimas')
    is_active = fields.Boolean(string='Aktyvus', default=True)
    do_reconcile = fields.Boolean(string='Automatiškai dengti sąskaitas', default=True)
    journal_id = fields.Many2one('account.journal', string='Susietas žurnalas', inverse='set_state')
    state = fields.Selection([
        ('active', 'Veikiantis'),
        ('warning', 'Trūksta konfigūracijos'),
    ], string='Būsena', compute='_compute_state', store=True)

    # TODO: Remove partner ID after code update
    partner_id = fields.Many2one('res.partner', string='Susietas partneris')

    @api.multi
    @api.depends('journal_id')
    def _compute_state(self):
        """Computes the state based on whether the journal record exists for current type"""
        for rec in self:
            rec.state = 'active' if rec.journal_id else 'warning'

    # CRUD -----------------------------------------------------------------------------------------------------------

    @api.multi
    def write(self, vals):
        if 'payment_type_code' in vals and not self.env.user.has_group('base.group_system'):
            vals.pop('payment_type_code')
        return super(RasoPaymentType, self).write(vals)

    @api.multi
    def unlink(self):
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Negalima ištrinti mokėjimo tipo!'))
        return super(RasoPaymentType, self).unlink()

    # Other Methods ---------------------------------------------------------------------------------------------------

    @api.multi
    def name_get(self):
        """Custom name-get"""
        return [(rec.id, str(rec.payment_type_name)) for rec in self]