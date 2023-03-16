# -*- coding: utf-8 -*-

from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    scoro_external_id = fields.Integer(string='Išorinis Scoro ID')


ResPartner()
