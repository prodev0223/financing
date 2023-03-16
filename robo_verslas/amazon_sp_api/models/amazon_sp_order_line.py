# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, tools, _


class AmazonSPOrderLine(models.Model):
    _name = 'amazon.sp.order.line'

    # Identifiers
    amazon_order_id = fields.Many2one(
        'amazon.sp.order', string='Amazon order ID')
    name = fields.Char(string='Line name')

    # Product codes & misc
    ext_product_code = fields.Char(string='External code')
    asin_product_code = fields.Char(
        string='ASIN product code', inverse='_set_asin_product_code')
    sku_product_code = fields.Char(stirng='SKU code')

    # Amounts / Quantities
    quantity = fields.Float(string='Quantity', default=1)
    total_amount_untaxed = fields.Float(string='Total amount (Untaxed)')
    total_tax_amount = fields.Float(string='Total tax amount')

    # Computed amounts
    total_amount_taxed = fields.Float(string='Total amount (Taxed)', compute='_compute_amounts')
    price_unit_untaxed = fields.Float(string='Price unit (Untaxed)', compute='_compute_amounts')
    price_unit_taxed = fields.Float(string='Price unit (Taxed)', compute='_compute_amounts')
    total_display_amount = fields.Float(
        string='Total line amount',
        compute='_compute_amounts', store=True,
    )
    total_report_display_amount = fields.Float(
        string='Total line amount',
        compute='_compute_amounts', store=True,
    )
    zero_tax_rate_line = fields.Boolean(compute='_compute_amounts')

    # States / Types
    state = fields.Selection([
        ('imported', 'Order line belongs to imported order'),
        ('created', 'Order line belongs to created order'),
        ('ext_cancel', 'Order line belongs to canceled order'),
        ('failed', 'Order line belongs to failed order')],
        string='State', compute='_compute_state')

    line_type = fields.Selection(
        [('principal', 'Main product/service'),
         ('promotion', 'Discounts'),
         ('shipping', 'Shipping fees'),
         ('fees', 'Other fees'),
         ('withheld_taxes', 'Withheld taxes'),
         ('gift_wraps', 'Gift wrap fees')],
        string='Line type', inverse='_set_line_type', required=True
    )

    # Relational fields
    amazon_product_id = fields.Many2one(
        'amazon.sp.product', string='Product')
    withheld_tax_line_id = fields.Many2one('amazon.sp.order.line')
    # Always a single record, thus naming _id (only written via code)
    taxable_withheld_line_id = fields.One2many(
        'amazon.sp.order.line', 'withheld_tax_line_id'
    )

    invoice_line_id = fields.Many2one(
        'account.invoice.line', string='Related invoice line')
    invoice_id = fields.Many2one(
        'account.invoice', string='Related invoice',
        compute='_compute_invoice_id', store=True)
    account_id = fields.Many2one(
        'account.account',
        compute='_compute_account_id')

    @api.multi
    @api.depends('quantity', 'total_amount_untaxed', 'total_tax_amount', 'withheld_tax_line_id')
    def _compute_amounts(self):
        """Computes total amounts - taxes, total taxed and total untaxed"""
        AmazonSpAPIBase = self.env['amazon.sp.api.base'].sudo()
        configuration = AmazonSpAPIBase.get_configuration()
        if not configuration:
            return

        for rec in self:
            # Add tax amount to the line only if there's no related withheld tax record
            total_amount_taxed = rec.total_amount_untaxed
            if not rec.withheld_tax_line_id:
                total_amount_taxed += rec.total_tax_amount

            price_unit_taxed = total_amount_taxed / (rec.quantity or 1)
            price_unit_untaxed = rec.total_amount_untaxed / (rec.quantity or 1)
            # Assign the amounts
            rec.total_amount_taxed = total_amount_taxed
            rec.price_unit_taxed = price_unit_taxed
            rec.price_unit_untaxed = price_unit_untaxed
            rec.zero_tax_rate_line = tools.float_is_zero(
                rec.total_tax_amount, precision_digits=2
            ) or rec.withheld_tax_line_id

            # Calculate total line display amount
            total_display_amount = total_report_display_amount = rec.total_amount_untaxed
            if configuration.include_order_tax:
                total_display_amount = total_amount_taxed
                # In report case we must ignore withheld tax amount that is added to the line
                # thus we re-calculate by using total_untaxed + total_tax
                total_report_display_amount = rec.total_amount_untaxed + rec.total_tax_amount
            rec.total_display_amount = total_display_amount
            rec.total_report_display_amount = total_report_display_amount

    @api.multi
    @api.depends('line_type')
    def _compute_account_id(self):
        """Assign specific static account to the line based on line and integration types"""
        account_5000 = self.env.ref('l10n_lt.1_account_412').id
        account_5001 = self.env.ref('l10n_lt.1_account_413').id

        for rec in self:
            rec.account_id = account_5000 if rec.line_type in ['principal', 'promotion'] else account_5001

    @api.multi
    @api.depends('invoice_line_id')
    def _compute_invoice_id(self):
        """Gets related account.invoice record based on invoice line"""
        for rec in self.filtered(lambda x: x.invoice_line_id):
            rec.invoice_id = rec.invoice_line_id.invoice_id

    @api.multi
    @api.depends('amazon_order_id.state')
    def _compute_state(self):
        """Determines line state which is based on order state"""
        for rec in self:
            rec.state = rec.amazon_order_id.state

    @api.multi
    def _set_asin_product_code(self):
        """Finds product by ASN code, and, if product does not have ext_product_code, write it."""
        # Skip this inverse on sum integration
        configuration = self.env['amazon.sp.api.base'].get_configuration()
        if configuration.integration_type == 'sum':
            return
        for rec in self.filtered(lambda x: x.asin_product_code and x.ext_product_code):
            amazon_product = self.env['amazon.sp.product'].search(
                [('asin_product_code', '=', rec.asin_product_code)], limit=1)
            if not amazon_product.ext_product_code:
                amazon_product.write({'ext_product_code': rec.ext_product_code})
            rec.amazon_product_id = amazon_product

    @api.multi
    def _set_line_type(self):
        """
        If integration type is 'Quantitative', assigns special product to non 'Principal' lines.
        If integration type is 'Sum', assigns special product to all lines
        """
        configuration = self.env['amazon.sp.api.base'].get_configuration()
        sum_integration = configuration.integration_type == 'sum'
        spec_mapping = {
            'shipping': self.env.ref('amazon_sp_api.sp_product_amazon_shipping').id,
            'fees': self.env.ref('amazon_sp_api.sp_product_amazon_fees').id,
            'promotion': self.env.ref('amazon_sp_api.sp_product_amazon_promotion').id,
            'gift_wraps': self.env.ref('amazon_sp_api.sp_product_amazon_gift_wraps').id,
            'principal': self.env.ref('amazon_sp_api.sp_product_amazon_principal').id,
        }
        # If integration type is sum, get principal product as well
        for rec in self:
            if rec.line_type == 'withheld_taxes' or rec.line_type == 'principal' and not sum_integration:
                continue
            rec.amazon_product_id = spec_mapping[rec.line_type]

    @api.multi
    @api.constrains('ext_product_code', 'line_type')
    def _check_product_code(self):
        """If line type is not 'principal' product must have ext product code"""
        # Skip this inverse on sum integration
        configuration = self.env['amazon.sp.api.base'].get_configuration()
        if configuration.integration_type == 'sum':
            return
        for rec in self.filtered(lambda x: x.line_type == 'principal'):
            if not rec.ext_product_code or not rec.asin_product_code:
                raise exceptions.ValidationError(_('Principal line must contain product code!'))

    @api.multi
    def recompute_fields(self):
        """Recompute (only stored) and re-inverse all significant fields"""
        self._set_asin_product_code()
