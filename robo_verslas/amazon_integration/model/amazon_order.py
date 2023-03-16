# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools, exceptions, _
from datetime import datetime
from six import iteritems


class AmazonOrder(models.Model):
    _name = 'amazon.order'
    _inherit = ['mail.thread']

    # ID's / names
    order_id = fields.Char(string='Užsakymo ID')
    marketplace_code = fields.Char(string='Parduotuvės kodas', inverse='_set_marketplace')
    marketplace_name = fields.Char(string='Parduotuvės pavadinimas', inverse='_set_marketplace')
    fulfillment_channel = fields.Char(string='Kanalas')

    # Dates
    order_time = fields.Datetime(string='Užsakymo laikas')
    order_date = fields.Date(string='Užsakymo data', compute='_compute_order_date', store=True)
    order_month = fields.Char(compute='_compute_order_month', store=True)

    # Statuses
    state = fields.Selection([('imported', 'Užsakymas importuotas'),
                              ('created', 'Užsakymas sukurtas sistemoje'),
                              ('ext_cancel', 'Užsakymas atšauktas išorinėje sistemoje'),
                              ('failed', 'Klaida kuriant užsakymą')],
                             string='Būsena', default='imported', track_visibility='onchange')
    ext_order_status = fields.Char(string='Išorinis užsakymo statusas', inverse='_set_ext_order_status')
    ext_order_type = fields.Char(string='Išorinis orderio tipas')

    # Other fields
    refund_order = fields.Boolean(string='Grąžinimas', inverse='_set_refund_order')
    premium_order = fields.Boolean(string='Premium užsakymas')
    business_order = fields.Boolean(string='Verslo užsakymas')
    buyer_email = fields.Char(string='Pirkėjo paštas')
    currency_code = fields.Char(string='Valiuta', inverse='_set_currency_code')

    # Amounts
    quantity_not_shipped = fields.Float(string='Neišsiųstas kiekis')
    order_amount_total = fields.Float(string='Galutinė suma', compute='_compute_order_amounts')
    order_amount_shipping = fields.Float(string='Siuntimo suma', compute='_compute_order_amounts')
    order_amount_discount = fields.Float(string='Nuolaidos', compute='_compute_order_amounts')
    order_amount_principal = fields.Float(string='Pagrindinė suma', compute='_compute_order_amounts')
    # Including refunds
    order_amount_principal_display = fields.Float(string='Pagrindinė suma', compute='_compute_order_amounts')
    order_amount_total_display = fields.Float(string='Galutinė suma', compute='_compute_order_amounts')

    # Relational fields
    partner_id = fields.Many2one('res.partner', string='Partneris', compute='_compute_partner_id')
    currency_id = fields.Many2one('res.currency', string='Valiuta')
    marketplace_id = fields.Many2one('amazon.marketplace', string='Prekiavietė')
    amazon_order_line_ids = fields.One2many('amazon.order.line', 'amazon_order_id', string='Užsakymo eilutės')
    invoice_id = fields.Many2one('account.invoice', string='Sisteminė sąskaita')
    refunded_order_id = fields.Many2one('amazon.order', string='Kredituojamo užsakymo ID',
                                        compute='_compute_refunded_order_id')
    refunding_order_id = fields.Many2one('amazon.order', string='Kreditinio užsakymo ID',
                                         compute='_compute_refunding_order_id')

    # Computes / Inverses / Constraints -------------------------------------------------------------------------------

    @api.multi
    @api.depends('order_id', 'refund_order')
    def _compute_refunded_order_id(self):
        """
        Compute //
        Get refunded order ID -- Same ID, different settings
        :return: None
        """
        for rec in self.filtered(lambda x: x.refund_order):
            rec.refunded_order_id = self.env['amazon.order'].search(
                [('order_id', '=', rec.order_id), ('refund_order', '=', False)], limit=1)

    @api.multi
    @api.depends('order_id', 'refund_order')
    def _compute_refunding_order_id(self):
        """
        Compute //
        Get refunding order ID -- Same ID, different settings
        :return: None
        """
        for rec in self.filtered(lambda x: not x.refund_order):
            rec.refunded_order_id = self.env['amazon.order'].search(
                [('order_id', '=', rec.order_id), ('refund_order', '=', True)], limit=1)

    @api.multi
    @api.depends('order_time')
    def _compute_order_date(self):
        """
        Compute //
        Get order date from order datetime
        :return: None
        """
        for rec in self.filtered(lambda x: x.order_time):
            rec.order_date = rec.order_time[:10]

    @api.multi
    @api.depends('order_time')
    def _compute_order_month(self):
        """
        Compute //
        Get order month from order datetime
        :return: None
        """
        for rec in self.filtered(lambda x: x.order_time):
            order_time_dt = datetime.strptime(rec.order_time, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            rec.order_month = '{}-{}'.format(order_time_dt.year, order_time_dt.month)

    @api.multi
    @api.depends('marketplace_id.partner_id')
    def _compute_partner_id(self):
        """
        Compute //
        Get partner ID from related marketplace
        :return: None
        """
        for rec in self.filtered(lambda x: x.marketplace_id):
            rec.partner_id = rec.marketplace_id.partner_id

    @api.multi
    def _compute_order_amounts(self):
        """
        Compute //
        Calculate amounts (total, tax, fees) based on amazon order lines
        :return: None
        """
        for rec in self.filtered(lambda x: x.amazon_order_line_ids):
            # Calculate total order amounts
            sign = -1 if rec.refund_order else 1

            # Calculate principal display and actual amount
            principal_lines = rec.amazon_order_line_ids.filtered(lambda x: x.line_type == 'principal')
            rec.order_amount_principal = sum(x.line_amount for x in principal_lines)
            rec.order_amount_principal_display = rec.order_amount_principal * sign

            # Calculate total display and actual amount
            total_lines = rec.amazon_order_line_ids.filtered(lambda x: x.line_type != 'fees')
            rec.order_amount_total = sum(x.line_amount for x in total_lines)
            rec.order_amount_total_display = rec.order_amount_total * sign

            # Calculate other amounts
            rec.order_amount_shipping = sum(
                 x.line_amount for x in rec.amazon_order_line_ids.filtered(lambda x: x.line_type == 'shipping'))
            rec.order_amount_discount = sum(
                 x.line_amount for x in rec.amazon_order_line_ids.filtered(lambda x: x.line_type == 'promotion'))

    @api.multi
    def _set_currency_code(self):
        """
        Inverse //
        Find corresponding res.currency based on external currency code
        :return: None
        """
        for rec in self.filtered(lambda x: x.currency_code):
            currency = self.env['res.currency'].search([('name', '=', rec.currency_code)], limit=1)
            if not currency:
                raise exceptions.UserError(_('Nerasta valiuta su kodu %s!') % rec.currency_code)
            rec.currency_id = currency

    @api.multi
    def _set_ext_order_status(self):
        """
        Inverse //
        If ext order status is not 'Shipped' set ROBO state to 'ext_cancel'
        :return: None
        """
        for rec in self.filtered(lambda x: x.ext_order_status != 'Shipped'):
            rec.state = 'ext_cancel'

    @api.multi
    def _set_marketplace(self):
        """
        Inverse //
        Create or assign a marketplace based on external code
        :return: None
        """
        for rec in self.filtered(lambda x: x.marketplace_code and x.marketplace_name):
            marketplace = self.env['amazon.marketplace'].search([('marketplace_code', '=', rec.marketplace_code)])
            rec.marketplace_id = marketplace

    @api.multi
    def _set_refund_order(self):
        """
        Inverse //
        If order is refund, abs all of it's principal/shipping/wrapping lines
        :return: None
        """
        for rec in self.filtered(lambda x: x.refund_order):
            for line in rec.amazon_order_line_ids:
                sign = -1 if line.line_type not in ['shipping', 'principal', 'gift_wraps'] else 1
                # Always make them negative, some endpoints return refunds with minuses
                # some without... that's why it's ABS'ed first
                line.line_amount = abs(line.line_amount) * sign
                line.amount_tax = abs(line.amount_tax) * sign

    @api.multi
    @api.constrains('order_id')
    def _check_order_id(self):
        """
        Constraints //
        If order is not refund, ensure that order_id is unique
        :return: None
        """
        for rec in self.filtered(lambda x: not x.refund_order):
            if self.search_count(
                    [('order_id', '=', rec.order_id), ('id', '!=', rec.id), ('refund_order', '=', False)]):
                raise exceptions.ValidationError(_('Užsakymo ID negali kartotis!'))

    @api.multi
    def recompute_fields(self):
        """
        Recompute and Re-inverse all significant fields
        :return: None
        """
        self._set_currency_code()
        self._set_marketplace()
        self._compute_refunded_order_id()
        self._compute_refunding_order_id()
        self._compute_order_date()
        self._compute_order_month()
        self._compute_partner_id()

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def validator(self):
        """
        Validate amazon.order and amazon.order.line records, so they meet all criteria
        for account.invoice creation
        :return: None
        """
        validated_records = self.env['amazon.order']
        # Filtering
        filtered_records = self.filtered(
            lambda x: not x.invoice_id and x.state in ['imported', 'failed'] and x.ext_order_status == 'Shipped')

        # Recompute all fields
        filtered_records.recompute_fields()
        filtered_records.mapped('amazon_order_line_ids').recompute_fields()

        # Validate the fields
        for rec in filtered_records:
            error_template = str()
            if not rec.amazon_order_line_ids:
                error_template += 'Nerastos Amazon užsakymo eilutės\n'
            if not rec.marketplace_id:
                error_template += 'Nerasta Amazon prekiavietė\n'
            if not rec.partner_id:
                error_template += 'Nerastas prekiavietės partneris\n'
            if not rec.currency_id:
                error_template += 'Nerasta užsakymo valiuta\n'
            if rec.marketplace_id and rec.marketplace_id.state != 'configured':
                error_template += 'Nesukonfigūruota susijusi prekiavietė\n'

            # Always create refunds without refunded order_id
            # Line is left here if behaviour changes in the future
            if rec.refund_order and not rec.refunded_order_id:
                pass

            # We skip fee lines in account invoice creation
            for line in rec.amazon_order_line_ids.filtered(lambda x: x.line_type != 'fees'):
                if not line.amazon_product_id.product_id:
                    error_template += 'Eilutė "{}" neturi sukonfigūruoto produkto\n'.format(line.ext_line_name)
                if not line.amazon_product_id.spec_product and not line.amazon_product_id.amazon_category_id:
                    error_template += 'Eilutė "{}" neturi sukonfigūruotos kategorijos\n'.format(line.ext_line_name)
                if line.amazon_product_id and line.amazon_product_id.state != 'working':
                    error_template += 'Eilutės "{}" Amazon produktas nėra sukonfigūruotas\n'.format(line.ext_line_name)
                if line.amazon_product_id.amazon_category_id and not \
                        line.amazon_product_id.amazon_category_id.activated:
                    error_template += 'Eilutės "{}" kategorija nėra aktyvuota\n'.format(line.ext_line_name)
                if not line.account_id:
                    error_template += 'Eilutė "{}" neturi numatytosios buh. sąskaitos\n'.format(line.ext_line_name)

            if error_template:
                error_template = 'Nepavyko sukurti Amazon užsakymo dėl šių problemų: \n\n' + error_template
                self.post_message(error_template, state='failed', orders=rec)
            else:
                validated_records |= rec
        return validated_records

    @api.multi
    def invoice_creation_prep(self, validate=True):
        """
        Prepare amazon.order for account.invoice creation by sending them to validator
        :return None
        """
        # Only activate invoice creation if amazon integration is configured
        if not self.env.user.company_id.amazon_integration_configured:
            return

        # Validate the records
        validated_orders = self
        if validate:
            validated_orders = self.validator()

        refund_orders = validated_orders.filtered(lambda x: x.refund_order)
        sale_orders = validated_orders.filtered(lambda x: not x.refund_order)

        grouped_data = {}
        for sale_order in sale_orders:
            # Loop through lines and build dict of dicts with following mapping
            # {PARTNER: {MONTH: SALE_ORDER, MONTH_2: SALE_ORDER}}...
            partner = sale_order.partner_id
            grouped_data.setdefault(partner, {})

            month = sale_order.order_month
            grouped_data[partner].setdefault(month, self.env['amazon.order'])
            grouped_data[partner][month] |= sale_order

        for partner, months in iteritems(grouped_data):
            for month, lines in iteritems(months):
                lines.create_invoices()

        # Do not group refund orders in separate invoices, create them one by one
        for rec in refund_orders:
            rec.create_invoices(refund=True)

    @api.multi
    def create_invoices(self, refund=False):
        """
        Create account.invoice records from amazon.order records.
        Two types of creation can be done - normal operation and refund operation
        :param refund: indicates whether operation is of refund type
        :return: None
        """
        default_obj = self.sorted(lambda r: r.order_date, reverse=True)[0]
        invoice_obj = self.env['account.invoice'].sudo()
        company = self.sudo().env.user.company_id

        default_account = self.env['account.account'].search([('code', '=', '2410')], limit=1).id
        default_journal = self.env['account.journal'].search([('type', '=', 'sale')], limit=1).id
        default_location = self.env['stock.location'].search(
            [('usage', '=', 'internal')], order='create_date desc', limit=1)
        delivery_wizard = self.env['invoice.delivery.wizard'].sudo()

        invoice_lines = []
        invoice_values = {
            'external_invoice': True,
            'imported_api': True,
            'force_dates': True,
            'price_include_selection': 'inc',
            'account_id': default_account,
            'journal_id': default_journal,
            'partner_id': default_obj.marketplace_id.partner_id.id,
            'invoice_line_ids': invoice_lines,
            'type': 'out_refund' if refund else 'out_invoice',
            'date_invoice': default_obj.order_date,
            'currency_id': default_obj.currency_id.id,
        }

        order_lines = self.mapped('amazon_order_line_ids')
        spec_order_lines = main_order_lines = self.env['amazon.order.line']

        # If amazon tax is included, main order lines are treated as spec lines
        if company.include_amazon_tax:
            spec_order_lines = order_lines.filtered(lambda x: x.line_type == 'principal')
        else:
            main_order_lines = order_lines.filtered(lambda x: x.line_type == 'principal')

        # Check if fee inclusion option is selected, and if so, add all fee lines as well
        if company.include_amazon_commission_fees:
            spec_order_lines |= order_lines.filtered(lambda x: x.line_type != 'principal')
        else:
            spec_order_lines |= order_lines.filtered(lambda x: x.line_type not in ['fees', 'principal'])

        total_invoice_amount = 0.0

        grouped_lines = {}
        for line in main_order_lines:
            # Loop through lines and build dict of dicts with following mapping
            # {PRODUCT: {PRICE_UNIT: ORDER_LINES, PRICE_UNIT_2: ORDER_LINES}}...
            product = line.amazon_product_id.product_id
            grouped_lines.setdefault(product, {})
            grouped_lines[product].setdefault(line.price_unit, self.env['amazon.order.line'])
            grouped_lines[product][line.price_unit] |= line

        # Loop through grouped lines and add them to invoice_line list
        for product, by_price_unit in iteritems(grouped_lines):
            for price_unit, lines in iteritems(by_price_unit):
                tot_quantity = sum(lines.mapped('quantity'))
                total_invoice_amount += price_unit * tot_quantity
                self.add_invoice_line(invoice_lines, lines, tot_quantity, price_unit, product)

        # Prepare spec product lines, lines are grouped only by product
        grouped_lines = {}
        for line in spec_order_lines:
            product = line.amazon_product_id.product_id
            grouped_lines.setdefault(product, self.env['amazon.order.line'])
            grouped_lines[product] |= line

        # Loop through grouped lines and add them to invoice_line list
        for product, lines in iteritems(grouped_lines):
            spec_amount = sum(lines.mapped('line_amount_w_vat'))
            total_invoice_amount += spec_amount
            self.add_invoice_line(invoice_lines, lines, 1, spec_amount, product)

        try:
            invoice = invoice_obj.create(invoice_values)
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
                body = _('Sąskaitos suma nesutampa su paskaičiuota suma (%s != %s).\n') % (
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

        # Create delivery
        rec = self.sudo().env['ir.module.module'].search([('name', '=', 'robo_stock')])
        if rec and rec.state in ['installed', 'to upgrade']:
            wizard = delivery_wizard.with_context(invoice_id=invoice.id).create({'location_id': default_location.id})
            wizard.create_delivery()
            if invoice.picking_id:
                invoice.picking_id.action_assign()
                if invoice.picking_id.state == 'assigned':
                    invoice.picking_id.do_transfer()

        # Write state changes and commit
        self.write({'state': 'created', 'invoice_id': invoice.id})

        # Reconcile with refund
        self.reconcile_with_refund(refund)
        self.env.cr.commit()

    @api.model
    def add_invoice_line(self, invoice_lines, group, qty, amount, product):
        """
        Add invoice line to the invoice lines list
        :param invoice_lines: list of invoice.line values
        :param group: group loop variable (amazon.order.line)
        :param qty: quantity of the line
        :param amount: amount of the line
        :param product: product of the line
        :return: None
        """
        default_obj = group[0]
        if default_obj.amazon_product_id.product_id.acc_product_type == 'service':
            account_tax = default_obj.amazon_order_id.marketplace_id.service_tax_id
        else:
            account_tax = default_obj.amazon_order_id.marketplace_id.product_tax_id

        # Determine the account of the product //
        # Take it from product or category or use the static one
        product_account = product.get_product_income_account()
        if not product_account:
            product_account = default_obj.account_id

        line_vals = {
            'name': default_obj.ext_line_name,
            'product_id': product.id,
            'quantity': qty,
            'price_unit': amount,
            'account_id': product_account.id,
            'invoice_line_tax_ids': [(6, 0, account_tax.ids)],
            'amazon_order_line_ids': [(6, 0, group.ids)]
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
                _('Priešingas sudengimas galimas tik tos pačios sąskaitos užsakymams'))

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
                    body = _('Nepavyko sudengimas su priešinga sąskaita, sisteminė klaida: %s') % str(exc.args[0])
                    self.post_message(body, orders=rec)

    # Misc methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def custom_rollback(self, msg):
        """
        Rollback current transaction, post message to the object and commit
        :return: None
        """
        self.env.cr.rollback()
        body = _('Nepavyko sukurti sąskaitos, sisteminė klaida: %s') % str(msg)
        self.post_message(body, state='failed', orders=self)
        self.env.cr.commit()

    @api.model
    def post_message(self, body, state=None, orders=None):
        """
        Post message to amazon.order
        :param body: message to-be posted to amazon.order (str)
        :param state: object state (str)
        :param orders: amazon.order records
        :return: None
        """
        if orders is None:
            orders = self.env['amazon.order']
        if orders:
            if state:
                orders.write({'state': state})
            for order in orders:
                order.message_post(body=body)

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(x.id, _('Užsakymas %s') % x.order_id) for x in self]


AmazonOrder()
