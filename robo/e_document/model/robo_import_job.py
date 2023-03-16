# -*- encoding: utf-8 -*-
from odoo import models, api, _


class RoboImportJob(models.Model):

    _inherit = 'robo.import.job'

    @api.model
    def get_action_name_mapping(self):
        res = super(RoboImportJob, self).get_action_name_mapping()
        res.update({
            'import_full_downtime_orders': _('Full downtime orders'),
            'import_pension_fund_transfers': _('Pension fund transfers'),
            'import_bonus_documents': _('Bonus orders'),
        })
        return res
