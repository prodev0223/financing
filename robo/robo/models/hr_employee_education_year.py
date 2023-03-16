# -*- coding: utf-8 -*-


from datetime import datetime

from odoo import _, api, exceptions, fields, models, tools


class HrEmployeeEducationYear(models.Model):
    _name = 'hr.employee.education.year'

    def _default_date_from(self):
        year = datetime.utcnow().year
        return datetime(year, 9, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _default_date_to(self):
        year = datetime.utcnow().year
        return datetime(year + 1, 6, 10).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    employee_id = fields.Many2one('hr.employee', string="Darbuotojas", required=True, ondelete='cascade')
    name = fields.Char(string='Pavadinimas', default='Mokslo metai')
    date_from = fields.Date(string='Pradžios data', required=True, default=_default_date_from)
    date_to = fields.Date(string='Pabaigos data', required=True, default=_default_date_to)
    education_schedule_ids = fields.One2many('hr.employee.education.year.schedule', 'education_year_id',
                                             string='Mokymosi grafikai')

    @api.multi
    @api.constrains('date_from', 'date_to', 'education_schedule_ids')
    def _check_dates(self):
        for rec in self:
            if rec.date_from > rec.date_to:
                raise exceptions.UserError(_('Mokslo metų pradžia turi būti prieš jų pabaigą.'))
            for education_schedule_id in rec.education_schedule_ids:
                if education_schedule_id.date_from < rec.date_from:
                    msg = _('Neteisingai įvesta mokslo metų pradžios data. Egzistuoja grafikas {0}, kuris prasideda {1}. '
                            'Pirmiausia pakeiskite šio grafiko pradžios datą.')
                    msg = msg.format(education_schedule_id.name, education_schedule_id.date_from)
                    raise exceptions.UserError(msg)
                if education_schedule_id.date_to > rec.date_to:
                    msg = _('Neteisingai įvesta mokslo metų pabaigos data. Egzistuoja grafikas {0}, kuris baigiasi {1}. '
                            'Pirmiausia pakeiskite šio grafiko pabaigos datą.')
                    msg = msg.format(education_schedule_id.name, education_schedule_id.date_to)
                    raise exceptions.UserError(msg)
