# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _


class EnableBankingConfiguration(models.Model):
    _name = 'enable.banking.configuration'
    _description = 'Model that stores various EnableBanking API settings'

    # Main configuration fields
    application_key = fields.Char(string='Application identifier')
    api_state = fields.Selection([
        ('not_initiated', 'API is disabled'),
        ('failed', 'Failed to configure the API'),
        ('partially_working', 'Some of the connectors are expired/failed'),
        ('working', 'API is working'),
    ], string='State', compute='_compute_api_state')
    # Related bank connectors
    connector_ids = fields.One2many(
        'enable.banking.connector',
        'configuration_id', string='Bank connectors',
    )

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    def _compute_api_state(self):
        """Compute API state based on connectors state"""
        for rec in self:
            api_state = 'not_initiated'
            if rec.connector_ids:
                # Get all of the different states in a set
                states = set(rec.connector_ids.mapped('api_state'))
                if 'failed' in states or 'expired' in states:
                    # If failed and expired is in states, check whether there's
                    # any working connector, if not, whole configuration is failed
                    # otherwise it's partially working
                    api_state = 'partially_working' if 'working' in states else 'failed'
                elif 'working' in states:
                    api_state = 'working'
            rec.api_state = api_state

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def action_open_bank_connectors(self):
        """
        Returns action that opens bank connector tree view.
        Filters out inactive connectors
        :return: JS action (dict)
        """
        action = self.env.ref('sepa.action_open_enable_banking_connector_manager').read()[0]
        # Updated action domain to exclude inactive records
        # (Not done via use of context, since it's passed into children records as well)
        return action

    @api.multi
    def action_open_bank_connectors_system(self):
        """
        Returns action that opens bank connector tree view.
        Does not filter domain, button only visible to Admin.
        :return: JS action (dict)
        """
        action = self.env.ref('sepa.action_open_enable_banking_connector').read()[0]
        return action

    @api.multi
    def check_configuration(self):
        """
        Check whether Enable banking integration is configured
        :return: True/False (bool)
        """
        self.ensure_zero_or_one()
        return self.api_state != 'not_initiated' and self.application_key

    @api.multi
    def initiate_settings(self):
        """
        Initiate Enable banking settings record and all of the connectors.
        If settings record already exists, return it.
        :return: enable.banking.configuration (record)
        """
        e_banking_settings = self.search([])
        if not e_banking_settings:
            # Call the method to gather connector data and create the settings
            connectors = self.env['enable.banking.connector'].prepare_connector_creation_data()
            e_banking_settings = self.create({'connector_ids': connectors, })
            e_banking_settings.conntector_ids.relate_to_corresponding_banks()
        return e_banking_settings

    @api.multi
    def update_connectors(self):
        """
        Method that is used to update connector's data.
        Fetches any new connectors that are added to Enable banking API
        and creates corresponding records in the system.
        Only access-able by admin user
        :return: None
        """
        if self.env.user.has_group('base.group_system'):
            # Call the method to gather connector data and create the settings
            connectors = self.env['enable.banking.connector'].prepare_connector_creation_data()
            if connectors:
                self.write({'connector_ids': connectors, })
            self.connector_ids.relate_to_corresponding_banks()

    @api.multi
    def name_get(self):
        """Returns static string as name get for all of the records"""
        return [(x.id, _('Enable banking configuration')) for x in self]

    # CRUD ------------------------------------------------------------------------------------------------------------

    @api.multi
    def create(self, vals):
        """
        Ensure that only one Enable banking configuration exists in the system
        :param vals: record values (dict)
        :return: super of create method
        """
        if self.search_count([]):
            raise exceptions.ValidationError(_('You cannot create several Enable banking configuration records!'))
        return super(EnableBankingConfiguration, self).create(vals)
