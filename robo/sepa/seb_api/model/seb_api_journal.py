# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _
from ... import api_bank_integrations as abi


class SEBAPIJournal(models.Model):
    _name = 'seb.api.journal'
    _description = '''Intermediate model that holds SEB journals. 
    Journals can be activated/deactivated just for the integration'''

    @api.model
    def _get_journal_id_domain(self):
        """Default domain to only select SEB banks"""
        return [('bank_id.bic', '=', abi.SEB_BANK)]

    seb_conf_id = fields.Many2one('seb.configuration')
    journal_id = fields.Many2one('account.journal', string='Journal', domain=_get_journal_id_domain)
    retry_eod_transaction_fetch = fields.Boolean(string='Repeat EOD fetch')
    bank_account = fields.Char(string='Bank account', related='journal_id.bank_acc_number')
    activated = fields.Boolean(string='Activated', inverse='_set_activated', default=True)
    error_message = fields.Text(string='Message')
    state = fields.Selection([
        ('non_configured', 'Not-configured'),
        ('failed', 'Configuration error'),
        ('working', 'Configured')],
        string='Journal state', default='non_configured', inverse='_set_state'
    )

    @api.multi
    def _set_activated(self):
        """
        On deactivation SEB journal state is reset
        :return: None
        """
        for rec in self:
            if not rec.activated:
                rec.state = 'non_configured'

    @api.multi
    def _set_state(self):
        """
        On state change, manually recompute related journal integration status
        :return: None
        """
        for rec in self:
            # Clear the error message
            if rec.state == 'working':
                rec.error_message = False
            rec.journal_id._compute_api_integrated_bank()

    @api.multi
    @api.constrains('journal_id')
    def _check_journal_id(self):
        """Ensure that journal is SEB journal"""
        for rec in self:
            if rec.journal_id.bank_id.bic != abi.SEB_BANK:
                raise exceptions.ValidationError(_('Passed journal is not of SEB type'))
            if self.search_count([('journal_id', '=', rec.journal_id.id)]) > 1:
                raise exceptions.ValidationError(_('You cannot have two SEB accounts with the same journal'))

    @api.multi
    def button_toggle_activated(self):
        """
        Method to either deactivate or activate the journal
        :return: None
        """
        for rec in self:
            rec.activated = not rec.activated
