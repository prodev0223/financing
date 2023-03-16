# -*- coding: utf-8 -*-


from odoo import fields, models


class RoboHeaderItems(models.Model):
    _name = 'robo.header.items'

    header = fields.Many2one('robo.header', string='Antraštė')
    name = fields.Char(string='Pavadinimas', translate=True)
    icon = fields.Char(string='Ikona')
    action = fields.Many2one('ir.actions.act_window', string='Veiksmas')
    item_class = fields.Char(string='CSS klasė')
    help = fields.Char(string='Pagalbos aprašymas', translate=True)
    group_ids = fields.Many2many('res.groups')
