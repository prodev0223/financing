# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, fields, api, exceptions, _, tools
from dateutil.relativedelta import relativedelta
from ... import api_bank_integrations as abi
from .. import seb_api_tools as sb
from datetime import datetime


class SEBConfiguration(models.Model):
    _name = 'seb.configuration'
    _inherit = ['mail.thread']
    _description = 'SEB API Configuration settings'

    organisation_id = fields.Char(string='SEB organisation ID (OrgID)', compute='_compute_organisation_id')
    api_state = fields.Selection([
        ('not_initiated', 'API is disabled'),
        ('failed', 'Failed to configure the API'),
        ('working', 'API is working'),
        ('awaiting_confirmation', 'Waiting for API confirmation'),
    ], string='State', default='not_initiated')

    system_notification = fields.Text(string='API error message (ADMIN)')
    initially_authenticated = fields.Boolean(string='Indicates whether user tested the connection')
    seb_journal_ids = fields.One2many('seb.api.journal', 'seb_conf_id', string='SEB journals')

    # External signing fields
    allow_external_signing = fields.Boolean(
        string='Enable transaction signing', groups='base.group_system', inverse='_set_allow_external_signing')
    external_signing_daily_limit = fields.Float(
        string='Daily transaction signing limit', groups='base.group_system', inverse='_set_allow_external_signing')
    external_signing_daily_limit_residual = fields.Float(
        string='Daily transaction signing limit residual', groups='base.group_system')

    # Enabled endpoint groups
    intra_day_endpoint = fields.Boolean(string='Real-time balance')
    statement_endpoint = fields.Boolean(string='Bank statements')
    payment_init_endpoint = fields.Boolean(string='Payment initiation', default=True)

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    def _compute_organisation_id(self):
        """Compute organisation ID based on company registry"""
        registry = self.sudo().env.user.company_id.company_registry
        for rec in self:
            rec.organisation_id = registry

    @api.multi
    def _set_allow_external_signing(self):
        """
        Inverse //
        Set external signing daily limit and residual
        based on whether external signing was enabled
        :return: None
        """
        for rec in self:
            if rec.allow_external_signing and tools.float_is_zero(
                    rec.external_signing_daily_limit, precision_digits=2):
                raise exceptions.ValidationError(
                    _('It is mandatory to set a daily amount limit if you want to enable transaction signing'))
            current_residual = rec.external_signing_daily_limit
            if not tools.float_is_zero(rec.external_signing_daily_limit_residual, precision_digits=2):
                current_residual = min([rec.external_signing_daily_limit_residual, rec.external_signing_daily_limit])
            rec.external_signing_daily_limit_residual = current_residual

    # Main Methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def check_configuration(self):
        """
        Check whether SEB integration is configured
        :return: True/False
        """
        self.ensure_zero_or_one()
        return self.api_state == 'working' and self.organisation_id and self.initially_authenticated

    @api.multi
    def renew_journal_data(self):
        """Recreates SEB API journal records from systemic SEB journals"""
        self.ensure_one()

        # Search for SEB journals
        acc_journals = self.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('bank_id.bic', '=', abi.SEB_BANK),
            ('gateway_deactivated', '=', False),
        ])
        for num, acc_journal in enumerate(acc_journals):
            # Check if current SEB journal exists in the journal list
            if not self.env['seb.api.journal'].search_count([('journal_id', '=', acc_journal.id)]):
                # Create the journal if it does not exist
                journal_values = {
                    'seb_conf_id': self.id,
                    'journal_id': acc_journal.id,
                }
                self.env['seb.api.journal'].create(journal_values)

        # Recompute API integrated bank values for every SEB journal
        acc_journals._compute_api_integrated_bank()

    @api.multi
    def initiate_test_api(self):
        """
        Method used to test SEB API by calling end balance fetching endpoint.
        If response is successful - API is ready and working
        :return: None
        """
        self.ensure_one()

        # Check whether there are any seb journals
        seb_journals = self.seb_journal_ids.filtered(lambda x: x.activated)
        if not seb_journals:
            raise exceptions.ValidationError(
                _('No SEB journal/bank account was found in the integration setup. '
                  'Configure at least one account if you want to proceed')
            )

        # Action endpoints to check, mapped with corresponding fields to set
        action_mapping = {
            'get_balance': 'intra_day_endpoint',
            'get_period_statements': 'statement_endpoint',
        }
        # Loop through journals and try to call balance endpoint
        system_notifications = str()
        endpoint_results_by_journal = {}
        working_mapping = {}
        for action, field in action_mapping.items():
            # Loop through endpoints
            endpoint_results_by_journal.setdefault(field, {})
            for seb_journal in seb_journals:
                endpoint_results_by_journal[field].setdefault(seb_journal, {})
                working_mapping.setdefault(seb_journal, False)
                # Get the IBAN of the journal
                j_iban = seb_journal.journal_id.bank_acc_number
                extra_data = {'object_id': j_iban, }

                # If action is get period statements, update the extra data dict
                if action == 'get_period_statements':
                    # Date to is two days from now, due to EOD generation timings
                    date_to = (datetime.utcnow() - relativedelta(days=2)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    date_from = (datetime.utcnow() - relativedelta(days=3)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    extra_data.update({
                        'limit': sb.API_RECORD_LIMIT,
                        'd_from': date_from,
                        'd_to': date_to,
                    })
                # Call the endpoint
                successful_call, response_data = self.env['seb.api.base'].call(
                    action=action,
                    extra_data=extra_data,
                    manual_action=True,
                )
                # Get the error messages
                error_message = response_data.get('status_description', str())
                sys_error = response_data.get('system_notification', str())

                # If at least one endpoint for current journal worked - it's working
                if not working_mapping[seb_journal] and successful_call:
                    working_mapping[seb_journal] = True

                # If code is not in forbidden codes, simply raise
                if not successful_call and response_data['status_code'] not in sb.FORBIDDEN:
                    # TODO: Improve this part, maybe gather errors per endpoint and post to journal
                    raise exceptions.ValidationError(
                        _('Failed to authenticate SEB API, error message - {}').format(error_message)
                    )
                # Collect the results
                endpoint_results_by_journal[field][seb_journal] = {
                    'state': 'working' if successful_call else 'failed',
                    'error_message': response_data.get('status_description', str()),
                    'system_error': response_data.get('system_notification', str()),
                    'status_code': response_data['status_code'],
                }
                if sys_error:
                    system_notifications += 'IBAN - {}\nEndpoint - {}.\nSystem error - {}\n\n'.format(
                        j_iban, action, sys_error
                    )

        # Activate the endpoints and journals
        status_codes = []
        for field, by_journal in endpoint_results_by_journal.items():
            endpoint_state = False
            for journal_data in by_journal.values():
                if journal_data['state'] == 'working':
                    endpoint_state = True
                status_codes.append(journal_data['status_code'])
            self.write({field: endpoint_state})

        # Update the states
        for journal, working in working_mapping.items():
            journal.write({'state': 'working' if working else 'failed'})

        # Check whether there's any working endpoint
        working_endpoints = self.statement_endpoint or self.intra_day_endpoint

        # Determine the global state
        global_state = 'failed'
        if working_endpoints:
            global_state = 'working'
        elif all(x in sb.FORBIDDEN for x in status_codes):
            global_state = 'awaiting_confirmation'

        self.write({
            'api_state': global_state,
            'system_notification': system_notifications,
            'initially_authenticated': working_endpoints,
        })

    # Auxiliary Methods -----------------------------------------------------------------------------------------------

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(x.id, _('SEB configuration')) for x in self]

    @api.multi
    def initiate_settings(self):
        """
        Initiate SEB settings record.
        If settings record exists, return it.
        :return: seb.settings record
        """
        settings = self.search([])
        if not settings:
            settings = self.create({})
        return settings

    @api.multi
    def create(self, vals):
        """
        Create method override, if settings record already exists,
        do not allow to create another instance
        :param vals: record values
        :return: super of create method
        """
        if self.search_count([]):
            raise exceptions.ValidationError(_('You cannot create several SEB configuration records!'))
        return super(SEBConfiguration, self).create(vals)

    @api.multi
    def get_related_journals(self, include_error=False):
        """
        Returns (SEB) account journals from configuration
        that are activated
        :return: account.journal recordset
        """
        self.ensure_one()
        if not include_error:
            # Prevent double filtering
            return self.seb_journal_ids.filtered(
                lambda x: x.activated and x.state == 'working').mapped('journal_id')
        return self.seb_journal_ids.filtered(lambda x: x.activated).mapped('journal_id')

    # Cron-jobs -------------------------------------------------------------------------------------------------------

    @api.model
    def cron_clear_external_signing_daily_limit_residual(self):
        """
        Cron-job //
        Method that is used to clear external signing daily limit residual
        amount -- called each night
        :return: None
        """
        configuration = self.search([], limit=1)
        if not configuration.allow_external_signing:
            return

        date_now_dt = datetime.utcnow()
        latest_signed_export = self.env['bank.export.job'].search(
            [('journal_id.bank_id.bic', '=', abi.SEB_BANK), ('e_signed_export', '=', True)],
            order='date_signed desc', limit=1)

        residual_reset = configuration.external_signing_daily_limit
        if not latest_signed_export:
            configuration.write({'external_signing_daily_limit_residual': residual_reset})
        else:
            last_sign_date_dt = datetime.strptime(
                latest_signed_export.date_signed, tools.DEFAULT_SERVER_DATETIME_FORMAT)

            diff = date_now_dt - last_sign_date_dt
            # If latest update was done less than two hours ago we only write half of residual
            # P3:DivOK
            if diff.total_seconds() / 3600.0 < 2:
                residual_reset = residual_reset / 2

            configuration.write({'external_signing_daily_limit_residual': residual_reset})
