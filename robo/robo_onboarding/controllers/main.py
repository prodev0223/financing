# -*- coding: utf-8 -*-

import logging

from odoo.addons.web.controllers.main import Home

from odoo import http
from odoo.http import request
import math

_logger = logging.getLogger(__name__)


class OnboardingHome(Home):

    @http.route('/web', type='http', auth="none")
    def web_client(self, s_action=None, **kw):
        additional_context = kw.get('additional_context', {})
        user = request.env['res.users'].browse(request.session.uid)
        show_robo_onboarding = False
        if user and user.is_premium_manager():
            show_robo_onboarding = user.company_id.sudo().robo_onboarding_is_shown
        additional_context['show_robo_onboarding'] = show_robo_onboarding

        action = request.env.ref('robo_onboarding.robo_onboarding_tasks_main_user_view_action')
        additional_context['robo_onboarding_action_id'] = '/web?#action=' + str(action.id)

        onboarding_progress_data = request.env['robo.onboarding.category'].get_robo_onboarding_progress_data()
        completed_weight = onboarding_progress_data.get('completed_weight', 0)
        total_weight = onboarding_progress_data.get('total_weight', 0)
        onboarding_tasks_completed = onboarding_progress_data.get('completed', 0)
        onboarding_tasks_total = onboarding_progress_data.get('total', 0)
        try:
            onboarding_percentage = round(completed_weight / float(total_weight) * 100.0, 2)
        except ZeroDivisionError:
            onboarding_percentage = 0.0
        additional_context['robo_onboarding_completion_percentage'] = int(math.floor(onboarding_percentage))
        additional_context['robo_onboarding_tasks_completed'] = onboarding_tasks_completed
        additional_context['robo_onboarding_tasks_total'] = onboarding_tasks_total

        return super(OnboardingHome, self).web_client(s_action=s_action, additional_context=additional_context, **kw)


Home()
