# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, api, fields, tools, exceptions, _
from odoo.tools import float_compare, float_round
from datetime import datetime
from dateutil.relativedelta import relativedelta
from pytz import timezone
import logging
from odoo.addons.queue_job.job import identity_exact, job

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = 'mrp.production'
    _order = 'date_planned_start desc,id'

    @api.model
    def _get_default_force_accounting_date(self):
        """Get forced accounting date from company settings"""
        return self.env.user.company_id.force_accounting_date

    @api.model
    def _get_default_location_src_id(self):
        """Get default source location"""
        location = False
        company = self.env.user.sudo().company_id
        # Check if default production locations are disabled
        if not company.disable_default_production_locations:
            if company.default_mrp_production_location_src_id:
                location = self.env.user.sudo().company_id.default_mrp_production_location_src_id.id
            location = location or super(MrpProduction, self)._get_default_location_src_id()
        return location

    @api.model
    def _get_default_location_dest_id(self):
        """Get default destination location"""
        location = False
        company = self.env.user.sudo().company_id
        # Check if default production locations are disabled
        if not company.disable_default_production_locations:
            if self.env.user.sudo().company_id.default_mrp_production_location_dest_id:
                location = self.env.user.sudo().company_id.default_mrp_production_location_dest_id.id
            location = location or super(MrpProduction, self)._get_default_location_dest_id()
        return location

    @api.model
    def _get_default_picking_type(self):
        """
        Returns default picking type for current production. If disable default locations
        is set on the company, search is not executed
        """
        company = self.env.user.sudo().company_id
        if company.disable_default_production_locations:
            return

        search_domain = [
            ('code', '=', 'mrp_operation'),
            ('warehouse_id.company_id', 'in', [self.env.context.get('company_id', self.env.user.company_id.id), False])
        ]
        src_domain = []
        dest_domain = []
        if self.env.user.sudo().company_id.default_mrp_production_location_dest_id:
            dest_domain = ('default_location_dest_id.warehouse_id', '=',
                           self.env.user.sudo().company_id.default_mrp_production_location_dest_id.warehouse_id.id)
        if self.env.user.sudo().company_id.default_mrp_production_location_src_id:
            src_domain = ('default_location_src_id.warehouse_id', '=',
                          self.env.user.sudo().company_id.default_mrp_production_location_src_id.warehouse_id.id)
        picking_type = self.env['stock.picking.type'].search(
            search_domain + [d for d in [src_domain, dest_domain] if d], limit=1)
        if not picking_type:
            if src_domain and dest_domain:
                extra_domain = [('|'), src_domain, dest_domain]
            else:
                extra_domain = []
            picking_type = self.env['stock.picking.type'].search(search_domain + extra_domain, limit=1)
        return picking_type.id

    location_src_id = fields.Many2one(default=_get_default_location_src_id)
    location_dest_id = fields.Many2one(default=_get_default_location_dest_id)
    picking_type_id = fields.Many2one(default=_get_default_picking_type, sequence=100)

    force_accounting_date = fields.Boolean(
        string='Priverstinė apskaitos data',
        default=_get_default_force_accounting_date,
        states={'done': [('readonly', 'True')], 'cancel': [('readonly', 'True')]},
    )

    accounting_date = fields.Datetime(
        string='Apskaitos data', default=fields.Datetime.now,
        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]},
        copy=False
    )
    localized_accounting_date = fields.Datetime(compute='_compute_localized_accounting_date')
    cancel_move_raw_ids = fields.One2many(
        'stock.move', 'cancel_raw_material_production_id',
        copy=False, readonly=True, sequence=100,
    )
    cancel_move_finished_ids = fields.One2many(
        'stock.move', 'cancel_production_id',
        copy=False, readonly=True, sequence=100,
    )
    date_planned_start = fields.Datetime(
        readonly=False, inverse='_propagate_planned_date',
        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}
    )
    user_id = fields.Many2one(
        'res.users', readonly=False,
        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}
    )
    origin = fields.Char(
        readonly=False, states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}, sequence=100,
    )
    availability = fields.Selection([
        ('assigned', 'Rezervuota'),
        ('partially_available', 'Dalinai rezervuota'),
        ('waiting', 'Laukiama atsargų'),
        ('none', 'Nėra')])

    state = fields.Selection([('draft', 'Juodraštis'),
                              ('confirmed', 'Paruošta'),
                              ('planned', 'Suplanuota'),
                              ('progress', 'Vykdoma'),
                              ('done', 'Patvirtinta'),
                              ('cancel', 'Atšaukta')])

    product_qty = fields.Float(inverse='_set_final_product_qty', track_visibility='onchange')

    bom_id = fields.Many2one('mrp.bom', required=False, sequence=100)

    move_raw_ids_second = fields.One2many(
        'stock.move', 'raw_material_production_id', 'Komponentai', oldname='move_lines',
        copy=False, states={'done': [('readonly', True)], 'cancel': [('readonly', True)]},
        domain=[('scrapped', '=', False)], sequence=100)
    move_raw_ids = fields.One2many(inverse='_inverse_move_raw_ids', sequence=100)

    production_type = fields.Selection([
        ('dynamic', 'Kintantis'),
        ('static', 'Fiksuotas')], string='Gamybos tipas', required=True, default='static')

    company_dynamic = fields.Boolean(compute='_compute_company_dynamic')
    let_modify = fields.Boolean(compute='_compute_let_modify')
    saved_mo = fields.Boolean(compute='_compute_saved_mo')
    created_components = fields.Boolean(compute='_compute_created_components')

    # Recursive BOM production fields
    recursive_bom_production_mode = fields.Selection(
        [('explode_none', 'Neskleisti sudėtinių komponentų'),
         ('explode_all', 'Išskleisti visus sudėtinius komponentus'),
         ('explode_no_stock', 'Išskleisti sudėtinius komponentus trūkstant atsargų'),
         ], string='Sudėtiniu komplektacijų gaminimo būdas',
        compute='_compute_recursive_bom_production', store=True
    )
    recursive_bom_production = fields.Boolean(
        compute='_compute_recursive_bom_production',
        store=True, sequence=100
    )
    modification_rule_production = fields.Boolean(
        compute='_compute_modification_rule_production',
    )
    exploded_bom_table = fields.Html(
        string='Visi sudėtiniai komponentai',
        compute='_compute_bom_tables', store=True,
        sequence=100,
    )
    parent_bom_component_table = fields.Html(
        string='Pagrindiniai komponentai',
        compute='_compute_bom_tables', store=True,
        sequence=100,
    )

    # Production modification rule group
    production_modification_rule_ids = fields.One2many(
        'mrp.production.modification.rule', 'production_id',
        string='Gamybos komplektacijos modifikavimo taisyklės',
        sequence=100,
    )

    workorder_ids = fields.One2many(sequence=100)
    scrap_ids = fields.One2many(sequence=100)
    routing_id = fields.Many2one(sequence=100)
    propagate = fields.Boolean(sequence=100)
    product_uom_id = fields.Many2one(sequence=100)
    product_tmpl_id = fields.Many2one(sequence=100)
    procurement_ids = fields.One2many(sequence=100)
    procurement_group_id = fields.Many2one(sequence=100)
    post_visible = fields.Boolean(sequence=100)
    move_finished_ids = fields.One2many(sequence=100)
    message_partner_ids = fields.Many2many(sequence=100)
    message_needaction = fields.Boolean(sequence=100)
    message_last_post = fields.Datetime(sequence=100)
    message_is_follower = fields.Boolean(sequence=100)
    message_ids = fields.One2many(sequence=100)
    message_follower_ids = fields.One2many(sequence=100)
    message_channel_ids = fields.Many2many(sequence=100)

    @api.multi
    def _compute_created_components(self):
        """
        Check whether any raw moves exist for current production
        :return: None
        """
        for rec in self:
            rec.created_components = rec.move_raw_ids | rec.move_raw_ids_second

    @api.multi
    @api.depends('accounting_date')
    def _compute_localized_accounting_date(self):
        """
        Computes localized forced accounting date
        based on context timezone (If empty uses Europe/Vilnius)
        :return: None
        """
        for rec in self.filtered(lambda x: x.accounting_date):
            date = rec.accounting_date
            try:
                time_z = self._context.get('tz') or 'Europe/Vilnius'
                diff = int(round((datetime.now(
                    timezone(time_z)).replace(tzinfo=None) - datetime.utcnow()).total_seconds(), 0))
                value_dt = datetime.strptime(
                    rec.accounting_date, tools.DEFAULT_SERVER_DATETIME_FORMAT
                ) + relativedelta(seconds=diff)
                date = value_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            except Exception as exc:
                _logger.info('Production: Failed to localize accounting date. {}'.format(exc.args[0]))
            rec.localized_accounting_date = date

    @api.multi
    @api.depends('bom_id', 'production_type', 'product_qty', 'recursive_bom_production', 'product_uom_id')
    def _compute_bom_tables(self):
        """
        Computes exploded HTML stock move table
        with every child component that is included
        :return: None
        """
        for rec in self:
            if rec.bom_id and rec.product_uom_id and rec.production_type == 'static' and rec.recursive_bom_production:
                # P3:DivOK
                factor = rec.product_uom_id._compute_quantity(
                    rec.product_qty, rec.bom_id.product_uom_id) / rec.bom_id.product_qty
                # Render all exploded lines
                bom_lines_html = rec.bom_id.bom_line_ids.compose_exploded_bom_lines_table(
                    factor=factor, production=rec
                )
                rec.exploded_bom_table = self.env['ir.qweb'].render(
                    'robo_mrp.bom_line_production_table_template', {'table_body': bom_lines_html}
                )
                # Render only parent bom lines
                parent_bom_lines_html = rec.bom_id.bom_line_ids.render_bom_lines(factor=factor, production=rec)
                rec.parent_bom_component_table = self.env['ir.qweb'].render(
                    'robo_mrp.bom_line_production_table_template', {'table_body': parent_bom_lines_html}
                )

    @api.multi
    @api.depends('bom_id')
    def _compute_recursive_bom_production(self):
        """
        Compute recursive production mode
        and whether it's activated or not, based
        on data set in the company.
        :return: None
        """
        # We store this value so we can preserve
        # the history of recursive productions
        company = self.sudo().env.user.company_id
        for rec in self:
            rec.recursive_bom_production = company.enable_recursive_bom_production
            if company.enable_recursive_bom_production:
                rec.recursive_bom_production_mode = company.recursive_bom_production_mode

    @api.multi
    def _compute_modification_rule_production(self):
        """
        Check whether modification rules for
        the production are enabled
        :return: None
        """
        # Check whether modification rules are enabled in the system
        modification_enabled = self.sudo().env.user.company_id.enable_production_modification_rules
        for rec in self:
            rec.modification_rule_production = modification_enabled

    @api.multi
    @api.depends('force_accounting_date')
    def _compute_company_dynamic(self):
        """
        Compute production type based
        on settings in res company.
        :return: None
        """
        company = self.env.user.company_id
        for rec in self:
            rec.company_dynamic = company.mrp_type == 'dynamic'

    @api.one
    @api.depends('force_accounting_date', 'production_type')
    def _compute_let_modify(self):
        if self.company_dynamic and self.production_type == 'dynamic':  # and not self.create_date:
            self.let_modify = True
        else:
            self.let_modify = False

    @api.one
    def _compute_saved_mo(self):
        self.saved_mo = bool(self.create_date)

    @api.multi
    @api.constrains('bom_id', 'production_type', 'date_planned_start')
    def _check_base_constraints(self):
        """Check base production constraints"""
        for rec in self:
            if not rec.bom_id:
                raise exceptions.ValidationError(
                    _('Nenustatyta komplektacija')
                )
            if rec.production_type == 'dynamic' and rec.bom_id.active:
                raise exceptions.ValidationError(
                    _('Jūs negalite naudoti šios komplektacijos kintančiai gamybai')
                )
            if rec.production_type == 'static' and not rec.bom_id.valid_bom(rec.date_planned_start):
                raise exceptions.ValidationError(
                    _('Gamybos [{}] data nepatenka į susijusios komplektacijos galiojimo periodą: {} - {}').format(
                        rec.name, rec.bom_id.valid_from, rec.bom_id.valid_to or _('Neapibrėžta'))
                )

    @api.onchange('picking_type_id')
    def onchange_picking_type(self):
        """
        Override of add-ons method. Added surrounding if statement, that only
        changes the location if picking type is set.
        :return: None
        """
        if self.picking_type_id:
            location = self.env.ref('stock.stock_location_stock')
            self.location_src_id = self.picking_type_id.default_location_src_id.id or location.id
            self.location_dest_id = self.picking_type_id.default_location_dest_id.id or location.id

    @api.onchange('date_planned_start')
    def _onchange_date_planned_start(self):
        """
        If date planned is changed and bom expiry dates are enabled,
        return the domain to filter out products with expired BOMs.
        :return: JS domain (dict)
        """
        if self.production_type == 'static' and self.sudo().env.user.company_id.enable_bom_expiry_dates:
            # Do not reset products if there are components
            if not self.created_components:
                self.product_id = False
            date = self.date_planned_start or datetime.now().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            base_domain = self.get_base_product_domain()
            base_domain += [
                ('bom_ids', '!=', False),
                ('bom_ids.active', '=', True),
                ('bom_ids.valid_from', '<=', date),
                '|',
                ('bom_ids.valid_to', '=', False),
                ('bom_ids.valid_to', '>=', date),
            ]
            return {'domain': {'product_id': base_domain}}

    @api.onchange('production_type')
    def _onchange_production_type(self):
        """
        If production type is changed either return the domain
        to filter out all products without BOMs (static mode), or
        filter out all products that are not of type product (dynamic mode)
        :return: JS domain (dict)
        """
        # Split to separate method because we do not want to reset product_id
        # on date_planned_start change, UNLESS bom_expiry_dates are activated
        base_domain = self.get_base_product_domain()
        if self.production_type == 'static':
            self.product_id = False
            base_domain += [('bom_ids', '!=', False), ('bom_ids.active', '=', True)]
        return {'domain': {'product_id': base_domain}}

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
            ('product_id', '=', self.product_id.id), '&',
            ('product_tmpl_id.product_variant_ids', '=', self.product_id.id),
            ('product_id', '=', False),
            ('type', '=', 'normal')
        ]
        if self.sudo().env.user.company_id.enable_bom_expiry_dates:
            # If expiry dates are enabled, get bom date to check against
            date = self.date_planned_start or datetime.now().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            base_domain += [
                ('valid_from', '<=', date),
                '|',
                ('valid_to', '=', False),
                ('valid_to', '>=', date),
            ]
        return {'domain': {'bom_id': base_domain}}

    @api.onchange('bom_id')
    def _onchange_bom_id(self):
        if self.bom_id:
            if not self.bom_id.product_tmpl_id.active:
                raise exceptions.UserError(
                    _('Gaminys yra suarchyvuotas, pakeiskite komplektaciją arba aktyvuokite produktą.'))
            self.product_id = self.bom_id.product_tmpl_id.product_variant_ids[0]

    @api.one
    def _inverse_move_raw_ids(self):
        if self.env.context.get('do_not_inverse_move_raw_ids'):
            return
        if self.production_type == 'dynamic' and self.product_id:
            bom_vals = {
                'product_id': self.product_id.id,
                'product_tmpl_id': self.product_id.product_tmpl_id.id,
                'product_uom_id': self.bom_id.product_uom_id.id,
                'product_qty': self.product_qty,
                'active': False,
                'bom_line_ids': [(5,)] + [(0, 0, {
                    'product_id': line.product_id.id,
                    'product_qty': line.product_uom_qty,
                    'product_uom_id': line.product_uom.id,
                    'location_src_id': line.location_id.id,
                }) for line in self.move_raw_ids_second or self.move_raw_ids]
            }
            self.bom_id.write(bom_vals)
            original_quantity = self.product_qty
            for line in self.with_context(do_not_inverse_move_raw_ids=True).move_raw_ids:
                # P3:DivOK
                line.write({'unit_factor': line.product_uom_qty / original_quantity if original_quantity else 0})
        # self._adjust_procure_method()
        # self.move_raw_ids.action_confirm()

    @api.multi
    def _set_final_product_qty(self):
        """
        Do not allow changes to produced quantity if state is in cancel or done,
        and execute extra unit_factor calculations if production is dynamic.
        :return: None
        """
        for rec in self:
            if rec.state in ['done', 'cancel']:
                raise exceptions.UserError(
                    _('Jūs negalite pakeisti kiekio, kadangi gamyba yra atlikta arba yra atšaukta'))
            if rec.production_type == 'dynamic':
                rec.move_finished_ids.write({'product_uom_qty': rec.product_qty})
                original_quantity = rec.product_qty
                for line in rec.with_context(do_not_inverse_move_raw_ids=True).move_raw_ids:
                    # P3:DivOK
                    line.write({'unit_factor': line.product_uom_qty / original_quantity if original_quantity else 0})

    @api.multi
    def action_set_draft(self):
        """Un-reserves and deletes related moves. State is set to draft"""
        # create_moves=False only un-reserves and deletes the moves
        for rec in self:
            if rec.production_type == 'dynamic':
                raise exceptions.ValidationError(
                    _('Kintanti gamyba negali būti atstatyta į juodraštį. '
                      'Juodraščio būseną galima naudoti tik tada, kai komponentai yra kūriami automatiškai.')
                )
            if rec.state != 'confirmed':
                raise exceptions.ValidationError(
                    _('Į juodraštį galima atstatyti tik "Paruošta" būsenos gamybas')
                )
        self.recreate_raw_moves(create_new_moves=False)
        self.recreate_finished_moves(create_new_moves=False)
        self.write({'state': 'draft'})

    @api.multi
    def action_confirm_production(self):
        """Creates raw moves for production and sets it to confirmed state"""
        self.recreate_raw_moves()
        self.recreate_finished_moves()
        self.write({'state': 'confirmed'})

    @api.multi
    def recalculate_bom_tables(self):
        """
        Used to manually recompute the HTML tables
        for current bom exploded/parent components
        :return: None
        """
        self.ensure_one()
        self._compute_bom_tables()

    @api.multi
    def _generate_moves(self):
        """
        Complete override of _generate_moves method
        original in addons/mrp/models/mrp_production.
        Most of the behaviour is kept unchanged,
        moves are exploded if recursive production is enabled.
        :return: True (kept from addons)
        """
        for rec in self:
            rec._generate_finished_moves()
            rec.generate_raw_moves()
        return True

    @api.model
    def get_base_product_domain(self):
        """Returns base product domain for production on-changes, meant to be overridden"""
        return [('type', '=', 'product')]

    @api.multi
    def get_failed_to_reserve_moves(self):
        """
        Filters out and returns related
        stock moves that failed to be reserved
        :return: stock.move recordset
        """
        self.ensure_one()
        failed_to_reserve_moves = self.move_raw_ids.filtered(
            lambda x: x.state in ('confirmed', 'waiting', 'assigned') and
            tools.float_compare(
                x.product_uom_qty, x.quantity_available, precision_rounding=x.product_uom.rounding or 0.01) > 0
        )
        return failed_to_reserve_moves

    @api.model
    def create(self, vals):
        if vals.get('production_type') == 'dynamic' and vals.get('bom_id'):
            bom = self.env['mrp.bom'].browse(vals.get('bom_id'))
            if bom.active:
                vals.pop('bom_id')
        if vals.get('production_type') == 'dynamic' and not vals.get('bom_id'):
            if 'product_id' in vals:
                product_id = self.env['product.product'].browse(vals['product_id'])
                bom_vals = {
                    'product_id': product_id.id,
                    'product_tmpl_id': product_id.product_tmpl_id.id,
                    'product_uom_id': vals.get('product_uom_id'),
                    'product_qty': vals.get('product_qty', 1),
                    'active': False
                }
                raw_ids = vals.get('move_raw_ids', [])
                if not raw_ids:
                    raw_ids = vals.get('move_raw_ids_second', [])
                bom_line_ids = []
                for line in raw_ids:
                    line_vals = {
                        'product_id': line[2]['product_id'],
                        'product_qty': line[2]['product_uom_qty'],
                        'product_uom_id': line[2]['product_uom'],
                        'location_src_id': line[2]['location_id'],
                    }
                    bom_line_ids.append((0, 0, line_vals))
                bom_vals['bom_line_ids'] = bom_line_ids
                bom_id = self.env['mrp.bom'].create(bom_vals)
                vals['bom_id'] = bom_id.id
                vals['move_raw_ids'] = []
                vals['move_raw_ids_second'] = []
        res = super(MrpProduction, self.with_context(do_not_inverse_move_raw_ids=True)).create(vals)
        if res.production_type == 'dynamic':
            res.bom_id.code = res.name
        return res

    @api.multi
    def copy(self, default=None):
        self.ensure_one()
        if self.production_type == 'dynamic':
            bom = self.bom_id.copy()
            default = default or {}
            default.update(bom_id=bom.id)
        return super(MrpProduction, self).copy(default)

    @api.multi
    def write(self, vals):
        """
        Write method override for Mrp Production.
        Handles dynamic production extensions.
        :param vals: Written values (dict)
        """
        # Check whether there are any fields that are being written that should trigger dynamic production warnings
        trigger_values = any(
            key for key, val in vals.items() if key in
            ['product_id', 'move_raw_ids', 'move_raw_ids_second', 'product_qty']
        )
        # Check whether there are any assigned dynamic productions
        target_productions = self.filtered(
            lambda x: x.production_type == 'dynamic'
            and x.availability in ['assigned', 'partially_available'] and trigger_values
        )
        if target_productions:
            raise exceptions.ValidationError(
                _('You cannot apply these changes if any of the production components are reserved')
            )
        for move in vals.get('move_raw_ids', []):
            if len(move) == 3 and move[0] == 0:
                if len(self) == 1:
                    # Get the source location
                    source_location = move[2].get('location_id') and self.env['stock.location'].browse(
                        move[2].get('location_id')) or self.env['stock.location']
                    # Compose value dict
                    values = {
                        'name': self.name, 'origin': self.name,
                        'group_id': self.procurement_group_id.id,
                        'warehouse_id': source_location.get_warehouse().id,
                    }
                elif 'raw_material_production_id' in move[2]:
                    production = self.env['mrp.production'].browse(move[2].get('raw_material_production_id'))
                    # Compose value dict
                    values = {
                        'name': production.name, 'origin': production.name,
                        'group_id': production.procurement_group_id.id,
                    }
                else:
                    values = {'name': move[2].get('name') or 'MO/'}
                move[2].update(values)
            if len(move) == 3 and move[0] == 2 and move[1]:
                move = self.env['stock.move'].browse(move[1])
                if move and move.state == 'done':
                    raise exceptions.UserError(_('Negalima ištrinti įrašo (%s)') % move.product_id.name)
                if move:
                    move.do_unreserve()
                    move.action_cancel()
        product_id = vals.get('product_id')
        res = super(MrpProduction, self).write(vals)
        if product_id:
            for rec in self:
                if rec.production_type != 'dynamic':
                    continue
                rec.move_finished_ids.do_unreserve()
                rec.move_finished_ids.action_cancel()
                rec.move_finished_ids.unlink()
                rec._generate_finished_moves()
        return res

    @api.one
    def _propagate_planned_date(self):
        (self.move_raw_ids | self.move_finished_ids).write({
            'date_expected': self.date_planned_start,
            'date': self.date_planned_start,
        })

    @api.multi
    def _get_move_src_location(self, bom_line):
        self.ensure_one()
        return bom_line.location_src_id or super(MrpProduction, self)._get_move_src_location(bom_line)

    @api.multi
    def open_account_move_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.line',
            'view_mode': 'tree,form,pivot',
            'view_type': 'form',
            'views': [(False, 'tree'), (False, 'form'), (False, 'pivot')],
            'target': 'self',
            'context': {'search_default_name': self.name}
        }

    @api.model
    def create_action_production_copy_wizard_multi(self):
        """Creates action for multi production copy wizard"""
        action = self.env.ref('robo_mrp.action_production_copy_wizard_multi')
        if action:
            action.create_action()

    @api.multi
    def action_open_production_copy_wizard(self):
        """
        Create and open mass production copy wizard.
        Can be either called from the form (single production),
        or from the tree, on multi record-set.
        :return: JS action (dict)
        """
        # Filter out canceled productions
        productions = self.filtered(lambda x: x.state not in ['cancel', 'draft'])
        if not productions:
            raise exceptions.ValidationError(_('Nepaduota nė viena tinkamos būsenos gamyba'))

        # Extended copy is not allowed on dynamic productions
        if any(pr.production_type == 'dynamic' for pr in productions):
            raise exceptions.ValidationError(_('Išplėstinę kopiją galite daryti tik fiksuoto tipo gamyboms'))

        # Create the wizard and generate copy lines
        wizard = self.env['mrp.production.copy.wizard'].create({
            'production_ids': [(4, prod.id) for prod in productions]
        })
        wizard.generate_copy_lines()

        return {
            'name': _('Masinis gamybų kopijavimas'),
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.production.copy.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
            'res_id': wizard.id,
            'view_id': self.env.ref('robo_mrp.form_mrp_production_copy_wizard').id,
        }

    def _cal_price(self, consumed_moves):
        self.ensure_one()
        super(MrpProduction, self)._cal_price(consumed_moves)
        production_qty_uom = sum(self.move_finished_ids.mapped('product_uom_qty'))
        for produce_move in self.move_finished_ids:
            is_main_product = (produce_move.product_id == self.product_id) and self.product_id.cost_method == 'real'
            if is_main_product:
                total_cost = consumed_moves._calculate_total_cost()
                # production_cost = self._calculate_workcenter_cost(cr, uid, production_id, context=context)
                # FIXME: Why do we keep this production_cost if hard set to 0 ?
                # P3:DivOK
                price_unit = total_cost / production_qty_uom
                produce_move.write({'price_unit': price_unit})

    @api.multi
    @job
    def produce_simplified(self):
        """ Simplified MRP production """
        self.ensure_one()
        if self.state in ['cancel', 'done']:
            raise exceptions.UserError(_('Negalite tvirtinti gamybos šioje stadijoje'))
        if not self.move_raw_ids:
            raise exceptions.UserError(_('Jūs bandote pagaminti produkciją nesunaudodami jokio produkto!'))
        if not self.force_accounting_date:
            self.accounting_date = fields.Datetime.now()
        consume_moves = self.move_raw_ids
        quantity = self.product_qty
        # TODO: if we want to support partial production, quantity should be computed by substracting self.qty_produced.
        # However, there will be issues with unit factor on partial production, as the rounding of the produced part can
        # be wrong, so the update rule has to be rethough of
        if float_compare(quantity, 0, precision_rounding=self.product_uom_id.rounding) <= 0:
            raise exceptions.UserError(_('Gaminamos produkcijos kiekis turi būti teigiamas'))

        # Do not check the quantities via factoring in explode all or explode no stock
        # since factors are lost when we compose several stock moves from one bom line
        # and same product stock moves are aggregated
        if self.recursive_bom_production_mode in ['explode_all', 'explode_no_stock']:
            for move in consume_moves.filtered(lambda x: x.state not in ('done', 'cancel')):
                move.quantity_done_store = move.product_uom_qty
        else:
            for move in consume_moves.filtered(lambda x: x.product_id.tracking == 'none' and
                                                         x.state not in ('done', 'cancel')):
                if move.unit_factor:
                    rounding = move.product_uom.rounding
                    # This += operation assumes either that quantity is only the quantity difference,
                    # or that there can be no partial production, cf previous todo
                    move.quantity_done_store += float_round(quantity * move.unit_factor, precision_rounding=rounding)
            for move in self.move_raw_ids.filtered(lambda x: x.state not in ('done', 'cancel')):
                # rounding = move.product_uom.rounding
                # ROBO:
                # TODO:autocreate
                rounding = 0.01
                if float_compare(move.quantity_done, move.product_uom_qty, precision_rounding=rounding) != 0:
                    raise exceptions.UserError(_('Ne visi SN nuskenuoti'))

        produce_moves = self.move_finished_ids.filtered(lambda x: x.product_id.tracking == 'none' and
                                                                  x.state not in ('done', 'cancel'))
        for move in produce_moves:
            rounding = move.product_uom.rounding
            if move.product_id.id == self.product_id.id:
                move.quantity_done_store += float_round(quantity, precision_rounding=rounding)
            elif move.unit_factor:
                # byproducts handling
                move.quantity_done_store += float_round(quantity * move.unit_factor, precision_rounding=rounding)

        for move in self.move_finished_ids:
            rounding = move.product_uom.rounding
            if float_compare(move.quantity_done, move.product_uom_qty, precision_rounding=rounding) != 0:
                if move.product_id.tracking in ['lot', 'serial'] and move.product_id.autocreate_lot_number:
                    try:
                        move._auto_create_lot_numbers()
                    except Exception as e:
                        msg = _('Nepavyko sukurti SN numerio')
                        if self.env.user.has_group('base.group_system'):
                            msg += '\n' + e.message
                        raise exceptions.UserError(msg)
                    continue
                raise exceptions.UserError(_('Ne visi SN nuskenuoti'))
        if self.state == 'confirmed':
            self.write({
                'state': 'progress',
                'date_start': datetime.now(),
            })
        self.with_context(force_period_date=self.accounting_date).button_mark_done()

    @api.multi
    def action_cancel_production(self):
        self._action_cancel_production()

    @job
    def _action_cancel_production(self):
        self.ensure_one()
        if self.state != 'done':
            return
        initial_value = sum(self.move_raw_ids.mapped('quant_ids').filtered(
            lambda q: q.location_id.usage == 'production').mapped('inventory_value'))
        current_value = sum(self.move_finished_ids.mapped('quant_ids.inventory_value'))
        if float_compare(initial_value, current_value, precision_digits=8) != 0:
            raise exceptions.UserError(
                _('Nesutampa vertės. Galbūt yra savikainos koregavimui, kuriuos reikėtų pirmiau atšaukti.'))
        moves = self.env['stock.move']
        for move in self.move_raw_ids.filtered(lambda r: r.state == 'done'):
            new_move = move.copy({
                'location_id': move.location_dest_id.id,
                'location_dest_id': move.location_id.id,
                'error_move': True,
                'cancel_raw_material_production_id': self.id,
                'origin_returned_move_id': move.id,
                'production_id': False,
                'raw_material_production_id': False,
            })
            for active_lot_id in move.active_move_lot_ids:
                new_move.active_move_lot_ids |= new_move.active_move_lot_ids.new({
                    'lot_id': active_lot_id.lot_id.id,
                    'quantity': active_lot_id.quantity,
                    'quantity_done': active_lot_id.quantity_done,
                    'done_wo': active_lot_id.done_wo,
                })
            moves |= new_move
        for move in self.move_finished_ids.filtered(lambda r: r.state == 'done'):
            new_move = move.copy({
                'location_id': move.location_dest_id.id,
                'location_dest_id': move.location_id.id,
                'error_move': True,
                'cancel_production_id': self.id,
                'origin_returned_move_id': move.id,
                'production_id': False,
                'raw_material_production_id': False,
            })
            for active_lot_id in move.active_move_lot_ids:
                new_move.active_move_lot_ids |= new_move.active_move_lot_ids.new({
                    'lot_id': active_lot_id.lot_id.id,
                    'quantity': active_lot_id.quantity,
                    'quantity_done': active_lot_id.quantity_done,
                    'done_wo': active_lot_id.done_wo,
                })
            moves |= new_move
        moves.mapped('origin_returned_move_id.quant_ids.reservation_id').do_unreserve()
        moves.action_assign()
        moves.action_done()
        # Preserve original dates
        for move in moves:
            move.write({'date': move.date_expected})
        states = list(set(moves.mapped('state')))
        if len(states) == 1 and states[0] == 'done':
            self.state = 'cancel'
        else:
            raise exceptions.Warning(_('Nepavyko atšaukti gamybos'))

    # Overload the original one to add updating of unit_factor
    # TODO: if we want to support partial production, this will lead to issues. unit_factor recompute would need to be rewritten
    @api.multi
    def _update_raw_move(self, bom_line, line_data):
        quantity = line_data['qty']
        self.ensure_one()
        move = self.move_raw_ids.filtered(
            lambda x: x.bom_line_id.id == bom_line.id and x.state not in ('done', 'cancel'))
        if move:
            if quantity > 0:
                original_quantity = self.product_qty
                # P3:DivOK
                move[0].write({'product_uom_qty': quantity,
                               'unit_factor': quantity / original_quantity})
            else:
                if move[0].quantity_done > 0:
                    raise exceptions.UserError(_('Eilučių negalima ištrinti, nes yra dar nesunaudotų komponentų.'))
                move[0].action_cancel()
                move[0].unlink()
            return move
        else:
            self._generate_raw_move(bom_line, line_data)

    @api.multi
    def unlink(self):
        field_list = ['move_raw_ids', 'cancel_move_raw_ids', 'move_finished_ids', 'cancel_move_finished_ids']
        for rec in self:
            if any(move.state != 'cancel' for move_field in field_list for move in rec.mapped(move_field)):
                if rec.state == 'cancel':
                    raise exceptions.UserError(_('You cannot delete canceled productions that were already produced.'))
                raise exceptions.UserError(_('You cannot delete non-canceled productions.'))
        return super(MrpProduction, self).unlink()

    @api.multi
    def button_action_assign(self):
        """
        Button that calls action assign method.
        Split to separate function so return
        types are consistent.
        :return: JS action dict
        """
        self.ensure_one()
        insufficient_stock_moves = self.move_raw_ids.filtered(
            lambda x: x.insufficient_stock
        )
        # If surplus is enabled and we have insufficient stock moves, call surplus reserve wizard
        if self.env.user.sudo().company_id.enable_production_surplus and insufficient_stock_moves:
            wizard = self.env['mrp.production.surplus.reserve'].create({'production_id': self.id})
            view_id = self.env.ref('robo_mrp.mrp_production_surplus_reserve_form').id
            return {
                'name': _('Rezervuoti atsargas su pertekliumi?'),
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'mrp.production.surplus.reserve',
                'views': [(view_id, 'form')],
                'view_id': view_id,
                'target': 'new',
                'res_id': wizard.id,
                'context': self.env.context,
            }
        self.action_assign()
        return {'type': 'ir.actions.do_nothing'}

    @api.multi
    def action_assign(self):
        for rec in self:
            # Check whether current BOM is valid
            if rec.bom_id and not rec.bom_id.valid_bom(rec.date_planned_start):
                raise exceptions.ValidationError(_('Susijusi komplektacija yra nebegaliojanti'))
            raw_moves = rec.move_raw_ids.filtered(lambda x: x.state == 'draft')
            if raw_moves:
                rec._adjust_procure_method()
                raw_moves.action_confirm()
        res = super(MrpProduction, self).action_assign()
        if not self._context.get('skip_stock_availability_check'):
            for rec in self:
                failed_to_reserve_moves = rec.get_failed_to_reserve_moves()
                if failed_to_reserve_moves:
                    failed_products = '\n'.join(failed_to_reserve_moves.mapped('product_id.name'))
                    raise exceptions.UserError(
                        _('Rezervavimas nepavyko, turima mažiau atsargų nei planuojama sunaudoti: \n\n{}').format(
                            failed_products)
                    )
        return res

    @api.multi
    def button_unreserve(self):
        res = super(MrpProduction, self).button_unreserve()
        self.move_raw_ids.filtered(lambda x: x.state not in ('done', 'cancel')).write({'state': 'draft'})
        return res

    @api.multi
    def open_produce_product(self):
        """
        Do not allow partial production
        on explode_all, explode_no_stock
        recursive production modes
        :return: None
        """
        self.ensure_one()
        if self.recursive_bom_production_mode in ['explode_all', 'explode_no_stock']:
            raise exceptions.UserError(
                _('Negalite gaminti dalinės gamybos jei įgalinta rekursyvi gamybos būsena, kuri skaido komplektacijas')
            )
        return super(MrpProduction, self).open_produce_product()

    @api.multi
    def recreate_raw_moves(self, create_new_moves=True):
        """
        Method that is used to recreate raw moves
        for specific production record if none
        of the moves are already canceled or done
        :param create_new_moves: Flag that indicates
        whether moves should be created
        :return: None
        """
        for rec in self:
            # Dynamic production components cannot be recalculated
            if rec.production_type == 'dynamic':
                raise exceptions.ValidationError(
                    _('Negalite perskaičiuoti komponentų kintančiai gamybos')
                )
            # Gather the raw moves and check constraints
            raw_moves = rec.move_raw_ids | rec.move_raw_ids_second
            if any(x.state in ['done', 'cancel'] for x in raw_moves):
                raise exceptions.UserError(
                    _('Negalite perkurti komponentų, bent vienas gamybos komponentas yra atšauktas arba pagamintas')
                )
            # Un-reserve and delete the moves if any
            if raw_moves:
                raw_moves.do_unreserve()
                raw_moves.action_cancel()
                raw_moves.unlink()
            if create_new_moves:
                # Call method to generate new raw moves
                rec.generate_raw_moves()

    @api.multi
    def recreate_finished_moves(self, create_new_moves=True):
        """
        Method that is used to recreate finished moves.
        Can be used for unlinking only if flag is not set.
        :param create_new_moves: Flag that indicates
        whether moves should be created
        :return: None
        """
        for rec in self:
            # Check if there's any moves to unlink
            if rec.move_finished_ids:
                if any(x.state in ['done', 'cancel'] for x in rec.move_finished_ids):
                    raise exceptions.UserError(
                        _('Negalite perkurti komponentų, gamybos produktas yra pagamintas.')
                    )
                rec.move_finished_ids.do_unreserve()
                rec.move_finished_ids.action_cancel()
                rec.move_finished_ids.unlink()
            # Check if moves should be recreated
            if create_new_moves:
                rec._generate_finished_moves()

    @api.multi
    def generate_raw_moves(self):
        """
        Generates move raw IDs for specific production
        by calculating the factor and splitting
        them based on recursive production mode
        :return: None
        """
        for rec in self:
            # Get the factor
            # P3:DivOK
            factor = rec.product_uom_id._compute_quantity(
                rec.product_qty, rec.bom_id.product_uom_id) / rec.bom_id.product_qty
            # If recursive production is not activated
            # or recursive production move is explode none
            # continue with previous behaviour
            p_mode = rec.recursive_bom_production_mode
            if not rec.recursive_bom_production or not p_mode or p_mode == 'explode_none':
                bom, lines = rec.bom_id.explode(rec.product_id, factor, picking_type=rec.bom_id.picking_type_id)
                rec._generate_raw_moves(lines)
            else:
                rec.bom_id.explode_bom_recursively(production=rec, factor=factor, create_moves=True)
            # Apply modification rules if any
            if rec.modification_rule_production:
                rec.production_modification_rule_ids.apply_modification_rule(factor)
            # Check for all draft moves whether they are mto or not
            rec._adjust_procure_method()
            rec.move_raw_ids.action_confirm()

    @api.multi
    def renew_production_locations(self):
        """
        Normalizes/updates the locations of insufficient production moves
        by taking the current location of the related BOM line.
        :return: None
        """
        for production in self:
            # Gather all the moves and products of current production's BOM
            moves = production.move_raw_ids | production.move_raw_ids_second
            bom_products = production.bom_id.bom_line_ids.mapped('product_id')
            # Filter out insufficient stock moves
            insufficient_stock_moves = moves.filtered(
                lambda x: x.insufficient_stock and x.state not in ['done', 'cancel'])
            if insufficient_stock_moves and production.availability not in ['none', 'waiting']:
                production.button_unreserve()
            # Loop through moves and check the locations
            for move in insufficient_stock_moves:
                src_location = self.env['stock.location']
                if move.production_modification_rule_id:
                    src_location = move.production_modification_rule_id.location_src_id
                if not src_location:
                    product = move.product_id
                    if product not in bom_products:
                        # If current move product is not in BOM (product was recursively split),
                        # get the parent bom line from move, and do reverse checkup to find the location
                        bom_lines = move.bom_line_id.find_child_bom_line_recursive(product)
                    else:
                        # If current move product is in BOM (product was not recursively split),
                        # get the current location from the BOM line
                        bom_lines = production.bom_id.bom_line_ids.filtered(lambda x: x.product_id.id == product.id)
                    # There can be several BOM lines with the same product,
                    # and we take the first location as a default in a case like this
                    src_locations = bom_lines.mapped('location_src_id')
                    src_location = src_locations and src_locations[0]

                if src_location and move.location_id != src_location:
                    move.write({'location_id': src_location.id})

    @api.model
    def cron_renew_production_locations(self):
        """
        Cron that calls renew_production_locations on
        every not done static production record
        :return: None
        """

        # Executed only if recursive production is activated
        if not self.sudo().env.user.company_id.enable_recursive_bom_production:
            return

        # Gather all non-done static productions
        productions = self.env['mrp.production'].search(
            [('state', '!=', 'done'), ('production_type', '=', 'static')])
        productions.renew_production_locations()

