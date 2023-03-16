# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AccountAccountTemplate(models.Model):
    _inherit = 'account.account.template'

    use_rounding = fields.Boolean('Apvalinti mokėjimus', default=False)
    structured_code = fields.Char(String='Struktūruotas kodas',
                                  help='struktūruotas kodas, kuris bus naudojamas atliekant eksportą')

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not args:
            args = []
        args = args[:]
        if name:
            ids = self.search(
                ['|', ('name', operator, name), ('code', '=', name)] + args,
                limit=limit)
        else:
            ids = self.search(args, limit=limit)
        return ids.name_get()
