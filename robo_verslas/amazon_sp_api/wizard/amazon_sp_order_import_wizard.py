# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _, tools
from .. import amazon_sp_api_tools as at
from datetime import datetime
import StringIO
import logging
import base64
import csv

_logger = logging.getLogger(__name__)


class AmazonSPOrderImportWizard(models.TransientModel):

    _name = 'amazon.sp.order.import.wizard'

    file_data = fields.Binary(string='CSV file', required=True)
    file_name = fields.Char(string='CSV file name', size=128, required=False)

    @api.multi
    def button_data_import(self):
        """Imports Amazon CSV data and corrects current invoices"""
        self.ensure_one()

        AmazonSpAPIBase = self.env['amazon.sp.api.base'].sudo()
        configuration = AmazonSpAPIBase.get_configuration()
        if not configuration:
            return

        # Ensure that operation would only be run if individual invoice option is selected
        if not configuration.create_individual_order_invoices:
            raise exceptions.ValidationError(
                _('Operation can only be executed if individual invoice option is selected in Amazon settings')
            )

        # Try to parse the file
        correct_file = False
        try:
            string_io = StringIO.StringIO(base64.decodestring(self.file_data))
            csv_reader = csv.reader(string_io, delimiter=',', quotechar='"')
            header = csv_reader.next()
            correct_file = header == at.CSV_IMPORT_HEADERS
        except Exception as exc:
            _logger.info('Amazon SP-API: CSV Import failed: {}'.format(str(exc.args)))

        # Check whether file is correct and raise otherwise
        if not correct_file:
            raise exceptions.ValidationError(_('Incorrect file format'))

        AmazonSPOrderImportJob = self.env['amazon.sp.order.import.job'].sudo()
        # If file is correct create the job and process it

        active_jobs = AmazonSPOrderImportJob.search_count([('execution_state', '=', 'in_progress')])
        if active_jobs:
            raise exceptions.ValidationError(
                _('There is another import that is already being processed in the background! '
                  'If you think that it is stuck, you can manually reset the state')
            )
        # Create import job and process it
        import_job = AmazonSPOrderImportJob.create({
            'file_data': self.file_data,
            'file_name': self.file_name,
            'execution_start_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
        })
        import_job.with_delay(channel='root.single_1').process_import_job()

