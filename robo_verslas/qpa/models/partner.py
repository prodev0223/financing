# -*- coding: utf-8 -*-
from odoo import models, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _get_apr_template_dict(self):
        templates = super(ResPartner, self)._get_apr_template_dict()
        templates.update(after='qpa.apr_email_template_res_partner_after_invoice')
        return templates


ResPartner()
