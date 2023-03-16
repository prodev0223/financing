# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, api, tools


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_vaiko_prieziuros_atostogu_nutraukimo_workflow(self):
        self.ensure_one()
        holidays = self.env['hr.holidays'].search([
            ('employee_id', '=', self.employee_id2.id),
            ('holiday_status_id', '=', self.env.ref('hr_holidays.holiday_status_VP').id),
            ('state', '=', 'validate'),
            ('date_from', '<', self.date_1),
            ('date_to', '>', self.date_1)
        ])
        if holidays:
            date = datetime.strptime(self.date_1, tools.DEFAULT_SERVER_DATE_FORMAT)
            date -= relativedelta(days=1)
            holidays.stop_in_the_middle(date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))


EDocument()
