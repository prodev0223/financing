# -*- coding: utf-8 -*-


from odoo import fields, models


class IrActionsActWindowSettings(models.Model):
    _name = 'ir.actions.act_window.settings'

    action = fields.Many2one('ir.actions.act_window', string='Robo front settings', required=1, copy=False)
    cards_template = fields.Char(string='Neseniai atnaujintų šablonas')
    cards_template_subtype = fields.Char(string='Šablono tipas')
    cards_domain = fields.Char(string='Recenly updated domain', default="[]")
    cards_force_order = fields.Char(string='Neseniai atnaujintų įrašų rūšiavimas')
    cards_limit = fields.Integer(string='Matomų kortelių skaičius')
    search_add_custom = fields.Boolean(string='Rodyti išplėstinę paiešką', default=True)
    cards_new_action = fields.Many2one('ir.actions.act_window', string='Rodyti naujo įrašo kūrimą')
    show_duplicate = fields.Boolean(string='Rodyti dublikavimo mygtuką', default=False)
