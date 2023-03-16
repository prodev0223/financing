# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import api, models, tools


class AccountFinancialReportAdditionWizard(models.TransientModel):
    _inherit = 'account.financial.report.addition.wizard'

    @api.multi
    def prepare_first_page_data(self):
        """
        Prepare data to write on the first page of report
        :return: dictionary of company info
        """
        data = super(AccountFinancialReportAdditionWizard, self).prepare_first_page_data()
        date_from = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        fiscal_date_from = self.env.user.company_id.compute_fiscalyear_dates(date=date_from)['date_from']
        employee_count_report = self.env['employee.count.report'].create({
            'date_from': fiscal_date_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT), #TODO: Or should it be calendar year, always?
        })
        data['avg_employee_nb'] = employee_count_report.employee_count
        data['shareholders'] = self.env['res.company.shareholder'].search([]).mapped('shareholder_name')
        data['material_assets'] = self.env.user.company_id.longterm_assets_min_val
        data['non_material_assets'] = self.env.user.company_id.longterm_non_material_assets_min_val

        return data


AccountFinancialReportAdditionWizard()
