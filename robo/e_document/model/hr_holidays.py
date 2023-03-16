# -*- encoding: utf-8 -*-
from odoo import api, models


class HrHolidays(models.Model):
    _inherit = 'hr.holidays'

    @api.multi
    def unlink_manual_holiday_related_records(self):
        """
        Intended to be overridden
        :return: None
        """
        return
