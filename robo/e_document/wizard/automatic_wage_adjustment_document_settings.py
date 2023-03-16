# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AutomaticWageAdjustmentDocumentSettings(models.TransientModel):
    _name = 'automatic.wage.adjustment.document.settings'

    minimum_wage_adjustment_document_creation_deadline_days = fields.Integer(
        string='Number of days before minimum wage changes to create the salary change documents',
        groups='robo_basic.group_robo_premium_accountant',
    )
    keep_salary_differences_when_changing_minimum_wage = fields.Boolean(
        string='Keep the difference between the current minimum wage and the current salary when changing the minimum '
               'wage for employees who earn less than the next new minimum wage',
        groups='robo_basic.group_robo_premium_accountant',
    )
    mma_adjustment_when_creating_salary_change_documents = fields.Float(
        string='Amount to adjust the minimum monthly wage by when creating minimum wage adjustment documents',
        groups='robo_basic.group_robo_premium_accountant',
    )
    mmh_adjustment_when_creating_salary_change_documents = fields.Float(
        string='Amount to adjust the minimum hourly wage by when creating minimum wage adjustment documents',
        groups='robo_basic.group_robo_premium_accountant',
    )

    @api.model
    def default_get(self, field_list):
        res = super(AutomaticWageAdjustmentDocumentSettings, self).default_get(field_list)
        company = self.env.user.company_id
        company_fields_list = (
            'minimum_wage_adjustment_document_creation_deadline_days',
            'keep_salary_differences_when_changing_minimum_wage',
            'mma_adjustment_when_creating_salary_change_documents',
            'mmh_adjustment_when_creating_salary_change_documents',
        )
        fields_to_get_from_company = [field for field in company_fields_list if field in field_list]
        company_fields = company.read(fields_to_get_from_company)[0]
        res.update(company_fields)
        return res

    @api.multi
    def save(self):
        self.ensure_one()
        if self.env.user.is_accountant():
            self.env.user.company_id.write({
                'minimum_wage_adjustment_document_creation_deadline_days':
                    self.minimum_wage_adjustment_document_creation_deadline_days,
                'keep_salary_differences_when_changing_minimum_wage':
                    self.keep_salary_differences_when_changing_minimum_wage,
                'mma_adjustment_when_creating_salary_change_documents':
                    self.mma_adjustment_when_creating_salary_change_documents,
                'mmh_adjustment_when_creating_salary_change_documents':
                    self.mmh_adjustment_when_creating_salary_change_documents,
            })