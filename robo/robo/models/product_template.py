# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models
from datetime import datetime


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    skip_analytic = fields.Boolean(string='Nekurti nurašymo analitikos įrašų',
                                   lt_string='Nekurti nurašymo analitikos įrašų',
                                   sequence=100,
                                   )

    packaging_ids = fields.One2many(sequence=100)
    message_is_follower = fields.Boolean(sequence=100)
    message_last_post = fields.Datetime(sequence=100)
    message_needaction = fields.Boolean(sequence=100)
    message_needaction_counter = fields.Integer(sequence=100)
    message_follower_ids = fields.One2many(sequence=100)
    message_partner_ids = fields.Many2many(sequence=100)
    message_channel_ids = fields.Many2many(sequence=100)
    lst_price = fields.Float(sequence=100)
    landed_cost_ok = fields.Boolean(sequence=100)
    item_ids = fields.One2many(sequence=100)
    hs_code = fields.Char(sequence=100)
    description_sale = fields.Text(sequence=100)
    description_purchase = fields.Text(sequence=100)
    description_picking = fields.Text(sequence=100)
    description = fields.Text(sequence=100)
    deferred_revenue_category_id = fields.Many2one(sequence=100)
    color = fields.Integer(sequence=100)
    can_be_expensed = fields.Boolean(sequence=100)
    attribute_line_ids = fields.One2many(sequence=100)
    warranty = fields.Float(sequence=100)
    warehouse_id = fields.Many2one(sequence=100)
    virtual_available = fields.Float(sequence=100)
    uom_po_id = fields.Many2one(sequence=100)
    track_service = fields.Selection(sequence=100)
    taxes_id = fields.Many2many(sequence=100)
    supplier_taxes_id = fields.Many2many(sequence=100)
    sequence = fields.Integer(sequence=100)
    seller_ids = fields.One2many(sequence=100)
    sale_line_warn_msg = fields.Text(sequence=100)
    sale_line_warn = fields.Selection(sequence=100)
    sale_delay = fields.Float(sequence=100)
    route_ids = fields.Many2many(sequence=100)
    purchase_line_warn_msg = fields.Text(sequence=100)
    purchase_line_warn = fields.Selection(sequence=100)
    property_valuation = fields.Selection(sequence=100)
    asset_category_id = fields.Many2one(sequence=100)
    property_stock_production = fields.Many2one(sequence=100)
    property_stock_procurement = fields.Many2one(sequence=100)
    property_stock_inventory = fields.Many2one(sequence=100)
    property_stock_account_output = fields.Many2one(sequence=100)
    property_stock_account_input = fields.Many2one(sequence=100)
    property_account_income_id = fields.Many2one(sequence=100)
    property_account_expense_id = fields.Many2one(sequence=100)
    property_account_creditor_price_difference = fields.Many2one(sequence=100)
    project_id = fields.Many2one(sequence=100)
    product_variant_ids = fields.One2many(sequence=100)
    product_variant_id = fields.Many2one(sequence=100)
    product_cost_account_id = fields.Many2one(sequence=100)
    pricelist_id = fields.Many2one(sequence=100)
    tracking = fields.Selection(sequence=100)
    split_method = fields.Selection(sequence=100)
    property_cost_method = fields.Selection(sequence=100)
    image = fields.Binary(sequence=100)
    image_small = fields.Binary(sequence=100)
    image_medium = fields.Binary(sequence=100)
    expense_policy = fields.Selection(sequence=100)

    @api.constrains('default_code')
    def constraint_default_code(self):
        if not self._context.get('skip_constraints', False):
            allow_duplicate = not self.env.user.company_id.sudo().prevent_duplicate_product_code
            allow_empty = not self.env.user.company_id.sudo().prevent_empty_product_code
            for product in self:
                if product.default_code and not allow_duplicate:
                    if self.env['product.template'].search([('id', '!=', product.id),
                                                            ('default_code', '=', product.default_code)], limit=1):
                        raise exceptions.ValidationError(_('Produkto vidinis numeris negali kartotis! '
                                                           'Kompanijos profilyje galite šį draudimą išjungti.'))
                if not product.default_code and not allow_empty and product.product_variant_count < 2:
                    raise exceptions.ValidationError(_('Produkto vidinis numeris negali būti tuščias! '
                                                       'Kompanijos profilyje galite šį draudimą išjungti.'))

    @api.multi
    def copy(self, default=None):
        """Override default copy method by passing context to skip constraints"""
        # If we prevent duplicate code, we set default copy code to empty
        # constraint of empty code will not be triggered since it's skipped
        # but the user will have to manually set the code themselves
        records = self
        default = {} if default is None else default
        company = self.env.user.company_id.sudo()

        prevent_duplicate = company.prevent_duplicate_product_code
        prevent_empty = company.prevent_empty_product_code

        if prevent_duplicate or prevent_empty:
            # Generate random default code if prevent empty flag is set
            # otherwise reset code to False.
            default_code = datetime.now().strftime('%s')
            default['default_code'] = default_code if prevent_empty else False
            records = self.with_context(skip_constraints=True)
        return super(ProductTemplate, records).copy(default)
