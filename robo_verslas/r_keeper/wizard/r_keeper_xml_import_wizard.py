# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, tools, exceptions
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class RKeeperXMLImportWizard(models.TransientModel):
    _name = 'r.keeper.xml.import.wizard'
    _description = '''
    Wizard that is used to import rKeeper XML files
    to the system.
    '''

    xml_data = fields.Binary(string='XML failas', required=True)
    xml_name = fields.Char(string='XML failo pavadinimas', size=128, required=False)

    @api.multi
    def import_xml_file(self):
        """
        Method that creates rKeeper data import job record,
        which parses imported XML file.
        :return: None
        """
        self.ensure_one()
        # Explicitly check this so the user instantly knows
        # that they should wait if file is already being imported.
        if self.env['r.keeper.data.import.job'].search_count(
                [('state', '=', 'in_progress'), ('file_type', '=', 'sale_xml')]):
            raise exceptions.ValidationError(_('Negalite ikelti failo, šio tipo failas yra importuojamas šiuo metu'))

        vals = {
            'execution_start_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            'state': 'in_progress',
            'imported_file_name': self.xml_name,
            'imported_file': self.xml_data,
            'file_type': 'sale_xml',
        }
        # Create import job record and call import function in threaded mode
        import_job = self.env['r.keeper.data.import.job'].create(vals)
        self.env.cr.commit()
        import_job.parse_xml_file_prep(threaded=True)


