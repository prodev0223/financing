# -*- coding: utf-8 -*-
from odoo import models, _, api


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.one
    def _prepare_analytic_line(self):
        """ Prepare the values used to create() an account.analytic.line upon validation of an account.move.line having
            an analytic account. This method is intended to be extended in other modules.
        """

        res = super(AccountMoveLine, self)._prepare_analytic_line()
        if type(res) == list:
            res = res[0]

        # Get date to use - if operation date exists, give the priority to it
        date_to_use = self.invoice_id.operacijos_data or self.date
        # If date_to_use is in locked analytic period, re-force the date to second priority option
        if self.env['analytic.lock.dates.wizard'].check_locked_analytic(date_to_use, mode='return'):
            date_to_use = self.date

        res['date'] = date_to_use
        return res

    @api.multi
    def unlink(self):
        self.mapped('analytic_line_ids').with_context(skip_locked_analytic_assertion=True).unlink()
        return super(AccountMoveLine, self).unlink()


AccountMoveLine()


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.multi
    def unlink(self):
        self.mapped('line_ids.analytic_line_ids').with_context(skip_locked_analytic_assertion=True).unlink()
        return super(AccountMove, self).unlink()


AccountMove()
