# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _

TRIGGER_FIELDS = [
    'default_code', 'name', 'uom_id', 'r_keeper_price_unit', 'vat_rate',
    'is_weighed', 'related_product_id', 'r_keeper_product_state'
]


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # rKeeper data fields
    r_keeper_price_unit = fields.Float(string='Produkto kaina')
    r_keeper_vat_rate = fields.Selection(
        [('0', '0 %'),
         ('9', '9 %'),
         ('21', '21 %')
         ], string='Produkto PVM procentas', default='21'
    )
    r_keeper_is_weighed = fields.Boolean(string='Sveriama prekė')
    r_keeper_related_product_id = fields.Many2one(
        'product.template',
        string='Susijęs produktas'
    )
    r_keeper_product_state = fields.Selection(
        [('active', 'Aktyvus'),
         ('inactive', 'Neaktyvus'),
         ('deleted', 'Ištrintas')
         ], string='Produkto statusas', default='active'
    )

    # Other fields
    r_keeper_update = fields.Boolean(string='Reikalingas rKeeper atnaujinimas', copy=False)
    r_keeper_point_of_sale_product_ids = fields.One2many(
        'r.keeper.point.of.sale.product',
        'product_id', copy=False
    )
    r_keeper_product = fields.Boolean(
        compute='_compute_r_keeper_product',
        store=True, string='rKeeper produktas'
    )
    default_code = fields.Char(copy=False)

    # Computes / Constraints ------------------------------------------------------------------------------------------

    @api.multi
    @api.depends('categ_id.r_keeper_category')
    def _compute_r_keeper_product(self):
        """
        Compute //
        Check whether current product
        is rKeeper product
        :return: None
        """
        for rec in self:
            rec.r_keeper_product = rec.categ_id.r_keeper_category

    @api.multi
    @api.constrains('default_code')
    def _check_default_code(self):
        """
        Constraints //
        1. If product belongs to rKeeper category
        it must have it's default code set
        2. Default code must be unique
        :return: None
        """
        if self._context.get('skip_r_keeper_constraints'):
            return
        for rec in self:
            if rec.r_keeper_product:
                if not rec.default_code:
                    raise exceptions.ValidationError(
                        _('Produktai priklausantys rKeeper kategorijai privalo turėti vidinį numerį.')
                    )
                if self.search_count([('default_code', '=', rec.default_code)]) > 1:
                    raise exceptions.ValidationError(
                        _('Produktų kurie priklauso rKeeper kategorijai kodas privalo būti unikalus.')
                    )

    @api.multi
    def _set_categ_id(self):
        """
        Set filters on rKeeper product if filtering functionality
        is enabled and if product belongs to POS category
        :return: None
        """
        super(ProductTemplate, self)._set_categ_id()
        configuration = self.env['r.keeper.configuration'].sudo().get_configuration(raise_exception=False)
        if configuration.enable_pos_product_filtering:
            for rec in self.mapped('product_variant_ids'):
                rec.r_keeper_pos_filter = rec.categ_id.r_keeper_pos_category

    @api.onchange('list_price')
    def _onchange_list_price(self):
        """
        If list price is changed and r_keeper_price_unit
        is empty, add list price as a default value
        :return: None
        """
        if self.list_price and not self.r_keeper_price_unit:
            self.r_keeper_price_unit = self.list_price

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def copy(self, default=None):
        """Added context that is used to bypass constraint checks on record copy"""
        return super(ProductTemplate, self.with_context(skip_r_keeper_constraints=True)).copy(default=default)

    @api.multi
    def action_open_pos_update_wizard(self):
        """
        Create and open point of sale update wizard.
        Can be either called from the form (single product update),
        or from the tree, on multi record-set.
        :return: JS action (dict)
        """
        products = self.filtered(lambda x: x.r_keeper_product)
        if not products:
            raise exceptions.ValidationError(_('Nepaduotas nė vienas produktas priklausantis rKeeper kategorijai'))

        wizard = self.env['r.keeper.pos.update.wizard'].create({
            'product_ids': [(4, product.id) for product in products]
        })
        return {
            'name': _('Pardavimo taškų atnaujinimas'),
            'type': 'ir.actions.act_window',
            'res_model': 'r.keeper.pos.update.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
            'res_id': wizard.id,
            'view_id': self.env.ref('r_keeper.from_r_keeper_pos_update_wizard').id,
        }

    @api.model
    def create_action_pos_update_wizard_multi(self):
        """Creates action for multi POS update wizard"""
        action = self.env.ref('r_keeper.action_pos_update_wizard_multi')
        if action:
            action.create_action()

    # CRUD Methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def write(self, vals):
        for rec in self:
            # Do not let writes of default code if product was already imported in rKeeper
            if 'default_code' in vals and any(
                    x.r_keeper_export_state != 'not_tried' for x in rec.sudo().r_keeper_point_of_sale_product_ids):
                raise exceptions.ValidationError(
                    _('Negalima keisti produkto kodo jei produktas bent kart buvo importuotas į rKeeper serverį. '
                      'Jeigu pageidaujate keisti kodą, susikurkite naują produkto kortelę.')
                )
            # If any of the trigger fields are changed, and product belongs to r_keeper category
            # or that category is being written at the moment, mark product as need to update
            r_keeper_update = rec.r_keeper_product
            category_id = vals.get('categ_id')
            if not r_keeper_update and category_id:
                r_keeper_update = self.env['product.category'].browse(category_id).exists().r_keeper_category
            if r_keeper_update and any(x in vals for x in TRIGGER_FIELDS):
                vals['r_keeper_update'] = True
        return super(ProductTemplate, self).write(vals)
