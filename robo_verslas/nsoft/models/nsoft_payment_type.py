# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, exceptions

payment_type_mapper = {
    'p': {'int_code': 'csh', 'name': 'Grynieji'},
    'c': {'int_code': 'crd', 'name': 'Mokėjimo Kortelės'},
    'k': {'int_code': 'gft', 'name': 'Dovanų Čekiai'},
    'i': {'int_code': 'web', 'name': 'Pardavimai Internetu'},
    'f': {'int_code': 'trans', 'name': 'Pavedimu'},
    }


class NsoftPaymentType(models.Model):
    _name = 'nsoft.payment.type'

    is_active = fields.Boolean(string='Aktyvus', default=True)
    ext_payment_type_code = fields.Char(inverse='_set_ext_payment_type_code', string='Išorinės sistemos kodas')
    name = fields.Char(string='Mokėjimo tipas')
    internal_code = fields.Char(string='Vidinis sistemos kodas')
    journal_id = fields.Many2one('account.journal', string='Susietas žurnalas')
    alternative_name_ids = fields.One2many('nsoft.payment.alt.names', 'pay_type_id', string='Alternatyvūs pavadinimai')
    do_reconcile = fields.Boolean(string='Automatiškai dengti sąskaitas', default=True)
    state = fields.Selection([
        ('working', 'Mokėjimo tipas sukonfigūruotas'),
        ('failed', 'Trūksta konfigūracijos (Pavadinimas, žurnalas)')],
        string='Būsena', track_visibility='onchange', compute='_compute_state'
    )

    # Individual invoices are created for sales that have payments with this type
    create_individual_invoices = fields.Boolean(string='Kurti atskiras sąskaitas faktūras')
    forced_partner_id = fields.Many2one('res.partner', string='Priverstinis partneris')

    # Fields that are used for cash operations
    cash_operation_payment_type = fields.Boolean(string='Cash operations')
    account_id = fields.Many2one('account.account')

    @api.multi
    @api.constrains('ext_payment_type_code')
    def type_constraint(self):
        for rec in self.filtered('ext_payment_type_code'):
            if self.env['nsoft.payment.type'].search_count(
                    [('id', '!=', rec.id), ('ext_payment_type_code', '=', rec.ext_payment_type_code)]):
                raise exceptions.ValidationError(_('Produkto išorinis identifikatorius negali kartotis!'))

    @api.multi
    @api.depends('journal_id', 'name', 'ext_payment_type_code', 'do_reconcile')
    def _compute_state(self):
        for rec in self:
            configured = rec.ext_payment_type_code and rec.name
            # If operation is simple payment, but is reconcilable, journal must be set
            if rec.do_reconcile:
                configured = configured and rec.journal_id
            # If operation payment type is cash, both journal ir account must be set
            if rec.cash_operation_payment_type:
                configured = configured and rec.journal_id and rec.account_id
            # Check whether the state is working or not
            rec.state = 'working' if configured else 'failed'

    @api.multi
    def _set_ext_payment_type_code(self):
        for rec in self:
            mapped_data = payment_type_mapper.get(rec.ext_payment_type_code.lower())
            if mapped_data:
                rec.internal_code = mapped_data.get('int_code')
                rec.name = mapped_data.get('name')

    @api.multi
    def unlink(self):
        if self.mapped('journal_id'):
            raise exceptions.UserError(_('Negalima ištrinti mokėjimo būdo kuris turi susietą žurnalą!'))
        return super(NsoftPaymentType, self).unlink()
