# -*- coding: utf-8 -*-
from odoo import fields, models, api, tools
from datetime import datetime

from dateutil.relativedelta import relativedelta


class EDocumentBusinessTripExtraWorkedDays(models.Model):
    _inherit = 'e.document.business.trip.extra.worked.days'

    pay_allowance = fields.Boolean(default=False)


EDocumentBusinessTripExtraWorkedDays()


class EDocumentBusinessTripWorkSchedule(models.Model):
    _inherit = 'e.document.business.trip.employee.line'

    @api.multi
    def get_not_pay_allowance_days(self):
        self.ensure_one()

        doc = self.e_document_id
        pay_allowance_days = self.extra_worked_day_ids.filtered(lambda l: l.pay_allowance).mapped('date')
        date_from_dt = datetime.strptime(doc.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_dt = datetime.strptime(doc.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        iteration_dt = date_from_dt
        not_pay_allowance_days = []

        while iteration_dt <= date_to_dt:
            iteration = iteration_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if iteration not in pay_allowance_days:
                not_pay_allowance_days.append(iteration)
            iteration_dt += relativedelta(days=1)

        return not_pay_allowance_days


EDocumentBusinessTripWorkSchedule()
