# -*- coding: utf-8 -*-
from odoo import models, fields, _, api, exceptions, tools
from datetime import datetime


class AnalyticLockDatesWizard(models.TransientModel):
    """
    Wizard -- Enables user to lock analytics in two modes:
    Freeze - Analytic changes in objects (invoice_line/move_line) are allowed, but analytic lines are not created.
    Block - Analytic changes in objects are denied.
    """

    _name = 'analytic.lock.dates.wizard'

    def _default_manager_lock_date(self):
        return self.env.user.company_id.sudo().manager_lock_date_analytic

    def _default_user_lock_date(self):
        return self.env.user.company_id.sudo().user_lock_date_analytic

    def _default_analytic_lock_type(self):
        return self.env.user.company_id.sudo().analytic_lock_type

    analytic_lock_type = fields.Selection(
        [('freeze', 'Užšaldyti analitiką'),
         ('block', 'Blokuoti analitiką')],
        string='Analitikos užrakinimo tipas',
        default=_default_analytic_lock_type
    )

    manager_lock_date_analytic = fields.Date(
        string='Analitikos užrakinimo data vadovams',
        default=_default_manager_lock_date
    )

    user_lock_date_analytic = fields.Date(
        string='Analitikos užrakinimo data naudotojams',
        default=_default_user_lock_date
    )

    @api.model
    def get_lock_type(self):
        """
        :return: current analytic lock type
        """
        return self.sudo().env.user.company_id.analytic_lock_type

    @api.multi
    def set_dates(self):
        """
        Write changes from the wizard to the company settings
        :return: None
        """
        self.ensure_one()
        company_id = self.env.user.company_id
        company_id.sudo().manager_lock_date_analytic = self.manager_lock_date_analytic
        company_id.sudo().user_lock_date_analytic = self.user_lock_date_analytic
        company_id.sudo().analytic_lock_type = self.analytic_lock_type

    @api.multi
    def check_locked_analytic(self, analytic_date, mode='raise'):
        """
        :param analytic_date: date to check analytic lock date against
        :param mode: mode parameter that either raises the error or returns boolean value
        :return: None/Bool
        """
        if self._context.get('skip_locked_analytic_assertion', False):
            return False
        manager_lock_date = self.sudo().env.user.company_id.manager_lock_date_analytic
        user_lock_date = max(manager_lock_date, self.sudo().env.user.company_id.user_lock_date_analytic)
        date_to_check = manager_lock_date if self.env.user.is_premium_manager() else user_lock_date
        if date_to_check:
            check_date_dt = datetime.strptime(date_to_check, tools.DEFAULT_SERVER_DATE_FORMAT)
            analytic_date_dt = datetime.strptime(analytic_date, tools.DEFAULT_SERVER_DATE_FORMAT) \
                if analytic_date else False
            if analytic_date_dt and analytic_date_dt <= check_date_dt:
                if mode in ['raise']:
                    raise exceptions.ValidationError(_('Negalite koreguoti analitikos ankstesniems '
                                                       'įrašams nei analitikos užrakinimo data %s') % date_to_check)
                else:
                    return True
        return False


AnalyticLockDatesWizard()
