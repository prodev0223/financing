# -*- encoding: utf-8 -*-
from odoo import models, fields
from odoo.addons.queue_job.job import job


class AccountInvoice(models.Model):
    """
    Robo API extension to account.invoice
    """
    _inherit = 'account.invoice'

    imported_api = fields.Boolean(string='API', readonly=True, groups='base.group_system', copy=False)

    @job
    def queue_job_fetch_partner_data(self):
        """
        A temporary queue job to fetch partner data for API imported - WooCommerce - invoices
        :return: None
        """
        self.ensure_one()
        if not self.imported_api:
            return
        self.partner_id.vz_read()
        self.partner_data_force()


AccountInvoice()
