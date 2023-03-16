# -*- coding: utf-8 -*-

from odoo import api, models, _, fields


class MailChannel(models.Model):
    _inherit = 'mail.channel'

    group_public_ids = fields.Many2many('res.groups', 'mail_channel_res_groups_access_rel', 'mail_channel_id', 'gid',
                                        string='Groups authorized to access mail channels', )
    category = fields.Selection([
        ('e_documents', 'E Documents'),
        ('invoices', 'Invoices'),
        ('hr', 'HR'),
    ], string=_('Kategorija'))
    robo_front = fields.Boolean(name='Rodyti vartotojui', default=False)
