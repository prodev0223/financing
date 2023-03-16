# -*- coding: utf-8 -*-
from odoo import api, fields, models, exceptions, _


class AccountAssetChangeLine(models.Model):
    _name = 'account.asset.change.line'

    _order = 'date'

    asset_id = fields.Many2one('account.asset.asset', string='Ilgalaikis turtas', required=True, ondelete='cascade')
    invoice_ids = fields.Many2many('account.invoice', string='Sąskaita faktūra', compute='_compute_invoice_ids')
    invoice_line_ids = fields.Many2many('account.invoice.line', string='Sąskaitos faktūros eilutės', required=True)
    change_amount = fields.Float(string='Pagerinimo dydis')
    date = fields.Date(string='Data', required=True)
    method_number = fields.Integer(string='Nudėvėjimų skaičius')
    comment = fields.Text(string='Komentaras')

    @api.one
    @api.depends('invoice_line_ids')
    def _compute_invoice_ids(self):
        self.invoice_ids = self.invoice_line_ids.mapped('invoice_id')

    @api.constrains('date', 'asset_id')
    def constrain_date(self):
        if any(rec.date < rec.asset_id.date for rec in self):
            raise exceptions.ValidationError(_('You cannot change value on previous date than asset'))

    @api.constrains('method_number')
    def constrain_positive_methon_number(self):
        if any(rec.method_number < 0 for rec in self):
            raise exceptions.ValidationError(_('Number of depreciations must be positive'))


AccountAssetChangeLine()
