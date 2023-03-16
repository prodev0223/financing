from odoo import models, api, tools
from datetime import datetime


class EDocumentBusinessTripEmployeeLine(models.Model):
    _inherit = 'e.document.business.trip.employee.line'

    @api.onchange('employee_id', 'e_document_id.date_from', 'e_document_id.date_to')
    def _allowance_default(self):
        if self.e_document_id.date_from and self.e_document_id.date_to:
            date_from_dt = datetime.strptime(self.e_document_id.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = datetime.strptime(self.e_document_id.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            if not (date_to_dt - date_from_dt).days:
                self.allowance_percentage = 50


EDocumentBusinessTripEmployeeLine()
