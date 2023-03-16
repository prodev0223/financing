# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import api, models, tools


class EDocumentLine(models.Model):
    _inherit = 'e.document.line'

    @api.multi
    def employee_data_is_accessible(self):
        """
        Method to specify if employee data should be accessible for the current user
        :return: Indication if employee data may be accessible for the user
        """
        self.ensure_one()
        user = self.env.user
        if user.is_manager() or user.is_hr_manager():
            return True
        if not self.e_document_id.template_id.is_signable_by_region_manager or not self.employee_id2.department_id \
                or not user.employee_ids or not user.is_region_manager():
            return False
        date = self.e_document_id.date_document or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        return user.employee_ids[0].is_region_manager_at_date(self.employee_id2.department_id.id,
                                                              self.e_document_id.template_id.id, date)
