# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class EbayOrderLine(models.Model):
    _name = 'ebay.order.line'

    # Identifiers
    ebay_order_id = fields.Many2one(
        'ebay.order', string='Ebay order ID')
    name = fields.Char(string='Line name')

    # Product fields -- Would be used in extended integration
    ext_product_code = fields.Char(string='External code', inverse='_set_ext_product_code')
    product_id = fields.Many2one('product.product', string='Product')

    # Amounts / Quantities
    quantity = fields.Float(string='Quantity', default=1)
    amount = fields.Float(string='Amount', compute='_compute_amount')
    price_unit = fields.Float(string='Price unit')

    # States / Types
    state = fields.Selection([
        ('imported', 'Order line belongs to imported order'),
        ('created', 'Order line belongs to created order'),
        ('failed', 'Order line belongs to failed order')],
        string='State', compute='_compute_state')

    line_type = fields.Selection(
        [('main', 'Main product/service'),
         ('shipping', 'Shipping fees'),
         ('collected_taxes', 'Taxes')],
        string='Line type', required=True,
        inverse='_set_line_type',
    )

    invoice_line_id = fields.Many2one(
        'account.invoice.line', string='Related invoice line',
    )
    invoice_id = fields.Many2one(
        'account.invoice', string='Related invoice',
        compute='_compute_invoice_id', store=True,
    )
    account_id = fields.Many2one(
        'account.account',
        compute='_compute_account_id')

    @api.multi
    def _set_ext_product_code(self):
        """
        Searches for related product in the system based on external code.
        Only used on quantitative integration
        :return: None
        """
        # Check what configuration type is currently set
        configuration = self.env['ebay.configuration'].get_configuration()
        if configuration.integration_type != 'qty':
            return

        ProductProduct = self.env['product.product'].sudo()
        for rec in self.filtered(lambda x: x.line_type == 'main'):
            # Find related product record
            product = ProductProduct.search(
                [('default_code', '=', rec.ext_product_code)], limit=1)
            rec.product_id = product

    @api.multi
    def _set_line_type(self):
        """
        Assigns product to the line based on the line and integration types.
        If integration type is Quantitative, assigns special product to non Main lines.
        If integration type is Sum, assigns special product to all lines
        """
        configuration = self.env['ebay.configuration'].get_configuration()
        qty_integration = configuration.integration_type == 'qty'
        spec_mapping = {
            'shipping': self.env.ref('ebay.ebay_product_shipping').product_variant_id.id,
            'main': self.env.ref('ebay.ebay_product_main').product_variant_id.id,
            'collected_taxes': self.env.ref('ebay.ebay_product_taxes').product_variant_id.id,
        }
        # If integration type is quantitative exclude main lines
        lines = self.filtered(lambda x: x.line_type != 'main') if qty_integration else self
        for rec in lines:
            rec.product_id = spec_mapping[rec.line_type]

    @api.multi
    @api.depends('line_type')
    def _compute_account_id(self):
        """Assign specific static account to the line based on the line and integration types"""
        account_5000 = self.env.ref('l10n_lt.1_account_412').id
        account_5001 = self.env.ref('l10n_lt.1_account_413').id

        for rec in self:
            rec.account_id = account_5000 if rec.line_type in ['main', 'collected_taxes'] else account_5001

    @api.multi
    @api.depends('price_unit', 'quantity')
    def _compute_amount(self):
        """Calculate price unit based on amount and quantity"""
        for rec in self:
            rec.amount = rec.price_unit * rec.quantity

    @api.multi
    @api.depends('invoice_line_id')
    def _compute_invoice_id(self):
        """Gets related account invoice record based on invoice line"""
        for rec in self.filtered(lambda x: x.invoice_line_id):
            rec.invoice_id = rec.invoice_line_id.invoice_id

    @api.multi
    @api.depends('ebay_order_id.state')
    def _compute_state(self):
        """Determines line state which is based on order state"""
        for rec in self:
            rec.state = rec.ebay_order_id.state
