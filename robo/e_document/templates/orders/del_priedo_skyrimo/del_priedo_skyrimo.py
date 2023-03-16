# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, tools


class EDocument(models.Model):
    _inherit = 'e.document'

    possible_to_forecast_salary = fields.Boolean(compute='_compute_possible_to_forecast_salary')
    current_salary_forecast = fields.Float(string='Prognozuojamas atlyginimas (NETO)',
                                             help='Šią sumą darbuotojas turėtų gauti į rankas su pasirinkto mėnesio '
                                                  'atlyginimu',
                                             compute='_compute_current_salary_forecast', store=True)
    salary_with_bonus_forecast = fields.Float(string='Prognozuojamas atlyginimas skyrus priedą (NETO)',
                                                help='Šią sumą darbuotojas turėtų gauti į rankas su pasirinkto mėnesio '
                                                     'atlyginimu priskaičiavus dokumente nurodytą priedo sumą',
                                                compute='_compute_salary_with_bonus_forecast')

    @api.multi
    def _possible_to_get_salary_info(self):
        self.ensure_one()
        has_access_rights = self.employee_data_is_accessible()
        is_neto_bonus = self.bonus_input_type and self.bonus_input_type == 'neto'
        is_monthly_bonus = self.bonus_type_selection and self.bonus_type_selection == '1men'
        date_for_is_set = bool(self.date_3)
        bonus_doc = self.env.ref('e_document.isakymas_del_priedo_skyrimo_template')
        employee_is_set = True if self.template_id.id == bonus_doc.id and self.employee_id2 else False
        correct_template = self.template_id.id == bonus_doc.id
        return has_access_rights and (employee_is_set and date_for_is_set and is_monthly_bonus and is_neto_bonus and
                                      correct_template)

    @api.multi
    @api.depends('employee_id2', 'bonus_type_selection', 'date_3', 'bonus_input_type')
    def _compute_possible_to_forecast_salary(self):
        for rec in self:
            if not rec._possible_to_get_salary_info():
                rec.possible_to_forecast_salary = False
            else:
                # Payslip can only exist when ziniarastis is confirmed.
                rec.possible_to_forecast_salary = self.env['hr.payslip'].search_count([
                    ('employee_id', '=', rec.employee_id2.id),
                    ('date_from', '<=', rec.date_3),
                    ('date_to', '>=', rec.date_3),
                    ('state', 'in', ['draft', 'done'])
                ])

    @api.multi
    @api.depends('employee_id2', 'bonus_type_selection', 'date_3', 'float_1', 'bonus_input_type')
    def _compute_current_salary_forecast(self):
        for rec in self:
            if not rec.possible_to_forecast_salary:
                rec.current_salary_forecast = 0.0
            else:
                payslip = self.env['hr.payslip'].search([
                    ('employee_id', '=', rec.employee_id2.id),
                    ('date_from', '<=', rec.date_3),
                    ('date_to', '>=', rec.date_3),
                    ('state', 'in', ['draft', 'done'])
                ], limit=1)
                if not payslip:
                    rec.current_salary_forecast = 0.0
                else:
                    rec.current_salary_forecast = payslip.moketinas  # BENDM

    @api.multi
    @api.depends('employee_id2', 'bonus_type_selection', 'date_3', 'float_1', 'bonus_input_type')
    def _compute_salary_with_bonus_forecast(self):
        for rec in self:
            if rec.possible_to_forecast_salary and tools.float_compare(rec.float_1, 0.0, precision_digits=2) > 0:
                rec.salary_with_bonus_forecast = rec.current_salary_forecast + rec.float_1
            else:
                rec.salary_with_bonus_forecast = rec.current_salary_forecast

    @api.multi
    def isakymas_del_priedo_skyrimo_workflow(self):
        self.ensure_one()
        date_from_dt = datetime.strptime(self.date_3, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_from = (date_from_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = (date_from_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        bonus_rec = self.env['hr.employee.bonus'].create({
            'employee_id': self.employee_id2.id,
            'for_date_from': self.date_1,
            'for_date_to': self.date_2,
            'payment_date_from': date_from,
            'payment_date_to': date_to,
            'bonus_type': self.bonus_type_selection,
            'amount': self.float_1,
            'amount_type': self.bonus_input_type,
        })
        bonus_rec.confirm()
        self.write({
            'record_model': 'hr.employee.bonus',
            'record_id': bonus_rec.id,
        })
        bonus_rec.write({'related_document': self.id})


EDocument()
