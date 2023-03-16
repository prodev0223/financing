# -*- coding: utf-8 -*-
from odoo import api, models


class HrPayroll(models.Model):
    _inherit = 'hr.payroll'

    @api.model
    def _reset_running_status(self):
        """ Reset running field to False """
        self.search(['|', ('busy', '=', True), ('partial_calculations_running', '=', True)]).write({
            'busy': False,
            'partial_calculations_running': False,
        })


HrPayroll()
