# -*- encoding: utf-8 -*-
from odoo import models, api, _


class RoboImportJob(models.Model):

    _inherit = 'robo.import.job'

    @api.model
    def get_action_name_mapping(self):
        res = super(RoboImportJob, self).get_action_name_mapping()
        res.update({
            'import_stock': _('Inventory balances'),
            'import_pickings': _('Internal pickings'),
        })
        return res
