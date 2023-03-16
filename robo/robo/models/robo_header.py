# -*- coding: utf-8 -*-


from odoo import _, fields, models


class RoboHeader(models.Model):
    _name = 'robo.header'

    header_items_ids = fields.One2many('robo.header.items', 'header')
    button_name = fields.Char(default=_('Sukurti naują...'), translate=True)
    button_class = fields.Char(string='CSS klasė', default='')
    fit = fields.Boolean(string='Siauresnės paraštės', default=False)
    robo_xs_header = fields.Boolean(string='Sumažinta antraštė', default=False)
    robo_help_header = fields.Boolean(string='Pagalba antraštė', default=False)
    switch_views_buttons = fields.Boolean(string='Peržiūros keitimo mygtukai', default=False)

    # ROBO: kaip klientai/tiekejai atveju
    action_switcher_ids = fields.Many2many('robo.header.action.switcher', string='Header action switcher')
    active_action_switcher = fields.Selection([('action1', 'action1'), ('action2', 'action2')])
    group_ids = fields.Many2many('res.groups')
