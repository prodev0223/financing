# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _


class RKeeperPointOfSale(models.Model):
    _name = 'r.keeper.point.of.sale'
    _order = 'name asc'
    _description = '''
    Model that stores rKeeper point of sales,
    specific journal and location can be set,
    set data is used in invoice creation.
    '''

    # Identification
    name = fields.Char(string='Pavadinimas', inverse='_set_base_info')
    code = fields.Char(string='Kodas', inverse='_set_base_info')

    # Main point of sale fields
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        domain="[('account_type', 'in', ['income', 'profit'])]",
        string='Numatytoji analitinė sąskaita'
    )
    show_analytic_account_selection = fields.Boolean(compute='_compute_show_analytic_account_selection')
    partner_id = fields.Many2one('res.partner', string='Susietas partneris', copy=False)
    journal_id = fields.Many2one(
        'account.journal', string='Sąskaitų faktūrų žurnalas',
        domain="[('type', '=', 'sale')]"
    )
    cash_journal_id = fields.Many2one(
        'account.journal', string='Grynųjų pinigų žurnalas',
        domain="[('type', '=', 'cash')]", copy=False
    )
    location_id = fields.Many2one(
        'stock.location',
        domain="[('usage','=','internal')]", string='Lokacija'
    )
    picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Gamybos operacija',
        compute='_compute_picking_type_id'
    )

    # State fields
    configured = fields.Boolean(string='Sukonfigūruotas', compute='_compute_configured')
    configured_text = fields.Text(compute='_compute_configured')

    # Product line fields
    products_to_update = fields.Boolean(
        string='Reikia atnaujinti',
        compute='_compute_products_to_update',
        store=True
    )
    point_of_sale_product_ids = fields.One2many(
        'r.keeper.point.of.sale.product',
        'point_of_sale_id',
        string='Pardavimo taško prekės', copy=False
    )

    # Computes / Inverses / Constraints -------------------------------------------------------------------------------

    @api.multi
    def _compute_picking_type_id(self):
        """
        Find related stock picking type
        for current POS location
        :return: None
        """
        for rec in self.filtered(lambda x: x.location_id):
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'mrp_operation'),
                ('default_location_src_id', '=', rec.location_id.id),
            ], limit=1)
            rec.picking_type_id = picking_type

    @api.multi
    def _compute_show_analytic_account_selection(self):
        """
        Check whether analytic account ID
        field should be showed in the form view
        :return: None
        """
        robo_analytic_installed = self.sudo().env['ir.module.module'].search_count(
            [('name', '=', 'robo_analytic'), ('state', 'in', ['installed', 'to upgrade'])]
        )
        for rec in self:
            rec.show_analytic_account_selection = robo_analytic_installed

    @api.multi
    @api.depends('point_of_sale_product_ids', 'point_of_sale_product_ids.r_keeper_update')
    def _compute_products_to_update(self):
        """
        Compute //
        Check whether there any products to update
        :return: None
        """
        for rec in self:
            rec.products_to_update = any(prod.r_keeper_update for prod in rec.point_of_sale_product_ids)

    @api.multi
    @api.depends('location_id', 'partner_id', 'journal_id', 'name')
    def _compute_configured(self):
        """
        Compute //
        Computes whether current point of sale is configured
        :return: None
        """
        for rec in self:
            configured = rec.location_id and rec.partner_id and rec.journal_id and rec.name
            rec.configured = configured
            rec.configured_text = _('Sėkmingai sukonfigūruota') if configured else _('Trūksta konfigūracijos')

    @api.multi
    def _set_base_info(self):
        """
        Inverse //
        Find or create related partner record,
        and cash operation journal for
        for current point of sale
        :return: None
        """
        for rec in self.filtered(lambda x: x.code and x.name):
            if not rec.partner_id:
                # Search for partner by using composite code
                composite_code = 'rKeeper // {}'.format(rec.code)
                partner = self.env['res.partner'].search(
                    [('kodas', '=', composite_code), ('r_keeper_pos', '=', True)]
                )
                # if partner does not exist -- create the record
                if not partner:
                    composite_name = _('rKeeper // {}').format(rec.name)
                    partner = self.env['res.partner'].create({
                        'name': composite_name,
                        'kodas': composite_code,
                        'is_company': True,
                        'r_keeper_pos': True,
                    })
                rec.partner_id = partner
            # Write name changes to partner
            elif rec.partner_id and rec.partner_id.name != rec.name:
                rec.partner_id.name = rec.name

    @api.multi
    @api.constrains('code')
    def _check_code(self):
        """
        Constraints //
        Ensure that point of sale code is unique
        :return: None
        """
        for rec in self:
            if self.search_count([('code', '=', rec.code), ('id', '!=', rec.id)]):
                raise exceptions.ValidationError(_('Pardavimo taško kodas privalo būti unikalus!'))

    @api.multi
    @api.constrains('point_of_sale_product_ids')
    def _check_point_of_sale_product_ids(self):
        """
        Constraints //
        Ensure that all lines are rKeeper product lines
        :return: None
        """
        for rec in self:
            if any(not x.product_id.r_keeper_product for x in rec.point_of_sale_product_ids):
                raise exceptions.ValidationError(_('Visi pridėti produktai privalo būti rKeeper produktai!'))

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def action_open_point_of_sale_products(self):
        """
        Opens related product lines
        in a tree view
        :return: JS action (dict)
        """
        action_data = self.env.ref('r_keeper.action_open_r_keeper_point_of_sale_product_front').read()[0]
        action_data.pop('context', False)
        action_data['domain'] = [('id', 'in', self.point_of_sale_product_ids.ids)]
        return action_data

    @api.multi
    def action_open_pos_transfer_wizard(self):
        """
        Create and open point of sale transfer wizard
        :return: JS action (dict)
        """
        self.ensure_one()
        wizard = self.env['r.keeper.pos.transfer.wizard'].create({
            'destination_point_of_sale_id': self.id,
        })
        return {
            'name': _('Pardavimo taško informacijos perkėlimas'),
            'type': 'ir.actions.act_window',
            'res_model': 'r.keeper.pos.transfer.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
            'res_id': wizard.id,
            'view_id': self.env.ref('r_keeper.from_r_keeper_pos_transfer_wizard').id,
        }

    @api.multi
    def action_open_data_export_wizard(self):
        """
        Create and open point of sale update wizard.
        Can be either called from the form (single product update),
        or from the tree, on multi record-set.
        :return: JS action (dict)
        """
        self.ensure_one()

        pos_lines = self.point_of_sale_product_ids.filtered(lambda x: x.r_keeper_update)
        wizard = self.env['r.keeper.data.export.wizard'].create({
            'point_of_sale_product_ids': [(4, line.id) for line in pos_lines],
            'point_of_sale_id': self.id,
        })
        return {
            'name': _('rKeeper duomenų eksportas'),
            'type': 'ir.actions.act_window',
            'res_model': 'r.keeper.data.export.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
            'res_id': wizard.id,
            'view_id': self.env.ref('r_keeper.from_r_keeper_data_export_wizard').id,
        }

    @api.model
    def create_point_of_sale(self, code):
        """
        Method that is used to create
        related point of sale by using
        code provided by rKeeper
        :param code: rKeeper POS code
        :return: created record
        """
        point_of_sale = self.env['r.keeper.point.of.sale'].create({
            'name': _('Taškas {}').format(code),
            'code': code,
        })
        return point_of_sale

    # CRUD Methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def unlink(self):
        for rec in self:
            # Prevent modification of records in waiting state
            if rec.point_of_sale_product_ids and not self.env.user.has_group('base.group_system'):
                raise exceptions.ValidationError(
                    _('Negalite ištrinti pardavimo taško, pirmiausia ištrinkite produktų eilutes')
                )
        return super(RKeeperPointOfSale, self).unlink()
