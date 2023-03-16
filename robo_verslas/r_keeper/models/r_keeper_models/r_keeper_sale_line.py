# -*- coding: utf-8 -*-
import logging
from odoo.addons.queue_job.job import identity_exact, job
from odoo import models, fields, api, tools, _, SUPERUSER_ID
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo.api import Environment
from odoo.exceptions import MissingError

_logger = logging.getLogger(__name__)


class RKeeperSaleLine(models.Model):
    _name = 'r.keeper.sale.line'
    _inherit = ['mail.thread']
    _description = '''
    Model that stores rKeeper sale records,
    account invoices are created using sale data.
    '''

    # Identification
    doc_number = fields.Char(string='Dokumento numeris')

    # Dates
    doc_date = fields.Date(string='Dokumento data')
    sale_date = fields.Date(string='Pardavimo data')

    # Product information
    product_name = fields.Char(string='Produkto pavadinimas')
    uom_code = fields.Char(string='Produkto vnt. kodas')
    product_code = fields.Char(string='Produkto kodas')
    product_type = fields.Selection(
        [('1', 'Paslauga'),
         ('2', 'Sandėliuojamas produktas')],
        string='Produkto tipas', default='1'
    )
    product_id = fields.Many2one(
        'product.product', string='Produktas',
        compute='_compute_product_id', store=True
    )
    r_keeper_sale_line_modifier_ids = fields.One2many(
        'r.keeper.sale.line.modifier',
        'r_keeper_sale_line_id',
        string='Pardavimo modifikatoriai'
    )

    # Amounts / Quantities
    quantity = fields.Float(string='Kiekis')
    pu_wo_vat = fields.Float(string='Vnt. kaina be PVM')
    pu_w_vat = fields.Float(string='Vnt. kaina su PVM')
    calculated_price_unit = fields.Float(compute='_compute_calculated_price_unit')
    amount_wo_vat = fields.Float(string='Suma be PVM')
    amount_vat = fields.Float(string='Mokesčių suma')
    amount_w_vat = fields.Float(
        string='Suma su PVM',
        compute='_compute_amount_w_vat', store=True,
    )

    # Fields for zero amount sales
    zero_amount_sale = fields.Boolean(
        compute='_compute_zero_amount_sale',
        store=True, string='Nulinės sumos'
    )
    zero_sale_prime_cost = fields.Float(
        compute='_compute_zero_sale_prime_cost',
        store=True, string='Nulinio pardavimo savikaina'
    )

    # Tax information
    tax_id = fields.Many2one(
        'account.tax', string='Susiję mokesčiai',
        compute='_compute_tax_id', store=True
    )
    force_taxes = fields.Boolean(
        string='Taikyti priverstinius mokesčius',
        compute='_compute_tax_id',
        store=True
    )
    # Indicates that current tax_id is from mapper
    mapped_taxes = fields.Boolean(
        compute='_compute_tax_id', store=True
    )

    # Point of sale info
    pos_code = fields.Char(string='Pardavimo taško kodas', inverse='_set_pos_code')
    point_of_sale_id = fields.Many2one('r.keeper.point.of.sale', string='Pardavimo taškas')

    # State / Relations
    state = fields.Selection(
        [('imported', 'Importuota'),
         ('updated', 'Atnaujinta (Reikia peržiūrėti)'),
         ('created', 'Sąskaita sukurta sistemoje'),
         ('failed', 'Klaida kuriant sąskaitą'),
         ('created_inventory', 'Nurašymas sukurtas sistemoje'),
         ('failed_inventory', 'Klaida kuriant nurašymą')],
        string='Būsena', default='imported', track_visibility='onchange'
    )
    line_type = fields.Selection(
        [('out_refund', 'Grąžinimas'),
         ('out_invoice', 'Pardavimas')],
        string='Būsena', compute='_compute_line_type'
    )
    invoice_id = fields.Many2one(
        'account.invoice', string='Sisteminė sąskaita',
        related='invoice_line_id.invoice_id',
        copy=False, store=True
    )
    picking_id = fields.Many2one(
        'stock.picking', string='Važtaraštis',
        related='invoice_id.picking_id',
        auto_join=True, index=True,
        copy=False, store=True
    )
    inventory_id = fields.Many2one('stock.inventory', string='Atsargų nurašymas')
    invoice_line_id = fields.Many2one('account.invoice.line', string='Sisteminė sąskaitos eilutė', copy=False)
    mrp_production_id = fields.Many2one('mrp.production', string='Susijusi gamyba', copy=False)
    production_state = fields.Selection(
        [('not_produced', 'Negaminta'),
         ('failed_to_create', 'Gaminimas nepavyko'),
         ('failed_to_reserve', 'Rezervavimas nepavyko'),
         ('produced', 'Pagaminta')],
        string='Gamybos būsena',
        compute='_compute_production_state', store=True
    )
    # Misc fields
    extra_data = fields.Text(string='Papildoma informacija')
    payment_completed = fields.Boolean(string='Apmokėta')
    allow_production_creation = fields.Boolean(compute='_compute_allow_production_creation')
    has_bom_at_sale_date = fields.Boolean(
        string='Produktas turi komplektaciją pardavimo datai',
    )

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    @api.depends('amount_w_vat')
    def _compute_zero_amount_sale(self):
        """Computes whether current sale is zero amount sale"""
        for rec in self:
            if tools.float_is_zero(rec.amount_w_vat, precision_digits=2):
                rec.zero_amount_sale = True

    @api.multi
    @api.depends('zero_amount_sale', 'product_id', 'quantity')
    def _compute_zero_sale_prime_cost(self):
        """Calculate prime cost, only applied on zero amount sales"""
        for rec in self.filtered('zero_amount_sale'):
            rec.zero_sale_prime_cost = rec.product_id.avg_cost * rec.quantity

    @api.multi
    @api.depends('amount_wo_vat', 'amount_vat')
    def _compute_amount_w_vat(self):
        """Calculate amount with taxes"""
        for rec in self:
            rec.amount_w_vat = rec.amount_wo_vat + rec.amount_vat

    @api.multi
    @api.depends('amount_wo_vat', 'quantity', 'mapped_taxes')
    def _compute_calculated_price_unit(self):
        """
        Calculates artificial price unit from final amount without VAT.
        If product has mapped taxes, simple amount with VAT is used
        """
        for rec in self:
            # If product has mapped taxes always use amount with VAT
            if rec.mapped_taxes:
                rec.calculated_price_unit = rec.pu_w_vat
            elif rec.quantity:
                rec.calculated_price_unit = rec.amount_wo_vat / rec.quantity

    @api.multi
    @api.depends('mrp_production_id.state')
    def _compute_production_state(self):
        """
        Compute production state based on
        actual MRP production record state.
        Failed state is written manually
        :return:
        """
        for rec in self:
            if not rec.mrp_production_id:
                rec.production_state = 'not_produced'
            elif rec.mrp_production_id.state == 'done':
                rec.production_state = 'produced'
            else:
                rec.production_state = 'failed_to_reserve'

    @api.multi
    def _compute_allow_production_creation(self):
        """
        Check if production creation can be allowed
        on current record
        :return: None
        """
        for rec in self:
            rec.allow_production_creation = \
                rec.production_state in ['not_produced', 'failed_to_create'] and (
                        rec.invoice_id or rec.zero_amount_sale) \
                and rec.product_id.product_tmpl_id.bom_id and not rec.mrp_production_id

    @api.multi
    @api.depends('product_code')
    def _compute_product_id(self):
        """
        Compute //
        Make relation between sale and system product
        using product_code passed in the sale
        :return: None
        """
        for rec in self.filtered(lambda x: x.product_code):
            rec.product_id = self.env['product.product'].sudo().search(
                [('default_code', '=', rec.product_code)], limit=1
            )

    @api.multi
    @api.depends('amount_wo_vat', 'amount_vat', 'product_id')
    def _compute_tax_id(self):
        """
        Compute //
        Make relation between sale and system product
        using product_code passed in the sale
        :return: None
        """
        for rec in self:
            account_tax, force_taxes, mapped_taxes = rec.find_related_account_tax()
            rec.tax_id = account_tax
            rec.force_taxes = force_taxes
            rec.mapped_taxes = mapped_taxes

    @api.multi
    @api.depends('amount_wo_vat')
    def _compute_line_type(self):
        """
        Compute //
        Check whether current line
        is refund line or not
        """
        for rec in self:
            if tools.float_compare(0.0, rec.amount_wo_vat, precision_digits=2) > 0:
                rec.line_type = 'out_refund'
            else:
                rec.line_type = 'out_invoice'

    @api.multi
    def _set_pos_code(self):
        """
        Inverse //
        Find related point of sale using the code provided
        by rKeeper. If record does not exist - create it
        :return: None
        """
        for rec in self.filtered(lambda x: x.pos_code):
            point_of_sale = self.env['r.keeper.point.of.sale'].search([('code', '=', rec.pos_code)])
            if not point_of_sale:
                point_of_sale = point_of_sale.create_point_of_sale(rec.pos_code)
            rec.point_of_sale_id = point_of_sale

    @api.multi
    def recompute_fields(self):
        """
        Manually triggers all computes
        and inverses of current model
        :return: None
        """
        self._compute_product_id()
        self._compute_tax_id()
        self._compute_line_type()
        self._set_pos_code()

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def calculate_has_bom_at_date(self):
        """Manually calculates whether sale product has a bom at sale date"""
        sale_lines = self
        sales_with_bom = sales_wo_bom = self.env['r.keeper.sale.line']
        if not sale_lines or self._context.get('all_records'):
            # If no sales are passed, search for all non produced records without related BOM
            sale_lines = self.search([('production_state', '!=', 'produced'), ('has_bom_at_sale_date', '=', False)])
            # Instantly add produced sales to the batch
            sales_with_bom |= self.search(
                [('production_state', '=', 'produced'), ('has_bom_at_sale_date', '=', False)]
            )
        for rec in sale_lines:
            # Dependency is on bom_ids, but we call bom_id,
            # while passing bom_at_date, so only single record is returned
            if rec.product_id.with_context(bom_at_date=rec.sale_date).product_tmpl_id.bom_id:
                sales_with_bom |= rec
            else:
                sales_wo_bom |= rec
        sales_with_bom.sudo().filtered(lambda x: not x.has_bom_at_sale_date).write({'has_bom_at_sale_date': True})
        sales_wo_bom.sudo().filtered(lambda x: x.has_bom_at_sale_date).write({'has_bom_at_sale_date': False})

    @api.multi
    def find_related_account_tax(self):
        """
        Find account.tax record for the sale line, based on
        forced tax code, or percentage that is calculated from
        other sale amounts
        :return: account.tax record,
                 True/False (depending on if tax amounts should be forced),
                 True/False (depending if specific tax record was forcibly mapped)
        """
        self.ensure_one()
        account_tax = self.env['account.tax']
        force_taxes = mapped_taxes = False

        # Check whether tax mapper exists
        tax_mapper = self.env['r.keeper.product.tax.mapper'].search(
            [('product_id', '=', self.product_id.id)]
        )
        if tax_mapper:
            mapped_taxes = True
            account_tax = tax_mapper.tax_id

        if not account_tax:
            amount_total = self.amount_wo_vat + self.amount_vat
            if not tools.float_is_zero(amount_total, precision_digits=2):
                percentage = round(((amount_total / self.amount_wo_vat) - 1) * 100, 2)
                forbidden_taxe_codes = self.env['ir.config_parameter'].sudo().get_param('r_keeper_forbidden_tax_codes')
                base_tax_domain = [('type_tax_use', '=', 'sale'), ('price_include', '=', False)]
                if forbidden_taxe_codes:
                    base_tax_domain.append(('code', 'not in', forbidden_taxe_codes.split(',')))
                account_tax = self.env['account.tax'].search([('amount', '=', percentage)] + base_tax_domain, limit=1)

                # If corresponding taxes were not found, try to round the percentage to the nearest one
                # accepted percentages are 21, 9 and 5. If percentage is not in these ranges, continue
                if not account_tax:
                    # TODO: improve this maybe with some sort of settings. Removing the option to have PVM3 for bk
                    # r_keeper seems to be passing weird amounts 0.20 + 0.01 tax when rate should be 9%
                    # lower amounts are also problematic.
                    amount_leaf_added = False
                    if 15 <= percentage <= 30:
                        base_tax_domain.append(('amount', '=', 21))
                        amount_leaf_added = True
                    elif 3 <= percentage < 15:
                        base_tax_domain.append(('amount', '=', 9))
                        amount_leaf_added = True
                    elif 3 <= percentage < 7:
                        base_tax_domain.append(('amount', '=', 5))
                        amount_leaf_added = True

                    # Indicates that domain has amount leaf appended
                    if amount_leaf_added:
                        force_taxes = True
                        account_tax = self.env['account.tax'].search(base_tax_domain, limit=1)

        return account_tax, force_taxes, mapped_taxes

    @api.multi
    def create_invoices_prep(self):
        """
        Prepare rKeeper sale line objects
        for account invoice creation
        :return: None
        """
        # Filter records that have invoices or incorrect states
        sales = self.filtered(
            lambda x: not x.invoice_id and x.state in ['imported', 'failed'] and not x.zero_amount_sale
        )
        # Check constraints and validate records
        validated_records = sales.check_record_creation_constraints()
        if validated_records:
            # This way of looping is way faster than filtered
            grouped_lines = {}
            for line in validated_records:
                # Loop through lines and build dict of dicts with following mapping
                pos = line.point_of_sale_id
                s_date = line.sale_date
                l_type = line.line_type

                grouped_lines.setdefault(pos, {})
                grouped_lines[pos].setdefault(s_date, {})
                grouped_lines[pos][s_date].setdefault(l_type, {})
                grouped_lines[pos][s_date][l_type].setdefault(line.product_id, self.env['r.keeper.sale.line'])
                grouped_lines[pos][s_date][l_type][line.product_id] |= line
            count = 0
            batch_size = int(self.env['ir.config_parameter'].get_param('r_keeper_split_invoice_by_products_number', 10))
            sale_lines = self.env['r.keeper.sale.line']
            # Loop through grouped lines and create invoices for each batch
            for pos, by_pos in grouped_lines.items():
                for sale_date, by_sale_date in by_pos.items():
                    for line_type, by_product_data in by_sale_date.items():
                        for product, lines in by_product_data.items():
                            sale_lines |= lines
                            count += 1
                            if count >= batch_size:
                                sale_lines.with_delay(
                                    channel=self.env['r.keeper.data.import'].get_channel_to_use(1, 'invoice'),
                                    identity_key=identity_exact, priority=90,
                                    description='Create rKeeper Invoices', eta=30
                                ).create_invoices()
                                sale_lines = self.env['r.keeper.sale.line']
                                count = 0

    @api.multi
    def check_record_creation_constraints(self, invoice_mode=True):
        """
        Check constraints for rKeeper sale records,
        so they meet all criteria for account.invoice/stock.inventory creation.
        Records that have some errors are filtered out
        :return: None
        """
        validated_records = self.env['r.keeper.sale.line']
        if not self._context.get('skip_creation_computation'):
            # Recompute all fields
            self.recompute_fields()
        # Validate the fields
        for rec in self:
            error_template = str()
            if not rec.point_of_sale_id.configured:
                error_template += _('Nerastas arba nesukonfigūruotas susijęs pardavimo taškas\n')
            if not rec.product_id:
                error_template += _('Nerastas susijęs produktas\n')
            if invoice_mode and not rec.tax_id:
                error_template += _('Nerasti susiję mokesčiai\n')
            if error_template:
                error_template = 'Nepavyko sukurti rKeeper užsakymo dėl šių problemų: \n\n' + error_template
                rec.post_message(error_template, state='failed')
            else:
                validated_records |= rec
        return validated_records

    @api.multi
    @job
    def create_invoices(self):
        """
        Create account.invoice records from rKeeper sale records.
        Two types of creation can be done - normal operation and refund operation
        :return: None
        """
        default_obj = self.sorted(lambda r: r.sale_date, reverse=True)[0]
        invoice_obj = self.env['account.invoice'].sudo()

        # Account 2410
        default_account = self.env.ref('l10n_lt.1_account_229')
        default_type = default_obj.line_type

        # Get other default values from POS
        default_journal = default_obj.point_of_sale_id.journal_id
        default_location = default_obj.point_of_sale_id.location_id
        default_partner = default_obj.point_of_sale_id.partner_id
        default_analytic = default_obj.point_of_sale_id.analytic_account_id

        invoice_lines = []
        invoice_values = {
            'external_invoice': True,
            'imported_api': True,
            'force_dates': True,
            'skip_isaf': True,
            'skip_global_reconciliation': True,
            'price_include_selection': 'exc',
            'account_id': default_account.id,
            'journal_id': default_journal.id,
            'partner_id': default_partner.id,
            'invoice_line_ids': invoice_lines,
            'type': default_type,
            'date_invoice': default_obj.sale_date,
        }

        # Check if any line has taxes calculated with error margin
        force_taxes = any(x.force_taxes for x in self)
        forced_taxes_amounts = {}

        # Declare the control invoice amounts
        total_invoice_amount = vat_invoice_amount = untaxed_artificial_amount = untaxed_invoice_amount = 0.0

        grouped_lines = {}
        for line in self:
            # Loop through lines and build dict of dicts with following mapping
            # {PRODUCT: TAX: {PRICE_UNIT: SALE_LINES, PRICE_UNIT_2: SALE_LINES}}...
            product = line.product_id
            tax = line.tax_id
            p_unit = line.calculated_price_unit
            grouped_lines.setdefault(product, {})
            grouped_lines[product].setdefault(line.tax_id, {})
            grouped_lines[product][tax].setdefault(p_unit, self.env['r.keeper.sale.line'])
            grouped_lines[product][tax][p_unit] |= line

        # Loop through grouped lines and add them to invoice_line list
        for product, by_product in grouped_lines.items():
            for tax, by_tax in by_product.items():
                for price_unit, lines in by_tax.items():
                    # Determine the account of the product
                    product_account = product.get_product_income_account(return_default=True)
                    # Taxes are always mapped per product
                    mapped_taxes = lines[0].mapped_taxes
                    # Get total quantity of batch lines
                    tot_quantity = sum(lines.mapped('quantity'))
                    # Accumulate artificial invoice amount
                    untaxed_artificial_amount += price_unit * tot_quantity
                    # If mapped taxes are applied, price_unit is always VAT included
                    if mapped_taxes:
                        untaxed_invoice_amount += price_unit * tot_quantity
                    else:
                        # Get amount vat of the batch
                        batch_amount_vat = sum(lines.mapped('amount_vat'))
                        if force_taxes:
                            # If at least one line had forced taxes
                            # save forced amounts grouped by key of tax/account/analytic-account
                            tax_account = tax.account_id or product_account
                            group_key = '{}/{}/{}'.format(tax.id, tax_account.id, default_analytic.id)
                            forced_taxes_amounts.setdefault(
                                group_key, {
                                    'amount': 0.0, 'tax_id': tax.id,
                                    'tax_account_id': tax_account.id,
                                    'line_account_id': product_account.id,
                                    'analytic_account_id': default_analytic.id,
                                })
                            forced_taxes_amounts[group_key]['amount'] += batch_amount_vat

                        # Accumulate total vat amount and untaxed amount
                        vat_invoice_amount += batch_amount_vat
                        untaxed_invoice_amount += sum(lines.mapped('amount_wo_vat'))

                    base_invoice_line_vals = {
                        'name': product.name,
                        'product_id': product.id,
                        'quantity': tot_quantity,
                        'price_unit': price_unit,
                        'account_analytic_id': default_analytic.id,
                        'account_id': product_account.id,
                        'invoice_line_tax_ids': [(6, 0, tax.ids)],
                        'r_keeper_sale_line_ids': [(6, 0, lines.ids)],
                    }

                    # Get additional line values that fix rounding issues caused by total price division by quantity
                    # for price_unit
                    additional_line_values = self._get_additional_balancing_line_values(base_invoice_line_vals)

                    # Add additional line values as invoice lines
                    total_additional_line_quantity = 0.0
                    for line_values in additional_line_values:
                        total_additional_line_quantity += line_values.get('quantity', 0.0)
                        invoice_lines.append((0, 0, line_values))

                    line_vals = base_invoice_line_vals.copy()
                    # Quantity should be adjusted since additional lines use the quantity of the lines
                    line_vals['quantity'] = tot_quantity - total_additional_line_quantity
                    invoice_lines.append((0, 0, line_vals))

        # Calculate total invoice amount
        total_invoice_amount += vat_invoice_amount + untaxed_artificial_amount

        # Check whether rKeeper amounts match
        if tools.float_compare(untaxed_artificial_amount, untaxed_invoice_amount, precision_digits=2):
            self.custom_rollback('rKeeper sąskaitos sumos yra neteisingos')
            return

        # Try to create the invoice
        try:
            invoice = invoice_obj.create(invoice_values)
        except Exception as e:
            self.custom_rollback(e.args[0])
            return

        # Check if there are any forced taxes amounts
        if forced_taxes_amounts:
            for data in forced_taxes_amounts.values():
                # Find corresponding invoice tax line
                invoice_tax_line = invoice.tax_line_ids.filtered(
                    lambda x: x.tax_id.id == data['tax_id'] and x.account_id.id == data['tax_account_id']
                    and (x.account_analytic_id.id == data['analytic_account_id'] or not x.account_analytic_id)
                )
                current_amount = invoice_tax_line.amount
                # Get the difference between tax amounts
                tax_difference = tools.float_round(data['amount'] - current_amount, precision_digits=2)
                if not tools.float_is_zero(tax_difference, precision_digits=2):
                    # Check if amount should be "moved" or just subtracted
                    untaxed_difference = tools.float_round(
                        invoice.amount_untaxed_signed - untaxed_artificial_amount, precision_digits=2)
                    # If there's a difference, write new amount
                    # to tax line and force the taxes
                    invoice_tax_line.write({'amount': data['amount']})
                    if not invoice.force_taxes:
                        invoice.force_taxes = True

                    if not tools.float_is_zero(untaxed_difference, precision_digits=2):
                        # Get the invoice line that contains this tax
                        invoice_line_to_modify = invoice.invoice_line_ids.filtered(
                            lambda x: data['tax_id'] in x.invoice_line_tax_ids.ids
                            and x.account_id.id == data['line_account_id']
                            and x.account_analytic_id.id == data['analytic_account_id']
                        )[0]
                        # Calculate new amount and subtract it from current amount
                        # depends so that new forced tax amount and this untaxed
                        # amount still make the same total e.g.
                        # Before this block of code -> vat5 + untaxed15 = total20,
                        # after this block of code -> vat6 + untaxed14 = total20
                        new_amount = tools.float_round(
                            invoice_line_to_modify.amount_depends - untaxed_difference, precision_digits=2
                        )
                        invoice_line_to_modify.write({
                            'amount_depends': new_amount,
                            'price_subtotal_make_force_step': True,
                            'price_subtotal_save_force_value': new_amount
                        })
                        invoice_line_to_modify.with_context(
                            direct_trigger_amount_depends=True).onchange_amount_depends()

        if default_type == 'out_refund':
            total_invoice_amount *= -1

        # Check whether amounts do match before opening an invoice
        compare_amounts = [
            (total_invoice_amount, invoice.amount_total_signed, 'Total Amount'),
            (vat_invoice_amount, invoice.amount_tax_signed, 'VAT Amount')
        ]
        # Get allowed invoice difference
        allowed_diff = self.env['ir.config_parameter'].sudo().get_param(
            'r_keeper_invoice_allowed_diff_amount'
        )
        try:
            allowed_diff = float(allowed_diff)
        except (TypeError, ValueError):
            allowed_diff = 0.01

        amount_errors = str()
        for calculated, factual, a_type in compare_amounts:
            if tools.float_compare(calculated, factual, precision_digits=2):
                diff = tools.float_round(abs(calculated - factual), precision_digits=2)
                # It's already rounded here, so it's fine to compare with '>'
                if diff > allowed_diff:
                    amount_errors += _('Sąskaitos suma nesutampa su paskaičiuota suma (%s != %s). %s') % (
                        calculated, factual, a_type
                    )
        # Check if invoice has any amount errors and rollback with error if it does
        if amount_errors:
            self.custom_rollback(amount_errors)
            return

        # Open the invoice and force the partner
        try:
            invoice.partner_data_force()
            invoice.action_invoice_open()
        except Exception as e:
            self.custom_rollback(e.args[0])
            return

        invoice.accountant_validated = True
        self.write({'state': 'created'})

        # Create delivery
        if any(x.product_id.type == 'product' for x in self):
            wizard = self.env['invoice.delivery.wizard'].sudo().with_context(
                invoice_id=invoice.id).create(
                {'location_id': default_location.id}
            )
            # If we fail to create the picking, we rollback the whole invoice creation
            try:
                wizard.create_delivery()
            except Exception as e:
                self.custom_rollback(e.args[0], action_type='delivery_creation')
                return

        self.env.cr.commit()

    @api.model
    def _get_additional_balancing_line_values(self, base_line_values):
        """
        Returns a list of adjustment lines based on the base line values provided. When having a large quantity and a
        total amount, dividing the total amount by the quantity returns a price unit amount which rounded and
        multiplied by the quantity doesn't return the initial (total) amount.

        For example 256.0/21 = 12.19047619
        Rounded is 12.19, 12.19*21=255.99
        In this case 20 products should be of price 12.19 and 1 product of price 12.2

        """
        res = list()
        if not base_line_values:
            return res
        quantity = base_line_values.get('quantity', 0.0)
        if tools.float_compare(quantity, 1.0, precision_digits=2) <= 0:
            # Only add additional lines if the quantity is more than one
            return res
        price_unit = base_line_values.get('price_unit', 0.0)
        if not price_unit or tools.float_compare(price_unit, 0.0, precision_digits=2) <= 0:
            return res

        product_price_dp = self.env['decimal.precision'].sudo().precision_get('Product Price') or 2
        allowed_rounding_diff = 0.01

        # Calculate difference after rounding
        amount_total_untaxed = quantity * price_unit
        price_unit_rounded = tools.float_round(price_unit, precision_digits=product_price_dp)
        amount_total_untaxed_rounded = price_unit_rounded * quantity
        # Subtotal is rounded to two digits
        price_subtotal = tools.float_round(amount_total_untaxed_rounded, precision_digits=2)
        rounding_diff = amount_total_untaxed - price_subtotal

        # No additional lines are necessary if the difference after rounding is zero
        if tools.float_is_zero(rounding_diff, precision_digits=product_price_dp):
            return res

        # Bigger difference than expected - provide no additional lines, invoice creation should fail later due to price
        # mismatch
        if tools.float_compare(abs(rounding_diff), allowed_rounding_diff, precision_digits=product_price_dp) > 0:
            return res

        # Calculate the adjustment based on the total amount and the total rounded amount
        adjustment_line_vals = base_line_values.copy()
        adjustment_line_vals.update({
            'quantity': 1.0,
            'price_unit': tools.float_round(
                amount_total_untaxed - price_unit_rounded * (quantity - 1),
                precision_digits=product_price_dp
            )
        })
        res.append(adjustment_line_vals)
        return res

    @api.multi
    def create_inventory_write_off_prep(self):
        """
        Prepare rKeeper sale line objects for stock inventory creation.
        Sales that contain zero prices amounts are used in this action.
        Records are validated and filtered out before creation.
        :return: None
        """
        # Filter out sales before validation
        sales = self.filtered(
            lambda x: x.state in ['imported', 'failed', 'failed_inventory']
            and not x.inventory_id and x.zero_amount_sale
            and x.production_state == 'produced'
        )
        # Check constraints and validate records
        validated_records = sales.check_record_creation_constraints(invoice_mode=False)
        if validated_records:
            grouped_lines = {}
            for line in validated_records:
                # Loop through lines and build dict of dicts with following mapping
                pos = line.point_of_sale_id
                s_date = line.sale_date
                l_type = line.line_type

                grouped_lines.setdefault(pos, {})
                grouped_lines[pos].setdefault(s_date, {})
                grouped_lines[pos][s_date].setdefault(l_type, self.env['r.keeper.sale.line'])
                grouped_lines[pos][s_date][l_type] |= line

            # Loop through grouped lines and create inventory write-offs for each batch
            for pos, by_pos in grouped_lines.items():
                for sale_date, by_sale_date in by_pos.items():
                    for line_type, sale_lines in by_sale_date.items():
                        sale_lines.with_delay(
                            channel=self.env['r.keeper.data.import'].get_channel_to_use(1, 'confirm_stock_moves'),
                            identity_key=identity_exact,
                            priority=80,
                            description='Create rKeeper inventory write-offs',
                            eta=30
                        ).create_inventory_write_off()

    @api.multi
    @job
    def create_inventory_write_off(self):
        """
        Creates stock inventory records from grouped rKeeper sales.
        :return: None
        """
        # Check for active alignment committee
        committee = self.env['alignment.committee'].sudo().search([
            ('state', '=', 'valid'), ('type', '=', 'inventory')],
            order='date DESC', limit=1
        )
        if not committee:
            self.custom_rollback(
                _('Nerasta aktyvi atsargų nurašymo komisija'), action_type='inventory_creation'
            )
            return

        default_obj = self.sorted(lambda r: r.sale_date, reverse=True)[0]
        default_analytic = default_obj.point_of_sale_id.analytic_account_id
        default_location = default_obj.point_of_sale_id.location_id
        stock_reason = self.env.ref('robo_stock.reason_line_18')
        # Prepare the name for the inventory
        name = _('Prekių suvartojimas privatiems poreikiams {} {}').format(
            default_obj.sale_date, default_obj.point_of_sale_id.code
        )
        # Prepare inventory values
        inventory_lines = []
        inventory_values = {
            'name': name,
            'filter': 'partial',
            'komisija': committee.id,
            'date': default_obj.sale_date,
            'reason_line': stock_reason.id,
            'location_id': default_location.id,
            'account_analytic_id': default_analytic.id,
            'accounting_date': default_obj.sale_date,
            'account_id': stock_reason.account_id.id,
            'line_ids': inventory_lines,
        }
        # Prepare stock inventory lines based on sales
        for line in self:
            line_values = {
                'product_id': line.product_id.id,
                'product_uom_id': line.product_id.uom_id.id,
                'location_id': default_location.id,
                'account_analytic_id': default_analytic.id,
                'consumed_qty': line.quantity * -1,
            }
            inventory_lines.append((0, 0, line_values))
        # Create inventory record
        try:
            inventory = self.env['stock.inventory'].create(inventory_values)
            # Try to confirm the inventory
            inventory.prepare_inventory()
            inventory.action_done()
            inventory.mark_validated()
        except Exception as e:
            self.custom_rollback(e.args[0], action_type='inventory_creation')
            return
        self.write({'state': 'created_inventory', 'inventory_id': inventory.id})
        self.env.cr.commit()

    @job
    @api.multi
    def create_production_prep(self):
        """
        Prepare rKeeper sale line objects
        for Mrp Production creation
        :return: None
        """
        # Check if automatic manufacturing is enabled
        configuration = self.env['r.keeper.configuration'].get_configuration()
        if not configuration.enable_automatic_sale_manufacturing:
            return

        # Get the automatic manufacturing mode
        man_mode = configuration.automatic_sale_manufacturing_mode

        # Filter out records without invoices or with produced states
        sales = self.filtered(
            lambda x: x.production_state in ['not_produced', 'failed_to_create'] or not x.production_state
        )
        # Validate the records
        validated_records = sales.check_production_creation_constraints()

        # This way of looping is way faster than filtered
        grouped_lines = {}
        for line in validated_records:
            # Loop through lines and build dict of dicts with following mapping
            pos = line.point_of_sale_id
            s_date = line.sale_date
            product = line.product_id

            grouped_lines.setdefault(pos, {})
            grouped_lines[pos].setdefault(s_date, {})
            grouped_lines[pos][s_date].setdefault(product, self.env['r.keeper.sale.line'])
            grouped_lines[pos][s_date][product] |= line

        # Loop through grouped lines and create productions for each batch
        for pos, by_pos in grouped_lines.items():
            for sale_date, by_sale_date in by_pos.items():
                for product, sale_lines in by_sale_date.items():
                    sale_lines.with_delay(
                        channel=self.env['r.keeper.data.import'].get_channel_to_use(1, 'production_prep'),
                        identity_key=identity_exact,
                        priority=80,
                        description='Create rKeeper production',
                        eta=30
                    ).create_production(man_mode)

    @api.multi
    @job
    def _produce_related_production(self):
        self.ensure_one()
        if self.production_state == 'produced':
            return
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, SUPERUSER_ID, self._context.copy())
            sale_line = env['r.keeper.sale.line'].browse(self.id)
            production = sale_line.mrp_production_id
            try:
                production.produce_r_keeper_sales()
            except Exception as e:
                _logger.info(
                    'rKeeper Threaded: Failed to confirm production - {}. Record ID - {}'.format(
                        e.args[0] if e.args else e, production.id)
                )
                env.cr.rollback()

                # TODO why is Dummy write to update write_date needed?
                try:
                    sale_line.write({'doc_number': sale_line.doc_number})
                    env.cr.commit()
                except MissingError as e:
                    # TODO MissingError is sometimes raised when setting doc_number even if sale_line.exists()
                    env.cr.rollback()
            finally:
                env.cr.commit()
                env.cr.close()

    @api.multi
    def check_production_creation_constraints(self):
        """
        Check constraints for rKeeper sale records,
        so they meet all criteria for Mrp Production creation.
        Records that have some errors are filtered out
        :return: None
        """
        validated_records = self.env['r.keeper.sale.line']
        if not self._context.get('skip_creation_computation'):
            # Recompute all fields
            self.recompute_fields()
        # Validate the fields
        for rec in self:
            # If current product BOM does not exist, do not create the manufacturing
            bom = rec.product_id.with_context(bom_at_date=rec.sale_date).product_tmpl_id.bom_id
            if not bom:
                continue
            # Check other constraints
            error_template = str()
            if not rec.invoice_id and not rec.zero_amount_sale:
                error_template += _('Gamybą galima kurti tik tada jei pardavimas turi susijusią sąskaitą faktūrą\n')
            # Check modifier constraints
            modifier_errors = False
            for sale_modifier in rec.r_keeper_sale_line_modifier_ids:
                # If there's any un-configured rules, we do not create the production
                if any(not x.configured for x in sale_modifier.r_keeper_modifier_id.modifier_rule_ids):
                    modifier_errors = True
                    break
            if modifier_errors:
                error_template += _('Rasta nesukonfigūruotų modifikatorių taisyklių\n')
            if not rec.point_of_sale_id.configured:
                error_template += _('Nerastas arba nesukonfigūruotas susijęs pardavimo taškas\n')
            if not rec.point_of_sale_id.picking_type_id:
                error_template += _('Nerasta lokacijos gamybos operacija\n')
            if error_template:
                error_template = 'Nepavyko sukurti rKeeper gamybos užsakymo dėl šių problemų: \n\n' + error_template
                rec.post_message(error_template, production_state='failed_to_create')
            else:
                validated_records |= rec
        return validated_records

    @api.multi
    @job
    def create_production(self, manufacturing_mode):
        """
        Creates MrpProduction records from rKeeper sale
        lines if they already have created invoices.
        Lines are aggregated based on the product
        :return: None
        """
        default_obj = self.sorted(lambda r: r.sale_date, reverse=True)[0]

        # Get base values
        location = default_obj.point_of_sale_id.location_id
        picking_type = default_obj.point_of_sale_id.picking_type_id
        product = default_obj.product_id
        date = default_obj.sale_date

        # Gather up total quantity
        total_quantity = sum(x.quantity for x in self)
        # Get quantity to produce based on manufacturing mode
        if manufacturing_mode == 'produce_no_stock':
            quantities = default_obj.product_id.get_product_quantities(location=location)
            # If usable quantity is zero or negative -- quantity to produce is total quantity, otherwise, calculate
            if tools.float_compare(
                    0.0, quantities['usable_quantity'],
                    precision_rounding=product.uom_id.rounding) > 0:
                quantity_to_produce = total_quantity
            else:
                quantity_to_produce = tools.float_round(
                    total_quantity - quantities['usable_quantity'],
                    precision_rounding=product.uom_id.rounding
                )
                # Already rounded, it's ok to check like this.
                # If there's no quantity to produce, return
                if quantity_to_produce <= 0.0:
                    return
        else:
            quantity_to_produce = total_quantity
        # Get the active BOM of the product
        bom = default_obj.product_id.with_context(bom_at_date=date).product_tmpl_id.bom_id
        # Aggregate production modifiers
        aggregated_modifiers = {}
        for sale_modifier in self.mapped('r_keeper_sale_line_modifier_ids'):
            base = sale_modifier.r_keeper_modifier_id
            aggregated_modifiers.setdefault(base, 0.0)
            aggregated_modifiers[base] += sale_modifier.modified_quantity

        # Create production rules
        production_rules = []
        for base_modifier, quantity in aggregated_modifiers.items():
            for rule in base_modifier.modifier_rule_ids:
                remove_quantity = add_quantity = 0.0
                if rule.applied_action in ['add', 'swap']:
                    # ADD: Simple action quantity is final quantity
                    add_quantity = rule.action_quantity
                if rule.applied_action in ['remove', 'swap']:
                    # REMOVE: Quantity of the line in the bom is final quantity
                    bom_line = bom.bom_line_ids.filtered(lambda x: x.product_id == rule.remove_product_id)
                    remove_quantity = bom_line.product_qty

                # If quantity is not zero, create new production rule
                if not tools.float_is_zero(remove_quantity, precision_digits=5) \
                        or not tools.float_is_zero(add_quantity, precision_digits=5):
                    rule_values = {
                        'location_src_id': rule.location_src_id.id,
                        'remove_product_id': rule.remove_product_id.id,
                        'add_product_id': rule.add_product_id.id,
                        'applied_action': rule.applied_action,
                        'action_quantity': add_quantity,
                        'action_remove_quantity': remove_quantity,
                        'application_count': quantity,
                    }
                    production_rules.append((0, 0, rule_values))

        production_vals = {
            'product_id': product.id,
            'product_uom_id': product.uom_id.id,
            'bom_id': bom.id,
            'product_qty': quantity_to_produce,
            'date_planned_start': date,
            'origin': default_obj.invoice_id.number,
            'picking_type_id': picking_type.id,
            'location_src_id': location.id,
            'location_dest_id': location.id,
            'r_keeper_sale_line_ids': [(6, 0, self.ids)],
            'production_modification_rule_ids': production_rules,
        }
        # Force accounting date to date planned start
        if self.env.user.company_id.force_accounting_date:
            production_vals.update({
                'accounting_date': date,
            })

        # Mrp production HTML tables are computed in english on cron execution
        # so we take the language from the CEO user. Since production tables are
        # stored HTML computes language is not translated on for each user,
        # thus it's better to use most 'common' language in the company
        lang = self.env.user.company_id.vadovas.user_id.lang or 'lt_LT'

        # Try to create the production
        try:
            production = self.env['mrp.production'].with_context(lang=lang).create(production_vals)
        except Exception as e:
            self.custom_rollback(e.args[0], action_type='production_create')
            return

        # Commit if creation was successful
        self.env.cr.commit()
        # Create job to try and reserve the production
        for line in production.r_keeper_sale_line_ids:
            channel = self.env['r.keeper.data.import'].get_channel_to_use(line.point_of_sale_id.id, 'reservation')
            line.with_delay(channel=channel, identity_key=identity_exact, priority=90,
                description='Produce related rKeeper production (reservation)', eta=30)._produce_related_production()

    # Reconfirmation methods ------------------------------------------------------------------------------------------

    @api.multi
    def confirm_related_productions(self):
        """
        Reserves and confirms the productions
        of sale lines that have 'failed_to_reserve'
        production state. Also tries to recreate
        the productions with 'failed_to_create' state
        :return: None
        """

        # Get the sales with productions that were failed to reserve
        sales_to_reconfirm = self.filtered(
            lambda x: x.mrp_production_id and x.mrp_production_id.state not in ['done', 'cancel']
        )

        # Map out the productions
        grouped_lines = {}
        for line in sales_to_reconfirm:
            grouped_lines.setdefault(line.mrp_production_id, self.env['r.keeper.sale.line'])
            grouped_lines[line.mrp_production_id] |= line

        # Loop through productions and try to reserve them
        for production, sales in grouped_lines.items():
            try:
                production.produce_r_keeper_sales()
            except Exception as e:
                sales.custom_rollback(e.args[0], action_type='production_process')
            else:
                # On success write the state
                sales.write({'production_state': 'produced'})
                self.env.cr.commit()

    # Utility methods -------------------------------------------------------------------------------------------------

    @api.model
    def create_action_recalculate_selected_sale_bom(self):
        """Creates action for selected recordset 'has BOM' re-computation"""
        action = self.env.ref('r_keeper.action_recalculate_selected_sale_bom')
        if action:
            action.create_action()

    @api.model
    def create_action_recalculate_all_sale_bom(self):
        """Creates action for 'has BOM' re-computation for all records"""
        action = self.env.ref('r_keeper.action_recalculate_all_sale_bom')
        if action:
            action.create_action()

    @api.model
    def create_action_create_invoices_prep_multi(self):
        """Creates action for multi-set invoice creation all"""
        action = self.env.ref('r_keeper.action_create_invoices_prep_multi')
        if action:
            action.create_action()

    @api.model
    def create_action_recompute_fields_multi_sale(self):
        """Creates action for multi-set recompute all"""
        action = self.env.ref('r_keeper.action_recompute_fields_multi_sale')
        if action:
            action.create_action()

    @api.multi
    def custom_rollback(self, msg, action_type='invoice_creation'):
        """
        Rollback current transaction,
        post message to the object and commit
        :return: None
        """
        self.env.cr.rollback()
        self.env.all.todo = {}
        self.env.clear()
        if action_type == 'inventory_creation':
            body = _('Nepavyko sukurti nurašymo, sisteminė klaida: {}').format(msg)
            self.post_message(body, state='failed_inventory')
        if action_type == 'invoice_creation':
            body = _('Nepavyko sukurti sąskaitos, sisteminė klaida: {}').format(msg)
            self.post_message(body, state='failed')
        if action_type == 'delivery_creation':
            body = _('Nepavyko sukurti važtaraščio, sisteminė klaida: {}').format(msg)
            self.post_message(body, state='failed')
        elif action_type == 'production_create':
            body = _('Nepavyko sukurti gamybos, sisteminė klaida: {}').format(msg)
            self.post_message(body, production_state='failed_to_create')
        elif action_type == 'production_process':
            body = _('Nepavyko rezervuoti/patvirtinti gamybos, sisteminė klaida: {}').format(msg)
            self.post_message(body)
        elif action_type == 'delivery_confirmation':
            body = _('Nepavyko patvirtinti važtaraščio, sisteminė klaida: {}').format(msg)
            self.post_message(body)
        self.env.cr.commit()

    @api.model
    def post_message(self, body, state=None, production_state=None):
        """
        Post message to rKeeper sales
        :param body: message to-be posted(str)
        :param state: object state (str)
        :param production_state: object production state
        :return: None
        """
        if state:
            self.write({'state': state})
        if production_state:
            self.write({'production_state': production_state})
        for sale in self:
            msg = {
                'body': body,
                'priority': 'low',
                'front_message': True,
                'message_type': 'notification',
            }
            # Use robo message post so front user can see the messages
            sale.robo_message_post(**msg)

    @api.multi
    def name_get(self):
        return [(x.id, _('Pardavimas #{} -- {}').format(x.id, x.doc_number)) for x in self]

    @api.model
    def cron_import_about_failed_sales(self):
        """
        Checks whether there are any failed sales in previous months,
        and informs the accountant. Cron is always ran on 15th day of current month.
        :return: None
        """
        # Do not execute the method if current day is not 15th,
        # if needed, can be updated to config parameter
        current_time = datetime.utcnow()
        if current_time.day != 15:
            return

        # Get the sales for previous months
        sale_threshold = (
                current_time - relativedelta(day=31, months=1)
        ).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        failed_sales = self.search([
            ('sale_date', '<=', sale_threshold),
            ('state', 'in', ['failed', 'failed_inventory']),
        ])

        # Filter out the sales that do not have product, and other failed sales
        no_product_sales = other_failed_sales = self.env['r.keeper.sale.line']
        for sale in failed_sales:
            if sale.product_id:
                other_failed_sales |= sale
            else:
                no_product_sales |= sale

        message_body = str()
        # Check if there's any failed sales due to missing product
        if no_product_sales:
            product_codes = no_product_sales.mapped('product_code')
            # Get the product codes and add them to the base body string
            product_code_str = ', '.join(product_codes)
            message_body += '''Rasta {} rKeeper pardavimo eilučių, kurioms trūksta 
            sisteminių produktų. Produktų kodai:\n\n{}. '''.format(
                len(no_product_sales), product_code_str
            )
        # Check if there's any failed sales due to other reasons
        if other_failed_sales:
            message_body += '''Rasta {} rKeeper pardavimo eilučių, 
            kurių nepavyko sukurti dėl kitų priežąsčių.'''.format(
                len(other_failed_sales),
            )
        # Send the email to findir if there's any failed sales
        if message_body:
            findir_email = self.sudo().env.user.company_id.findir.partner_id.email
            subject = '{} // [{}]'.format('rKeeper suklydę pardavimai', self._cr.dbname)
            self.env['script'].send_email(emails_to=[findir_email], subject=subject, body=message_body)

