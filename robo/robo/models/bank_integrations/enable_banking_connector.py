# -*- coding: utf-8 -*-
from odoo import models, api


class EnableBankingConnector(models.Model):
    _inherit = 'enable.banking.connector'

    @api.multi
    def post_custom_message(self, post_data):
        """
        Extend custom message posting by sending a direct message
        (as well as comment in the record) to the partners.
        :return: None
        """
        self.ensure_one()
        super(EnableBankingConnector, self).post_custom_message(post_data)
        post_data.update({
            'priority': 'high',
            'front_message': True,
            'rec_model': 'enable.banking.connector',
            'rec_id': self.id,
            'view_id': self.env.ref('sepa.form_enable_banking_connector').id,
        })
        self.robo_message_post(**post_data)

    # CRUD ------------------------------------------------------------------------------------------------------------

    @api.multi
    def read(self, fields=None, load='_classic_read'):
        """Override read by including inactive records for specific action"""
        record_set = self
        # In some cases context gets lost, thus if we get specific action
        # inside of the read we force active test = False.
        actions = []
        connector_action = self.env.ref(
            'sepa.action_open_enable_banking_connector', raise_if_not_found=False)
        connector_manager_action = self.env.ref(
            'sepa.action_open_enable_banking_connector_manager', raise_if_not_found=False)
        comp_settings_action = self.env.ref(
            'robo.action_robo_company_settings', raise_if_not_found=False)

        # Append all of the actions
        if connector_action:
            actions.append(connector_action.id)
        if connector_manager_action:
            actions.append(connector_manager_action.id)
        if comp_settings_action:
            actions.append(comp_settings_action.id)
        # Check whether active test context should be passed or not
        if self._context.get('robo_front') or actions and self._context.get('params', {}).get('action') in actions:
            record_set = record_set.with_context(active_test=False)
        return super(EnableBankingConnector, record_set).read(fields=fields, load=load)
