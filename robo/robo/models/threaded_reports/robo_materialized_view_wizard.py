# -*- coding: utf-8 -*-
from odoo import models, api, fields, tools, exceptions, _
from datetime import datetime
from dateutil.relativedelta import relativedelta
from . import threaded_report_tools as rt
import ast


class RoboMaterializedViewWizard(models.TransientModel):

    """
    Wizard that is used for big pivot (materialized) report management:
        -User can refresh the pivot view with a tread
        -User can proceed with report opening without refresh
        -Data in the pivot view is limited based on period domain
        that is selected in the wizard itself
    """
    _name = 'robo.materialized.view.wizard'

    @api.model
    def _default_period_start(self):
        """Default period start -- One month from today"""
        return (datetime.utcnow() - relativedelta(months=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.model
    def _default_period_end(self):
        """Default period end -- today"""
        return fields.Date.today()

    model = fields.Char(string='Modelis', required=True)
    name = fields.Char(string='Ataskaitos pavadinimas')

    period_start = fields.Date(string='Periodo pradžia', default=_default_period_start)
    period_end = fields.Date(string='Periodo pabaiga', default=_default_period_end)

    @api.multi
    def check_date_constraints(self):
        """
        Check various date constrains for the period
            -Both period fields must be filled
            -Period end must be later than start
        :return: None
        """
        self.ensure_one()
        if not self.period_end or not self.period_start:
            raise exceptions.ValidationError(_('Nenurodyta periodo pradžios ir/arba pabaigos data!'))

        period_start_dt = datetime.strptime(self.period_start, tools.DEFAULT_SERVER_DATE_FORMAT)
        period_end_dt = datetime.strptime(self.period_end, tools.DEFAULT_SERVER_DATE_FORMAT)

        if period_start_dt >= period_end_dt:
            raise exceptions.ValidationError(_('Periodo pabaigos data privalo būti vėlesnė už pradžios datą!'))

    @api.multi
    def prepare_model_domain(self):
        """
        Prepare materialized report domain based on period
        and the date field that corresponds to this model.
        Domain formation can be expanded
        :return: domain (list)
        """
        self.ensure_one()
        date_field = rt.MODEL_TO_DATE_MAPPING.get(self.model)
        if not date_field:
            raise exceptions.ValidationError(_('Nerasti susijusio modelio nustatymai!'))
        domain = [('{}'.format(date_field), '>=', self.period_start),
                  ('{}'.format(date_field), '<=', self.period_end)]
        return domain

    @api.multi
    def action_open_materialized_view(self, extra_identifier=None, skip_domain=False):
        """
        Method that returns the corresponding materialized view action.
        Domain for period limiting is added to the corresponding action.
        :param extra_identifier: Used if same model has different actions
        :param skip_domain: Identifies whether model domain forming should be skipped
        :return: action (dict)
        """
        self.ensure_one()
        if self.env['robo.report.job'].search_count(
                [('state', '=', 'in_progress'), ('job_type', '=', 'refresh'), ('refresh_model', '=', self.model)]):
            raise exceptions.UserError(
                _('Šiuo metu ataskaita yra perkraunama, pabandykite po kelių minučių.'))

        self.check_date_constraints()
        action_ext_id = rt.get_action(self.model, threaded=True, extra_identifier=extra_identifier)
        if not action_ext_id:
            raise exceptions.ValidationError(_('Nerasti susijusio modelio nustatymai!'))
        action_obj = self.env.ref(action_ext_id)
        action = action_obj.read()[0]

        # Prepare domain
        if not skip_domain:
            model_domain = self.prepare_model_domain()
            # Always write the domain to threaded action, it's always dynamic
            action['domain'] = model_domain

        # Pivot group-by is always empty
        new_context = {'pivot_row_groupby': []}

        # Get extra context if extra_identifier exists
        if extra_identifier:
            new_context.update(rt.get_extra_context(self.model, extra_identifier))
        # Get action context
        prev_context = action.get('context')
        if prev_context:
            # If action has context, parse it from the string value
            prev_context = ast.literal_eval(prev_context)
            new_context.update(prev_context)

        # Only add it here because previous context might have it as False
        new_context['clear_breadcrumbs'] = True
        action['context'] = new_context
        return action

    @api.multi
    def action_refresh_materialized_view(self):
        """
        Action that calls robo.report.job method to refresh the materialized view.
        Method executes the refreshing in separate threaded function
        :return: None
        """
        self.ensure_one()
        return self.env['robo.report.job'].refresh_materialized_view(self.model, self.name)

    @api.multi
    def button_action_open_materialized_view(self):
        """
        Separate method used for a button because when called from
        a form view, it fills default args with the context..
        :return: None
        """
        return self.action_open_materialized_view()


RoboMaterializedViewWizard()
