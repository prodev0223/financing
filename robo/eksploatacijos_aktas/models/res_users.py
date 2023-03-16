# -*- coding: utf-8 -*-
from odoo import models, api


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def get_accountant_mail_channel_ids(self):
        accountant_mail_channel_ids = [
            'eksploatacijos_aktas.eksploatacijos_aktas_channel',
        ]

        channel_ids = super(ResUsers, self).get_accountant_mail_channel_ids() or []
        channel_ids.extend(
            channel.id for channel in map(lambda x: self.env.ref(x, False), accountant_mail_channel_ids) if channel
        )
        return channel_ids
