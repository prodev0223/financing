# -*- encoding: utf-8 -*-
from datetime import datetime
from odoo import models, api, tools


class AccountTax(models.Model):
    _inherit = 'account.tax'

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        date = self._context.get('date', datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
        if not self.env.user.sudo().company_id.allow_use_ne_pvm_objektas and \
                self._context.get('skip_non_vat') and not self.env.user.is_accountant() and \
                self.env.user.sudo().company_id.with_context(date=date).vat_payer:
            args += [('non_vat_object', '=', False)]
        return super(AccountTax, self).search(args, offset=0, limit=limit, order=order, count=count)
