# -*- coding: utf-8 -*-
from odoo import fields, models, api, _, exceptions, tools


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    bank_journal_ids = fields.Many2many('account.journal', string='Banko sąskaitos', domain=[('type', '=', 'bank')],
                                        relation='account_journal_bank_journal_rel', column1='journal_id', column2='bank_id')
    mail_server_id = fields.Many2one('ir.mail_server', 'SMTP serveris',
                                     groups='robo_basic.group_robo_premium_accountant')


AccountJournal()

