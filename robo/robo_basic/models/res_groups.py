# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResGroups(models.Model):
    _inherit = 'res.groups'

    robo_front = fields.Boolean(string='Leisti vartotojui keisti šią teisių grupę')
    front_category_id = fields.Many2one('front.res.groups.category', string='Kategorija',
                                        help='Kategorija, kurioje grupė bus rodoma vartotojų teisių valdyme')
    robo_front_only_shown_to_super = fields.Boolean(string='Rodoma tik buhalteriui ir aukštesnių teisių vartotojam')
    front_help = fields.Char(string='Grupės aprašymas', translate=True)
    front_help_preview = fields.Html(compute='_compute_front_help_preview')

    @api.depends('front_help')
    def _compute_front_help_preview(self):
        for rec in self.filtered(lambda g: g.front_help):
            text = '''<div class="group_help_preview"><i class="fa fa-question-circle"/>
                        <span class="group_help_preview_tooltip">
                            {0}
                        </span></div>'''.format(rec.front_help)
            rec.front_help_preview = text


ResGroups()
