# -*- coding: utf-8 -*-


from odoo import fields, models


class RoboHeaderActionSwitcher(models.Model):
    _name = 'robo.header.action.switcher'

    action_id = fields.Many2one('ir.actions.act_window', string='Veiksmas', required=True)
    menu_id = fields.Many2one('ir.ui.menu', string='Menu', required=True)
    name = fields.Char(string='Pavadinimas', required=True)
    priority = fields.Selection([('action1', 'action1'), ('action2', 'action2')], required=True, string='Svarbumas',
                                lt_string='Svarbumas')
