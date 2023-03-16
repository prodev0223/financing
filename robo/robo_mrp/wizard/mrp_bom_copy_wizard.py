# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions, _
from dateutil.relativedelta import relativedelta
from datetime import datetime


class MrpBomCopyWizard(models.TransientModel):
    _name = 'mrp.bom.copy.wizard'
    _description = '''Wizard that allows user to copy BOM with various 
    settings regarding the bom that is being copied from'''

    @api.model
    def _default_dst_valid_from(self):
        """Get default dst. valid from"""
        if self.sudo().env.user.company_id.enable_bom_expiry_dates:
            return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    bom_id = fields.Many2one('mrp.bom', string='Komplektacija')

    # Various settings
    archive_source = fields.Boolean(string='Suarchyvuoti kopijuojamą komplektaciją')
    src_valid_to = fields.Date(string='Kopijuojamos komplektacijos galiojimo pabaigos data')
    dst_valid_from = fields.Date(
        string='Naujos komplektacijos galiojimo pradžios data',
        default=_default_dst_valid_from,
    )
    dst_valid_to = fields.Date(string='Naujos komplektacijos galiojimo pabaigos data')

    bom_expiry_dates_enabled = fields.Boolean(
        compute='_compute_bom_expiry_dates_enabled'
    )

    @api.multi
    def _compute_bom_expiry_dates_enabled(self):
        """
        Checks whether BOM expiry date functionality is
        enabled in the system.
        """
        bom_expiry_dates_enabled = self.sudo().env.user.company_id.enable_bom_expiry_dates
        for rec in self:
            rec.bom_expiry_dates_enabled = bom_expiry_dates_enabled

    @api.onchange('valid_from')
    def onchange_valid_from(self):
        """Change source BOM expiry date to second before to-be-created BOM start date"""
        if self.bom_expiry_dates_enabled and self.dst_valid_from and not self.bom_id.valid_to:
            src_valid_to = (datetime.strptime(
                self.dst_valid_from, tools.DEFAULT_SERVER_DATE_FORMAT) -
                            relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            self.src_valid_to = src_valid_to

    @api.multi
    def copy_bom(self):
        """Copy the BOM with custom settings"""
        self.ensure_one()

        # Check basic constraints
        if self.dst_valid_to and self.dst_valid_to < self.dst_valid_from:
            raise exceptions.ValidationError(
                _('Komplektacijos galiojimo pabaigos data privalo būti vėlesnė nei galiojimo pradžios data')
            )

        # Prepare copy and source values
        src_data = {'active': not self.archive_source}
        copy_data = {'active': True}

        if self.bom_expiry_dates_enabled:
            copy_data.update({'valid_from': self.dst_valid_from, 'valid_to': self.dst_valid_to})
            src_data.update({'valid_to': self.src_valid_to})

        # Write values to source first, and create a copy
        self.bom_id.write(src_data)
        new_bom = self.bom_id.with_context(wizard_call=True).copy(copy_data)

        # Return copied record in editable form view
        return {
            'name': _('Komplektacija'),
            'view_mode': 'form',
            'view_id': self.env.ref('robo_mrp.robo_mrp_bom_form_view').id,
            'view_type': 'form',
            'res_model': 'mrp.bom',
            'res_id': new_bom.id,
            'type': 'ir.actions.act_window',
            'flags': {'initial_mode': 'edit'},
        }
