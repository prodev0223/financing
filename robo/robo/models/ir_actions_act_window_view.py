# -*- coding: utf-8 -*-


from odoo import fields, models


class IrActionsActWindowView(models.Model):
    _inherit = 'ir.actions.act_window.view'

    view_mode = fields.Selection(selection_add=[('tree_robo', 'Robo Tree'),
                                                ('tree_employees', 'Robo employees'),
                                                # ('form_robo', 'Robo Form'),
                                                ('calendar_robo', 'Robo Calendar'),
                                                ('tree_expenses_robo', 'Robo expenses'),
                                                ('tree_front_messages', 'Robo expenses'),
                                                ('grid', 'Robo grid')])
