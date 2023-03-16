# -*- coding: utf-8 -*-
from odoo import fields, models, api, _, exceptions, tools


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    image = fields.Binary(string='', attachment=True,
                          help="This field holds the logo used when printing the invoice",)
    logo_web = fields.Binary(compute='_compute_logo_web', store=True)
    mail_server_id = fields.Many2one('ir.mail_server', 'SMTP serveris', groups='robo_basic.group_robo_premium_accountant')

    @api.depends('image')
    def _compute_logo_web(self):
        for journal in self:
            if journal.image:
                journal.logo_web = tools.image_resize_image(journal.image, (180, None))
            else:
                journal.logo_web = False


AccountJournal()
