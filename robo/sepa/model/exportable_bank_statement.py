# -*- coding: utf-8 -*-
from odoo import models, api, fields, _
from odoo.addons.sepa import api_bank_integrations as abi


class ExportableBankStatement(models.AbstractModel):

    """
    Abstract model that is used for bank export functionality that is shared
    between AccountBankStatement and later inherited by FrontBankStatement
    since the two models are not inheriting one another
    """

    _name = 'exportable.bank.statement'

    # Bank export fields
    api_integrated_journal = fields.Boolean(compute='_compute_api_integrated_data')
    api_full_integration = fields.Boolean(compute='_compute_api_integrated_data')
    api_sepa_integration = fields.Boolean(compute='_compute_api_integrated_data')

    bank_export_state = fields.Selection(
        abi.BANK_EXPORT_STATES, string='Eksportavimo būsena', compute='_compute_bank_export_state')
    bank_export_state_html = fields.Text(compute='_compute_bank_export_state_html')
    bank_export_state_alert_html = fields.Html(compute='_compute_bank_export_state_html')
    show_bank_export_signing_alert = fields.Boolean(compute='_compute_show_bank_export_signing_alert')

    @api.multi
    @api.depends('bank_export_state')
    def _compute_bank_export_state_html(self):
        """
        Compute //
        Make html badge based on bank export state
        Which visually displays it.
        :return: None
        """
        for rec in self:
            rec.bank_export_state_html = \
                self.env['api.bank.integrations'].get_bank_export_state_html_data(
                    model=self._name,  # No singleton issue
                    state=rec.bank_export_state,
                )
            rec.bank_export_state_alert_html = \
                self.env['api.bank.integrations'].get_bank_export_state_alert_html_data(
                    state=rec.bank_export_state,
                )

    @api.multi
    @api.depends('line_ids.bank_export_state')
    def _compute_bank_export_state(self):
        """
        Compute //
        Determine the bank_export_state of the parent
        statement based on the related lines
        :return: None
        """
        for rec in self:
            if rec.line_ids and all(x.bank_export_state == 'accepted' for x in rec.line_ids):
                rec.bank_export_state = 'accepted'
            elif rec.line_ids and all(x.bank_export_state == 'processed' for x in rec.line_ids):
                rec.bank_export_state = 'processed'
            elif any(x.bank_export_state == 'rejected' for x in rec.line_ids):
                rec.bank_export_state = 'rejected'
            elif any(x.bank_export_state == 'waiting' for x in rec.line_ids):
                rec.bank_export_state = 'waiting'
            else:
                rec.bank_export_state = 'no_action'

    @api.multi
    @api.depends('journal_id.api_integrated_journal')
    def _compute_api_integrated_data(self):
        """
        Compute //
        Determine whether the journal that the statements
        are being exported to is API integrated,
        whether the integration is non-partial
        and whether integration is of SEPA XML type
        :return: None
        """
        for rec in self:
            rec.api_integrated_journal = rec.journal_id.api_integrated_journal
            rec.api_full_integration = rec.journal_id.api_full_integration
            rec.api_sepa_integration = abi.INTEGRATION_TYPES.get(rec.journal_id.api_bank_type) == 'sepa_xml'

    @api.multi
    def _compute_show_bank_export_signing_alert(self):
        """
        Compute //
        Check whether there are any lines that can be signed
        that are contained in this statement
        :return: None
        """
        for rec in self:
            rec.show_bank_export_signing_alert = any(x.bank_exports_to_sign for x in rec.line_ids)
