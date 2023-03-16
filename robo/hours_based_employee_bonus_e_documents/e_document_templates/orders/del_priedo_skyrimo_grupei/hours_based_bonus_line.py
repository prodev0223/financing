# -*- coding: utf-8 -*-
from odoo import models, fields, exceptions, api, _, tools
from datetime import datetime
from dateutil.relativedelta import relativedelta


class HoursBasedBonusLine(models.Model):
    _name = 'hours.based.bonus.line'

    e_document_id = fields.Many2one('e.document', required=True, ondelete='cascade', inverse='_check_employee_has_appointment')
    employee_id2 = fields.Many2one('hr.employee', string='Darbuotojas', required=True)
    normal_hours = fields.Float(string='Darbo valandos', default=0.0)
    night_hours = fields.Float(string='Iš kurių darbas naktį', default=0.0)
    date = fields.Date(string='Data', related='e_document_id.date_3')
    valandinis_bruto = fields.Float(string='Valandinis darbo užmokestis', compute='_get_hourly_wage')
    float_1 = fields.Float(string='Priedo dydis (bruto)', required=True, default=0.0)

    @api.multi
    @api.constrains('normal_hours', 'night_hours')
    def _night_hours_fit_normal_hours(self):
        for rec in self:
            if rec.normal_hours < rec.night_hours:
                raise exceptions.ValidationError(_('Darbas naktį turi būti trumpesnis arba lygus darbo valandom (%s)')
                                                 % rec.employee_id2.name)

    @api.multi
    @api.constrains('normal_hours', 'night_hours')
    def _hours_are_positive(self):
        for rec in self:
            e_name = rec.employee_id2.name
            if rec.normal_hours < 0:
                raise exceptions.ValidationError(
                    _('Darbuotojo %s darbo valandų skaičius negali būti mažesnis už 0') % e_name)
            elif rec.night_hours < 0:
                raise exceptions.ValidationError(
                    _('Darbuotojo %s darbo naktį valandų skaičius negali būti neigiamas') % e_name)

    @api.one
    def _check_employee_has_appointment(self):
        date_from_dt = datetime.strptime(self.date, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = (date_from_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        appointment = self.env['hr.contract.appointment'].search([
            ('employee_id', '=', self.employee_id2.id),
            ('date_start', '<=', date_to),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', self.date)
        ])
        if not appointment:
            raise exceptions.UserError(
            _('Nurodytam išmokėjimo periodui nerastas darbuotojo %s priedas') % self.employee_id2.name)

    @api.one
    @api.depends('employee_id2')
    def _get_hourly_wage(self):
        employee = self.employee_id2
        date = self.date
        appointment = None
        if employee and date:
            appointment = employee.with_context(date=date).contract_id.appointment_id
            if not appointment:
                appointments = employee.contract_ids.mapped('appointment_ids').filtered(
                    lambda app: app.date_start > date
                ).sorted(key=lambda app: app.date_start)
                appointment = appointments and appointments[0]
        self.valandinis_bruto = appointment.hypothetical_hourly_wage if appointment else 0.0

    @api.onchange('employee_id2', 'normal_hours', 'night_hours', 'date')
    def _compute_bruto(self):
        normal_hours = self.normal_hours if self.normal_hours else 0.0
        dn_hours = self.night_hours if self.night_hours else 0.0
        regular_hours = normal_hours - dn_hours
        dn_coefficient = self.env.user.company_id.with_context(date=self.date).dn_coefficient #TODO what is the date here? is it date doc? if not we should check if holiday and use DPN
        self.float_1 = self.valandinis_bruto * regular_hours + self.valandinis_bruto * dn_hours * dn_coefficient


HoursBasedBonusLine()
