# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions, _
from six import iteritems


class EbayOrder(models.Model):
    _name = 'ebay.order'
    _description = _('Model that holds eBay order information')
    _inherit = ['mail.thread']

    # Identifiers
    ext_order_id = fields.Char(
        string='Order ID',
        help='Ebay defined order identifier',
    )
    ext_sale_id = fields.Char(
        string='Sale ID',
        help='Ebay defined sale identifier',
    )

    # Dates
    order_date = fields.Datetime(string='Purchase date')
    shipping_date = fields.Datetime(string='Shipping date')

    # Statuses
    state = fields.Selection([
        ('imported', 'Order imported'),
        ('created', 'Invoice created'),
        ('failed', 'Failed to create the invoice')
    ], string='State', default='imported', track_visibility='onchange')

    # Amount related fields
    ext_currency_code = fields.Char(string='Custom currency code', inverse='_set_ext_currency_code')
    amount_total = fields.Float(string='Order amount', compute='_compute_amount_total')

    # Country related data
    destination_country_name = fields.Char(
        string='Destination country name', inverse='_set_destination_country_name')

    origin_country_id = fields.Many2one('res.country', string='Origin country')
    destination_country_id = fields.Many2one('res.country', string='Destination country')
    ebay_tax_rule_id = fields.Many2one(
        'ebay.tax.rule', store=True,
        compute='_compute_ebay_tax_rule_id',
        string='Related tax rule'
    )

    # Buyer related fields
    buyer_name = fields.Char(
        string='Buyer name', inverse='_set_partner_data')
    buyer_address = fields.Char(string='Buyer address')
    buyer_vat = fields.Char(
        string='Buyer VAT', inverse='_set_partner_data')
    partner_id = fields.Many2one(
        'res.partner', string='Partner',
    )

    # Other fields
    fulfilled_by_ebay = fields.Boolean(string='Fulfilled by eBay')

    # Other relational fields
    ebay_order_line_ids = fields.One2many(
        'ebay.order.line', 'ebay_order_id',
        string='Order lines',
    )
    currency_id = fields.Many2one('res.currency', string='Currency')
    invoice_id = fields.Many2one('account.invoice', string='Invoice')

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    @api.depends('ebay_order_line_ids.amount', 'ebay_order_line_ids')
    def _compute_amount_total(self):
        """Calculates order amount total based on lines"""
        for rec in self:
            amount_total = sum(rec.mapped('ebay_order_line_ids.amount'))
            rec.amount_total = amount_total

    @api.multi
    @api.depends('origin_country_id', 'destination_country_id')
    def _compute_ebay_tax_rule_id(self):
        """Gets related Ebay tax rule based on countries"""
        EbayTaxRule = self.env['ebay.tax.rule'].sudo()
        for rec in self:
            origin_country = rec.origin_country_id
            tax_rule = EbayTaxRule.get_tax_rule(
                origin_country=origin_country,
                destination_country=rec.destination_country_id,
            )
            rec.ebay_tax_rule_id = tax_rule

    @api.multi
    def _set_destination_country_name(self):
        """ Find corresponding res country based on destination country code"""
        ResCountry = self.env['res.country'].sudo().with_context(lang='en_US')
        for rec in self.filtered(lambda x: x.destination_country_name):
            country = ResCountry.search(
                [('name', '=', rec.destination_country_name)], limit=1)
            # If country was not found, use 'like' search
            if not country:
                country = ResCountry.search([('name', 'like', rec.destination_country_name)])
            if not country or len(country) > 1:
                raise exceptions.UserError(
                    _('Destination country with the name [%s] was not found!') % rec.destination_country_name)
            rec.destination_country_id = country

    @api.multi
    def _set_ext_currency_code(self):
        """ Find corresponding currency based on external currency code"""
        EbayCurrencyMapper = self.env['ebay.currency.mapper']
        for rec in self.filtered(lambda x: x.ext_currency_code):
            currency_mapper = EbayCurrencyMapper.search([('external_code', '=', rec.ext_currency_code)], limit=1)
            if not currency_mapper:
                raise exceptions.UserError(
                    _('Currency mapper with the code [%s] was not found!') % rec.ext_currency_code)
            rec.currency_id = currency_mapper.currency_id

    @api.multi
    def _set_partner_data(self):
        """Create or relate systemic partner based on external buyer data"""
        ResPartner = self.env['res.partner']
        for rec in self.filtered(lambda x: x.buyer_name):
            partner_name = 'eBay // {}'.format(rec.buyer_name)
            # If order has buyer vat code, create separate partner for it
            partner = ResPartner.search([('name', '=', partner_name)], limit=1)
            if not partner:
                partner = ResPartner.create({
                    'name': partner_name,
                    'contact_address': rec.buyer_address,
                    'vat': rec.buyer_vat,
                })
            rec.partner_id = partner

    @api.multi
    def recompute_fields(self):
        """Recomputes/Re-inverses all the significant fields"""
        self._set_destination_country_name()
        self._compute_ebay_tax_rule_id()
        self._set_ext_currency_code()
        self._set_partner_data()

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def invoice_creation_prep(self, validate=True):
        """
        Prepare eBay orders for account invoice creation by sending them to validator
        and passing validated orders to invoice creation method
        :return None
        """
        # Validate passed ebay orders if validate flag is set
        validated_orders = self
        if validate:
            validated_orders = self.check_constraints()

        for order in validated_orders:
            order.create_invoices()

    @api.multi
    def check_constraints(self, raise_exception=False):
        """
        Validate eBay order records, so they meet all criteria
        for account invoice creation
        :param raise_exception: Indicates whether any errors
        should be raised or posted directly to the order
        :return: recordset: validated orders
        """
        # Define empty set (Naming due to the same class name)
        EbayOrderCl = self.env['ebay.order']
        validated_records = EbayOrderCl

        # Filter the records
        filtered_records = self.filtered(
            lambda x: not x.invoice_id and x.state in ['imported', 'failed'])

        # Recompute all fields (action is skipped on wizard import call and is meant
        # to be used on integration extension)
        if not self._context.get('skip_recomputes'):
            filtered_records.recompute_fields()

        # Validate the fields
        for rec in filtered_records:
            error_template = str()
            if not rec.ebay_order_line_ids:
                error_template += _('Ebay order lines were not found.\n')
            if not rec.partner_id:
                error_template += _('Related partner was not found.\n')
            if not rec.currency_id:
                error_template += _('Order currency was not found.\n')
            if not rec.ebay_tax_rule_id:
                error_template += _('Related tax rule was not found.\n')

            # Check whether lines have product assigned to them
            for line in rec.ebay_order_line_ids:
                if not line.product_id:
                    error_template += _('Line "{}" does not have configured product.\n').format(line.name)

            # Check whether any errors were gathered during validation
            if error_template:
                error_template = _('Errors: \n\n') + error_template
                # Raise exception if flag is passed
                if raise_exception:
                    raise exceptions.ValidationError(error_template)
                self.post_message(error_template, state='failed', orders=rec)
            else:
                validated_records |= rec
        return validated_records

    @api.multi
    def create_invoices(self, raise_exception=False):
        """
        Create account invoice records from eBay orders
        :param raise_exception: Indicates whether exception should be raised.
        If set to False, error message will be posted to the order
        :return: None
        """

        # Used models
        AccountInvoice = self.env['account.invoice'].sudo()
        EbayOrderLine = self.env['ebay.order.line'].sudo()

        EbayConfiguration = self.env['ebay.configuration'].sudo()
        # Get eBay configuration record
        configuration = EbayConfiguration.get_configuration()

        # Get the defaults
        default_order = self.sorted(lambda r: r.order_date, reverse=True)[0]
        default_account = self.env.ref('l10n_lt.1_account_229')
        default_tax_rule = default_order.ebay_tax_rule_id
        invoice_number = default_order.ext_order_id

        invoice_lines = []
        invoice_values = {
            'external_invoice': True,
            'imported_api': True,
            'force_dates': True,
            'price_include_selection': 'inc',
            'account_id': default_account.id,
            'journal_id': configuration.default_journal_id.id,
            'partner_id': default_order.partner_id.id,
            'invoice_line_ids': invoice_lines,
            'type': 'out_invoice',
            'date_invoice': default_order.order_date,
            'currency_id': default_order.currency_id.id,
            'move_name': invoice_number,
            'number': invoice_number,
        }

        total_invoice_amount = 0.0
        all_order_lines = self.mapped('ebay_order_line_ids')

        # Filter out main product lines
        main_order_lines = all_order_lines.filtered(lambda x: x.line_type == 'main')
        # Check if any inclusion option is selected, and if so, add all needed lines as well
        line_type_domain = ['main']
        if not configuration.include_order_shipping_fees:
            line_type_domain += ['shipping']
        if not configuration.include_order_collected_taxes:
            line_type_domain += ['collected_taxes']
        # Filter out other order lines
        spec_order_lines = all_order_lines.filtered(lambda x: x.line_type not in line_type_domain)

        grouped_lines = {}
        for line in main_order_lines:
            # Loop through lines and build dict of dicts with following mapping
            # {PRODUCT: {PRICE_UNIT: ORDER_LINES, PRICE_UNIT_2: ORDER_LINES}}...
            product = line.product_id
            grouped_lines.setdefault(product, {})
            grouped_lines[product].setdefault(line.price_unit, EbayOrderLine)
            grouped_lines[product][line.price_unit] |= line

        # Loop through grouped lines and add them to invoice_line list
        for product, by_price_unit in iteritems(grouped_lines):
            for price_unit, ord_lines in iteritems(by_price_unit):
                # Sum the total quantity and amount
                tot_quantity = sum(ord_lines.mapped('quantity'))
                total_invoice_amount += price_unit * tot_quantity
                # Extract needed taxes from the tax rule
                account_tax = self.get_taxes_from_rule(ord_lines, default_tax_rule)
                # Add the values to the invoice line list
                line_values = {
                    'amount': price_unit, 'quantity': tot_quantity,
                    'product': product, 'account_tax': account_tax,
                }
                self.add_invoice_line(invoice_lines, ord_lines, line_values)

        # Prepare spec product lines, lines are grouped only by product
        grouped_lines = {}
        for line in spec_order_lines:
            product = line.product_id
            grouped_lines.setdefault(product, EbayOrderLine)
            grouped_lines[product] |= line

        # Loop through grouped lines and add them to invoice_line list
        for product, ord_lines in iteritems(grouped_lines):
            # Sum the total special amount
            total_spec_amount = sum(ord_lines.mapped('amount'))
            if tools.float_is_zero(total_spec_amount, precision_digits=2):
                continue

            total_invoice_amount += total_spec_amount
            # Extract needed taxes from the tax rule
            account_tax = self.get_taxes_from_rule(ord_lines, default_tax_rule)
            # Add the values to the invoice line list
            line_values = {
                'amount': total_spec_amount, 'quantity': 1,
                'product': product, 'account_tax': account_tax,
            }
            self.add_invoice_line(invoice_lines, ord_lines, line_values)

        # Try to create the account invoice
        try:
            invoice = AccountInvoice.create(invoice_values)
        except Exception as e:
            if raise_exception:
                raise exceptions.ValidationError(str(e.args))
            self.custom_rollback(e.args[0])
            return

        # Check whether amounts do match before opening an invoice
        if tools.float_compare(total_invoice_amount, invoice.amount_total_signed, precision_digits=2) != 0:
            diff = tools.float_round(abs(total_invoice_amount - invoice.amount_total_signed), precision_digits=2)
            # It's already rounded here, so it's fine to compare with '>'
            if diff > 0.01:
                body = _('Invoice amount does not match with calculated amount (%s != %s).\n') % (
                    invoice.amount_total_signed, total_invoice_amount)
                if raise_exception:
                    raise exceptions.ValidationError(body)
                self.custom_rollback(body)
                return

        # Open the invoice and force the partner
        try:
            invoice.partner_data_force()
            invoice.action_invoice_open()
        except Exception as e:
            if raise_exception:
                raise exceptions.ValidationError(str(e.args))
            self.custom_rollback(e.args[0])
            return

        # Write state changes and commit
        self.write({'state': 'created', 'invoice_id': invoice.id})
        self.env.cr.commit()

    @api.model
    def get_taxes_from_rule(self, line_batch, tax_rule):
        """Returns corresponding taxes from the eBay tax rule based on the parameters"""
        # Take default line, they are already grouped and sorted
        default_line = line_batch[0]
        account_tax = tax_rule.product_zero_rate_tax_id
        if default_line.product_id.acc_product_type == 'service' and default_line.line_type != 'main':
            account_tax = tax_rule.service_zero_rate_tax_id
        return account_tax

    @api.model
    def add_invoice_line(self, invoice_lines, lines_to_add, line_values):
        """
        Add invoice line to the invoice lines list
        :param invoice_lines: Processed invoice line values (list)
        :param lines_to_add: eBay order lines that are being added (records)
        :param line_values: Values that are used in processed dict (dict)
        :return: None
        """
        default_obj = lines_to_add[0]
        product = line_values.get('product')

        # Determine the account of the product - take it from product, category or use the static one
        product_account = product.get_product_income_account()
        if not product_account:
            product_account = default_obj.account_id

        line_vals = {
            'name': default_obj.name or product.name,
            'product_id': product.id,
            'quantity': line_values.get('quantity'),
            'price_unit': line_values.get('amount'),
            'account_id': product_account.id,
            'invoice_line_tax_ids': [(6, 0, line_values.get('account_tax').ids)],
            'ebay_order_line_ids': [(6, 0, lines_to_add.ids)]
        }
        invoice_lines.append((0, 0, line_vals))

    # Misc methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def unlink(self):
        """Unlink the lines when unlinking eBay order"""
        self.mapped('ebay_order_line_ids').unlink()
        return super(EbayOrder, self).unlink()

    @api.multi
    def custom_rollback(self, msg):
        """
        Rollback current transaction, post message to the object and commit
        :return: None
        """
        self.env.cr.rollback()
        body = _('Failed to create the invoice. Error: %s') % str(msg)
        self.post_message(body, state='failed', orders=self)
        self.env.cr.commit()

    @api.model
    def post_message(self, body, state=None, orders=None):
        """
        Post message to eBay order and write the state if its passed
        :param body: str: Message to be posted
        :param state: str: Order state
        :param orders: recordset: Orders to be posted
        :return: None
        """
        if orders is None:
            orders = self.env['ebay.order']
        if orders:
            if state:
                orders.write({'state': state})
            for order in orders:
                order.message_post(body=body)

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(x.id, _('Order - [%s]') % x.ext_order_id) for x in self]
