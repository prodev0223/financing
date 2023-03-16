# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, fields, api, tools, _, exceptions
from odoo.addons import decimal_precision as dp


class MrpBomProportionWizard(models.TransientModel):
    _name = 'mrp.bom.proportion.wizard'

    quantity = fields.Float(
        string='Quantity', digits=dp.get_precision('Product Unit of Measure'),
    )
    bom_id = fields.Many2one('mrp.bom', string='Related BOM')
    component_proportion_table = fields.Html(tring='Components')

    @api.multi
    def button_calculate_proportions(self):
        """
        Renders BOM lines with passed quantity and
        generates component proportion table.
        :return: None
        """
        self.ensure_one()
        # Ensure that quantity is not zero
        if tools.float_is_zero(self.quantity, precision_digits=2):
            raise exceptions.ValidationError(_('Quantity cannot be zero'))
        # Calculate the factor and render the lines
        # P3:DivOK
        factor = self.quantity / (self.bom_id.product_qty or 1)
        bom_lines_html = self.bom_id.bom_line_ids.with_context(
            skip_transitional_components=True).compose_exploded_bom_lines_table(factor=factor)
        # Render the component table using the body
        component_proportion_table = self.env['ir.qweb'].render(
            'robo_mrp.bom_line_table_template', {'table_body': bom_lines_html}
        )
        self.component_proportion_table = component_proportion_table
        return {'type': 'ir.actions.do_nothing'}
