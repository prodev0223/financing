# -*- coding: utf-8 -*-

from odoo import models, api


class ResUsers(models.Model):

    _inherit = 'res.users'

    @api.multi
    def is_gemma_manager(self):
        self.ensure_one()
        if self.has_group('gemma.group_gemma_manager'):
            return True
        else:
            return False


ResUsers()
