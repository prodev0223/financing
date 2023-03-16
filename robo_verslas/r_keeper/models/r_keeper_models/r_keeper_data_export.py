# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools, exceptions, _
from ... import r_keeper_tools as rkt
from datetime import datetime
import base64
import csv
import os
import io


class RKeeperDataExport(models.Model):
    _name = 'r.keeper.data.export'
    _order = 'create_date desc'
    _description = '''
    Model that stores rKeeper data export files with revisions 
    of the records that are being exported
    '''

    export_file = fields.Binary(string='Perduodami duomenys')
    export_file_name = fields.Char(string='Failo pavadinimas')

    state = fields.Selection(
        [('no_action', 'Paruošta'),
         ('waiting', 'Laukiama'),
         ('accepted', 'Priimta'),
         ('rejected', 'Atmesta')
         ], string='Eksportavimo būsena', default='no_action'
    )
    revision_ids = fields.One2many(
        'r.keeper.data.export.revision', 'data_export_id',
        string='Eksportuotų įrašų versijos'
    )
    point_of_sale_id = fields.Many2one(
        'r.keeper.point.of.sale',
        string='Susijęs pardavimo taškas'
    )

    # Main Methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def generate_export_file(self):
        """
        Method that is used to generate UPD export file using passed
        revisions and point of sale information. After generation
        CSV file is pushed to rKeeper server.
        :return: None
        """
        self.ensure_one()

        def convert(value):
            """Converts false values to empty string"""
            return value if value else str()

        csv_output = io.BytesIO()
        csv_writer = csv.writer(csv_output, dialect='excel', delimiter=';')

        product_lines = self.revision_ids.mapped('point_of_sale_product_id')
        for line in product_lines:
            data_to_write = [
                'V',  # 1. col: Static value provided by rKeeper
                convert(line.product_state),  # 2. col: Product state
                convert(line.product_id.default_code),  # 3. col: Product code
                convert(line.product_id.name),  # 3. col: Product code
                convert(line.category_id.name),  # 5. col: Group name
                convert(line.price_unit_exportable),  # 6. col: Price unit
                convert(line.vat_rate),  # 7. col: VAT rate
                int(line.is_weighed),  # 8. col: NUMERIC: Is weighed
                convert(line.uom_id.name),  # 9. col: Uom name
                convert(self.point_of_sale_id.code),  # 10. col: Point of sale code
                convert(line.related_product_id.default_code),  # 11. col: Related product code
                convert(line.related_product_uom_id.name),  # 12. col: Related product uom
            ]
            csv_writer.writerow(data_to_write)

        # Write the data to current model
        csv_data = csv_output.getvalue()
        self.export_file = base64.b64encode(csv_data)

        file_name = '{}_{}_{}.{}'.format(
            self.point_of_sale_id.code,
            datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            self.id,
            rkt.EXPORTED_FILE_EXTENSION,
        )

        self.export_file_name = file_name
        self.upload_export_file()

    @api.multi
    def upload_export_file(self):
        """
        Method that is used to upload CSV export file using passed
        revisions and point of sale information. After generation
        CSV file is pushed to rKeeper server.
        :return: None
        """
        self.ensure_one()

        # Check rKeeper integration (Only partially, records are fetched every day)
        if not self.env['r.keeper.configuration'].check_r_keeper_configuration(partial_check=True):
            return

        # Initiate SSH connection
        rk_ssh_obj = self.env['r.keeper.ssh.connector']
        ssh_conn = rk_ssh_obj.initiate_r_keeper_connection()

        # Open SFTP connection
        sftp_object = ssh_conn.open_sftp()
        # Get external directory names
        dirs = rk_ssh_obj.get_r_keeper_directories(sftp_object)

        # File to export
        f_name = self.export_file_name
        f_data = base64.decodestring(self.export_file)
        ult_local_file_path = '{}/{}'.format(dirs['local_temp_dir'], f_name)

        # Write the data to the file
        with open(ult_local_file_path, 'w+') as file_to_export:
            file_to_export.write(f_data)

        # Prepare upload error message that is used several times
        upload_error_message = _(
            'Nepavyko įkelti failo. Pabandykite pakartoti veiksmą kelių minučių bėgyje. '
            'Pakartotinai gavus šį pranešimą susisiekite su administratoriais'
        )
        # Build ultimate remote file path
        ult_remote_file_path = '{}\\{}'.format(dirs['ult_import_dir'], f_name)

        # Try to upload the file via SFTP
        try:
            sftp_object.put(ult_local_file_path, ult_remote_file_path)
        except IOError:
            os.remove(ult_local_file_path)
            raise exceptions.ValidationError(upload_error_message)
        # Check if path exists in external system
        if not rk_ssh_obj.check_external_path(sftp_object, ult_remote_file_path):
            os.remove(ult_local_file_path)
            raise exceptions.ValidationError(upload_error_message)

        # Delete the file locally
        os.remove(ult_local_file_path)
        # Write the state, commit changes and display success message
        self.state = 'waiting'
        self.env.cr.commit()
        raise exceptions.ValidationError(
            _('Failas sėkmingai įkeltas, laukiama atsakymo iš rKeeper serverio!')
        )

    @api.model
    def cron_check_pending_export_state(self):
        """
        Method that is used to generate
        CSV export file using passed
        revisions and point of sale information.
        After generation CSV file is pushed
        to rKeeper server
        :return: None
        """

        # Check rKeeper integration (Only partially, records are fetched every day)
        if not self.env['r.keeper.configuration'].check_r_keeper_configuration(partial_check=True):
            return

        # Check if there's any pending exports that must be checked
        pending_exports = self.search([('state', '=', 'waiting')])
        if pending_exports:
            # Initiate SSH connection
            rk_ssh_obj = self.env['r.keeper.ssh.connector']
            ssh_conn = rk_ssh_obj.initiate_r_keeper_connection()

            # Open SFTP connection
            sftp_object = ssh_conn.open_sftp()
            # Get external directory names
            dirs = rk_ssh_obj.get_r_keeper_directories(sftp_object)

            # Loop through pending exports
            for export in pending_exports:
                # Build path-to-state mapping
                f_name = export.export_file_name
                path_to_state_mapping = {
                    'waiting': '{}\\{}'.format(dirs['ult_import_dir'], f_name),
                    'rejected': '{}\\{}'.format(dirs['ult_import_error_dir'], f_name),
                    'accepted': '{}\\{}'.format(dirs['ult_imported_dir'], f_name)
                }
                export_state = str()
                # Loop through paths and check what is the state of the file
                for state, ext_path in path_to_state_mapping.items():
                    if rk_ssh_obj.check_external_path(sftp_object, ext_path):
                        export_state = state
                        break

                # Write state changes if any and commit
                if export_state != export.state:
                    export.write({'state': export_state})
                    self.env.cr.commit()

    # Utility Methods -------------------------------------------------------------------------------------------------

    @api.multi
    def name_get(self):
        return [(rec.id, _('Eksportas #{}').format(rec.id)) for rec in self]

