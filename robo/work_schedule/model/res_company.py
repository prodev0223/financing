# -*- coding: utf-8 -*-

from datetime import datetime

from odoo import api, fields, models, tools
from odoo.tools.translate import _


class ResCompany(models.Model):
    _inherit = 'res.company'

    dn_start_time = fields.Float('Nakties pradžia', compute='_compute_dn_start_time')
    dn_end_time = fields.Float('Nakties pabaiga', compute='_compute_dn_end_time')
    min_dn_time = fields.Float('Minimalus DN laikas (h.)', compute='_compute_min_dn_time')
    quarterly_weekly_max_hours = fields.Float('Maksimalus darbo laikas per 7 dienas skaičiuojant ketvirčiais (h.)',
                                              compute='_compute_quarterly_weekly_max_hours')
    max_daily_time = fields.Float('Maksimalus darbo laikas per dieną (h.)', compute='_compute_max_daily_time')
    minimum_time_between_shifts_lower = fields.Float(
        'Minimalus poilsio laikas tarp pamainų dirbant mažiau valandų (h.)',
        compute='_compute_minimum_time_between_shifts_lower')
    minimum_time_between_shifts_higher = fields.Float(
        'Minimalus poilsio laikas tarp pamainų dirbant daugiau valandų (h.)',
        compute='_compute_minimum_time_between_shifts_higher')
    maximum_time_between_breaks = fields.Float('Maksimalus pertraukos laikas (h.)',
                                               compute='_compute_maximum_time_between_breaks')
    minimum_time_between_breaks = fields.Float('Minimalus pertraukos laikas (h.)',
                                               compute='_compute_minimum_time_between_breaks')
    maximum_active_budejimas_time = fields.Float('Maksimalus aktyvaus budejimo laikas (h.)',
                                                 compute='_compute_maximum_active_budejimas_time')
    maximum_work_time_to_break = fields.Float('Maksimalus darbo laikas iki pertraukos (h.)',
                                              compute='_compute_maximum_work_time_to_break')
    shift_break_threshold = fields.Float(
        'Valandų skaičius pagal kurį nustatoma ar privalomas ilgesnis laikas tarp pamainų (h.)',
        compute='_compute_shift_break_threshold')
    main_7_day_break_length = fields.Float('Minimalus ilgosios pertraukos tarp pamainų kartą per 7 dienas laikas (h.)',
                                           compute='_compute_main_7_day_break_length')
    schedule_period_ids = fields.One2many('res.company.extended.schedule.period', 'company_id',
                                          inverse='_inverse_schedule_period_ids')
    extended_schedule = fields.Boolean(compute='_extended_schedule')
    schedule_policy = fields.Selection([('one_step', _('Grafikai tvirtinami iš karto kompanijos lygiu')),
                                        ('two_step', _('Grafikai iš pradžių tvirtinami skyriaus lygiu'))],
                                       string='Darbo grafiko tvirtinimo politika',
                                       required=True, default='two_step')
    work_schedule_labour_code_bypass = fields.Selection([('allowed', _('Leidžiama')),
                                                         ('disallowed', _('Neleidžiama'))],
                                                        string='Darbo grafiko tvirtinimas, nepaisant darbo kodekso apribojimų',
                                                        default='disallowed', required=True,
                                                        groups='robo_basic.group_robo_premium_accountant')
    work_schedule_state_to_check_constraints = fields.Selection([('validate', _('Preliminariai tvirtinant grafiką')),
                                                                 ('confirm', _('Pateikiant grafiką'))],
                                                                string='Kada tikrinami darbo kodekso apribojimai darbo grafike',
                                                                default='validate',
                                                                groups='robo_basic.group_robo_premium_accountant')
    show_user_who_exported_info = fields.Selection([('show', _('Rodyti')),
                                                    ('dont_show', _('Nerodyti'))],
                                                   string='Eksportuojant grafiką rodyti duomenis, kas sudarė grafiką')
    schedule_export_extra_text_1 = fields.Text(string="Papildomas tekstas eksportuojant grafikus")
    schedule_export_extra_text_2 = fields.Text(string="Papildomas tekstas eksportuojant grafikus")
    update_planned_schedule_on_holiday_set = fields.Selection([('update', _('Atnaujinti')),
                                                               ('dont_update', _('Neatnaujinti'))],
                                                              string="Atnaujinti planuojamus grafikus atsiradus neatvykimam",
                                                              groups='robo_basic.group_robo_premium_accountant')
    inform_employees_about_schedule_changes = fields.Selection(
        [('inform', _('Informuoti')), ('dont_inform', _('Neinformuoti'))],
        string='Informuoti darbuotojus, kuomet jų darbo grafikas būna pakeistas',
        default='dont_inform',
        groups='robo_basic.group_robo_premium_accountant'
    )

    def get_schedule_field_value(self, field_name):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        rec = self.env['work.schedule.parameters'].search([('company_id', '=', self.id), ('name', '=', field_name),
                                                           ('date', '<=', date)], order='date desc', limit=1)
        if not rec:
            rec = self.env['work.schedule.parameter'].search(
                [('company_id', '=', self.id), ('name', '=', field_name)], order='date desc', limit=1)
        if rec:
            return rec.value
        else:
            return 0.0

    @api.one
    def _compute_dn_start_time(self):
        self.dn_start_time = self.get_schedule_field_value('dn_start_time')

    @api.one
    def _compute_dn_end_time(self):
        self.dn_end_time = self.get_schedule_field_value('dn_end_time')

    @api.one
    def _compute_min_dn_time(self):
        self.min_dn_time = self.get_schedule_field_value('min_dn_time')

    @api.one
    def _compute_quarterly_weekly_max_hours(self):
        self.quarterly_weekly_max_hours = self.get_schedule_field_value('quarterly_weekly_max_hours')

    @api.one
    def _compute_max_daily_time(self):
        self.max_daily_time = self.get_schedule_field_value('max_daily_time')

    @api.one
    def _compute_minimum_time_between_shifts_lower(self):
        self.minimum_time_between_shifts_lower = self.get_schedule_field_value('minimum_time_between_shifts_lower')

    @api.one
    def _compute_minimum_time_between_shifts_higher(self):
        self.minimum_time_between_shifts_higher = self.get_schedule_field_value('minimum_time_between_shifts_higher')

    @api.one
    def _compute_maximum_time_between_breaks(self):
        self.maximum_time_between_breaks = self.get_schedule_field_value('maximum_time_between_breaks')

    @api.one
    def _compute_minimum_time_between_breaks(self):
        self.minimum_time_between_breaks = self.get_schedule_field_value('minimum_time_between_breaks')

    @api.one
    def _compute_maximum_active_budejimas_time(self):
        self.maximum_active_budejimas_time = self.get_schedule_field_value('maximum_active_budejimas_time')

    @api.one
    def _compute_maximum_work_time_to_break(self):
        self.maximum_work_time_to_break = self.get_schedule_field_value('maximum_work_time_to_break')

    @api.one
    def _compute_shift_break_threshold(self):
        self.shift_break_threshold = self.get_schedule_field_value('shift_break_threshold')

    @api.one
    def _compute_main_7_day_break_length(self):
        self.main_7_day_break_length = self.get_schedule_field_value('main_7_day_break_length')

    @api.one
    def _inverse_schedule_period_ids(self):
        self.cron_check_work_schedule_periods()

    @api.model
    def cron_check_work_schedule_periods(self):
        self = self.sudo()
        company = self.env.user.company_id
        is_extended = company.extended_schedule if company else False
        menu_group = self.env.ref('work_schedule.group_schedule_menu_visible', raise_if_not_found=False)
        base_user_group = self.env.ref('work_schedule.group_schedule_user', raise_if_not_found=False)
        if not menu_group or not base_user_group:
            return
        if is_extended:
            users = base_user_group.users
            users.write({'groups_id': [(4, menu_group.id,)]})
        else:
            users = menu_group.users
            users.write({'groups_id': [(3, menu_group.id,)]})

        # Disable work schedule view extensions
        views = self.env.ref('work_schedule.work_schedule_e_doc_business_trip_extra_days_worked_override') + \
                self.env.ref('work_schedule.change_work_schedule_group_access') + \
                self.env.ref('work_schedule.work_schedule_company_settings') + \
                self.env.ref('work_schedule.add_bypass_day_constraints_option_in_employee_card')
        views.sudo().write({'active': is_extended})

    @api.multi
    @api.depends('schedule_period_ids.date_from', 'schedule_period_ids.date_to')
    def _extended_schedule(self):
        date = self._context.get('date')
        if not date:
            date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        for company in self.filtered(lambda c: c.sudo().module_work_schedule):
            for s in company.sudo().schedule_period_ids:
                date_from_temp = s.date_from or date
                date_to_temp = s.date_to or date
                date_from = min(date_from_temp, date_to_temp)
                date_to = max(date_from_temp, date_to_temp)
                if date_from <= date <= date_to:
                    company.extended_schedule = True
                    break


ResCompany()
