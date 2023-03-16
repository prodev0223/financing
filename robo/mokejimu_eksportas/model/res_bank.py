# -*- coding: utf-8 -*-
from odoo import models, fields


class ResBank(models.Model):
    _inherit = 'res.bank'

    sepa_export_rules_code = fields.Char(
        string='SEPA export rules code',
        groups="base.group_system",
        lt_string='SEPA eksportavimo taisyklių kodas'
    )
