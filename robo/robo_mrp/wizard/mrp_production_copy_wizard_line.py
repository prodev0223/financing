# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, _
from datetime import datetime


class MrpProductionCopyWizardLine(models.TransientModel):
    _name = 'mrp.production.copy.wizard.line'
    _description = '''Wizard that allows user to copy production with various 
    settings regarding the production that is being copied from'''

    # Source data
    production_id = fields.Many2one('mrp.production')
    display_name = fields.Char(
        string='Kopijuojama gamyba',
        compute='_compute_display_name',
    )
    # Destination data
    dst_quantity = fields.Float(string='Kopijos kiekis')
    dst_planned_date = fields.Datetime(string='Kopijos data')
    dst_product_id = fields.Many2one('product.product', string='Gaminys')
    dst_bom_id = fields.Many2one('mrp.bom', string='Komplektacija')
    dst_location_src_id = fields.Many2one('stock.location', string='Žaliavų vieta')
    dst_location_dst_id = fields.Many2one('stock.location', string='Gaminių vieta')

    # Copied production
    dst_production_id = fields.Many2one('mrp.production', string='Sukurta gamyba')

    @api.multi
    def _compute_display_name(self):
        """Computes source production name for visual display"""
        for rec in self:
            rec.display_name = '[{}] {}'.format(
                rec.production_id.name, rec.production_id.product_id.display_name
            )

    @api.onchange('dst_product_id')
    def _onchange_dst_product_id(self):
        """Finds BOM of changed product"""
        if not self.dst_product_id:
            self.dst_bom_id = None
        else:
            bom = self.env['mrp.bom'].with_context(bom_at_date=self.dst_planned_date)._bom_find(
                product=self.dst_product_id, picking_type=self.production_id.picking_type_id,
                company_id=self.production_id.company_id.id
            )
            self.dst_bom_id = bom.id

    @api.onchange('dst_planned_date')
    def _onchange_fields_for_product_domain(self):
        """
        If date planned is changed and bom expiry dates are enabled,
        return the domain to filter out products with expired BOMs.
        :return: JS domain (dict)
        """
        if self.sudo().env.user.company_id.enable_bom_expiry_dates:
            date = self.dst_planned_date or datetime.now().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            if not self.dst_bom_id.valid_bom(date):
                self.dst_product_id = None
            bom_domain = [
                ('bom_ids', '!=', False),
                ('bom_ids.active', '=', True),
                ('bom_ids.valid_from', '<=', date),
                '|',
                ('bom_ids.valid_to', '=', False),
                ('bom_ids.valid_to', '>=', date),
            ]
            return {'domain': {'dst_product_id': bom_domain}}

    @api.onchange('date_planned_start', 'product_id')
    def _onchange_fields_for_bom_domain(self):
        """
        If date planned or product are changed
        and bom expiry dates are enabled, return
        the domain to filter out expired BOMs
        :return: JS domain (dict)
        """
        base_domain = [
            '&', '|',
            ('product_id', '=', self.dst_product_id.id), '&',
            ('product_tmpl_id.product_variant_ids', '=', self.dst_product_id.id),
            ('product_id', '=', False),
            ('type', '=', 'normal'),
        ]
        if self.sudo().env.user.company_id.enable_bom_expiry_dates:
            # If expiry dates are enabled, get bom date to check against
            date = self.dst_planned_date or datetime.now().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            base_domain += [
                ('valid_from', '<=', date),
                '|',
                ('valid_to', '=', False),
                ('valid_to', '>=', date),
            ]
        return {'domain': {'dst_bom_id': base_domain}}

    @api.multi
    def copy_productions(self):
        """
        Method that copies batch of productions, checks for
        value changes and calls intermediate re-computation
        methods. New record is linked to the line
        """
        for rec in self:
            # Check whether stock moves and locations should be recomputed
            recompute_moves = tools.float_compare(
                rec.production_id.product_qty, rec.dst_quantity, precision_digits=5
            ) or rec.dst_product_id != rec.production_id.product_id or rec.dst_bom_id != rec.production_id.bom_id
            recompute_locations = \
                rec.production_id.location_src_id.id != rec.dst_location_src_id.id or \
                rec.production_id.location_dest_id.id != rec.dst_location_dst_id.id
            # Base copy data
            copy_data = {
                'date_planned_start': rec.dst_planned_date,
                'accounting_date': rec.dst_planned_date,
            }
            # If moves should be recomputed, add more default copy values
            if recompute_moves:
                copy_data.update({
                    'product_id': rec.dst_product_id.id,
                    'bom_id': rec.dst_bom_id.id,
                    'product_uom_id': rec.dst_product_id.uom_id.id,
                    'move_raw_ids': False,
                    'move_raw_ids_second': False,
                    'move_finished_ids': False,
                })

            # Copy the production
            new_production = rec.production_id.copy(copy_data)
            if recompute_moves:
                # Create qty re-computation wizard and change the data
                change_qty_wizard = self.env['change.production.qty'].create({
                    'mo_id': new_production.id,
                    'product_qty': rec.dst_quantity,
                })
                change_qty_wizard.change_prod_qty()
            if recompute_locations:
                # Create location change wizard and change the data
                change_loc_wizard = self.env['change.production.location'].create({
                    'mo_id': new_production.id,
                    'location_src_id': rec.dst_location_src_id.id,
                    'location_dest_id': rec.dst_location_dst_id.id,
                })
                change_loc_wizard.change_prod_location()
            rec.write({'dst_production_id': new_production.id})
