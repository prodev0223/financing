# coding=utf-8
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, models, tools, fields

SHOW_FOR_AFTER_ALL_HAVE_BEEN_COMPLETED = 7  # How many days after all tasks have been completed to show the progress for


class ResCompany(models.Model):
    _inherit = 'res.company'

    force_do_not_show_onboarding = fields.Boolean(string='Do not show onboarding', default=True)
    robo_onboarding_is_shown = fields.Boolean(string='Robo onboarding is shown',
                                              compute='_compute_robo_onboarding_is_shown')

    @api.multi
    def _compute_robo_onboarding_is_shown(self):
        for rec in self:
            do_show = False
            if self.env.user.is_premium_manager() and not self.env.user.company_id.force_do_not_show_onboarding:
                do_show = True
                data = self.env['robo.onboarding.category'].get_robo_onboarding_progress_data()
                if data.get('completed') == data.get('total') and data.get('total') != 0:
                    last_completed = self.env['robo.onboarding.task'].search([
                        ('shown_to_client', '=', True),
                        ('completed', '=', True),
                    ], order='completion_date desc', limit=1)
                    if last_completed:
                        last_completion_date = datetime.strptime(last_completed.completion_date,
                                                                 tools.DEFAULT_SERVER_DATETIME_FORMAT)
                        now = datetime.utcnow()
                        show_until = last_completion_date + relativedelta(days=SHOW_FOR_AFTER_ALL_HAVE_BEEN_COMPLETED)
                        if now >= show_until:
                            do_show = False
            rec.robo_onboarding_is_shown = do_show

    @api.model
    def is_robo_onboarding_shown(self):
        return self.env.user.company_id.robo_onboarding_is_shown

    @api.model
    def set_force_do_not_show_onboarding(self, show_onboarding):
        self.env['res.company'].search([], limit=1).write({'force_do_not_show_onboarding': not show_onboarding})


ResCompany()
