# -*- coding: utf-8 -*-
from odoo import fields, models


class EDocumentTemplate(models.Model):
    _inherit = 'e.document.template'

    is_signable_by_region_manager = fields.Boolean(string='Document is signable by region manager')
