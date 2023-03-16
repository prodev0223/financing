# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields, tools, api, _, exceptions


class ResCurrency(models.Model):
    _inherit = 'res.currency'

    @api.multi
    def _compute_current_rate(self):
        if not self._context.get('force_exact_currency_rate'):
            return super(ResCurrency, self)._compute_current_rate()
        date = self._context.get('date') or fields.Datetime.now()
        if isinstance(date, datetime):
            date = date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_from = (datetime.strptime(date[:10], tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(days=1)).strftime(
            tools.DEFAULT_SERVER_DATE_FORMAT)
        date = date[:10] + ' 23:59:59'
        date_from = date_from[:10] + ' 00:00:00'
        company_id = self._context.get('company_id') or self.env['res.users']._get_company().id
        company_currency = self.env['res.company'].browse(company_id).currency_id.id
        # the subquery selects the last rate before 'date' for the given currency/company
        query = """SELECT c.id, (SELECT r.rate FROM res_currency_rate r
                                      WHERE r.currency_id = c.id AND r.name <= %s AND name > %s
                                        AND (r.company_id IS NULL OR r.company_id = %s)
                                   ORDER BY r.company_id, r.name DESC
                                      LIMIT 1) AS rate
                       FROM res_currency c
                       WHERE c.id IN %s"""
        self._cr.execute(query, (date, date_from, company_id, tuple(self.ids)))
        currency_rates = dict(self._cr.fetchall())
        for currency in self:
            if currency.id != company_currency and not currency_rates.get(currency.id):
                raise exceptions.UserError(_('Valiutos %s %s kursas nerastas') % (currency.name, date[:10]))
            currency.rate = currency_rates.get(currency.id) or 1.0

    @api.multi
    def toggle_active(self):
        if not self.env.user._is_admin():
            raise exceptions.UserError(_('Tik administratorius gali aktyvuoti/deaktyvuoti valiutą'))
        return super(ResCurrency, self).toggle_active()

    @api.multi
    def apply_currency_rounding(self, value):
        """
        Dummy method that is overridden in other
        modules that have potentiality to
        have very small values
        """
        self.ensure_one()
        return True
