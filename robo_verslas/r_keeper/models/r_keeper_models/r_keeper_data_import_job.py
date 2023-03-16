# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools, exceptions, _
from datetime import datetime
from odoo.api import Environment
import threading
import base64
import odoo


class RKeeperImportJob(models.Model):
    _name = 'r.keeper.data.import.job'
    _order = 'create_date desc'
    _description = '''
    Model that stores threaded XML/XLS data
    import execution results and files.
    '''

    imported_api = fields.Boolean(string='Importuotas per API')
    execution_start_date = fields.Datetime(string='Vykdymo pradžia')
    execution_end_date = fields.Datetime(string='Vykdymo pabaiga')
    state = fields.Selection(
        [('in_progress', 'Vykdoma'),
         ('finished', 'Sėkmingai įvykdyta'),
         ('failed', 'Vykdymas nepavyko'),
         ('no_action', 'Nevykdyta')], string='Būsena',
        default='no_action'
    )
    fail_message = fields.Char(string='Klaidos pranešimas')

    # File information
    imported_file_name = fields.Char(string='Importuoto failo pavadinimas')
    imported_file = fields.Binary(string='Importuotas failas', attachment=True, readonly=True)
    file_type = fields.Selection(
        [('sale_xml', 'Pardavimų XML'),
         ('payment_type_xls', 'Pardavimo tipų XLS')],
        string='Failo tipas', default='sale_xml'
    )

    # XML Importers ---------------------------------------------------------------------------------------------------

    @api.multi
    def parse_xml_file_prep(self, threaded=False):
        """
        Prepares the parsing of XML file contained
        on passed data import job record.
        :param threaded: Indicates whether parsing
        should be executed in threaded mode or not
        :return: None
        """
        self.ensure_one()

        # rKeeper ext IDs are composed of date and restaurant code, and, if data is exported for the period
        # instead of a single day, ext ID only contains the first day of the period, thus it will always lead
        # to overlaps that we cannot differentiate. Only differentiate-able criteria - period files have a dash,
        # thus if we encounter a file with a dash, we skip the parsing altogether.
        f_name = self.imported_file_name
        if f_name and len(f_name.split('-')) > 1:
            # Update the state of the job if it's not marked as failed
            if self.state != 'failed':
                self.write({'state': 'failed', })
            return

        if self.file_type != 'sale_xml':
            raise exceptions.ValidationError(_('Paduotas ne pardavimų XML failas'))

        if threaded:
            threaded_calculation = threading.Thread(
                target=self.parse_xml_file_threaded, args=(self.id, ))
            threaded_calculation.start()
        else:
            self.parse_xml_file()

    @api.model
    def parse_xml_file_threaded(self, job_id):
        """
        Intermediate method that calls parse_xml_file in a threaded mode
        :param job_id: r.keeper.data.import.job ID
        :return: None
        """
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, odoo.SUPERUSER_ID, {'lang': 'lt_LT'})
            import_job = env['r.keeper.data.import.job'].browse(job_id)
            # Context is lost on new thread, thus we pass it like this
            import_job.with_context(
                force_update_amounts=self._context.get('force_update_amounts')
            ).parse_xml_file()
            new_cr.close()

    @api.multi
    def parse_xml_file(self):
        """
        Method that is to parse XML file and create related records.
        State and message of the execution is stored in the current record.
        Can be called from the thread
        :return: None
        """
        self.ensure_one()
        file_data = base64.decodestring(self.imported_file)
        try:
            # Parse the files
            data = self.env['r.keeper.data.import'].parse_xml_file(file_data)
            self.env['r.keeper.data.import'].create_records_from_xml(data)
        # On execution end/interruption write corresponding
        # values to the import job record
        except Exception as exc:
            # Rollback new cursor on exception
            self.env.cr.rollback()
            values = {'state': 'failed', 'fail_message': str(exc.args[0])}
        else:
            values = {'state': 'finished'}
        values['execution_end_date'] = datetime.now().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        self.write(values)
        self.env.cr.commit()

    # Utility Methods -------------------------------------------------------------------------------------------------

    @api.multi
    def reset_state(self):
        """Resets import job state to 'no_action'"""
        self.write({'state': 'no_action'})

    @api.multi
    def name_get(self):
        return [(rec.id, _('Importavimas #{}').format(rec.id)) for rec in self]
