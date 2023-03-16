# -*- coding: utf-8 -*-
from odoo import fields, models, api


class AccountCommonReport(models.TransientModel):
    _inherit = 'account.common.report'

    force_lang = fields.Selection([('lt_LT', 'Lietuvių kalba'),
                                   ('en_US', 'Anglų kalba')], string='Priverstinė ataskaitos kalba')

    @api.multi
    def check_report(self):
        self.ensure_one()
        if self.force_lang:
            return super(AccountCommonReport, self.with_context(force_lang=self.force_lang, lang=self.force_lang)).check_report()
        else:
            return super(AccountCommonReport, self).check_report()


AccountCommonReport()
