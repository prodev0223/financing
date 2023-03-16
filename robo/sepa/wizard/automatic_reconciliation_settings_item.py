# -*- encoding: utf-8 -*-
from odoo import fields, models


class AutomaticReconciliationSettingsItem(models.TransientModel):
    _name = 'automatic.reconciliation.settings.item'

    partner_id = fields.Many2one('res.partner', string='Partneris')
    inc_account_id = fields.Many2one('account.account', string='Traukiama sąskaita')
    exc_account_id = fields.Many2one('account.account', string='Praleidžiama sąskaita')
    settings_id = fields.Many2one('automatic.reconciliation.settings')
    journal_id = fields.Many2one('account.journal', string='Banko sąskaitos')
