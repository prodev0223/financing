# -*- coding: utf-8 -*-

from odoo import models, api


class PensionFundTransfer(models.Model):
    _inherit = 'pension.fund.transfer'

    @api.model
    def _get_a_class_code(self):
        return self.env.ref('l10n_lt_payroll.a_klase_kodas_47').id