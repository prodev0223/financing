# -*- coding: utf-8 -*-


from odoo import fields, models


class AccountMoveLineSanityCheck(models.Model):
    _description = 'Apskaitos testai'
    _name = 'account.move.line.sanity.check'

    line_id = fields.Many2one('account.move.line')
    name = fields.Char(string='Pavadinimas')
    date = fields.Date(string='Data')
