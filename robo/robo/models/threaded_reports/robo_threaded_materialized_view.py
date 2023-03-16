# -*- coding: utf-8 -*-
from odoo import models, api, _
from . import threaded_report_tools as rt
import ast


class RoboThreadedMaterializedView(models.AbstractModel):

    """
    Abstract model that contains some computed fields (methods in the future)
    That are shared between all of the threaded reports
    """

    _name = 'robo.threaded.materialized.view'

    @api.model
    def threaded_reports(self):
        """
        Check whether threaded reports are activated
        and return the boolean result
        :return: True/False
        """
        return self.sudo().env.user.company_id.activate_threaded_front_reports

    @api.model
    def refresh_view(self):
        """
        Make a template method for view refreshing.
        Method is checking whether refresh should be allowed
        and returns boolean value.
        :return: True/False
        """
        if self.threaded_reports() and not self._context.get('force_refresh'):
            return False
        return True

    @api.model
    def action_open_materialized_view(self, extra_identifier=None):
        """
        Check if company has threaded mode on, if it does:
            -Refresh the view, read the simple (non-threaded) action
            and return it.
        Otherwise:
            -Fetch the report name from the mapping,
            and open the wizard which lets you select whether to
            open the report with limited data, or refresh the view in
            background thread
            -If extra_identifier is specified, then its not the main action of the model
            and it should be opened without the possibility to use refresh wizard
        :param extra_identifier: extra action identifier
        :return: either report or wizard action (dict)
        """
        if not self.threaded_reports():
            # If company mode is not threaded, just keep the previous behaviour
            self.refresh_view()
            external_id = rt.get_action(self._name)
            action = self.env.ref(external_id).read()[0]

            # If extra identifier is passed, fetch extra context
            if extra_identifier:
                used_context = ast.literal_eval(action.get('context', str()))
                used_context.update(rt.get_extra_context(self._name, extra_identifier))
                action['context'] = used_context
            return action
        else:
            report_name = rt.MODEL_TO_NAME_MAPPING.get(self._name, _('Ataskaita'))
            wizard = self.env['robo.materialized.view.wizard'].create({
                'model': self._name,
                'name': report_name
            })
            if extra_identifier:
                return wizard.action_open_materialized_view(extra_identifier=extra_identifier, skip_domain=True)

            return {
                'name': report_name,
                'view_type': 'form',
                'view_mode': 'form',
                'view_id': self.env.ref('robo.form_robo_materialized_view_wizard').id,
                'res_id': wizard.id,
                'res_model': 'robo.materialized.view.wizard',
                'type': 'ir.actions.act_window',
                'target': 'new',
            }

    @api.model
    def cron_reload_materialized_views(self):
        """
        If threaded report mode is activated, reload every view that inherits this module
        :return: None
        """
        if self.threaded_reports():
            for model_name in rt.THREADED_MODELS:
                self.env[model_name].with_context(force_refresh=True).refresh_view()


RoboThreadedMaterializedView()
