# -*- coding: utf-8 -*-

from datetime import datetime

from odoo import api, fields, models, exceptions
from odoo.tools.translate import _


class JumpToDateWizard(models.TransientModel):
    _name = 'jump.to.date.wizard'

    def _current_year(self):
        return int(datetime.utcnow().year)

    def _current_month(self):
        return str(datetime.utcnow().month)

    year = fields.Integer(string='Metai', required=True, default=_current_year)
    month = fields.Selection([('1', _('Sausis')),
                              ('2', _('Vasaris')),
                              ('3', _('Kovas')),
                              ('4', _('Balandis')),
                              ('5', _('Gegužė')),
                              ('6', _('Birželis')),
                              ('7', _('Liepa')),
                              ('8', _('Rugpjūtis')),
                              ('9', _('Rugsėjis')),
                              ('10', _('Spalis')),
                              ('11', _('Lapkritis')),
                              ('12', _('Gruodis'))], string='Mėnuo', required=True, default=_current_month)

    @api.multi
    @api.constrains('year')
    def _check_reasonable_year(self):
        for rec in self:
            if rec.year < 2000 or rec.year > 2100:
                raise exceptions.UserError(_("Metai turi būti nuo 2000-ūjų iki 2100-ūjų"))

    @api.multi
    def confirm(self):
        action = self.env.ref('work_schedule.action_main_work_schedule_view')
        menu_id = self.env.ref('work_schedule.menu_work_schedule_main').id
        return {
            'type': 'ir.actions.act_window',
            'view_id': action.view_id.id,
            'res_model': action.res_model,
            'target': 'main',
            'views': [[action.view_id.id, 'workschedule']],
            'view_type': 'form',
            'view_mode': 'workschedule',
            'name': "Darbo grafikas",
            'id': action.id,
            'context': {
                    'robo_menu_name': menu_id,
                    'force_back_menu_id': menu_id,
                    'robo_front': True,
                    'default_year': self.year,
                    'default_month': int(self.month),
            }
        }


JumpToDateWizard()