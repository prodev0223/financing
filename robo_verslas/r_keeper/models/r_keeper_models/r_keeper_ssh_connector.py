# -*- coding: utf-8 -*-

from odoo import models, api, exceptions, _
import paramiko
import logging
import os

_logger = logging.getLogger(__name__)


class RKeeperSSHConnector(models.AbstractModel):
    _name = 'r.keeper.ssh.connector'
    _description = 'Abstract model that contains various rKeeper SSH connecting methods'

    @api.model
    def check_external_path(self, sftp, path):
        """
        Checks whether given path exists in external server to which Paramiko SSH
        is connected. True is returned if directory exists, otherwise False
        :param sftp: Paramiko SFTP object
        :param path: external path (str)
        :return: Boolean value
        """
        try:
            sftp.stat(path)
        except IOError:
            return False
        return True

    @api.model
    def get_r_keeper_directories(self, sftp_object=None):
        """
        Returns external rKeeper directories that are set in config parameters.
        Config parameter data is validated internally, then ultimate directories
        are built. If Paramiko SFTP object is passed, ultimate directories
        are checked in external server - if they do not exist externally,
        error is raised
        :param sftp_object: Paramiko SFTP object
        :return: directory dict
        """
        config_obj = self.env['ir.config_parameter']

        # Get local temporary directory
        local_temp = config_obj.get_param('r_keeper_local_temp_directory')

        # Create temporary local directory if it does not exist
        if not os.path.isdir(local_temp):
            try:
                os.mkdir(local_temp)
            except (IOError, OSError):
                raise exceptions.ValidationError(
                    _('Nepavyko įkelti failo. Lokali talpykla nėra sukonfigūruota. Susiekite su administratoriais')
                )
        # Get all of the directories
        dirs = {
            'local_temp_dir': local_temp,
            'root_dir': config_obj.get_param('r_keeper_server_root_directory'),
            'imported_dir': config_obj.get_param('r_keeper_imported_sub_dir'),
            'import_dir': config_obj.get_param('r_keeper_to_import_sub_dir'),
            'import_error_dir': config_obj.get_param('r_keeper_imported_error_sub_dir'),
            'export_dir': config_obj.get_param('r_keeper_exported_sub_dir'),
            'proc_export_dir': config_obj.get_param('r_keeper_processed_export_sub_dir'),
        }

        # Check if all directories are set
        local_errors = str()
        for name, path in dirs.items():
            if not path:
                local_errors += _('Nenustatyta nuotolinė "{}" direktorija.\n'.format(name))
            else:
                # Strip the paths
                dirs[name] = path.strip()
        # Check if there's any errors, and raise if there are
        if local_errors:
            raise exceptions.ValidationError(
                _('Nepavyko įkelti failo dėl šių klaidų: \n\n {} \n Susisiekite su administratoriais.').format(
                    local_errors)
            )

        # Build ultimate directories
        ultimate_dirs = {
            'ult_import_dir': '{}\\{}'.format(dirs['root_dir'], dirs['import_dir']),
            'ult_import_error_dir': '{}\\{}'.format(dirs['root_dir'], dirs['import_error_dir']),
            'ult_imported_dir': '{}\\{}'.format(dirs['root_dir'], dirs['imported_dir']),
            'ult_export_dir': '{}\\{}'.format(dirs['root_dir'], dirs['export_dir']),
            'ult_proc_export_dir': '{}\\{}'.format(dirs['root_dir'], dirs['proc_export_dir']),
        }

        remote_errors = str()
        # If sftp object is passed, check if all ultimate dirs exist in remote server
        if sftp_object:
            for name, path in ultimate_dirs.items():
                # Workarounds due to rKeeper folders with spaces
                path = path.replace('"', '')
                if not self.check_external_path(sftp_object, path):
                    remote_errors += _('rKeeper serveryje nerasta "{}" direktorija.\n'.format(name))
        # Check if there's any errors, and raise if there are
        if remote_errors:
            raise exceptions.ValidationError(
                _('Nepavyko įkelti failo dėl šių klaidų: \n\n {} \n Susisiekite su administratoriais.').format(
                    remote_errors)
            )

        dirs.update(ultimate_dirs)
        return dirs

    @api.model
    def get_r_keeper_connection_parameters(self):
        """
        Returns rKeeper configuration parameters
        in dictionary format
        :return: dictionary
        """
        config_obj = self.sudo().env['ir.config_parameter']
        params = {
            'r_keeper_server_address': config_obj.get_param('r_keeper_server_address'),
            'r_keeper_user_name': config_obj.get_param('r_keeper_user_name'),
            'r_keeper_password': config_obj.get_param('r_keeper_password'),
            'r_keeper_directory': config_obj.get_param('r_keeper_server_root_directory'),
        }
        return params

    @api.model
    def initiate_r_keeper_connection(self):
        """
        Initiates SSH connection to external
        rKeeper server. If connection fails
        error is raised and detailed info is logged.
        :return: SSH connection object
        """
        # Get the parameters
        params = self.get_r_keeper_connection_parameters()

        # Initiate SSH connection
        ssh_conn = paramiko.SSHClient()
        ssh_conn.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh_conn.connect(
                params['r_keeper_server_address'],
                username=params['r_keeper_user_name'],
                password=params['r_keeper_password'],
                timeout=10,
            )
        except Exception as exc:
            error = 'rKeeper SSH connection error: {}'.format(exc.args[0])
            _logger.info(error)
            raise exceptions.ValidationError(
                _('Nepavyko pasiekti nuotolinio rKeeper serverio. Susisiekite su administratoriais')
            )
        return ssh_conn
