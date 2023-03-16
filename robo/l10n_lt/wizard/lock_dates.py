# -*- coding: utf-8 -*-


from odoo import models, fields, _, api, exceptions, tools
from datetime import datetime
from dateutil.relativedelta import relativedelta


class LockDates(models.TransientModel):
    _name = 'lock.dates'

    def _default_fiscalyear_lock_date(self):
        return self.env.user.company_id.sudo().fiscalyear_lock_date

    def _default_period_lock_date(self):
        return self.env.user.company_id.sudo().period_lock_date

    def _default_accountant_lock_date(self):
        return self.env.user.company_id.sudo().accountant_lock_date

    def _is_chief_accountant(self):
        return self.env.user.has_group('robo_basic.group_robo_premium_chief_accountant')



    fiscalyear_lock_date = fields.Date(string='Lock Date', help=_(
        'No users, including Advisers, can edit accounts prior to and inclusive of this date. Use it for fiscal year locking for example.'),
                                       default=_default_fiscalyear_lock_date)
    period_lock_date = fields.Date(string='Lock Date for Non-Advisers',
                                   help=_(
                                       "Only users with the 'Adviser' role can edit accounts prior to and inclusive of this date. Use it for period locking inside an open fiscal year, for example."),
                                   default=_default_period_lock_date)
    accountant_lock_date = fields.Date(string='Lock Date for Accountants', help="Only chief accountants will be able to edit accounts prior to and inclusive of this date.", default=_default_accountant_lock_date)
    is_chief_accountant = fields.Boolean(string='Vyr. buhalteris', compute='_get_is_user_chief_accountant', default=_is_chief_accountant)

    @api.multi
    def _get_is_user_chief_accountant(self):
        if self.env.user.has_group('robo_basic.group_robo_premium_chief_accountant'):
            self.is_chief_accountant = True
        else:
            self.is_chief_accountant = False

    @api.multi
    def set_dates(self):
        self.ensure_one()
        company_id = self.env.user.company_id
        company_id.sudo().period_lock_date = self.period_lock_date

        fy_lock_date_dt = datetime.strptime(company_id.sudo().fiscalyear_lock_date, tools.DEFAULT_SERVER_DATE_FORMAT) \
            if company_id.sudo().fiscalyear_lock_date else False

        fyw_lock_date_dt = datetime.strptime(self.fiscalyear_lock_date, tools.DEFAULT_SERVER_DATE_FORMAT) \
            if self.fiscalyear_lock_date else False
        acw_lock_date_dt = datetime.strptime(self.accountant_lock_date, tools.DEFAULT_SERVER_DATE_FORMAT) \
            if self.accountant_lock_date else False

        if not self.env.user.has_group('robo_basic.group_robo_premium_chief_accountant'):
            if not fyw_lock_date_dt or not acw_lock_date_dt:
                raise exceptions.UserError(_('Tik vyr. buhalteris(-ė) gali atrankinti periodą!'))
            if fy_lock_date_dt and (fyw_lock_date_dt < fy_lock_date_dt or
                                    acw_lock_date_dt < fy_lock_date_dt):
                    raise exceptions.UserError(_('Tik vyr. buhalteris(-ė) gali atrankinti periodą!'))
        company_id.sudo().write({
            'fiscalyear_lock_date': self.fiscalyear_lock_date,
            'accountant_lock_date': self.accountant_lock_date,
            'period_lock_date': self.period_lock_date,
        })




