# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _
from dateutil.relativedelta import relativedelta
from datetime import datetime


class NsoftImportWizard(models.TransientModel):

    @api.model
    def _date_from_default(self):
        return datetime.now() - relativedelta(months=1)

    @api.model
    def _date_to_default(self):
        return datetime.now()

    _name = 'nsoft.import.wizard'

    use_date = fields.Boolean(string='Leisti naudoti pasirinktas datas', default=False)
    date_from = fields.Datetime(string='Duomenys nuo', default=_date_from_default)
    date_to = fields.Datetime(string='Duomenys iki', default=_date_to_default)
    import_type = fields.Selection(
        [('invoices', 'Invoices'), ('sales', 'Sales'),
         ('cash_operations', 'Cash operations')],
        string='Import type', default='sales',
    )

    @api.multi
    def button_get_data(self):
        """
        Fetch data for nsoft invoice and nsoft.sale.line from external database,
        create records and proceed with account invoice creation
        :return: None if done by cron_job and action if done by hand
        """
        self.ensure_one()
        if not self.import_type:
            raise exceptions.ValidationError(_('No import type is selected'))

        # Ref base objects and init the cursor
        NsoftImportBase = self.env['nsoft.import.base'].sudo()
        sync_date = self.env.user.company_id.last_nsoft_db_sync
        cursor = NsoftImportBase.get_external_cursor()

        # Check if connection was made
        if not cursor:
            raise exceptions.ValidationError(_('Klaida jungiantis prie išorinės duomenų bazės'))

        date_from, date_to = sync_date, None
        if self.use_date:
            # Validate base date constraints
            if not self.date_from:
                raise exceptions.UserError(_('Įveskite datą nuo!'))

            if self.date_to:
                if self.date_to < self.date_from:
                    raise exceptions.UserError(_('Data nuo turi būti ankstesnė už datą iki'))

            # Assign the dates
            date_from, date_to = self.date_from, self.date_to

        # Call the endpoints based on the import type
        if self.import_type == 'invoices':
            NsoftImportBase.fetch_invoices(cursor, date_from, date_to)
        elif self.import_type == 'sales':
            NsoftImportBase.fetch_sale_lines(cursor, date_from, date_to)
        else:
            NsoftImportBase.fetch_cash_operation_data(cursor, date_from, date_to)
