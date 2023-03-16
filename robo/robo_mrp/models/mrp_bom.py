# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, api, exceptions, _, fields, tools
from odoo.addons import decimal_precision as dp
from dateutil.relativedelta import relativedelta
from datetime import datetime


class MrpBom(models.Model):
    _inherit = 'mrp.bom'
    _mail_post_access = 'read'

    type = fields.Selection(
        help='Apdorojant šio produkto pardavimo užsakymą, '
             'pristatymo užsakyme bus nurodytos žaliavos ar galutinis produktas.'
    )
    ready_to_produce = fields.Selection(default='all_available')
    comments = fields.Html(string='Komentarai')

    # Fields used in recursive bom production
    exploded_bom_lines_table = fields.Html(
        string='Sudedamieji komponentai',
        groups='robo_mrp.group_recursive_bom_production',
        compute='_compute_exploded_bom_lines_table'
    )
    # Expiry date fields
    bom_expiry_dates_enabled = fields.Boolean(
        compute='_compute_bom_expiry_dates_enabled'
    )
    duplicate_components_warning = fields.Boolean(
        compute='_compute_duplicate_components_warning',
    )
    valid_from = fields.Date(
        string='Komplektacijos galiojimo pradžia',
        groups='robo_mrp.group_bom_expiry_dates',
        inverse='_set_bom_expiry_dates',
        copy=False, track_visibility='onchange',
    )
    valid_to = fields.Date(
        string='Komplektacijos galiojimo pabaiga',
        groups='robo_mrp.group_bom_expiry_dates',
        inverse='_set_bom_expiry_dates',
        copy=False, track_visibility='onchange',
    )
    # Update DP of the product quantity to match BOM line
    product_qty = fields.Float(
        digits=dp.get_precision('Product Unit of Measure'),
    )

    @api.multi
    @api.depends('bom_line_ids', 'bom_line_ids.product_id')
    def _compute_duplicate_components_warning(self):
        """Check whether BOM has any products that are repeated several times"""
        for rec in self:
            if len(rec.bom_line_ids) != len(rec.bom_line_ids.mapped('product_id')):
                rec.duplicate_components_warning = True

    @api.multi
    @api.depends('product_qty')
    def _compute_bom_expiry_dates_enabled(self):
        """
        Checks whether BOM expiry date functionality is
        enabled in the system. Dummy depends so that
        compute is triggered on record creation
        in the form view as well.
        :return: None
        """
        bom_expiry_dates_enabled = self.sudo().env.user.company_id.enable_bom_expiry_dates
        for rec in self:
            rec.bom_expiry_dates_enabled = bom_expiry_dates_enabled

    @api.multi
    @api.depends('bom_line_ids')
    def _compute_exploded_bom_lines_table(self):
        """
        Computes exploded HTML BOM line table
        with every child component that is included.
        :return: None
        """
        for rec in self:
            bom_lines_html = rec.bom_line_ids.compose_exploded_bom_lines_table()
            rec.exploded_bom_lines_table = self.env['ir.qweb'].render(
                'robo_mrp.bom_line_table_template', {'table_body': bom_lines_html}
            )

    @api.multi
    @api.constrains('bom_line_ids')
    def _check_component_lines(self):
        """
        Ensure that current current BOM
        has at least one line
        :return: None
        """
        for rec in self:
            if not rec.bom_line_ids:
                raise exceptions.ValidationError(_('Jums reikia pasirinkti bent vieną komponentą'))

    @api.multi
    @api.constrains('product_uom_id')
    def _check_product_uom_id(self):
        """Ensure that BOM UOM is the same as product's UOM"""
        for rec in self.filtered(lambda x: x.product_uom_id and x.product_tmpl_id):
            if rec.product_uom_id.category_id.id != rec.product_tmpl_id.uom_id.category_id.id:
                raise exceptions.ValidationError(
                    _('The Product Unit of Measure you chose has a different category than in the product form.')
                )

    @api.multi
    @api.constrains('valid_from', 'valid_to')
    def _check_bom_expiry_dates(self):
        """
        Check various BOM expiry date constraints
        if BOM expiry date functionality is enabled
        :return: None
        """
        # No need to use the compute, one check vs several
        if self.sudo().env.user.company_id.enable_bom_expiry_dates:
            for rec in self:
                # Check if valid_from is set
                if not rec.valid_from:
                    raise exceptions.ValidationError(
                        _('Privalote nustatyti komplektacijos galiojimo pradžios datą.')
                    )
                # Check if valid_to is later than valid_from if it is set
                if rec.valid_to and rec.valid_to < rec.valid_from:
                    raise exceptions.ValidationError(
                        _('Komplektacijos galiojimo pabaigos data privalo būti vėlesnė nei galiojimo pradžios data')
                    )
                # Build base domain
                base_domain = [('state', 'not in', ['done', 'cancel']), ('bom_id', '=', rec.id)]
                if rec.valid_to:
                    base_domain += ['|', ('date_planned_start', '>=', rec.valid_to)]
                # Append only here, so valid to check is ORed with this check
                base_domain += [('date_planned_start', '<=', rec.valid_from)]
                # Check for unconfirmed productions with current BOM, and deny date changing if
                # there are any productions that go outside of the current range of dates
                if self.env['mrp.production'].search_count(base_domain):
                    raise exceptions.ValidationError(
                        _('Negalite keisti šios komplektacijos galiojimo datų, egzistuoja nepatvirtintų '
                          'gamybų naudojančių šią komplektaciją. '
                          'Patvirtinkite šias gamybas arba kurkite komplektacijos kopiją')
                    )

    @api.constrains('active')
    def _check_active(self):
        """
        Ensure that BOM cannot be set to active if it has related running productions
        it not draft or done states. Dynamic productions are filtered out,
        their BOM activity status is changed on each component modification
        :return: None
        """
        inactive_recs = self.filtered(lambda x: not x.active)
        if inactive_recs:
            mrp_productions = self.env['mrp.production'].search_count([
                ('bom_id', 'in', inactive_recs.ids),
                ('state', 'not in', ['done', 'cancel']),
                ('production_type', '=', 'static'),
            ])
            if mrp_productions:
                raise exceptions.ValidationError(
                    _('You can not archive a Bill of Material with running manufacturing orders.\n'
                      'Please close or cancel it first.')
                )

    @api.multi
    def _set_bom_expiry_dates(self):
        """
        Searches for intersecting bom, if
        intersecting BOM exists, check it's expiry date end and
        raise an error if it's set, otherwise set current BOM expiry date end
        to day before found BOM.
        :return: None
        """
        # No need to use the compute, one check vs several
        if self.sudo().env.user.company_id.enable_bom_expiry_dates:
            for rec in self:
                active_bom = rec.get_intersecting_bom(rec.valid_from, rec.valid_to)
                if active_bom:
                    # If active bom exists, and current bom has not end date and
                    # has start date earlier than found BOM, set it's end date
                    # to day before the found BOM start date
                    if not rec.valid_to and rec.valid_from < active_bom.valid_from:
                        end_date_dt = (datetime.strptime(
                            active_bom.valid_from, tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(days=1)
                        ).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                        rec.valid_to = end_date_dt
                    else:
                        # Exception is raised otherwise
                        raise exceptions.ValidationError(
                            _('Šis produktas turi galiojančią komplektaciją kuri kertasi su paduotu perdiodu. '
                              'Rastos komplektacijos datos: {} - {}.').format(
                                active_bom.valid_from, active_bom.valid_to or '/')
                        )

    @api.multi
    def get_intersecting_bom(self, valid_from, valid_to=None):
        """
        Searches for intersecting BOM based on passed
        expiry dates. Method is only used if expiry
        date functionality is enabled in the system
        :param valid_from: BOM valid_from
        :param valid_to: BOM valid_to
        :return: BOM record-set
        """
        self.ensure_one()
        # Gets base domain
        base_domain = self.with_context(get_base_domain=True).get_bom_find_domain(
            product_tmpl=self.product_tmpl_id, product=self.product_id
        )
        base_domain += [('id', '!=', self.id)]

        # Check 1: Firstly check if there's a BOM without any dates
        # set, this could be the case if there were already BOMs
        # before BOM expiry dates were activated. If that's the case
        # raise an error for them to configure it
        if self.search_count(base_domain + [('valid_from', '=', False), ('valid_to', '=', False)]):
            raise exceptions.ValidationError(
                _('Šis produktas turi komplektaciją kuri neturi nustatytų galiojimo datų. '
                  'Minima komplektacija buvo sukurta prieš galiojimo datų funkconalumo įgalinimą.'
                  'Sukonfigūruokite visų šio produktų komplektacijų datas')
            )
        # Check 2: Only date from is passed
        # Form the domain to search for intersection
        if valid_from and not valid_to:
            base_domain += [
                '&', '|',
                ('valid_from', '>=', valid_from),
                ('valid_from', '<=', valid_from),
                '|',
                ('valid_to', '=', False),
                ('valid_to', '>=', valid_from),
            ]
        # Check 3: both of the dates are passed
        # Form the domain to search for intersection
        elif valid_to:
            base_domain += [
                '|', '|', '&',
                ('valid_from', '<=', valid_from),
                ('valid_to', '>=', valid_from),
                '&',
                ('valid_from', '<=', valid_to),
                ('valid_from', '>=', valid_from),
                '&',
                ('valid_to', '=', False),
                ('valid_from', '<=', valid_from),
            ]
        # Return the result
        return self.search(base_domain, limit=1)

    @api.multi
    def copy(self, default=None):
        """
        Copy method instantly creates the record, thus constraints get
        triggered before user gets thew view of the new record.
        We cannot put copy=False on validity dates because it's not null,
        but we also cannot copy them because they cant intersect,
        thus we have to set dummy, not-intersecting dates
        """

        self.ensure_one()
        if not self._context.get('wizard_call') and self.bom_expiry_dates_enabled:
            valid_from = None
            # Get the base domain
            base_domain = self.with_context(get_base_domain=True).get_bom_find_domain(
                product_tmpl=self.product_tmpl_id, product=self.product_id
            )
            latest_bom = self.env['mrp.bom'].search(base_domain, order='valid_from desc, valid_to desc', limit=1)
            # If latest bom has valid date to - new record's valid_from is plus one day
            if latest_bom.valid_to:
                valid_from = (datetime.strptime(
                    latest_bom.valid_to, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)).strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT
                )
            else:
                # If latest bom does not have valid date to,
                # get earliest bom - new record's valid_from is minus one day
                earliest_bom = self.env['mrp.bom'].search(base_domain, order='valid_from', limit=1)
                if earliest_bom:
                    if not earliest_bom.valid_from:
                        raise exceptions.ValidationError(
                            _('Negalite atlikti šio veiksmo - rasta kitų šio produkto komplektacijų kurios neturi '
                              'galiojimo pradžios datos. Sukonfigūruokite datas ir pakartokite veiksmą.')
                        )
                    valid_from = (datetime.strptime(
                        earliest_bom.valid_from, tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(days=1)).strftime(
                        tools.DEFAULT_SERVER_DATE_FORMAT
                    )
            if valid_from:
                default = {} if default is None else default
                # Update default vals
                default.update({
                  'valid_from': valid_from,
                  'valid_to': valid_from,
                })
        return super(MrpBom, self).copy(default)

    @api.multi
    def recalculate_bom_line_table(self):
        """
        Used to manually recompute the HTML
        table for current bom exploded components
        :return: None
        """
        self.ensure_one()
        self._compute_exploded_bom_lines_table()

    @api.multi
    def valid_bom(self, date):
        """
        Check if current BOM is valid
        :param date: date to check against
        :return: True if valid, otherwise False
        """
        self.ensure_one()

        def convert_to_dt(in_date):
            """Convert passed date-string to datetime object"""
            try:
                date_dt = datetime.strptime(in_date, tools.DEFAULT_SERVER_DATE_FORMAT)
            except (ValueError, TypeError):
                date_dt = datetime.strptime(in_date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            return date_dt

        if self.bom_expiry_dates_enabled and self.active:
            # Convert dates to datetime objects
            at_date_dt = convert_to_dt(date)
            valid_from_dt = convert_to_dt(self.valid_from)
            valid_to_dt = None
            if self.valid_to:
                # Checks are executed for datetime objects
                valid_to_dt = convert_to_dt(self.valid_to) + relativedelta(hour=23, minute=59, second=59)
            if valid_from_dt > at_date_dt or valid_to_dt and valid_to_dt < at_date_dt:
                return False
        return True

    @api.model
    def get_bom_find_domain(self, product_tmpl=None, product=None, picking_type=None, company_id=False):
        """
        Override of the get_bom_find_domain //
        Added expiry date checks to the
        domain if functionality is enabled in the company
        """
        # Call the parent method to form base domain
        domain = super(MrpBom, self).get_bom_find_domain(product_tmpl, product, picking_type, company_id)
        if domain:
            get_base_domain = self._context.get('get_base_domain')
            # If expiry dates are enabled, get the date from context otherwise use current date
            if self.sudo().env.user.company_id.enable_bom_expiry_dates and not get_base_domain:
                bom_at_date = self._context.get('bom_at_date')
                if not bom_at_date:
                    bom_at_date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                # Add date checks to domain
                domain += [
                    ('valid_from', '<=', bom_at_date),
                    '|',
                    ('valid_to', '=', False),
                    ('valid_to', '>=', bom_at_date),
                ]
        return domain

    @api.multi
    def explode_bom_recursively(self, production, factor=None, create_moves=False):
        """
        Splits current bom lines and aggregates the moves
        :param production: related mrp production record
        :param create_moves: Flag that indicates whether exploded moves
        should be created after grouping
        :param factor: Rate of the production quantity vs current bom quantity
        :return: Dictionary of grouped bom lines by ID key
        """
        self.ensure_one()
        # Calculate the factor based on production record if it's not passed
        if factor is None:
            # P3:DivOK
            factor = production.product_uom_id._compute_quantity(
                production.product_qty, self.product_uom_id) / self.product_qty
        # Split current bom lines
        stock_move_data = self.bom_line_ids.split_bom_lines(production=production, factor=factor)
        # Aggregate the move data based on location, product, operation and unit factor
        grouped_data = {}
        for move in stock_move_data:
            # Compose a key - product/location/operation
            key = '{}/{}/{}'.format(
                move['product_id'], move['location_id'], move['operation_id']
            )
            if key not in grouped_data:
                grouped_data[key] = move
            else:
                grouped_data[key]['product_uom_qty'] += move['product_uom_qty']
        # Check whether moves should be created
        if create_moves:
            for move in grouped_data.values():
                self.env['stock.move'].create(move)
        return grouped_data

    @api.multi
    def message_subscribe(self, partner_ids=None, channel_ids=None, subtype_ids=None, force=True):
        # ROBO allow post to the accountant (without write access rights):
        res = super(MrpBom, self).message_subscribe(partner_ids=partner_ids,
                                                    channel_ids=channel_ids,
                                                    subtype_ids=subtype_ids,
                                                    force=force,
                                                    create_allow=True)
        return res

    @api.multi
    def action_open_bom_export_wizard(self):
        """
        Called from a button, opens BOM
        PDF/XLS export wizard
        :return: JS action dict
        """
        self.ensure_one()
        if not self.bom_line_ids:
            raise exceptions.ValidationError(_('Negalite eksportuoti komplektacijos, nerasti susiję komponentai'))
        # Create the wizard
        wizard = self.env['mrp.bom.export.wizard'].create({'bom_id': self.id})
        return {
            'name': _('Eksportuoti komplektaciją'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mrp.bom.export.wizard',
            'view_id': self.env.ref('robo_mrp.form_mrp_bom_export_wizard').id,
            'target': 'new',
            'res_id': wizard.id,
            'context': self.env.context,
        }

    @api.multi
    def action_open_bom_proportion_wizard(self):
        """
        Called from a button, opens BOM proportion calculation wizard
        :return: JS action dict
        """
        self.ensure_one()
        if not self.bom_line_ids:
            raise exceptions.ValidationError(_('You cannot calculate proportions for a bom with no lines'))
        # Create the wizard
        wizard = self.env['mrp.bom.proportion.wizard'].create({
            'bom_id': self.id,
            'quantity': self.product_qty,
        })
        return {
            'name': _('Proportion calculation wizard'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mrp.bom.proportion.wizard',
            'view_id': self.env.ref('robo_mrp.mrp_bom_proportion_wizard_view_form').id,
            'target': 'new',
            'res_id': wizard.id,
            'context': self.env.context,
        }

    @api.multi
    def action_open_bom_copy_wizard(self):
        """
        Create and return the action to bom copy wizard
        :return: JS action dict
        """
        self.ensure_one()
        wizard_values = {'bom_id': self.id, }

        # Check for expiry date functionality
        if self.bom_expiry_dates_enabled:
            # If current BOM has valid date to, prepare default wizard dates
            if self.valid_to:
                dst_valid_from = (datetime.strptime(
                    self.valid_to, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)).strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT)
                wizard_values.update({
                    'src_valid_to': self.valid_to,
                    'dst_valid_from': dst_valid_from,
                })

        # Create the wizard
        wizard = self.env['mrp.bom.copy.wizard'].create(wizard_values)
        # Manually trigger the onchange
        wizard.onchange_valid_from()
        return {
            'name': _('Komplektacijų kopijavimo vedlys'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mrp.bom.copy.wizard',
            'view_id': self.env.ref('robo_mrp.form_mrp_bom_copy_wizard').id,
            'target': 'new',
            'res_id': wizard.id,
            'context': self.env.context,
        }

    @api.model
    def create_action_archive_mrp_bom_multi(self):
        action = self.env.ref('robo_mrp.action_archive_mrp_bom_multi')
        if action:
            action.create_action()
