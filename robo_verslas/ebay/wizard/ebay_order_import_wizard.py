# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _, tools
from .. import ebay_tools as et
from datetime import datetime
import StringIO
import logging
import base64
import csv

_logger = logging.getLogger(__name__)


class EbayOrderImportWizard(models.TransientModel):

    _name = 'ebay.order.import.wizard'

    @api.model
    def default_get(self, field_list):
        """Default get for wizard parameters"""
        res = super(EbayOrderImportWizard, self).default_get(field_list)
        configuration = self.env['ebay.configuration'].search([], limit=1)
        res.update({
            'origin_country_id': configuration.default_origin_country_id.id,
        })
        return res

    file_data = fields.Binary(string='CSV file', required=True)
    file_name = fields.Char(string='CSV file name', size=128, required=False)
    origin_country_id = fields.Many2one(
        'res.country', string='Origin country',
    )
    update_present_data = fields.Boolean(
        string='Update present data',
        help='If checked, orders that are already present in the system will be updated with newly passed data',
    )

    @api.multi
    def button_data_import(self):
        """
        Method that is used to import Ebay CSV files,
        create systemic orders and corresponding invoices
        :return: None
        """
        self.ensure_one()

        # Dummy get of the configuration so it's constraints are checked
        self.env['ebay.configuration'].get_configuration()
        if not self.origin_country_id:
            raise exceptions.ValidationError(_('Origin country is not specified!'))

        # Check if there's any rules already present, and if not, raise the warning
        if not self.env['ebay.tax.rule'].search_count([]):
            raise exceptions.ValidationError(
                _('No eBay tax rules were found! Configure at least one rule to proceed')
            )

        # Try to parse the file
        correct_file = False
        try:
            string_io = StringIO.StringIO(base64.decodestring(self.file_data))
            csv_reader = csv.reader(string_io, delimiter=',', quotechar='"')
            # Loop through first three rows, and check whether any of them
            # has a matching header, since sometimes they contain gaps.
            for row in range(3):
                header = csv_reader.next()
                correct_file = header == et.EBAY_CSV_HEADERS
                if correct_file:
                    break
        except Exception as exc:
            _logger.info('Ebay: CSV Import failed: {}'.format(str(exc.args)))

        # Check whether file is correct and raise otherwise
        if not correct_file:
            raise exceptions.ValidationError(_('Incorrect file format'))

        EbayOrderImportJob = self.env['ebay.order.import.job'].sudo()
        # If file is correct create the job and process it

        active_jobs = EbayOrderImportJob.search_count([('execution_state', '=', 'in_progress')])
        if active_jobs:
            raise exceptions.ValidationError(
                _('There is another import that is already being processed in the background! '
                  'If you think that it is stuck, you can manually reset the state')
            )
        # Create import job and process it
        import_job = EbayOrderImportJob.create({
            'file_data': self.file_data,
            'file_name': self.file_name,
            'origin_country_id': self.origin_country_id.id,
            'execution_start_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
        })
        self.env.cr.commit()
        import_job.with_delay(channel='root.single_1').preprocess_import_job(
            update_present_data=self.update_present_data,
        )

