# -*- coding: utf-8 -*-
import threading
from datetime import datetime

from pytz import timezone

from odoo import models, api, fields, exceptions, _, tools
from odoo.addons.robo.wizard.robo_company_settings import get_all_values, get_mapped, ImportRecord, RoboImportError


class EDocumentImport(models.TransientModel):
    _name = 'e.document.import'

    file_to_import = fields.Binary(string='Document', required=True)
    file_name = fields.Char(string='Document name', readonly=True)
    auto_confirm = fields.Boolean(string='Automatically form the created documents', default=True)

    @api.multi
    def import_document(self):
        self.ensure_one()
        if not self.env.user.is_accountant():
            raise exceptions.ValidationError(_('You do not have sufficient rights to perform this import'))

    @api.model
    def find_employee(self, name=None, identification=None):
        """
        Finds employee by provided name and/or identification
        :param name: (str) Employee's name
        :param identification: (str) Employee's identification
        :return: (hr.employee) Employee
        """
        HrEmployee = self.env['hr.employee'].sudo()
        employee = HrEmployee
        if identification:
            employee = HrEmployee.search([('identification_id', '=', identification)])
        if not employee and name:
            employee = HrEmployee.search([('name', '=', name)])
        if not employee:
            raise exceptions.UserError(_('Could not find employee'))
        if len(employee) > 1:
            raise exceptions.UserError(_('Multiple employees found'))
        return employee

    @api.model
    def process_amount(self, amount):
        """
        Processes the amount and converts it to float
        :param amount: (str/int/long/float) Amount
        :return: (float) amount
        """
        if isinstance(amount, (str, unicode, int, long)):
            try:
                amount = float(amount)
            except ValueError:
                amount = 0.0
        if not isinstance(amount, float) or tools.float_compare(amount, 0.0, precision_digits=2) <= 0:
            raise exceptions.UserError(_('Incorrect payment amount specified'))
        return amount

    @api.multi
    def threaded_import_prep(self, action, imported_file, function):
        """
        Prepares system for threaded XLS data import,
        checks whether any job of the same type is running,
        creates related job record and starts the thread.
        :param action: System-like name of the action that is to-be executed (str)
        :param function: function that will be used to process the file (function)
        :param imported_file: Imported, to-process file (str)
        :return: None
        """

        if not imported_file:
            return

        now_dt = datetime.now(tz=timezone('Europe/Vilnius'))
        now_str = now_dt.strftime("%H:%M")
        if "20:20" < now_str < "20:40":
            raise exceptions.UserError(_("Can't import data between 20:20 and 20:40, please wait."))

        import_obj = self.env['robo.import.job']
        # Check whether there are any jobs of the same type that are being imported
        if import_obj.search_count([('state', '=', 'in_progress'), ('action', '=', action)]):
            raise exceptions.UserError(_('Report is being refreshed at the moment, please try again in a few minutes.'))

        vals = {
            'action': action,
            'execution_start_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            'state': 'in_progress',
            'imported_file': imported_file,
            'user_id': self.env.user.id,
        }
        # Create import job record
        import_job = import_obj.create(vals)
        self.env.cr.commit()

        # Start the thread
        threaded_calculation = threading.Thread(
            target=import_obj.execute_threaded_import,
            args=(self, import_job.id, function, imported_file)
        )
        threaded_calculation.start()

    @api.model
    def process_and_validate_import_data(self, record, **kwargs):
        return record.read()[0]

    @api.model
    def process_worksheet_data(self, rows, header_mapping, **kwargs):
        """ Processes worksheet data into a list of dicts (parsed objects) """
        header_mapped = list()
        errors_general = list()
        errors_system = list()
        parsed_rows = list()

        # Parse record data from workbook
        for i, row in enumerate(rows):
            try:
                values = get_all_values(row)
                if not header_mapped:
                    header_mapped = get_mapped(values, header_mapping)
                    continue
                if len(set(values)) == 1:
                    break
                record = ImportRecord(values, header_mapped)
                record = self.process_and_validate_import_data(record, **kwargs)
                parsed_rows.append(record)
            except (exceptions.UserError, exceptions.ValidationError) as exc:
                error = '{} '.format(exc.name) + _('line') + ' {}'.format(i + 1)
                errors_general.append(error)
            except Exception as exc:
                error_msg = '{} '.format(exc) + _('line') + ' {}'.format(i + 1)
                errors_system.append(error_msg)
        if errors_general:
            raise exceptions.UserError('\n'.join(errors_general))
        if errors_system:
            raise RoboImportError('\n'.join(errors_system))
        return parsed_rows
