# -*- coding: utf-8 -*-


from odoo import _, api, exceptions, fields, models, tools


class HrEmployeeEducationYearScheduleDay(models.Model):
    _name = 'hr.employee.education.year.schedule.day'

    education_schedule_id = fields.Many2one('hr.employee.education.year.schedule', string='Mokslo metų šablonas',
                                            required=True, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', compute='_compute_employee_id')
    dayofweek = fields.Selection(
        [
            ('0', 'Pirmadienis'),
            ('1', 'Antradienis'),
            ('2', 'Trečiadienis'),
            ('3', 'Ketvirtadienis'),
            ('4', 'Penktadienis'),
            ('5', 'Šeštadienis'),
            ('6', 'Sekmadienis')
        ],
        string='Savaitės diena', required=True, index=True, default='0')
    time_from = fields.Float(string='Pradžia', required=True, index=True, help='Edukacijos pradžios laikas')
    time_to = fields.Float(string='Pabaiga', required=True, help='Edukacijos pabaigos laikas')
    time_total = fields.Float(string='Viso', compute='_compute_time_total', help='Edukacijos laikas per dieną')

    @api.one
    @api.depends('education_schedule_id.education_year_id')
    def _compute_employee_id(self):
        self.employee_id = self.education_schedule_id.education_year_id.employee_id

    @api.multi
    @api.constrains('time_from', 'time_to')
    def _check_times(self):
        for rec in self:
            if rec.time_from > rec.time_to:
                raise exceptions.ValidationError(_('Mokslų grafiko laiko pradžia turi būti ankstesnė nei pabaiga'))
            if tools.float_compare(rec.time_from, 0.0, precision_digits=2) < 0 or \
                    tools.float_compare(rec.time_from, 24, precision_digits=2) > 0:
                raise exceptions.ValidationError(_('Mokslų grafiko pradžios laikas privalo būti tarp 00:00 ir 24:00'))
            if tools.float_compare(rec.time_to, 0.0, precision_digits=2) < 0 or \
                    tools.float_compare(rec.time_to, 24, precision_digits=2) > 0:
                raise exceptions.ValidationError(_('Mokslų grafiko pabaigos laikas privalo būti tarp 00:00 ir 24:00'))

    @api.one
    @api.depends('time_from', 'time_to')
    def _compute_time_total(self):
        self.time_total = self.time_to - self.time_from
