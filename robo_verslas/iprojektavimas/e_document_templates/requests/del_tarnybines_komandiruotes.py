# -*- coding: utf-8 -*-
from odoo import models, api, tools
from datetime import datetime


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def _get_business_trip_request_allowance_percentage(self):
        self.ensure_one()
        date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        if not (date_to_dt - date_from_dt).days:
            return 50
        else:
            return 100


EDocument()
