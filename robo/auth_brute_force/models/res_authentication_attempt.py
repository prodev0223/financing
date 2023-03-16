# -*- encoding: utf-8 -*-
from odoo import models, fields, api
from odoo.tools.translate import _


class ResAuthenticationAttempt(models.Model):
    _name = 'res.authentication.attempt'
    _order = 'attempt_date desc'

    _ATTEMPT_RESULT = [
        ('successfull', 'Successful'),
        ('failed', 'Failed'),
        ('banned', 'Banned'),
    ]

    # Column Section
    attempt_date = fields.Datetime(string='Attempt Date')

    login = fields.Char(string='Tried Login')

    remote = fields.Char(string='Remote ID')

    result = fields.Selection(
        selection=_ATTEMPT_RESULT, string='Authentication Result')

    # Custom Section
    @api.model
    def search_last_failed(self, remote):
        last_ok = self.search(
            [('result', '=', 'successfull'), ('remote', '=', remote)],
            order='attempt_date desc', limit=1)
        if last_ok:
            return self.search([
                ('remote', '=', remote),
                ('attempt_date', '>', last_ok.attempt_date)])
        else:
            return self.search([('remote', '=', remote)])
