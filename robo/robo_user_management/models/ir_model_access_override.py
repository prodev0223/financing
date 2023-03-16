# -*- coding: utf-8 -*-

from odoo import api, fields, models, exceptions
from odoo.tools.translate import _


class IrModelAccessOverride(models.Model):
    _name = 'ir.model.access.override'

    _sql_constraints = [('no_duplicate_models_for_user', 'unique(model_id, user_id)',
                         _('Negalima du kartus pridėti to paties modelio teisių perrašymo tam pačiam darbuotojui'))]

    model_id = fields.Many2one('ir.model', 'Modelis', required=True)  # domain=[('allow_access_changes', '=', True)]
    user_id = fields.Many2one('res.users', 'Naudotojas', required=True)
    allow_create = fields.Boolean('Kurti')
    allow_read = fields.Boolean('Peržiūrėti')
    allow_write = fields.Boolean('Keisti')
    allow_unlink = fields.Boolean('Ištrinti')

    @api.onchange('allow_create', 'allow_write')
    def _onchange_allow_create_or_allow_write(self):
        # Must be able to read in order to write
        if self.allow_write:
            self.allow_read = True

        # Must be able to write, unlink and read in order to create
        if self.allow_create:
            self.allow_write = True
            self.allow_unlink = True
            self.allow_read = True

    @api.multi
    @api.constrains('allow_create', 'allow_write')
    def _check_read_is_allowed(self):
        for rec in self:
            # Must be able to read in order to create or write
            if (rec.allow_create or rec.allow_write) and not rec.allow_read:
                raise exceptions.ValidationError(
                    _('Turite suteikti vartotojui peržiūrėjimo prieigą modeliui "{0}", nes jos '
                      'reikia norint kurti ar keisti šio modelio įrašus').format(rec.model_id.name))

    @api.multi
    @api.constrains('allow_write')
    def _check_write_is_allowed(self):
        for rec in self:
            # Must be able to read in order to create or write
            if rec.allow_create and not rec.allow_write:
                raise exceptions.ValidationError(
                    _('Turite suteikti vartotojui keitimo prieigą modeliui "{0}", nes jos '
                      'reikia norint kurti šio modelio įrašus').format(rec.model_id.name)
                )

    @api.multi
    @api.constrains('allow_create', 'allow_unlink')
    def _check_unlink_is_allowed(self):
        for rec in self:
            # Must be able to read in order to create or write
            if rec.allow_create and not rec.allow_unlink:
                raise exceptions.ValidationError(
                    _('Turite suteikti vartotojui ištrynimo prieigą modeliui "{0}", nes jos '
                      'reikia norint kurti šio modelio įrašus').format(self.model_id.name)
                )
