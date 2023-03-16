# -*- coding: utf-8 -*-
from odoo import models, fields, api
from .. import nsoft_tools as nt


class NsoftReportMoveCategory(models.Model):
    """
    Model that is used as a mapper to assign correct account_account type to
    specific report act object
    """
    _name = 'nsoft.report.move.category'

    @api.model
    def _default_journal_id(self):
        """
        :return: Default nSoft report journal with static code NSIVR
        """
        return self.env['account.journal'].search([('code', '=', 'NSIVR')], limit=1).id

    @api.model
    def _default_account_id(self):
        """
        :return: Default nSoft report category account -- 652
        """
        return self.env['account.account'].search([('code', '=', '652')], limit=1).id

    name = fields.Char(string='Pavadinimas')
    report_type = fields.Integer(string='Akto tipas', required=True, inverse='_set_report_type')

    journal_id = fields.Many2one('account.journal', string='Susietas žurnalas', default=_default_journal_id)
    account_id = fields.Many2one(
        'account.account', string='Buhalterinė sąskaita', default=_default_account_id)

    @api.multi
    def _set_report_type(self):
        """
        Find related account account record based on
        static report_type to account code mapping
        :return: None
        """
        for rec in self:
            # If corresponding code is found, try to search for the account
            account_code = nt.DEFAULT_SUM_REPORT_ACCOUNTS.get(rec.report_type)
            if account_code:
                # If account is found, replace the default account with it
                account = self.env['account.account'].search([('code', '=', account_code)], limit=1)
                if account:
                    rec.account_id = account


NsoftReportMoveCategory()
