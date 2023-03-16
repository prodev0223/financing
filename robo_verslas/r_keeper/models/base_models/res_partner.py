# -*- coding: utf-8 -*-

from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    r_keeper_pos = fields.Boolean(string='rKeeper pardavimo taškas')
