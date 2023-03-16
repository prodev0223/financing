# -*- coding: utf-8 -*-
from odoo import api, models


class ReportRoboReportEmployeeContract(models.AbstractModel):
    _inherit = 'report.robo.report_employee_contract'

    @api.multi
    def should_sudo(self, employee):
        return self.env.user.is_region_manager_at_date(employee.department_id.id)
