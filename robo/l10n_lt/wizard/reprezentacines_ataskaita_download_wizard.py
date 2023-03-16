# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ReprezentacinesAtaskaitaDownloadWizard(models.TransientModel):

    _name = 'reprezentacines.ataskaita.download.wizard'
    #FIXME: default get behavior is unclear
    def _data_file(self):
        return self._context.get('file')

    file_1 = fields.Binary(string='File 1', default=_data_file, readonly=True)
    file_name_1 = fields.Char(default=_data_file)
    file_2 = fields.Binary(string='File 2', default=_data_file, readonly=True)
    file_name_2 = fields.Char(default=_data_file)

    @api.model
    def default_get(self, field_list):
        return {'file_1': self._context.get('file_1'),
                'file_2': self._context.get('file_2'),
                'file_name_1': self._context.get('file_name_1'),
                'file_name_2': self._context.get('file_name_2')}
