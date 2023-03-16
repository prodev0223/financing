# -*- encoding: utf-8 -*-
from odoo import fields, models, _, api, exceptions, tools


class RevolutApiPartner(models.Model):
    _name = 'revolut.api.partner'

    #TODO: link on accountant reconciling the statement

    name = fields.Char()
    uuid = fields.Char()
    partner_id = fields.Many2one('res.partner')


RevolutApiPartner()
