# -*- coding: utf-8 -*-

from odoo import models


class SafetyNetCondition(models.Model):
    _name = 'safety.net.condition'
    _inherit = 'invoice.approval.condition'
