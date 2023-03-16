# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, fields, api, tools
from odoo.tools.translate import _
from datetime import datetime, timedelta


class Years(models.Model):

    _name = 'years'

    _sql_constraints = [('code_unique', 'unique(code)',
                         _('Jau yra metai su šiuo kodu'))]

    @api.model_cr
    def init(self):
        if self.env['years'].search_count([]) == 0:
            for i in range(2000, 2116):
                year = {
                    'name': str(i),
                    'code': i,
                }
                self.env['years'].create(year)

    name = fields.Char(string='Year', required=True, readonly=True)
    code = fields.Integer(string='Year Number', required=True, readonly=True)


Years()


class EmployeeVdu(models.Model):

    _name = 'employee.vdu'

    _sql_constraints = [('employee_year_month_unique', 'unique(contract_id, year_id, month)',
                         _('Negali būti dviejų vdu įrašų tam pačiam darbuotojui ir tam pačiam mėnesiui'))]

    _order = 'date_from desc, employee_id'

    def default_year(self):
        year = datetime.utcnow().year
        year_id = self.env['years'].search([('code', '=', year)], limit=1)
        return year_id

    def default_month(self):
        return datetime.utcnow().month

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    contract_id = fields.Many2one('hr.contract', string='Contract')
    time_worked = fields.Integer(string='Dirbtų dienų / valandų skaičius', compute='_compute_time_worked')
    days_worked = fields.Float(string='Dirbtų dienų skaičius')
    hours_worked = fields.Float(string='Dirbtų valandų skaičius')
    amount = fields.Float(string='Priskaitytas DU')
    type = fields.Selection([('men', 'Mėnesinis'), ('val', 'Valandinis')], string='Tipas', required=True,
                            default='men')
    year_id = fields.Many2one('years', string='Metai', required=True, default=default_year)
    month = fields.Selection([(1, '01'), (2, '02'), (3, '03'), (4, '04'), (5, '05'), (6, '06'),
                              (7, '07'), (8, '08'), (9, '09'), (10, '10'), (11, '11'), (12, '12')], required=True,
                             default=default_month)
    date_from = fields.Date(string='Data nuo', compute='_date_from', store=True)
    vdu = fields.Float(string='VDU', group_operator='time_worked')
    vdu_d = fields.Float(string='VDU d.', compute='_get_vdu_extra')
    vdu_h = fields.Float(string='VDU val.', compute='_get_vdu_extra')

    @api.one
    @api.depends('days_worked', 'hours_worked', 'type')
    def _compute_time_worked(self):
        self.time_worked = self.days_worked if self.type == 'men' else self.hours_worked

    @api.one
    @api.depends('employee_id', 'amount', 'days_worked', 'hours_worked')
    def _get_vdu_extra(self):
        self.vdu_d = self.amount / self.days_worked if self.days_worked > 0 else 0.0  # P3:DivOK
        self.vdu_h = self.amount / self.hours_worked if self.hours_worked > 0 else 0.0  # P3:DivOK

    @api.one
    @api.depends('year_id', 'month')
    def _date_from(self):
        if self.year_id and self.month:
            self.date_from = datetime(self.year_id.code, self.month, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.model
    def fix_all_vdus(self):
        vdu_recs = self.env['employee.vdu'].search([])
        for vdu_rec in vdu_recs:
            if vdu_rec.type == 'men':
                vdu_rec.amount = vdu_rec.vdu * vdu_rec.hours_worked
                vdu_rec.days_worked = vdu_rec.time_worked
            else:
                vdu_rec.amount = vdu_rec.vdu * vdu_rec.time_worked
                vdu_rec.hours_worked = vdu_rec.time_worked


EmployeeVdu()
