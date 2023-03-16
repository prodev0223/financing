# -*- coding: utf-8 -*-

from odoo import models, fields


class RKeeperDestination(models.Model):
    """
    TODO: FILE NOT USED AT THE MOMENT
    Model used to hold rKeeper destinations
    that can either be physical partners
    or locations. Corresponds to res.partner
    or stock.warehouse in our system based
    on destination type
    """
    _name = 'r.keeper.destination'

    name = fields.Char(string='Name')
    ext_id = fields.Integer(string='External ID')
    code = fields.Char(string='Code')

    type = fields.Selection([
        ('company', 'Client company'),
        ('special', 'Special'),
        ('warehouse', 'Warehouse')],
        string='Destination type'
    )

    partner_id = fields.Many2one(string='Related partner')

