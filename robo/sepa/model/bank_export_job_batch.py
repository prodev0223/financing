# -*- coding: utf-8 -*-
from odoo.addons.sepa import api_bank_integrations as abi
from odoo import models, fields, api, exceptions, tools, _
from datetime import datetime
import base64


class BankExportJobBatch(models.Model):
    _name = 'bank.export.job.batch'

    # Information fields
    date_exported = fields.Datetime(string='Export date')
    no_response_upload_count = fields.Integer(string='No response upload count')
    batch_export_type = fields.Selection(abi.BANK_EXPORT_TYPES, string='Export type')

    # Related exports and file
    bank_export_job_ids = fields.One2many('bank.export.job', 'export_batch_id')
    xml_file_data = fields.Binary(string='XML Data')
    xml_file_name = fields.Char(string='XML File name')
    group_transfer = fields.Boolean(string='Indicates that batch is a group transfer')

    # eInvoicing fields
    request_xml_file_data = fields.Binary(string='XML Data')
    request_xml_file_name = fields.Char(string='XML File name')
    file_id_number = fields.Char(string='File ID')

    # Constraints ----------------------------------------------------------------------------------------------------

    @api.multi
    @api.constrains('bank_export_job_ids')
    def _check_bank_export_job_ids(self):
        """Ensures batch journal, export type and related export job integrity"""
        for rec in self:
            if len(rec.mapped('bank_export_job_ids.journal_id')) > 1:
                raise exceptions.ValidationError(
                    _('You cannot register export job batch that contains different journals')
                )
            if len(set(rec.mapped('bank_export_job_ids.export_data_type'))) > 1:
                raise exceptions.ValidationError(
                    _('You cannot register export job batch that contains different export types')
                )
            if not rec.bank_export_job_ids:
                raise exceptions.ValidationError(
                    _('You cannot register export job batch without any export jobs')
                )

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def re_export_data(self):
        """Re-exports current XML data file without creating new export jobs"""
        self.ensure_one()
        if self.bank_export_job_ids:
            # Constraint ensures that there's only one shared journal/type between exports
            related_journal = self.bank_export_job_ids[0].journal_id
            export_data_type = self.bank_export_job_ids[0].export_data_type
            # Only re-export SEPA XML integration batches
            integration_type = abi.INTEGRATION_TYPES.get(related_journal.api_bank_type)
            if integration_type != 'sepa_xml':
                return

            # Re-export the data based on type
            if export_data_type == 'e_invoice':
                export_data = {
                    'payload_xml': self.xml_file_data,
                    'payload_filename': self.xml_file_name,
                    'req_xml': self.request_xml_file_data,
                    'req_filename': self.request_xml_file_name,
                }
                # Re-upload eInvoice batch file
                self.env['swed.bank.api.import.invoice'].upload_e_invoice(
                    invoice_data=export_data)
            else:
                model_name, method_name = self.env['api.bank.integrations'].get_bank_method(
                    related_journal, m_type='push_transactions',
                )
                method_instance = getattr(self.env[model_name], method_name)
                # Gather exported data
                xml_stream = base64.b64decode(self.xml_file_data)
                export_data = {
                    'bank_exports': self.bank_export_job_ids,
                    'attachment': self.xml_file_data,
                    'xml_stream': xml_stream,
                }
                method_instance(export_data)
            # Update date exported
            self.write({
                'date_exported': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            })

    @api.model
    def cron_export_job_batch_cleanup(self):
        """
        Unlinks the batches that are successfully export or
        batches that are over repeat counter.
        :return: None
        """
        try:
            re_count = int(self.sudo().env['ir.config_parameter'].get_param(
                'pending_bank_export_resend_count', default=2,
            ))
        except (ValueError, TypeError):
            re_count = 2
        export_batches = self.search([
            '|', ('no_response_upload_count', '>=', re_count),
            ('bank_export_job_ids.export_state', '!=', 'waiting'),
        ])
        export_batches.unlink()
