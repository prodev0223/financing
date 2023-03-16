# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, tools, _


class AmazonOrderLine(models.Model):
    """
    Model that holds amazon order lines
    """
    _name = 'amazon.order.line'

    amazon_order_id = fields.Many2one('amazon.order', string='Amazon užsakymas')

    # External codes
    ext_line_name = fields.Char(string='Eilutės pavadinimas')
    ext_product_code = fields.Char(string='Išorinis produkto kodas')
    asin_product_code = fields.Char(string='ASIN produkto kodas', invese='_set_asin_product_code')
    sku_product_code = fields.Char(stirng='SKU produkto kodas')

    # Amounts / Quantities
    quantity = fields.Float(string='Kiekis', default=1)
    amount_tax = fields.Float(string='Mokesčių suma')
    line_amount = fields.Float(string='Suma')
    line_amount_w_vat = fields.Float(string='Suma su PVM', compute='_compute_line_amount_w_vat')
    price_unit = fields.Float(string='Vnt. Kaina', compute='_compute_price_unit')

    # States / Types
    state = fields.Selection([('imported', 'Užsakymo eilutė importuota'),
                              ('created', 'Užsakymo eilutė sukurta sistemoje'),
                              ('failed', 'Klaida kuriant užsakymo eilutę')],
                             string='Būsena', compute='_compute_state')
    line_type = fields.Selection(
        [('principal', 'Pagrindinė paslauga/produktas'),
         ('shipping', 'Siuntimo mokesčiai'),
         ('fees', 'Kiti mokesčiai'),
         ('promotion', 'Nuolaida'),
         ('gift_wraps', 'Dovanų pakavimai')], string='Eilutės tipas', inverse='_set_line_type')

    # Relational fields
    amazon_product_id = fields.Many2one('amazon.product', string='Produktas')
    invoice_line_id = fields.Many2one('account.invoice.line', string='Susijusi sąskaitos eilutė')
    invoice_id = fields.Many2one(
        'account.invoice', string='Susijusi sąskaita', compute='_compute_invoice_id', store=True)
    account_id = fields.Many2one('account.account', compute='_compute_account_id')

    @api.multi
    @api.depends('amount_tax', 'line_amount')
    def _compute_line_amount_w_vat(self):
        """Calculates line amount with VAT by adding line_amount + amount_tax"""
        for rec in self:
            rec.line_amount_w_vat = rec.amount_tax + rec.line_amount

    @api.multi
    @api.depends('quantity', 'line_amount')
    def _compute_price_unit(self):
        """
        Compute //
        Calculate price unit of the  line using following formula:
            line_amount / quantity
        :return: None
        """
        for rec in self:
            rec.price_unit = rec.line_amount / rec.quantity if not tools.float_is_zero(
                rec.quantity, precision_digits=2) else rec.line_amount

    @api.multi
    @api.depends('line_type')
    def _compute_account_id(self):
        """
        Compute //
        Assign specific static account to the line based on line and integration types
        :return: None
        """
        account_5000 = self.env.ref('l10n_lt.1_account_412').id
        account_5001 = self.env.ref('l10n_lt.1_account_413').id

        for rec in self:
            if rec.line_type in ['principal', 'promotion']:
                # Account - 5000
                rec.account_id = account_5000
            else:
                # Account - 5001
                rec.account_id = account_5001

    @api.multi
    @api.depends('invoice_line_id')
    def _compute_invoice_id(self):
        """
        Compute //
        Get related account.invoice record based on invoice line
        :return: None
        """
        for rec in self.filtered(lambda x: x.invoice_line_id):
            rec.invoice_id = rec.invoice_line_id.invoice_id

    @api.multi
    @api.depends('amazon_order_id.state')
    def _compute_state(self):
        """
        Compute //
        Determine line state which is based on order state
        :return: None
        """
        for rec in self:
            rec.state = rec.amazon_order_id.state

    @api.multi
    def _set_asin_product_code(self):
        """
        Inverse //
        Find product by ASIN code, and, if product does not have ext_product_code, write it.
        :return: None
        """
        # Skip this inverse on sum integration
        if self.sudo().env.user.company_id.amazon_integration_type == 'sum':
            return

        for rec in self.filtered(lambda x: x.asin_product_code and x.ext_product_code):
            amazon_product = self.env['amazon.product'].search(
                [('asin_product_code', '=', rec.asin_product_code)], limit=1)
            if not amazon_product.ext_product_code:
                amazon_product.write({'ext_product_code': rec.ext_product_code})
            rec.amazon_product_id = amazon_product

    @api.multi
    def _set_line_type(self):
        """
        Inverse //
        If integration type is 'Quantitative', assign special product to non 'Principal' lines.
        If integration type is 'Sum', assign special product to all lines
        :return: None
        """
        sum_integration = self.sudo().env.user.company_id.amazon_integration_type == 'sum'
        spec_mapping = {
            'shipping': self.env.ref('amazon_integration.a_product_amazon_shipping').id,
            'fees': self.env.ref('amazon_integration.a_product_amazon_fees').id,
            'promotion': self.env.ref('amazon_integration.a_product_amazon_promotion').id,
            'gift_wraps': self.env.ref('amazon_integration.a_product_amazon_gift_wraps').id,
            'principal': self.env.ref('amazon_integration.a_product_amazon_principal').id
        }

        # If integration type is sum, get principal product as well
        for rec in self:
            if rec.line_type == 'principal' and not sum_integration:
                continue
            rec.amazon_product_id = spec_mapping[rec.line_type]

    @api.multi
    @api.constrains('ext_product_code', 'line_type')
    def _check_product_code(self):
        """
        Constraints //
        If line type is not 'principal' product must have ext product code
        :return: None
        """
        # Skip this inverse on sum integration
        if self.sudo().env.user.company_id.amazon_integration_type == 'sum':
            return

        for rec in self.filtered(lambda x: x.line_type == 'principal'):
            if not rec.ext_product_code or not rec.asin_product_code:
                raise exceptions.ValidationError(_('Pagrindinė eilutė privalo turėti produkto kodą!'))

    @api.multi
    def recompute_fields(self):
        """
        Recompute and Re-inverse all significant fields
        :return: None
        """
        self._set_asin_product_code()
        self._compute_account_id()
        self._compute_invoice_id()
        self._compute_state()


AmazonOrderLine()
