# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions


class MrpProductionCopyWizard(models.TransientModel):
    _name = 'mrp.production.copy.wizard'
    _description = '''Wizard that allows user to copy production with various 
    settings regarding the production that is being copied from'''

    production_ids = fields.Many2many('mrp.production', string='Gamybos')
    production_line_copy_ids = fields.Many2many(
        'mrp.production.copy.wizard.line',
        string='Gamybos kopijavimo eilutės'
    )

    @api.multi
    def generate_copy_lines(self):
        """Generate copy lines from current productions"""
        self.ensure_one()
        copy_lines = []
        for production in self.production_ids:
            copy_lines.append((0, 0, {
                'production_id': production.id,
                'dst_product_id': production.product_id.id,
                'dst_bom_id': production.bom_id.id,
                'dst_quantity': production.product_qty,
                'dst_planned_date': production.date_planned_start,
                'dst_location_src_id': production.location_src_id.id,
                'dst_location_dst_id': production.location_dest_id.id,
            }))
        self.write({'production_line_copy_ids': copy_lines})

    @api.multi
    def copy_productions(self):
        """Copy the production with custom settings"""
        self.ensure_one()
        if not self.production_line_copy_ids:
            raise exceptions.ValidationError(_('Nerasta kopijuojamų gamybų'))

        # Copy the productions
        self.production_line_copy_ids.copy_productions()
        # Commit and open display window
        self.env.cr.commit()
        return {
            'name': _('Masinis gamybų kopijavimas'),
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.production.copy.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
            'res_id': self.id,
            'view_id': self.env.ref('robo_mrp.form_mrp_production_copy_wizard_done').id,
        }
