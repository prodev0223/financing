# -*- coding: utf-8 -*-
from odoo import models, exceptions, api, _


class BraintreeConfiguration(models.Model):
    _name = 'braintree.configuration'
    _description = 'Intermediate model to display information about Braintree configuration'

    @api.multi
    def get_configuration(self):
        """Creates Braintree configuration record if it does not exist"""
        braintree_configuration = self.search([])
        if not braintree_configuration:
            braintree_configuration = self.create({})
        return braintree_configuration

    @api.multi
    def action_open_api_gateways(self):
        """
        Returns action that opens API gateway tree view.
        :return: JS action (dict)
        """
        self.ensure_one()
        action = self.env.ref('sepa.action_open_braintree_gateway').read()[0]
        return action

    @api.multi
    def action_open_merchant_accounts(self):
        """
        Returns action that opens merchant account tree view.
        :return: JS action (dict)
        """
        self.ensure_one()
        action = self.env.ref('sepa.braintree_merchant_account_action').read()[0]
        return action

    @api.multi
    def action_open_transactions(self):
        """
        Returns action that opens transaction tree view.
        :return: JS action (dict)
        """
        self.ensure_one()
        action = self.env.ref('sepa.braintree_transaction_action').read()[0]
        return action

    @api.multi
    def action_open_customers(self):
        """
        Returns action that opens customer tree view.
        :return: JS action (dict)
        """
        self.ensure_one()
        action = self.env.ref('sepa.braintree_customer_action').read()[0]
        return action

    @api.multi
    def create(self, vals):
        """
        Ensure that only one Braintree configuration exists in the system
        :param vals: record values (dict)
        :return: super of create method
        """
        if self.search_count([]):
            raise exceptions.ValidationError(_('You cannot create several Braintree configuration records!'))
        return super(BraintreeConfiguration, self).create(vals)

    @api.multi
    def name_get(self):
        """Returns static string as name get for all of the records"""
        return [(x.id, _('Braintree configuration')) for x in self]
