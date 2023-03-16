# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions, _
from datetime import datetime
from six import iteritems


class AmazonSPOrder(models.Model):
    _name = 'amazon.sp.order'
    _description = _('Model that holds Amazon order information')
    _inherit = ['mail.thread']

    # Identifiers
    ext_order_id = fields.Char(
        string='Order ID',
        help='An Amazon-defined order identifier',
        inverse='_set_ext_order_id',
    )
    ext_replacement_order_id = fields.Char(
        string='Replacement order ID',
        help='The order ID value for the order that is being replaced',
    )
    seller_order_id = fields.Char(
        string='Seller order ID',
        help='A seller-defined order identifier',
    )
    marketplace_code = fields.Char(
        string='Marketplace code',
        inverse='_set_marketplace_code',
    )

    # Timestamps
    purchase_date = fields.Datetime(string='Purchase date')
    earliest_ship_date = fields.Datetime(string='Earliest ship date')
    latest_ship_date = fields.Datetime(string='Latest ship date')
    earliest_delivery_date = fields.Datetime(string='Earliest delivery date')
    latest_delivery_date = fields.Datetime(string='Latest delivery date')

    factual_order_date = fields.Datetime(string='Factual date of the order')
    factual_order_day = fields.Date(string='Order date', compute='_compute_factual_order_day', store=True)
    factual_order_month = fields.Char(compute='_compute_factual_order_month', store=True)

    # Statuses
    state = fields.Selection([
        ('imported', 'Order imported'),
        ('created', 'Order created'),
        ('ext_cancel', 'Order canceled externally'),
        ('failed', 'Failed to create the order')
    ], string='State', default='imported', track_visibility='onchange')

    # >>> Information on external order states
    # Pending: The order has been placed but payment has not been authorized.
    #   The order is not ready for shipment. Note that for orders with OrderType = Standard,
    #   the initial order status is Pending. For orders with OrderType = Preorder,
    #   the initial order status is PendingAvailability,
    #   and the order passes into the Pending status when the payment authorization process begins.
    # Unshipped: Payment has been authorized and order is ready for shipment,
    #   but no items in the order have been shipped.
    # PartiallyShipped: One or more (but not all) items in the order have been shipped.
    # Shipped: All items in the order have been shipped.
    # Canceled: The order was canceled.
    # Unfulfillable: The order cannot be fulfilled. This state applies only to Amazon-fulfilled
    #   orders that were not placed on Amazon's retail web site.
    # InvoiceUnconfirmed: All items in the order have been shipped. The seller has not yet given
    #   confirmation to Amazon that the invoice has been shipped to the buyer.
    # PendingAvailability: This status is available for pre-orders only. The order has been placed, payment has not
    #   been authorized, and the release date of the item is in the future. The order is not ready for shipment.

    external_state = fields.Selection([
        ('Pending', 'Pending'),
        ('Unshipped', 'Unshipped'),
        ('PartiallyShipped', 'Partially shipped'),
        ('Shipped', 'Shipped'),
        ('Canceled', 'Cancelled'),
        ('Unfulfillable', 'Unfulfillable'),
        ('InvoiceUnconfirmed', 'Invoice unconfirmed'),
        ('PendingAvailability', 'Pending availability'),
    ], string='External state', track_visibility='onchange', inverse='_set_external_state')

    # >>> Information on external order types
    # StandardOrder: An order that contains items for which the selling partner currently has inventory in stock.
    # LongLeadTimeOrder: An order that contains items that have a long lead time to ship.
    # Preorder: An order that contains items with a release date that is in the future.
    # BackOrder: An order that contains items that already have been released in the market
    #   but are currently out of stock and will be available in the future.
    # SourcingOnDemandOrder: A Sourcing On Demand order.

    # Other fields
    order_type = fields.Selection([
        ('StandardOrder', 'Standard order'),
        ('LongLeadTimeOrder', 'Long lead time order'),
        ('Preorder', 'Preorder'),
        ('BackOrder', 'Back order'),
        ('SourcingOnDemandOrder', 'Sourcing on demand order'),
    ], string='Order type'
    )

    fulfillment_channel = fields.Selection([
        ('MFN', 'Fulfilled by seller'),
        ('AFN', 'Fulfilled by Amazon'),
    ], string='Fulfillment channel')

    refund_order = fields.Boolean(string='Refund', inverse='_set_refund_order')
    number_of_items_unshipped = fields.Integer(string='Number of unshipped items')
    # Orders that are invoiced externally are not created in our system as invoices
    # But are kept just to check the amounts
    invoiced_externally = fields.Boolean(string='Invoiced externally')
    business_order = fields.Boolean(string='Business order')
    buyer_vat_code = fields.Char(string='Buyer VAT code')

    # Amount related fields
    currency_code = fields.Char(string='Currency code', inverse='_set_currency_code')
    control_amount = fields.Float(string='Order control amount')

    # Amounts calculated from the lines
    order_amount_total = fields.Float(
        string='Final amount (Included into invoices)',
        compute='_compute_order_amounts',
    )
    order_amount_shipping = fields.Float(
        string='Shipping amount',
        compute='_compute_order_amounts',
    )
    order_amount_discount = fields.Float(
        string='Discount amount',
        compute='_compute_order_amounts',
    )
    order_amount_principal = fields.Float(
        string='Main amount',
        compute='_compute_order_amounts',
    )
    order_amount_gift_wraps = fields.Float(
        string='Main amount',
        compute='_compute_order_amounts',
    )
    order_amount_fees = fields.Float(
        string='Main amount',
        compute='_compute_order_amounts',
    )

    # Amounts including refunds
    order_amount_principal_display = fields.Float(string='Main amount', compute='_compute_order_amounts')
    order_amount_total_display = fields.Float(string='Final amount', compute='_compute_order_amounts')

    # Country related data
    origin_country_code = fields.Char(
        string='Origin country code', inverse='_set_origin_country_code')
    destination_country_code = fields.Char(
        string='Destination country code', inverse='_set_destination_country_code')

    origin_country_id = fields.Many2one('res.country', string='Origin country')
    destination_country_id = fields.Many2one('res.country', string='Destination country')
    amazon_sp_tax_rule_id = fields.Many2one(
        'amazon.sp.tax.rule', store=True,
        compute='_compute_amazon_sp_tax_rule_id',
        string='Related tax rule'
    )

    # Amazon relational fields
    marketplace_id = fields.Many2one('amazon.sp.marketplace', string='Marketplace')
    amazon_order_line_ids = fields.One2many(
        'amazon.sp.order.line', 'amazon_order_id',
        string='Order lines',
    )
    refunded_order_id = fields.Many2one(
        'amazon.sp.order', string='Refunded order ID',
        compute='_compute_refunded_order_id',
    )
    refunding_order_id = fields.Many2one(
        'amazon.sp.order', string='Refunding order ID',
        compute='_compute_refunding_order_id',
    )
    # Base relational fields
    partner_id = fields.Many2one(
        'res.partner', string='Partner',
        compute='_compute_partner_id', store=True,
    )
    currency_id = fields.Many2one('res.currency', string='Currency')
    invoice_id = fields.Many2one('account.invoice', string='System invoice')

    # Computes / Inverses / Constraints -------------------------------------------------------------------------------

    @api.multi
    @api.depends('origin_country_id', 'destination_country_id', 'marketplace_id')
    def _compute_amazon_sp_tax_rule_id(self):
        """Gets related Amazon SP tax rule based on countries and marketplace"""
        AmazonSPTaxRule = self.env['amazon.sp.tax.rule'].sudo()
        for rec in self:
            origin_country = rec.origin_country_id or rec.marketplace_id.country_id
            tax_rule = AmazonSPTaxRule.get_tax_rule(
                origin_country=origin_country,
                destination_country=rec.destination_country_id,
                marketplace=rec.marketplace_id,
            )
            rec.amazon_sp_tax_rule_id = tax_rule

    @api.multi
    @api.depends('ext_order_id', 'refund_order')
    def _compute_refunded_order_id(self):
        """ Get refunded order ID -- Same ID, different settings"""
        for rec in self.filtered(lambda x: x.refund_order):
            rec.refunded_order_id = self.search([
                ('ext_order_id', '=', rec.ext_order_id), ('refund_order', '=', False)], limit=1)

    @api.multi
    @api.depends('ext_order_id', 'refund_order')
    def _compute_refunding_order_id(self):
        """Get refunding order ID -- Same ID, different settings"""
        for rec in self.filtered(lambda x: not x.refund_order):
            rec.refunded_order_id = self.search([
                ('ext_order_id', '=', rec.ext_order_id), ('refund_order', '=', True)], limit=1)

    @api.multi
    @api.depends('factual_order_date')
    def _compute_factual_order_day(self):
        """Get order date from factual_order_date"""
        for rec in self.filtered(lambda x: x.factual_order_date):
            rec.factual_order_day = rec.factual_order_date[:10]

    @api.multi
    @api.depends('factual_order_date')
    def _compute_factual_order_month(self):
        """Get order month from factual_order_date"""
        for rec in self.filtered(lambda x: x.factual_order_date):
            order_time_dt = datetime.strptime(rec.factual_order_date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            rec.factual_order_month = '{}-{}'.format(order_time_dt.year, order_time_dt.month)

    @api.multi
    @api.depends('marketplace_id', 'marketplace_id.partner_id', 'buyer_vat_code')
    def _compute_partner_id(self):
        """Get partner ID from related marketplace"""
        ResPartner = self.env['res.partner'].sudo()
        for rec in self.filtered(lambda x: x.marketplace_id):
            # Take the partner from the marketplace
            partner = rec.marketplace_id.partner_id
            if rec.buyer_vat_code:
                # If order has buyer vat code, create separate partner for it
                partner = ResPartner.search([('vat', '=', rec.buyer_vat_code)], limit=1)
                if not partner:
                    partner = ResPartner.create({
                        'name': 'Amazon // {}'.format(rec.buyer_vat_code),
                        'vat': rec.buyer_vat_code,
                        'is_company': rec.business_order,
                    })
            rec.partner_id = partner

    @api.multi
    def _compute_order_amounts(self):
        """Calculate amounts (total, tax, fees) based on amazon order lines """
        # Ref needed objects
        AmazonSpAPIBase = self.env['amazon.sp.api.base'].sudo()
        configuration = AmazonSpAPIBase.get_configuration()
        if not configuration:
            return

        # Check what amounts should be included in final amount
        include_fees = configuration.include_order_commission_fees
        include_shipping = configuration.include_order_shipping_fees
        include_gift_wraps = configuration.include_order_gift_wrap_fees
        include_discounts = configuration.include_order_promotion_discounts

        for rec in self.filtered(lambda x: x.amazon_order_line_ids):
            # Calculate total order amounts
            sign = -1 if rec.refund_order else 1
            # Group the lines by type
            grouped_lines = {}
            for line in rec.amazon_order_line_ids:
                grouped_lines.setdefault(line.line_type, 0.0)
                grouped_lines[line.line_type] += line.total_display_amount

            # Get the amounts and assign them to the variables
            rec.order_amount_principal = grouped_lines.get('principal', 0.0)
            rec.order_amount_fees = grouped_lines.get('fees', 0.0)
            rec.order_amount_shipping = grouped_lines.get('shipping', 0.0)
            rec.order_amount_discount = grouped_lines.get('promotion', 0.0)
            rec.order_amount_gift_wraps = grouped_lines.get('gift_wraps', 0.0)
            rec.order_amount_principal_display = rec.order_amount_principal * sign

            # Check what should be included in total, representational amount
            amount_total = rec.order_amount_principal
            if include_fees:
                amount_total += rec.order_amount_fees
            if include_shipping:
                amount_total += rec.order_amount_shipping
            if include_discounts:
                amount_total += rec.order_amount_discount
            if include_gift_wraps:
                amount_total += rec.order_amount_gift_wraps

            # Assign the total amounts
            rec.order_amount_total = amount_total
            rec.order_amount_total_display = rec.order_amount_total * sign

    @api.multi
    def _set_ext_order_id(self):
        """
        Manually relates withheld tax line after order
        is created for each principal order line
        :return: None
        """
        for rec in self:
            lines = rec.amazon_order_line_ids
            for taxable_line in lines.filtered(lambda x: x.line_type not in ['withheld_taxes', 'promotion']):
                # Sanitize taxable line name for withheld tax line matching (yes, can only be done via name...)
                sanitized_line_type = taxable_line.line_type.replace('_', str())
                related_withheld_tax_line = lines.filtered(
                    lambda x: x.line_type == 'withheld_taxes' and not tools.float_compare(
                        abs(x.total_amount_untaxed), abs(taxable_line.total_tax_amount), precision_digits=2)
                    and not x.taxable_withheld_line_id and sanitized_line_type in x.name.lower()
                )
                # We take the tax lines that do not already have related principal lines,
                # however since the matching can only be done via amount, we take the first line from the list.
                if related_withheld_tax_line:
                    taxable_line.withheld_tax_line_id = related_withheld_tax_line[0]

    @api.multi
    def _set_origin_country_code(self):
        """ Find corresponding res.country based on origin country code"""
        for rec in self:
            country = rec.marketplace_id.country_id
            if rec.origin_country_code:
                country = self.env['res.country'].search([('code', '=', rec.origin_country_code)], limit=1)
                if not country:
                    raise exceptions.UserError(
                        _('Origin country with the code [%s] was not found!') % rec.origin_country_code)
            rec.origin_country_id = country

    @api.multi
    def _set_destination_country_code(self):
        """ Find corresponding res.country based on destination country code"""
        for rec in self.filtered(lambda x: x.destination_country_code):
            country = self.env['res.country'].search([('code', '=', rec.destination_country_code)], limit=1)
            if not country:
                raise exceptions.UserError(
                    _('Destination country with the code [%s] was not found!') % rec.destination_country_code)
            rec.destination_country_id = country

    @api.multi
    def _set_currency_code(self):
        """ Find corresponding res.currency based on external currency code"""
        for rec in self.filtered(lambda x: x.currency_code):
            currency = self.env['res.currency'].search([('name', '=', rec.currency_code)], limit=1)
            if not currency:
                raise exceptions.UserError(_('Currency with the code [%s] was not found!') % rec.currency_code)
            rec.currency_id = currency

    @api.multi
    def _set_external_state(self):
        """If ext order status is not 'Shipped' set ROBO state to 'ext_cancel'"""
        for rec in self.filtered(lambda x: x.external_state != 'Shipped'):
            rec.state = 'ext_cancel'

    @api.multi
    def _set_marketplace_code(self):
        """Assign a marketplace based on external code"""
        for rec in self.filtered(lambda x: x.marketplace_code):
            marketplace = self.env['amazon.sp.marketplace'].search([('code', '=', rec.marketplace_code)])
            if not marketplace:
                raise exceptions.UserError(_('Marketplace with the code [%s] was not found!') % rec.marketplace_code)
            rec.marketplace_id = marketplace

    @api.multi
    def _set_refund_order(self):
        """If order is refund, abs all of it's principal/shipping/wrapping lines"""
        for rec in self.filtered(lambda x: x.refund_order):
            for line in rec.amazon_order_line_ids:
                sign = -1 if line.line_type not in ['shipping', 'principal', 'gift_wraps'] else 1
                # Always make them negative, some endpoints return refunds with minuses
                # some without... that's why it's ABSed first
                line.total_amount_untaxed = abs(line.total_amount_untaxed) * sign
                line.total_tax_amount = abs(line.total_tax_amount) * sign

    @api.multi
    @api.constrains('ext_order_id')
    def _check_ext_order_id(self):
        """If order is not refund, ensure that order_id is unique"""
        for rec in self.filtered(lambda x: not x.refund_order):
            if self.search_count(
                    [('ext_order_id', '=', rec.ext_order_id), ('id', '!=', rec.id), ('refund_order', '=', False)]):
                raise exceptions.ValidationError(
                    _('Order with ID [%s] is already in the system!') % rec.ext_order_id
                )

    @api.multi
    def recompute_fields(self):
        """ Recompute and re-inverse all significant fields"""
        self._set_currency_code()
        self._set_marketplace_code()
        self._compute_amazon_sp_tax_rule_id()
        self._compute_factual_order_day()
        self._compute_factual_order_month()
        self._compute_partner_id()
        # Recompute the fields for all of the lines as well
        self.mapped('amazon_order_line_ids').recompute_fields()

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def validator(self, strict_batch_creation):
        """
        Validate amazon.sp.order and amazon.sp.order.line records, so they meet all criteria
        for account.invoice creation
        :return: validated orders (recordset)
        """
        # Define base object and empty validated record set
        AmazonOrder = self.env['amazon.sp.order']
        validated_records = AmazonOrder

        # Filtering
        filtered_records = self.filtered(
            lambda x: not x.invoice_id and x.state in ['imported', 'failed']
            and x.external_state == 'Shipped' and not x.invoiced_externally
        )

        # Recompute all fields
        filtered_records.recompute_fields()
        filtered_records.mapped('amazon_order_line_ids').recompute_fields()

        # Validate the fields
        for rec in filtered_records:
            error_template = str()
            if not rec.amazon_order_line_ids:
                error_template += _('Amazon order lines were not found.\n')
            if not rec.partner_id:
                error_template += _('Marketplace partner was not found.\n')
            if not rec.currency_id:
                error_template += _('Order currency was not found.\n')
            if not rec.amazon_sp_tax_rule_id:
                error_template += _('Related tax rule was not found.\n')
            if rec.marketplace_id.state != 'configured':
                error_template += _('Related marketplace is not found or is not configured.\n')

            # We skip fee lines in account invoice creation
            for line in rec.amazon_order_line_ids.filtered(lambda x: x.line_type not in ['fees', 'withheld_taxes']):
                if not line.amazon_product_id.product_id:
                    error_template += _('Line "{}" does not have configured product.\n').format(line.name)
                if not line.amazon_product_id.spec_product and not line.amazon_product_id.amazon_category_id:
                    error_template += _('Line "{}" does not have configured category.\n').format(line.name)
                if line.amazon_product_id and not line.amazon_product_id.configured:
                    error_template += _('Line "{}" Amazon product ID state is not configured\n').format(line.name)
                if line.amazon_product_id.amazon_category_id and not \
                        line.amazon_product_id.amazon_category_id.activated:
                    error_template += _('Line "{}" Amazon category is not activated.\n').format(line.name)
                if not line.account_id:
                    error_template += _('Line "{}" does not have account ID.\n').format(line.name)
            if error_template:
                error_template = _('Amazon order was not created due to the following errors: \n\n') + error_template
                self.post_message(error_template, state='failed', orders=rec)
                # If strict batch creation is enabled we return empty set
                # if at least one order from the batch was not validated
                if strict_batch_creation:
                    return AmazonOrder
            else:
                validated_records |= rec
        return validated_records

    @api.multi
    def invoice_creation_prep(self, validate=True):
        """
        Prepare amazon.sp.order for account.invoice creation by sending them to validator
        :return True if batch was validated, False if not
        (on individual invoice creation, batch is always 'created')
        """
        # Only activate invoice creation if amazon integration is configured
        AmazonSpAPIBase = self.env['amazon.sp.api.base'].sudo()
        configuration = AmazonSpAPIBase.get_configuration()
        if not configuration:
            return

        # Check configuration settings
        strict_batch_creation = False
        individual_invoices = configuration.create_individual_order_invoices
        # If individual invoice option is activated, strict batch creation
        # option is always cancelled out
        if not individual_invoices:
            strict_batch_creation = configuration.strict_batch_creation

        validated_orders = self
        # Validate the records if strict batch creation is not enabled, and validation flag is passed
        if not strict_batch_creation and validate:
            validated_orders = self.validator(strict_batch_creation)

        all_batches_validated = True
        if individual_invoices:
            refund_orders = validated_orders.filtered(lambda x: x.refund_order)
            sale_orders = validated_orders.filtered(lambda x: not x.refund_order)

            for order in sale_orders:
                order.create_invoices(grouped_data=False)
            for order in refund_orders:
                order.create_invoices(refund=True, grouped_data=False)
        else:
            grouped_data = {}
            for sale_order in validated_orders:
                # Loop through lines and build dict of dicts with following mapping
                # {PARTNER: {MONTH: SALE_ORDER, MONTH_2: SALE_ORDER}}...
                partner = sale_order.partner_id
                month = sale_order.factual_order_month
                t_rule = sale_order.amazon_sp_tax_rule_id
                refund = sale_order.refund_order

                grouped_data.setdefault(partner, {})
                grouped_data[partner].setdefault(month, {})
                grouped_data[partner][month].setdefault(t_rule, {})
                grouped_data[partner][month][t_rule].setdefault(refund, self.env[self._name])
                grouped_data[partner][month][t_rule][refund] |= sale_order

            for partner, by_month in grouped_data.items():
                for month, by_tax_rule in by_month.items():
                    for tax_rule, by_refund in by_tax_rule.items():
                        for refund, orders in by_refund.items():
                            # If strict batch creation is enabled, we validate the grouped
                            # orders before the actual batch creation, and skip if at least
                            # one order is not validated. Mark the all_batches_validate flag
                            # as false, which indicates that next creation date is not shifted
                            if strict_batch_creation:
                                orders = orders.validator(strict_batch_creation)
                                if not orders:
                                    all_batches_validated = False
                            # Create the orders
                            if orders:
                                orders.create_invoices(refund=refund)

        return all_batches_validated

    @api.multi
    def create_invoices(self, refund=False, grouped_data=True):
        """
        Create account.invoice records from amazon orders.
        Two types of creation can be done - normal operation and refund operation
        :param refund: indicates whether operation is of refund type
        :param grouped_data: Indicates whether invoice that is being created
        is created from single order, or grouped order data
        :return: None
        """

        # Used models
        AccountInvoice = self.env['account.invoice'].sudo()
        InvoiceDeliveryWizard = self.env['invoice.delivery.wizard'].sudo()
        AmazonSpOrderLine = self.env['amazon.sp.order.line'].sudo()
        AmazonSpAPIBase = self.env['amazon.sp.api.base'].sudo()

        # Get the defaults
        default_order = self.sorted(lambda r: r.factual_order_date, reverse=True)[0]
        default_mp = default_order.marketplace_id
        default_account = self.env.ref('l10n_lt.1_account_229')
        default_tax_rule = default_order.amazon_sp_tax_rule_id

        invoice_lines = []
        invoice_values = {
            'external_invoice': True,
            'imported_api': True,
            'force_dates': True,
            'price_include_selection': 'inc',
            'account_id': default_account.id,
            'journal_id': default_mp.journal_id.id,
            'partner_id': default_order.partner_id.id,
            'invoice_line_ids': invoice_lines,
            'type': 'out_refund' if refund else 'out_invoice',
            'date_invoice': default_order.factual_order_date,
            'currency_id': default_order.currency_id.id,
        }
        # If data is not grouped, use order ID in the invoice number
        if not grouped_data:
            invoice_number = default_order.ext_order_id
            if refund:
                invoice_number = 'KR-{}'.format(default_order.refunded_order_id.ext_order_id)
                # Refunds are passed with the same ext order ID, however sometimes one order
                # can have several refunds, thus if one of them is already created in the system
                # we append refund order's factual date as a numeric timestamp
                if self.env['account.invoice'].search_count([('number', '=', invoice_number)]):
                    time_st = datetime.strptime(
                        default_order.factual_order_date, tools.DEFAULT_SERVER_DATETIME_FORMAT
                    ).strftime('%s')
                    invoice_number = '{}-{}'.format(invoice_number, time_st)

            invoice_values.update({
                'move_name': invoice_number,
                'number': invoice_number,
            })

        # Get Amazon configuration record
        configuration = AmazonSpAPIBase.get_configuration()

        all_order_lines = self.mapped('amazon_order_line_ids').filtered(
            lambda x: x.line_type != 'withheld_taxes'
        )
        # Split lines into zero tax lines and non zero tax lines
        zero_tax_lines = non_zero_tax_lines = self.env['amazon.sp.order.line']
        for line in all_order_lines:
            if line.zero_tax_rate_line:
                zero_tax_lines |= line
            else:
                non_zero_tax_lines |= line

        total_invoice_amount = 0.0
        # Loop through the different batches and append the lines to the invoice
        for zero_tax, order_lines in [(True, zero_tax_lines), (False, non_zero_tax_lines)]:
            principal_lines = order_lines.filtered(lambda x: x.line_type == 'principal')

            # If amazon tax is included, main order lines are treated as spec lines
            spec_order_lines, main_order_lines = (principal_lines, AmazonSpOrderLine) \
                if configuration.include_order_tax else (AmazonSpOrderLine, principal_lines)

            # Check if any inclusion option is selected, and if so, add all needed lines as well
            line_type_domain = ['principal']
            if not configuration.include_order_commission_fees:
                line_type_domain += ['fees']
            if not configuration.include_order_shipping_fees:
                line_type_domain += ['shipping']
            if not configuration.include_order_promotion_discounts:
                line_type_domain += ['promotion']
            if not configuration.include_order_gift_wrap_fees:
                line_type_domain += ['gift_wraps']
            spec_order_lines |= order_lines.filtered(lambda x: x.line_type not in line_type_domain)

            grouped_lines = {}
            for line in main_order_lines:
                # Loop through lines and build dict of dicts with following mapping
                # {PRODUCT: {PRICE_UNIT: ORDER_LINES, PRICE_UNIT_2: ORDER_LINES}}...
                product = line.amazon_product_id.product_id
                grouped_lines.setdefault(product, {})
                grouped_lines[product].setdefault(line.price_unit_untaxed, AmazonSpOrderLine)
                grouped_lines[product][line.price_unit_untaxed] |= line

            # Loop through grouped lines and add them to invoice_line list
            for product, by_price_unit in iteritems(grouped_lines):
                for price_unit, ord_lines in iteritems(by_price_unit):
                    # Sum the total quantity and amount
                    tot_quantity = sum(ord_lines.mapped('quantity'))
                    total_invoice_amount += price_unit * tot_quantity
                    # Extract needed taxes from the tax rule
                    account_tax = self.get_taxes_from_rule(zero_tax, ord_lines, default_tax_rule)
                    # Add the values to the invoice line list
                    line_values = {
                        'amount': price_unit, 'quantity': tot_quantity,
                        'product': product, 'account_tax': account_tax,
                    }
                    self.add_invoice_line(invoice_lines, ord_lines, line_values)

            # Prepare spec product lines, lines are grouped only by product
            grouped_lines = {}
            for line in spec_order_lines:
                product = line.amazon_product_id.product_id
                grouped_lines.setdefault(product, AmazonSpOrderLine)
                grouped_lines[product] |= line

            # Loop through grouped lines and add them to invoice_line list
            for product, ord_lines in iteritems(grouped_lines):
                # Sum the total special amount
                total_spec_amount = sum(ord_lines.mapped('total_amount_taxed'))
                total_invoice_amount += total_spec_amount
                # Extract needed taxes from the tax rule
                account_tax = self.get_taxes_from_rule(zero_tax, ord_lines, default_tax_rule)
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
            self.custom_rollback(e.args[0])
            return

        if refund:
            total_invoice_amount *= -1
        # Check whether amounts do match before opening an invoice
        if tools.float_compare(total_invoice_amount, invoice.amount_total_signed, precision_digits=2) != 0:
            diff = tools.float_round(abs(total_invoice_amount - invoice.amount_total_signed), precision_digits=2)
            # It's already rounded here, so it's fine to compare with '>'
            if diff > 0.01:
                body = _('Invoice amount does not match with calculated amount (%s != %s).\n') % (
                    invoice.amount_total_signed, total_invoice_amount)
                self.custom_rollback(body)
                return

        # Open the invoice and force the partner
        try:
            invoice.partner_data_force()
            invoice.action_invoice_open()
        except Exception as e:
            self.custom_rollback(e.args[0])
            return

        # Create delivery if integration is quantitative
        if configuration.integration_type == 'qty':
            # Create delivery
            if any(x.amazon_product_id.product_id.type == 'product' for x in order_lines):
                wizard = InvoiceDeliveryWizard.with_context(
                    invoice_id=invoice.id).create(
                    {'location_id': default_mp.location_id.id}
                )
                # If we fail to create the picking, we rollback the whole invoice creation
                try:
                    wizard.create_delivery()
                except Exception as e:
                    self.custom_rollback(e.args[0], action_type='delivery_creation')
                    return

        # Write state changes and commit
        self.write({'state': 'created', 'invoice_id': invoice.id})

        # Reconcile with refund
        self.reconcile_with_refund(refund)
        self.env.cr.commit()

    @api.model
    def get_taxes_from_rule(self, zero_amount_tax, line_batch, tax_rule):
        """Returns corresponding taxes from the Amazon SP tax rule based on the parameters"""
        # Take default line, they are already grouped and sorted
        default_line = line_batch[0]
        if zero_amount_tax:
            account_tax = tax_rule.product_zero_rate_tax_id
            if default_line.amazon_product_id.product_id.acc_product_type == 'service':
                account_tax = tax_rule.service_zero_rate_tax_id
        else:
            account_tax = tax_rule.product_non_zero_rate_tax_id
            if default_line.amazon_product_id.product_id.acc_product_type == 'service':
                account_tax = tax_rule.service_non_zero_rate_tax_id
        return account_tax

    @api.model
    def add_invoice_line(self, invoice_lines, lines_to_add, line_values):
        """
        Add invoice line to the invoice lines list
        :param invoice_lines: Processed invoice line values (list)
        :param lines_to_add: Amazon order lines that are being added (records)
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
            'amazon_sp_order_line_ids': [(6, 0, lines_to_add.ids)]
        }
        invoice_lines.append((0, 0, line_vals))

    @api.multi
    def reconcile_with_refund(self, refund=False):
        """
        Reconcile account invoice with reverse order:
        if current order is refund, search for order-to-refund
        otherwise, take refunding order. If invoice of reverse
        order exists, reconcile those two records
        :param refund: signifies whether current operation is of refund type
        :return: None
        """

        invoice = self.mapped('invoice_id')
        if len(invoice) != 1:
            raise exceptions.UserError(
                _('Reverse reconciliation is only possible for orders from the same invoice')
            )

        for rec in self:
            # Check whether refund exists
            reverse_invoice = self.env['account.invoice']
            if refund and rec.refunded_order_id.invoice_id:
                reverse_invoice = rec.refunded_order_id.invoice_id
            elif not refund and rec.refunding_order_id.invoice_id:
                reverse_invoice = rec.refunding_order_id.invoice_id
            if reverse_invoice and tools.float_compare(reverse_invoice.residual, 0, precision_digits=2) > 0 and \
                    tools.float_compare(invoice.residual, 0, precision_digits=2) > 0:
                # Try to reconcile refund and main invoice together
                line_ids = reverse_invoice.move_id.line_ids.filtered(
                    lambda r: r.account_id.id == reverse_invoice.account_id.id)
                line_ids |= invoice.move_id.line_ids.filtered(
                    lambda r: r.account_id.id == invoice.account_id.id)
                try:
                    if len(line_ids) > 1:
                        line_ids.with_context(reconcile_v2=True).reconcile()
                except Exception as exc:
                    # if reconciliation fails, post message to the order, but do not rollback
                    body = _('Failed to reverse reconcile the invoice: {}').format(exc.args[0])
                    self.post_message(body, orders=rec)

    # Misc methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def button_create_invoice(self):
        """Button method - creates account invoice from amazon order"""
        self.invoice_creation_prep()

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
        Post message to amazon.sp.order
        :param body: message to-be posted to amazon.sp.order (str)
        :param state: object state (str)
        :param orders: amazon.sp.order records
        :return: None
        """
        if orders is None:
            orders = self.env['amazon.sp.order']
        if orders:
            if state:
                orders.write({'state': state})
            for order in orders:
                order.message_post(body=body)

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(x.id, _('Order [%s]') % x.ext_order_id) for x in self]
