# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.tools.translate import _


class CompanySettings(models.TransientModel):
    _inherit = 'robo.company.settings'

    work_schedule_labour_code_bypass = fields.Selection([('allowed', _('Leidžiama')),
                                                         ('disallowed', _('Neleidžiama'))],
                                                        string='Darbo grafiko tvirtinimas, nepaisant darbo kodekso apribojimų',
                                                        default='disallowed',
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

    @api.model
    def default_get(self, field_list):
        res = super(CompanySettings, self).default_get(field_list)
        company = self.env.user.sudo().company_id
        if self.env.user.is_accountant():
            res.update({
                'work_schedule_labour_code_bypass': company.work_schedule_labour_code_bypass,
                'work_schedule_state_to_check_constraints': company.work_schedule_state_to_check_constraints,
                'update_planned_schedule_on_holiday_set': company.update_planned_schedule_on_holiday_set,
                'inform_employees_about_schedule_changes': company.inform_employees_about_schedule_changes,
            })
        res.update({
            'show_user_who_exported_info': company.show_user_who_exported_info,
            'schedule_export_extra_text_1': company.schedule_export_extra_text_1,
            'schedule_export_extra_text_2': company.schedule_export_extra_text_2,
        })
        return res

    @api.model
    def _get_company_policy_field_list(self):
        res = super(CompanySettings, self)._get_company_policy_field_list()
        res.extend((
            'work_schedule_labour_code_bypass',
            'work_schedule_state_to_check_constraints',
            'update_planned_schedule_on_holiday_set',
            'inform_employees_about_schedule_changes',
        ))
        return res

    @api.model
    def _get_company_info_field_list(self):
        res = super(CompanySettings, self)._get_company_info_field_list()
        res.extend((
            'show_user_who_exported_info',
            'schedule_export_extra_text_1',
            'schedule_export_extra_text_2',
        ))
        return res


CompanySettings()
