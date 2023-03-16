# -*- coding: utf-8 -*-
from odoo import models
from datetime import datetime
from odoo import tools


class suvestines_email(models.Model):

    _inherit = 'hr.payslip'

    def periodas(self):
        self.ensure_one()
        for slip in self:
            data = datetime.strptime(slip.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            return str(data.year) + '-' + str(data.month)

suvestines_email()
