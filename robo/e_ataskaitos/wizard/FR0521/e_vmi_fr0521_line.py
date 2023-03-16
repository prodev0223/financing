# -*- coding: utf-8 -*-
from odoo import models, fields


class FR0521Line(models.TransientModel):
    """
    Wizard that represents FR0521 fuel line
    """
    _name = 'e.vmi.fr0521.line'

    name = fields.Char(string='Pavadinimas', readonly=True)
    type = fields.Char(string='Degalų rūšis', readonly=True)
    quantity = fields.Float(string='Kiekis')

    # Relational fields
    wizard_id = fields.Many2one('e.vmi.fr0521', string='Vedlys')


FR0521Line()
