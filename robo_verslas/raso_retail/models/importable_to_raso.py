# -*- coding: utf-8 -*-

from odoo import models, api, fields, _


class ImportableToRaso(models.AbstractModel):

    """
    Abstract model that contains methods shared by objects that are importable to RASO
    """

    _name = 'importable.to.raso'

    raso_revision = fields.Char(string='Įrašo statusas RASO serveryje', compute='get_raso_revision')
    last_update_state = fields.Selection([('waiting', 'info'),
                                          ('rejected', 'danger'),
                                          ('out_dated', 'warning'),
                                          ('newest', 'success'),
                                          ('not_tried', 'muted')
                                          ], string='Importavimo būsena', compute='get_raso_revision')
    revision_number_display = fields.Char(compute='get_display_revision', string='Įrašo versija')

    @api.one
    def get_raso_revision(self):
        if self.imported_ids:
            last_import = self.imported_ids.sorted(lambda x: x.id, reverse=True)[0]
            revision_number = last_import.revision_ids.filtered(lambda x: x.res_id == self.id).revision_number

            suc_imports = self.imported_ids.filtered(lambda x: x.status == '1')
            last_successful_import = suc_imports.sorted(lambda x: x.id, reverse=True)[
                0] if suc_imports else self.env['sync.data.import']
            suc_revision_number = last_successful_import.revision_ids.filtered(
                lambda x: x.res_id == self.id).revision_number if last_successful_import else False
            if last_import.status == '1':
                if revision_number < self.revision_number:
                    self.raso_revision = 'Įrašo versija RASO serveryje ' \
                                         'yra senesnė: #{0} < #{1}'.format(revision_number, self.revision_number)
                    self.last_update_state = 'out_dated'
                else:
                    self.raso_revision = 'Įrašo versija RASO serveryje yra naujausia: #{0}'.format(revision_number)
                    self.last_update_state = 'newest'

            elif last_import.status in ['0', '2']:
                if last_successful_import:
                    self.raso_revision = 'Laukiama atsakymo iš raso serverio įkeltam #{0} įrašui. Paskutinė sėkmingai ' \
                                         'įkelta versija #{1}'.format(revision_number, suc_revision_number)
                    self.last_update_state = 'waiting'
                else:
                    self.raso_revision = 'Laukiama atsakymo iš raso serverio įkeltam #{0} įrašui'.format(
                        revision_number)
                    self.last_update_state = 'waiting'
            else:
                if last_successful_import:
                    self.raso_revision = 'Paskutinis įkėlimas #{0} įrašui buvo atmestas. Paskutinė sėkmingai įkelta' \
                                         ' versija #{1}'.format(revision_number, suc_revision_number)
                    self.last_update_state = 'rejected'
                else:
                    self.raso_revision = 'Paskutinis įkėlimas #{0} įrašui buvo atmestas'.format(
                        revision_number)
                    self.last_update_state = 'rejected'
        else:
            self.raso_revision = 'Įrašas nebandytas importuoti'
            self.last_update_state = 'not_tried'

    @api.multi
    def get_last_import_revision_num(self):
        self.ensure_one()
        return self.env['data.import.revisions'].search([('res_model', '=', self._name),
                                                         ('res_id', '=', self.id),
                                                         ('data_import_id.status', '!=', '3')],
                                                        order='id desc', limit=1).revision_number

    @api.one
    @api.depends('revision_number')
    def get_display_revision(self):
        self.revision_number_display = '#{0}'.format(self.revision_number)


ImportableToRaso()
