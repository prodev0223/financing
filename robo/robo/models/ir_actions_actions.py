# -*- coding: utf-8 -*-


from odoo import fields, models


class IrActionsActions(models.Model):
    _inherit = 'ir.actions.actions'

    robo_help = fields.Html(string='Robo veiksmo aprašymas', help='Robo veiksmo aprašymas', translate=True)
