# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountJournal(models.Model):
    _name = 'account.journal'
    _inherit = ['account.journal', 'mail.thread']

    user_control_ids = fields.Many2many('res.users', 'res_users_account_journal_rel', string='Leidžiami vartotojai',
                                        groups='robo_basic.group_robo_premium_manager')
    exclude_from_invoices = fields.Boolean(string='Nerodyti sąskaitose faktūrose')
    active = fields.Boolean(track_visibility='onchange')
    import_file_type = fields.Selection(track_visibility='onchange')
    exclude_from_robo_invoicing = fields.Boolean()  # Used by internal for invoicing.
