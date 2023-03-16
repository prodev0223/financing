# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.tools.translate import _

work_parameters_selection = [
    ('dn_start_time', _('Nakties pradžia')),
    ('dn_end_time', _('Nakties pabaiga')),
    ('min_dn_time', _('Minimalus DN laikas (h.)')),
    ('quarterly_weekly_max_hours', _('Maksimalus laikas per ketvirtį(h.)')),
    ('max_daily_time', _('Maksimalus dienos laikas (h.)')),
    ('minimum_time_between_shifts_lower', _('Minimalus poilsio laikas tarp pamainų dirbant mažiau valandų (h.)')),
    ('minimum_time_between_shifts_higher', _('Minimalus poilsio laikas tarp pamainų dirbant daugiau valandų (h.)')),
    ('shift_break_threshold',
     _('Valandų skaičius pagal kurį nustatoma ar privalomas ilgesnis laikas tarp pamainų (h.)')),
    ('maximum_time_between_breaks', _('Maksimalus pertraukos laikas (h.)')),
    ('minimum_time_between_breaks', _('Minimalus pertraukos laikas (h.)')),
    ('maximum_active_budejimas_time', _('Maksimalus aktyvaus budejimo laikas (h.)')),
    ('maximum_work_time_to_break', _('Maksimalus darbo laikas iki pertraukos (h.)')),
    ('main_7_day_break_length', _('Minimalus ilgosios pertraukos tarp pamainų kartą per 7 dienas laikas (h.)')),
]


class WorkScheduleParameter(models.Model):
    _name = 'work.schedule.parameters'

    _order = 'date desc'
    _sql_constraints = [('unique_date_field', 'unique(date, name)',
                         _('Tas pats parametras negali įgyti dviejų reikšmių tą pačią dieną'))]

    def _company_id(self):
        return self.env.user.company_id

    company_id = fields.Many2one('res.company', string='Kompanija', required=True, default=_company_id)
    name = fields.Selection(work_parameters_selection, string='Laukelis', required=True)
    value = fields.Float(string='Reikšmė', required=True)
    date = fields.Date(string='Data nuo', required=True)


WorkScheduleParameter()
