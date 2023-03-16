# -*- coding: utf-8 -*-
from odoo.api import Environment
import threading
import odoo
from odoo import models, fields, api, _, tools, exceptions
from datetime import datetime
import base64
import logging

_logger = logging.getLogger(__name__)


class RKeeperXLSImportWizard(models.TransientModel):
    _name = 'r.keeper.xls.import.wizard'
    _description = '''
    Wizard that is used to import rKeeper XLS files
    to the system.
    '''

    xls_data = fields.Binary(string='XLS failas', required=True)
    xls_name = fields.Char(string='XLS failo pavadinimas', size=128, required=False)
    import_type = fields.Selection(
        [('payment_type_xls', 'rKeeper mokėjimo tipai')],
        string='Importavimo tipas', default='payment_type_xls'
    )

    @api.multi
    def parse_xls_prep(self):
        """
        Method that prepares creation
        of records using passed XLS data.
        :return: None
        """
        self.ensure_one()
        if self.env['r.keeper.data.import.job'].search_count(
                [('state', '=', 'in_progress'), ('file_type', '=', self.import_type)]):
            raise exceptions.ValidationError(_('Negalite ikelti failo, šio tipo failas yra importuojamas šiuo metu'))

        xls_data = base64.decodestring(self.xls_data)
        vals = {
            'execution_start_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            'state': 'in_progress',
            'imported_file_name': self.xls_name,
            'imported_file': self.xls_data,
            'file_type': self.import_type,
        }
        # Create import job on threaded mode and pass data to
        # intermediate threaded method that handles the import
        import_job = self.env['r.keeper.data.import.job'].create(vals)
        self.env.cr.commit()
        threaded_calculation = threading.Thread(
            target=self.parse_xls_threaded, args=(xls_data, self.import_type, import_job.id))
        threaded_calculation.start()

    @api.model
    def parse_xls_threaded(self, xls_data, file_type, job_id):
        """
        Intermediate method that calls parse_xls in a threaded mode
        :param xls_data: XLS data (str)
        :param file_type: Indicates what type of XLS file is passed
        :param job_id: r.keeper.data.import.job ID
        :return: None
        """
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, odoo.SUPERUSER_ID, {'lang': 'lt_LT'})
            import_job = env['r.keeper.data.import.job'].browse(job_id)
            try:
                # Proceed with record creation
                data_set = env['r.keeper.data.import'].parse_xls_file(xls_data, file_type)
                env['r.keeper.data.import'].create_records_from_xls(data_set, file_type)
            # On execution end/interruption write corresponding
            # values to the import job record
            except Exception as exc:
                # Rollback new cursor on exception
                new_cr.rollback()
                values = {'state': 'failed', 'fail_message': str(exc.args[0])}
            else:
                values = {'state': 'finished'}
            values['execution_end_date'] = datetime.now().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            import_job.write(values)
        new_cr.commit()
        new_cr.close()

