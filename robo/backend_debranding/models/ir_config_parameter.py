# -*- coding: utf-8 -*-

from odoo import models, api, tools

PARAMS = [
    'backend_debranding.new_name',
    'backend_debranding.new_title_key',
    'backend_debranding.favicon_url',
    'backend_debranding.planner_footer'
]


class IrConfigParameter(models.Model):
    _inherit = 'ir.config_parameter'

    @api.model
    @tools.ormcache()
    def get_debranding_parameters(self):
        res = {}
        for param in PARAMS:
            value = self.env['ir.config_parameter'].get_param(param)
            res[param] = value
        return res

    @api.multi
    def write(self, vals, context=None):
        res = super(IrConfigParameter, self).write(vals)
        for r in self:
            if r.key in PARAMS:
                self.get_debranding_parameters.clear_cache(self)
                break
        return res
