# -*- coding: utf-8 -*-
##############################################################################
#
#    This module uses OpenERP, Open Source Management Solution Framework.
#    Copyright (C):
#        2012-Today Serpent Consulting Services (<http://www.serpentcs.com>)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>
#
##############################################################################

from odoo import models, fields, api, exceptions
from odoo.tools.translate import _
from six import iteritems


class MassObject(models.Model):

    _name = 'mass.object'

    name = fields.Char("Name", size=64, required=True, index=True)
    model_id = fields.Many2one('ir.model', 'Model', required=True, index=True)
    field_ids = fields.Many2many(
        'ir.model.fields', 'mass_field_rel', 'mass_id', 'field_id', 'Fields')
    ref_ir_act_window = fields.Many2one(
        'ir.actions.act_window', 'Sidebar Action', readonly=True,
        help="Sidebar action to make this template available on records \
             of the related document model")
    ref_ir_value = fields.Many2one(
        'ir.values', 'Sidebar Button', readonly=True,
        help="Sidebar button to open the sidebar action")
    model_ids = fields.Many2many('ir.model', string='Model List')

    _sql_constraints = [
        ('name_uniq', 'unique (name)', _('Name must be unique!')),
    ]

    @api.onchange('model_id')
    def onchange_model_id(self):
        if not self.model_id:
            self.model_ids = [(6, 0, [])]
            return
        model_ids = [self.model_id.id]
        model_obj = self.env['ir.model']
        active_model_obj = self.env[self.model_id.model]
        if active_model_obj._inherits:
            for key, val in iteritems(active_model_obj._inherits):
                found_model_ids = model_obj.search([('model', '=', key)]).mapped('id')
                model_ids += found_model_ids
        self.model_ids = [(6, 0, model_ids)]

    @api.multi
    def create_action(self):
        vals = {}
        action_obj = self.env['ir.actions.act_window']
        ir_values_obj = self.env['ir.values']
        for data in self:
            src_obj = data.model_id.model
            button_name = _('Mass Editing (%s)') % data.name
            vals['ref_ir_act_window'] = action_obj.sudo().create({
                    'name': button_name,
                    'type': 'ir.actions.act_window',
                    'res_model': 'mass.editing.wizard',
                    'src_model': src_obj,
                    'view_type': 'form',
                    'context': "{'mass_editing_object' : %d}" % data.id,
                    'view_mode': 'form,tree',
                    'target': 'new',
                    'auto_refresh': 1,
                }).id
            vals['ref_ir_value'] = ir_values_obj.sudo().create({
                    'name': button_name,
                    'model': src_obj,
                    'key2': 'client_action_multi',
                    'value': (
                        "ir.actions.act_window," +
                        str(vals['ref_ir_act_window'])),
                    'object': True,
                }).id
        self.write({
                'ref_ir_act_window': vals.get('ref_ir_act_window', False),
                'ref_ir_value': vals.get('ref_ir_value', False),
            })
        return True

    @api.multi
    def unlink_action(self):
        for template in self:
            try:
                if template.ref_ir_act_window:
                    template.ref_ir_act_window.sudo().unlink()
                if template.ref_ir_value:
                    template.ref_ir_value.sudo().unlink()
            except:
                raise exceptions.Warning(_("Deletion of the action record failed."))
        return True

    @api.multi
    def unlink(self):
        self.unlink_action()
        return super(MassObject, self).unlink()

    @api.multi
    def copy(self, default=None):
        if default is None:
            default = {}
        default.update({'name': '', 'field_ids': []})
        return super(MassObject, self).copy(default)
