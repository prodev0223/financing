# -*- encoding: utf-8 -*-
from odoo import fields, models, _, api
from odoo.addons.sepa import api_bank_integrations as abi


class PayseraPaymentTransferWizard(models.TransientModel):
    """
    Wizard that is used to display responses after
    payment was initiated to Paysera. If signing is
    enabled in company settings, user is allowed
    to sign specific transfers in the bank
    """
    _name = 'paysera.payment.transfer.wizard'

    bank_export_job_ids = fields.Many2many('bank.export.job', string='Lines')
    successfully_uploaded_batch = fields.Boolean(
        string='Successfully uploaded', compute='_compute_successfully_uploaded_batch')
    allow_signing = fields.Boolean(string='Allow eSigning', compute='_compute_allow_signing')

    @api.multi
    def _compute_successfully_uploaded_batch(self):
        """
        Compute //
        Checks whether all transferred transactions
        were accepted, if they were, bool is ticked.
        :return: None
        """
        for rec in self:
            rec.successfully_uploaded_batch = rec.bank_export_job_ids and all(
                x.export_state in abi.NON_SIGNED_ACCEPTED_STATES for x in rec.bank_export_job_ids)

    @api.multi
    def _compute_allow_signing(self):
        """
        Compute //
        Checks whether signing of the transactions
        is available or not.
        :return: None
        """
        configuration = self.env['paysera.api.base'].get_configuration()
        for rec in self:
            rec.allow_signing = configuration.sudo().allow_external_signing


PayseraPaymentTransferWizard()
