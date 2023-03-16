# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, _


class HrHolidaysReport(models.Model):
    _name = 'hr.holidays.report'
    _auto = False
    _description = 'Hr Holidays Report'

    employee_id = fields.Many2one('hr.employee', string='Employee')
    leave_name = fields.Char(string='Leave name', compute='_compute_holiday_view')
    holiday_id = fields.Many2one('hr.holidays', string='Holidays', sequence=85)
    department_id = fields.Many2one('hr.department', string='Department')
    date_from = fields.Date(string='Date from', readonly=True)
    date_to = fields.Date(string='Date to', readonly=True)

    @api.model_cr
    def init(self):
        tools.drop_view_if_exists(self._cr, 'hr_holidays_report')
        self._cr.execute('''
            CREATE or REPLACE view hr_holidays_report as (
            SELECT
              ROW_NUMBER() OVER (order by holiday_id) AS id,
              foo.holiday_id,
              foo.employee_id,
              foo.department_id,
              foo.leave_name,
              foo.date_from,
              foo.date_to,
              foo.type,
              foo.holiday_type,
              foo.state
            FROM (
            select 	hol.id as holiday_id,
                    hol.employee_id,
                    hol.name as leave_name,
                    hol.date_from,
                    hol.date_to,
                    hol.type,
                    hol.holiday_type,
                    hol.state,
                    empl.department_id 
                    from hr_holidays hol
                    left join hr_employee as empl ON hol.employee_id = empl.id
                    where hol.holiday_type like 'employee' and
                    hol.type  like 'remove' and
                    hol.state not like 'refuse'                   
                    ) as foo) 
                    ''')

    @api.multi
    def _compute_holiday_view(self):
        holiday_names = self._get_holiday_names()
        for holiday in self:
            if self.env.user.is_manager() or self.env.user.is_hr_manager():
                holiday.leave_name = '%s - %s' % (holiday.employee_id.name,
                                                  holiday_names.get(unicode(holiday.holiday_id.name),
                                                                    holiday.holiday_id.name)
                                                  or
                                                  holiday_names.get(unicode(holiday.holiday_id.holiday_status_id.name))
                                                  or
                                                  _('Neatvykęs (-usi)'))

            elif self.env.user.company_id.politika_neatvykimai == "own":
                if holiday.employee_id.id == self.env.user.employee_ids.id:
                    holiday.leave_name = '%s - %s' % (holiday.employee_id.name,
                                                      holiday_names.get(unicode(holiday.holiday_id.name),
                                                                        holiday.holiday_id.name) or
                                                      _('Neatvykęs (-usi)'))

            elif self.env.user.company_id.politika_neatvykimai == "department":
                if holiday.employee_id.department_id == self.env.user.employee_ids.department_id or \
                        holiday.employee_id.department_id.manager_id.id in self.env.user.employee_ids.ids:
                    if holiday.employee_id.id == self.env.user.employee_ids.id:
                        holiday.leave_name = '%s - %s' % (holiday.employee_id.name,
                                                          holiday_names.get(unicode(holiday.holiday_id.name),
                                                                            holiday.holiday_id.name) or
                                                      _('Neatvykęs (-usi)'))
                    else:
                        holiday.leave_name = '%s - %s' % (holiday.employee_id.name,  _('Neatvykęs (-usi)'))

            elif self.env.user.company_id.politika_neatvykimai == "all":
                if holiday.employee_id.id == self.env.user.employee_ids.id:
                    holiday.leave_name = '%s - %s' % (holiday.employee_id.name,
                                                      holiday_names.get(unicode(holiday.holiday_id.name),
                                                                        holiday.holiday_id.name) or
                                                      _('Neatvykęs (-usi)'))
                else:
                    holiday.leave_name = '%s - %s' % (holiday.employee_id.name,  _('Neatvykęs (-usi)'))

    def _get_holiday_names(self):
        return {
            u'Kasmetinės atostogos': _('Kasmetinės atostogos'),
            u'Neatvykimas dėl ligos': _('Neatvykimas dėl ligos'),
            u'Nedarbingumas': _('Nedarbingumas'),
            u'Nedarbingumo pažymėjimas': _('Nedarbingumo pažymėjimas'),
            u'Neapmokamas nedarbingumas': _('Nedarbingumo pažymėjimas'),
            u'Nedarbingumas dėl ligos ar traumų': _('Nedarbingumo pažymėjimas'),
            u'Nedarbingumas ligoniams slaugyti, turint pažymas': _('Nedarbingumo pažymėjimas'),
            u'Nemokamos atostogos': _('Nemokamos atostogos'),
            u'Nėštumo atostogų pažymėjimas': _('Nėštumo atostogų pažymėjimas'),
            u'Nėštumo ir gimdymo atostogos': _('Nėštumo atostogų pažymėjimas'),
            u'Tėvystės atostogos': _('Tėvystės atostogos'),
            u'Atostogos vaikui prižiūrėti': _('Atostogos vaikui prižiūrėti'),
            u'Vaiko priežiūros atostogos': _('Atostogos vaikui prižiūrėti'),
            u'Trijų mėnesių atostogos vaikui prižiūrėti': _('Trijų mėnesių atostogos vaikui prižiūrėti'),
            u'Tarnybinės komandiruotės': _('Tarnybinės komandiruotės'),
            u'Mokymosi atostogos': _('Mokymosi atostogos'),
            u'Prastova': _('Prastova'),
            u'Prastovos dėl darbuotojo kaltės': _('Prastova'),
            u'Prastovos ne dėl darbuotojo kaltės': _('Prastova'),
            u'Pravaikšta': _('Pravaikšta'),
            u'Pravaikštos ir kitoks neatvykimas į darbą be svarbios priežasties': _('Pravaikšta'),
            u'Kūrybinės atostogos': _('Kūrybinės atostogos'),
            u'Papildomos atostogos': _('Papildomos atostogos'),
            u'Kitų rūšių atostogos': _('Papildomos atostogos'),
            u'Kvalifikacijos kėlimas': _('Kvalifikacijos kėlimas'),
            u'Kvalifikacijos kėlimas (neapmokamas)': _('Kvalifikacijos kėlimas'),
            u'Stažuotės': _('Stažuotės'),
            u'Neatvykimas į darbą darbdaviui leidus': _('Neatvykimas į darbą darbdaviui leidus'),
            u'Poilsio dienos už komandiruotėje dirbtas poilsio dienas':
                _('Poilsio dienos už komandiruotėje dirbtas poilsio dienas'),
            u'Papildomos poilsio dienos, suteiktos už darbą virš kasdienio darbo laiko trukmės, darbą poilsio ir švenčių dienomis':
                _('Poilsio dienos už komandiruotėje dirbtas poilsio dienas'),
            u'Laisvas pusdienis pirmąją mokslo metų dieną': _('Laisvas pusdienis pirmąją mokslo metų dieną'),
            u'Papildomas poilsio laikas darbuotojams pirmąją mokslo metų dieną, auginantiems vaiką iki 14 metų besimokantį bendrojo ugdymo įstaigoje':
                _('Papildomas poilsio laikas darbuotojams pirmąją mokslo metų dieną, auginantiems vaiką iki 14 metų besimokantį bendrojo ugdymo įstaigoje'),
            u'Atleidimas nuo darbo visuomeninėms pareigoms atlikti': _(
                'Atleidimas nuo darbo visuomeninėms pareigoms atlikti'),
            u'Karinė tarnyba': _('Atleidimas nuo darbo visuomeninėms pareigoms atlikti'),
            u'Mokomosios karinės pratybos': _('Atleidimas nuo darbo visuomeninėms pareigoms atlikti'),
            u'Valstybinių, visuomeninių ar piliečio pareigų vykdymas':
                _('Atleidimas nuo darbo visuomeninėms pareigoms atlikti'),
            u'Papildomas poilsio laikas darbuotojams, auginantiems neįgalų vaiką iki 18 metų arba du ir daugiau vaikų iki 12 metų':
                _('Papildomas poilsio laikas darbuotojams, auginantiems neįgalų vaiką iki 18 metų arba du ir daugiau vaikų iki 12 metų'),
        }


HrHolidaysReport()
