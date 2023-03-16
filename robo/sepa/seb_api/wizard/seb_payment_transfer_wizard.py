# -*- encoding: utf-8 -*-
from odoo import fields, models, _, api
from odoo.addons.sepa import api_bank_integrations as abi


class SEBPaymentTransferWizard(models.TransientModel):

    _name = 'seb.payment.transfer.wizard'
    _description = """
        Wizard that is used to display responses after
        payment was initiated to SEB
        """

    bank_export_job_ids = fields.Many2many('bank.export.job', string='Lines')
    successfully_uploaded_batch = fields.Boolean(
        string='Successfully uploaded', compute='_compute_successfully_uploaded_batch')

    @api.multi
    def _compute_successfully_uploaded_batch(self):
        """
        Compute //
        Checks whether all transferred transactions
        were accepted, if they were, bool is ticked.
        :return: None
        """
        for rec in self:
            states = abi.ACCEPTED_STATES + ['waiting']
            rec.successfully_uploaded_batch = rec.bank_export_job_ids and all(
                x.export_state in states for x in rec.bank_export_job_ids
            )
