# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, api, _, fields, tools
import odoo.addons.decimal_precision as dp
from .. import robo_mrp_tools as rmt

# We rarely have deeper recursive production depths
CHILD_BOM_RECURSION_COUNT = 6


class MrpBomLine(models.Model):
    _inherit = 'mrp.bom.line'
    _order = 'sequence, id'

    location_src_id = fields.Many2one(
        'stock.location', string='Žaliavų vieta',
        domain=[('usage', '=', 'internal')]
    )
    recursive_component = fields.Boolean(
        string='Sudėtinis komponentas',
        compute='_compute_recursive_component'
    )
    average_cost = fields.Float(
        string='Vid. savikaina',
        compute='_compute_average_cost',
        digits=dp.get_precision('Product Price'),
    )

    @api.multi
    def _compute_average_cost(self):
        """Compute average cost for BOM line"""
        expiry_dates = self.env.user.company_id.enable_bom_expiry_dates
        recursive = self.env.user.company_id.enable_recursive_bom_production
        for rec in self:
            # Initially we pass a factor of 1
            if expiry_dates and rec.bom_id.valid_from:
                # Can't assign the context to rec (rec = rec.with_context())
                # since then rec becomes different variable and it does not
                # compute correctly, thus calculating like this
                average_cost = rec.with_context(
                    bom_at_date=rec.bom_id.valid_from).calculate_avg_cost_recursive(
                    factor=1, recursive_mode=recursive)
            else:
                average_cost = rec.calculate_avg_cost_recursive(
                    factor=1, recursive_mode=recursive)
            rec.average_cost = average_cost

    @api.multi
    def _compute_recursive_component(self):
        """
        Check whether BOM line product has another related BOM.
        Compute is not triggered if recursive production is not
        activated in the company.
        :return: None
        """
        if self.sudo().env.user.company_id.enable_recursive_bom_production:
            for rec in self:
                rec.recursive_component = rec.product_id.bom_id

    @api.onchange('product_id')
    def _onchange_product_id_set_location(self):
        """
        On product change take location from
        the product template and force it
        if it exists
        :return: None
        """
        src_location = self.product_id.product_tmpl_id.production_location_id
        if src_location:
            self.location_src_id = src_location

    @api.multi
    def write(self, vals):
        """Log changes that were made to bom line products"""
        # Check whether changes should be logged and gather previous values
        log_changes = 'product_id' in vals
        previous_values = {k.id: k.product_id for k in self} if log_changes else {}
        res = super(MrpBomLine, self).write(vals)
        # Gather up the changes in a table
        if log_changes:
            # Prepare the message template
            message_template = _(
                '''<strong>Previous values:\n</strong>
                    <table border="2" width=100%%>
                    <tr>
                        <td><b>Line #</b></td>
                        <td><b>Product</b></td>
                    </tr>'''
            )
            # Gather up the lines by BOM
            lines_by_bom = {}
            for line in self:
                # Otherwise, add the line to the grouped data
                lines_by_bom.setdefault(line.bom_id, line)
                lines_by_bom[line.bom_id] |= line

            # Loop through grouped data
            for bom, lines in lines_by_bom.items():
                bom_message = message_template
                for line in lines:
                    # If there is no product, skip
                    previous_product = previous_values.get(line.id)
                    if not previous_product:
                        continue
                    # Prepare the line data and append it to the body
                    line_data = '''<tr><td>%s</td><td>%s</td></tr>''' % (
                        line.sequence, previous_product.display_name
                    )
                    bom_message += line_data
                bom_message += '</table>'
                bom.message_post(body=bom_message)
        return res

    @api.multi
    def unlink(self):
        """Log unlinking of the bom lines in the parent bom record"""
        # Gather up the lines by their products
        lines_by_bom = {}
        for line in self:
            lines_by_bom.setdefault(line.bom_id, [])
            lines_by_bom[line.bom_id].append(line.product_id.display_name)

        # Post the messages to BOMs
        for bom, lines in lines_by_bom.items():
            bom_message = _('Lines with following products were removed: {}').format(
                ', '.join(lines))
            bom.message_post(body=bom_message)

        return super(MrpBomLine, self).unlink()

    # Recursive production render methods -----------------------------------------------------------------------------

    @api.multi
    def render_bom_recursive(self, parent_line, hierarchy_level=1, factor=None, production=None):
        """
        Renders parent (current) BOM line, then checks
        whether product of the line itself has a BOM.
        If it does, it loops through lines and calls
        itself again to render the data until the
        depth of first component BOM is reached
        :return: HTML string
        """
        self.ensure_one()

        # Check whether current line should be rendered
        skip_tr_comps = self._context.get('skip_transitional_components')
        render_line = not skip_tr_comps or (
                not self.product_id.bom_id or self.product_id.product_tmpl_id.skip_recursive_bom_splitting)
        rendered_bom_lines = str()
        if render_line:
            # Current line is rendered
            rendered_bom_lines = self.render_bom_lines(
                hierarchy_level=hierarchy_level,
                factor=factor, production=production,
            )

        # Check whether there's no recursion
        variants = parent_line.bom_id.product_tmpl_id.with_context(active_test=False).product_variant_ids
        pb_product = variants and variants[0]
        pbl_product = parent_line.product_id

        if self.product_id.bom_id and not self.product_id.product_tmpl_id.skip_recursive_bom_splitting:
            # Calculate the factor, reduced down recursively
            product_qty = self.product_qty * factor if factor else self.product_qty
            # P3:DivOK
            factor = product_qty / self.product_id.bom_id.product_qty

            # If we detect parent BOM product in recursive BOM lines,
            # we stop splitting process for this specific BOM tree
            bom_products = self.product_id.bom_id.bom_line_ids.mapped('product_id')
            if pb_product in bom_products or pbl_product in bom_products:
                return rendered_bom_lines

            # We loop through current line's product BOM lines if they exist,
            # increase the hierarchy level, and render them recursively
            for line in self.product_id.bom_id.bom_line_ids.sorted(key=lambda x: (x.sequence, x.id)):
                rendered_bom_lines += line.render_bom_recursive(
                    parent_line=parent_line,
                    hierarchy_level=hierarchy_level + 1,
                    factor=factor,
                    production=production
                )
        # Return rendered line's HTML
        return rendered_bom_lines

    @api.multi
    def render_bom_lines(self, hierarchy_level=1, factor=None, production=None):
        """
        Renders passed bom line data
        :return: HTML string
        """
        # Prepare specific style based on hierarchy level
        color = rmt.RECURSIVE_PRODUCTION_HIERARCHY_LEVEL_MAPPING.get(
            hierarchy_level, '#888888'
        )
        # Get the precision for product price (use default 3 digits if it does not exist)
        precision = self.env['decimal.precision'].precision_get('Product Price') or 3
        bom_line_html = str()
        for rec in self.sorted(key=lambda x: (x.sequence, x.id)):
            # If factor is passed, calculate used quantity based on the parent quantity
            used_quantity = tools.float_round(
                rec.product_qty if factor is None else rec.product_qty * factor,
                precision_rounding=rec.product_uom_id.rounding
            )
            avg_cost = tools.float_round(rec.average_cost, precision_digits=precision)
            data_to_render = {
                'hierarchy_level': hierarchy_level,
                'product_name': rec.product_id.display_name,
                'location_src_name': rec.location_src_id.display_name,
                'product_qty': '%f' % used_quantity,  # Preserve all the decimal points (does not convert to *e-05)
                'product_uom_name': rec.product_uom_id.display_name,
                'average_cost': '%.{}f'.format(precision) % avg_cost,
                'style': 'color: {}'.format(color),
            }
            template = 'robo_mrp.bom_line_template'
            # If production is passed use different template
            if production:
                location = rec.location_src_id if rec.location_src_id else production.location_src_id
                quantities = rec.product_id.get_product_quantities(
                    location=location
                )
                data_to_render.update({
                    'quantity_available': quantities['display_quantity'],
                })
                template = 'robo_mrp.bom_line_production_template'
            # Render the line
            bom_line_html += self.env['ir.qweb'].render(template, data_to_render)
        return bom_line_html

    @api.multi
    def compose_exploded_bom_lines_table(self, factor=None, production=None):
        """
        Used to render and compose HTML table
        from passed record-set data, using every
        child bom and their lines recursively.
        Called from parent BOM record
        :return: Rendered line data (str)
        """
        bom_lines = str()
        if not self.env.user.has_group('robo_mrp.group_recursive_bom_production'):
            return bom_lines

        # Build extra context, to get the BOMs at specific date
        # firstly, if production record is passed, take it from there
        bom_at_date = production and production.date_planned_start
        validity_dates = self.env.user.has_group('robo_mrp.group_bom_expiry_dates')
        for rec in self.sorted(key=lambda x: (x.sequence, x.id)):
            # If bom at date is empty, take current parent line's
            # validity date from as BOM at date checker
            if not bom_at_date and validity_dates and rec.bom_id.valid_from:
                bom_at_date = rec.bom_id.valid_from
            bom_lines += rec.with_context(bom_at_date=bom_at_date).render_bom_recursive(
                parent_line=rec, factor=factor, production=production)
        return bom_lines

    # Recursive production move prep methods --------------------------------------------------------------------------

    @api.multi
    def split_bom_lines(self, production, factor=None):
        """
        Creates split stock moves from current BOM lines.
        Executed in in two different modes:
        * Every BOM line is recursively exploded
          until the very first BOM
        * Only the lines that have insufficient usable
          quantity are recursively exploded
        :param production: Mrp Production record
        :param factor: Factor - Production quantity / Bom quantity
        :return: list of stock.move data to create
        """
        base_stock_move_data = []

        # Build extra context, to get the BOMs at production date
        bom_at_date = production and production.date_planned_start

        # Explode every move if production mode is explode_all
        if production.recursive_bom_production_mode == 'explode_all':
            for rec in self:
                base_stock_move_data += rec.with_context(
                    bom_at_date=bom_at_date).split_bom_lines_recursive(
                    production, rec, factor=factor
                )
        # Explode only those moves that have insufficient quantity to use
        elif production.recursive_bom_production_mode == 'explode_no_stock':
            for rec in self:
                location = rec.location_src_id or production.location_src_id
                quantities = rec.product_id.get_product_quantities(location=location)
                usable_quantity = quantities['usable_quantity']
                # Get needed quantity
                needed_quantity = rec.product_qty if factor is None else rec.product_qty * factor
                # If needed quantity is higher than usable, split the bom lines
                if tools.float_compare(
                        needed_quantity, usable_quantity,
                        precision_rounding=rec.product_uom_id.rounding) > 0:
                    base_stock_move_data += rec.with_context(
                        bom_at_date=bom_at_date).split_bom_lines_recursive(
                        production, rec, factor=factor
                    )
                else:
                    # Otherwise prepare a move from base line
                    base_stock_move_data += rec.prepare_split_stock_move(production, rec, factor=factor)
        return base_stock_move_data

    @api.multi
    def split_bom_lines_recursive(self, production, parent_line, factor=None):
        """
        Recursively splits BOM lines and prepares stock move
        data that is used for record creation.
        :param production: Mrp Production record
        :param parent_line: Parent most Mrp BOM line record
        :param factor: Factor - Recursively passed bom factor
        :return: list of stock.move data to create
        """
        self.ensure_one()
        base_stock_move_data = []

        # If we detect parent BOM product in recursive BOM lines,
        # we stop splitting process for this specific BOM tree and just prepare the move
        bom_products = self.product_id.bom_id.bom_line_ids.mapped('product_id')
        variants = parent_line.bom_id.product_tmpl_id.with_context(active_test=False).product_variant_ids
        pb_product = variants and variants[0]
        pbl_product = parent_line.product_id

        if not self.product_id.product_tmpl_id.skip_recursive_bom_splitting and \
                self.product_id.bom_id and pb_product not in bom_products and pbl_product not in bom_products:
            # Calculate the factor, reduced down recursively
            product_qty = self.product_qty * factor if factor else self.product_qty
            # P3:DivOK
            factor = product_qty / self.product_id.bom_id.product_qty
            # We loop through current line's product BOM lines if they exist,
            # increase the hierarchy level, and render them recursively
            for line in self.product_id.bom_id.bom_line_ids.sorted(key=lambda x: (x.sequence, x.id)):
                base_stock_move_data += line.split_bom_lines_recursive(
                    production, parent_line, factor=factor,
                )
        else:
            base_stock_move_data += self.prepare_split_stock_move(
                production, parent_line, factor=factor,
            )
        # Return rendered line's HTML
        return base_stock_move_data

    @api.multi
    def prepare_split_stock_move(self, production, parent_line, factor):
        """
        Prepares stock move data for
        split recursive production
        :param production: production record
        :param parent_line: Parent most bom line
        :param factor: unit factor
        :return: stock.move data (list)
        """
        stock_move_data = []
        for rec in self:
            # Search for location id for current split raw material
            source_location = rec.location_src_id or production.location_src_id
            # If factor is passed, calculate used quantity based on the parent quantity
            quantity = tools.float_round(
                rec.product_qty if factor is None else rec.product_qty * factor,
                precision_rounding=rec.product_uom_id.rounding
            )
            data = {
                'name': production.name,
                'date': production.date_planned_start,
                'date_expected': production.date_planned_start,
                'bom_line_id': parent_line.id,
                'product_id': rec.product_id.id,
                'product_uom_qty': quantity,
                'product_uom': rec.product_uom_id.id,
                'location_id': source_location.id,
                'location_dest_id': production.product_id.property_stock_production.id,
                'operation_id': rec.operation_id.id or parent_line.operation_id.id,
                'raw_material_production_id': production.id,
                'company_id': production.company_id.id,
                'price_unit': rec.product_id.standard_price,
                'procure_method': 'make_to_stock',
                'origin': production.name,
                'warehouse_id': source_location.get_warehouse().id,
                'group_id': production.procurement_group_id.id,
                'propagate': production.propagate,
                'unit_factor': quantity / rec.product_qty if rec.product_qty else 0,  # P3:DivOK
            }
            stock_move_data.append(data)
        return stock_move_data

    @api.multi
    def find_child_bom_line_recursive(self, product, level=0):
        """
        Searches for child BOM line based on product
        by recursively exploding all of the related
        BOMs of the current passed parent line
        :param product: product.product (record)
        :param level: indicates recursion level
        :return: mrp.bom.line (record)
        """
        self.ensure_zero_or_one()

        found_line = self.env['mrp.bom.line']
        current_bom = self.product_id.bom_id
        # If recursion level is exceeded, do not execute any further
        if current_bom and level <= CHILD_BOM_RECURSION_COUNT:
            bom_lines = current_bom.bom_line_ids
            products = bom_lines.mapped('product_id')
            if product not in products:
                # We loop through current line's product BOM lines if they exist,
                # increase the recursion level, and search for the BOM line
                for line in bom_lines:
                    found_line = line.find_child_bom_line_recursive(
                        product, level=level+1)
                    if found_line:
                        break
            else:
                found_line = bom_lines.filtered(
                    lambda x: x.product_id.id == product.id)
        return found_line

    @api.multi
    def calculate_avg_cost_recursive(self, factor, recursive_mode=False):
        """
        Calculates average cost recursively by going through each
        :param factor: Indicates product quantity ration factor
        based on the parent product quantity in the line | FLOAT
        :param recursive_mode: Indicates whether function should
        be used recursively, or whether it should just return
        the value on the first execution run | BOOL
        :return: calculated avg cost | FLOAT
        """
        self.ensure_one()

        # Get the current product qty in the parent bom
        product_qty = self.product_qty * factor if factor else self.product_qty
        average_cost = self.product_id.avg_cost * product_qty
        rounding = self.product_id.uom_id.rounding or 0.00001

        # If average cost is zero, and current product has a bom
        # try to calculate the cost recursively
        if tools.float_is_zero(average_cost, precision_rounding=rounding) \
                and self.product_id.bom_id and recursive_mode:
            # Calculate new factor, and loop through bom lines
            # P3:DivOK
            factor = product_qty / self.product_id.bom_id.product_qty
            for line in self.product_id.bom_id.bom_line_ids:
                average_cost += line.calculate_avg_cost_recursive(factor, recursive_mode)
        return average_cost
