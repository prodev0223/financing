# -*- coding: utf-8 -*-
from __future__ import division
from odoo import api, fields, models, tools

from datetime import datetime

class EDocumentLine(models.Model):
    _name = 'e.document.line'

    e_document_id = fields.Many2one('e.document', required=True)
    employee_id2 = fields.Many2one('hr.employee', string='Darbuotojo Vardas')
    float_1 = fields.Float()
    int_1 = fields.Integer(default=100)
    possible_to_forecast_salary = fields.Boolean(compute='_compute_possible_to_forecast_salary')
    current_salary_forecast = fields.Float(string='Prognozuojamas atlyginimas (NETO)',
                                           help='Šią sumą darbuotojas turėtų gauti į rankas su pasirinkto mėnesio '
                                                'atlyginimu',
                                           compute='_compute_current_salary_forecast', store=True)
    salary_with_bonus_forecast = fields.Float(string='Prognozuojamas atlyginimas skyrus priedą (NETO)',
                                              help='Šią sumą darbuotojas turėtų gauti į rankas su pasirinkto mėnesio '
                                                   'atlyginimu priskaičiavus dokumente nurodytą priedo sumą',
                                              compute='_compute_salary_with_bonus_forecast')
    related_document_id = fields.Many2one('e.document', required=False, readonly=True,
                                          string='Separate document the line relates to (not the main document)')
    employee_agrees_with_document = fields.Html(compute='_compute_employee_agrees_with_document')
    selection_1 = fields.Selection([('yes', 'Taip'), ('no', 'Ne')])
    char_1 = fields.Char()
    int_2 = fields.Integer(default=datetime.utcnow().year)
    int_3 = fields.Integer(default=datetime.utcnow().month)
    pension_fund_id = fields.Many2one('res.pension.fund', compute='_compute_pension_fund_id', store=True)

    @api.multi
    @api.depends('employee_id2.pension_fund_id')
    def _compute_pension_fund_id(self):
        for rec in self:
            rec.pension_fund_id = rec.employee_id2.sudo().pension_fund_id

    @api.multi
    @api.depends('e_document_id.template_id', 'related_document_id', 'related_document_id.state')
    def _compute_employee_agrees_with_document(self):
        self.employee_agrees_with_document = ''

    @api.multi
    @api.depends('employee_id2', 'e_document_id.date_3', 'e_document_id.bonus_input_type',
                 'e_document_id.bonus_type_selection', 'e_document_id.template_id')
    def _compute_possible_to_forecast_salary(self):
        for rec in self:
            if not rec._possible_to_get_salary_info():
                rec.possible_to_forecast_salary = False
            else:
                # Payslip can only exist when ziniarastis is confirmed.
                rec.possible_to_forecast_salary = self.env['hr.payslip'].sudo().search_count([
                    ('employee_id', '=', rec.employee_id2.id),
                    ('date_from', '<=', rec.e_document_id.date_3),
                    ('date_to', '>=', rec.e_document_id.date_3),
                    ('state', 'in', ['draft', 'done'])
                ])

    @api.multi
    @api.depends('employee_id2', 'e_document_id.date_3', 'e_document_id.bonus_input_type',
                 'e_document_id.bonus_type_selection', 'e_document_id.template_id')
    def _compute_current_salary_forecast(self):
        for rec in self:
            if not rec.possible_to_forecast_salary:
                rec.current_salary_forecast = 0.0
            else:
                payslip = self.env['hr.payslip'].sudo().search([
                    ('employee_id', '=', rec.employee_id2.id),
                    ('date_from', '<=', rec.e_document_id.date_3),
                    ('date_to', '>=', rec.e_document_id.date_3),
                    ('state', 'in', ['draft', 'done'])
                ], limit=1)
                if not payslip:
                    rec.current_salary_forecast = 0.0
                else:
                    rec.current_salary_forecast = payslip.moketinas  # BENDM

    @api.multi
    @api.depends('employee_id2', 'e_document_id.date_3', 'e_document_id.bonus_input_type',
                 'e_document_id.bonus_type_selection', 'e_document_id.template_id', 'float_1')
    def _compute_salary_with_bonus_forecast(self):
        for rec in self:
            if rec.possible_to_forecast_salary and tools.float_compare(rec.float_1, 0.0, precision_digits=2) > 0:
                rec.salary_with_bonus_forecast = rec.current_salary_forecast + rec.float_1
            else:
                rec.salary_with_bonus_forecast = rec.current_salary_forecast

    @api.onchange('int_1', 'employee_id2')
    def set_dienpinigiu_norma(self):
        country_allowance_lt = self.env.ref('l10n_lt_payroll.country_allowance_lt', raise_if_not_found=False)
        is_country_lt = country_allowance_lt and self.e_document_id.country_allowance_id.id == country_allowance_lt.id
        is_manager = self.employee_id2.id == self.env.user.company_id.vadovas.id
        self.e_document_id._num_calendar_days()
        if self.int_1 < 50:
            if self.e_document_id.num_calendar_days == 1 and is_country_lt:
                self.int_1 = 0
            else:
                self.int_1 = 50
        elif 200 >= self.int_1 > 100:
            if not is_manager:
                self.int_1 = 100
        elif self.int_1 > 200:
            if not is_manager:
                self.int_1 = 100
            else:
                self.int_1 = 200
        norma = self.int_1 / 100.0  # P3:DivOK

        if (self.e_document_id.num_calendar_days != 1 or not is_country_lt) and \
                tools.float_compare(norma, 0.5, precision_digits=2) == -1:
            norma = 1.0
            self.int_1 = 100
        amount = self.e_document_id.country_allowance_id.get_amount(self.e_document_id.date_from,
                                                                    self.e_document_id.date_to)
        self.float_1 = tools.float_round(amount * norma, precision_digits=2)

    @api.onchange('float_1')
    def allowance_limiter(self):
        business_trip_template = self.env.ref('e_document.isakymas_del_komandiruotes_grupei_template')
        trigger_allowance_limiter = self._context.get('norm', False)  # prevent endless onchange triggering
        if self.e_document_id.template_id.id == business_trip_template.id and trigger_allowance_limiter:
            country_allowance = self.e_document_id.country_allowance_id
            country_allowance_amount = country_allowance.get_amount(self.e_document_id.date_from,
                                                                    self.e_document_id.date_to)
            country_allowance_lt = self.env.ref('l10n_lt_payroll.country_allowance_lt', raise_if_not_found=False).id
            is_country_lt = country_allowance.id == country_allowance_lt
            mid_norm = tools.float_round(country_allowance_amount * 1, precision_digits=2)
            min_norm = tools.float_round(country_allowance_amount * 0.5, precision_digits=2)
            max_norm = tools.float_round(country_allowance_amount * 2, precision_digits=2)

            is_ceo = self.employee_id2.id == self.env.user.company_id.vadovas.id
            max_possible = 200 if is_ceo else 100
            self.e_document_id._num_calendar_days()
            if self.e_document_id.num_calendar_days == 1 and is_country_lt:
                min_possible = 0
            else:
                min_possible = 50
            try:
                per_percent = mid_norm // 100  # P3:DivOK
                percentage = self.float_1 // per_percent  # P3:DivOK

                if self.float_1 >= max_norm and is_ceo:
                    self.int_1 = max_possible
                    self.set_dienpinigiu_norma()
                elif self.float_1 > mid_norm and not is_ceo:
                    self.int_1 = max_possible
                    self.set_dienpinigiu_norma()
                elif self.float_1 <= min_norm:
                    self.int_1 = min_possible
                    self.set_dienpinigiu_norma()
                else:
                    self.int_1 = int(percentage)
                    self.set_dienpinigiu_norma()

            except ZeroDivisionError:
                self.int_1 = 0
                self.float_1 = 0
                self.set_dienpinigiu_norma()

    @api.multi
    def _possible_to_get_salary_info(self):
        self.ensure_one()
        has_access_rights = self.employee_data_is_accessible()
        document = self.e_document_id
        is_neto_bonus = document.bonus_input_type and document.bonus_input_type == 'neto'
        is_monthly_bonus = document.bonus_type_selection and document.bonus_type_selection == '1men'
        date_for_is_set = bool(document.date_3)
        bonus_doc = self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template')
        employee_is_set = True if self.employee_id2 and document.template_id.id == bonus_doc.id else False
        correct_template = self.e_document_id.template_id.id == bonus_doc.id
        return has_access_rights and (employee_is_set and date_for_is_set and is_monthly_bonus and is_neto_bonus and
                                      correct_template)

    @api.multi
    def employee_data_is_accessible(self):
        """
        Method is meant to be overridden
        :return: Indication if employee data may be accessible for the user
        """
        self.ensure_one()
        return self.env.user.is_manager() or self.env.user.is_hr_manager()


EDocumentLine()
