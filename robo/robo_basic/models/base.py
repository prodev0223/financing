# -*- coding: utf-8 -*-

from odoo import models, api, _, SUPERUSER_ID
from odoo.exceptions import AccessError


class Base(models.AbstractModel):
    _inherit = 'base'

    @api.model
    def check_global_readonly_access(self):
        user = self.env.user
        if not self._transient and user.id != SUPERUSER_ID and user.force_global_readonly_access:
            try:
                model_name = self._name
                ignored_names = ['bus.', 'robo.company.statistics', 'res.users.log']
                for ignored_name in ignored_names:
                    if model_name.startswith(ignored_name):
                        return
            except:
                pass
            raise AccessError(_('You have readonly access enabled. If you think this is a mistake - '
                                'please contact the system administrator'))

    @api.model
    def create(self, vals):
        self.check_global_readonly_access()
        return super(Base, self).create(vals)

    @api.multi
    def unlink(self):
        self.check_global_readonly_access()
        return super(Base, self).unlink()

    @api.multi
    def write(self, vals):
        self.check_global_readonly_access()
        return super(Base, self).write(vals)
