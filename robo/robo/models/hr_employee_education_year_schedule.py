# -*- coding: utf-8 -*-


from datetime import datetime

from odoo import _, api, exceptions, fields, models, tools


class HrEmployeeEducationYearSchedule(models.Model):
    _name = 'hr.employee.education.year.schedule'

    def _default_date_from(self):
        year = datetime.utcnow().year
        return datetime(year, 9, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _default_date_to(self):
        year = datetime.utcnow().year
        return datetime(year + 1, 6, 10).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    education_year_id = fields.Many2one('hr.employee.education.year', string='Mokslo periodas', required=True,
                                        ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', string="Darbuotojas", related='education_year_id.employee_id')
    name = fields.Char(string='Pavadinimas', default='Naujas Grafikas')
    education_day_ids = fields.One2many('hr.employee.education.year.schedule.day', 'education_schedule_id',
                                        groups="robo_basic.group_robo_free_manager,"
                                               "robo_basic.group_robo_premium_manager,"
                                               "robo_basic.group_robo_hr_manager",
                                        string='Mokslo dienos')
    date_from = fields.Date(string='Grafiko pradžios data', required=True, default=_default_date_from)
    date_to = fields.Date(string='Grafiko pabaigos data', required=True, default=_default_date_to)

    @api.multi
    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from < rec.education_year_id.date_from:
                raise exceptions.UserError(_('Mokslų grafikas negali prasidėti anksčiau, nei mokslo metai'))
            if rec.date_to > rec.education_year_id.date_to:
                raise exceptions.UserError(_('Mokslų grafikas negali pasibaigti vėliau, nei mokslo metai'))
            if rec.date_from > rec.date_to:
                raise exceptions.UserError(_('Mokslų grafikas turi prasidėti prieš savo pabaigą'))
