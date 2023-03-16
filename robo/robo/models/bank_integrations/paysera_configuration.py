# -*- coding: utf-8 -*-
from odoo import models, api


class PayseraConfiguration(models.Model):
    """
    Paysera configuration extension
    """
    _inherit = 'paysera.configuration'

    @api.multi
    def _set_allow_external_signing(self):
        """
        Inverse //
        Set external signing daily limit and residual
        based on whether external signing was enabled
        :return: None
        """
        super(PayseraConfiguration, self)._set_allow_external_signing()
        company = self.sudo().env.user.company_id
        for rec in self:
            if rec.allow_external_signing and not company.require_2fa:
                company.require_2fa = True
