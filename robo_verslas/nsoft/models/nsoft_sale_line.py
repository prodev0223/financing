# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, tools, exceptions
from datetime import datetime
from . import nsoft_tools as nt
from six import iteritems


class NsoftSale(models.Model):
    _name = 'nsoft.sale.line'
    _inherit = ['mail.thread']
    _description = 'nSoft lines that do not belong to any external invoice'

    product_code = fields.Char(string='Prekės kodas', required=True)
    ext_sale_id = fields.Integer(string='Išorinis prekės ID')
    cash_register_number = fields.Char(string='Kasos aparato numeris', inverse='_set_cash_register_id')
    quantity = fields.Float(string='Kiekis')
    ext_cash_register_id = fields.Integer(string='Kasos Nr.')
    sale_date = fields.Date(string='Pardavimo data')
    payment_date = fields.Datetime(string='Mokėjimo data')
    payment_due = fields.Date(string='Mokėjimo terminas')
    receipt_id = fields.Char(string='Čekio numeris', inverse='_set_nsoft_invoice_id')
    sale_type = fields.Char(string='Pardavimo tipas')
    line_type = fields.Char(compute='_compute_line_type')
    ext_product_category_id = fields.Integer(
        string='Išorinis prekės categorijos ID', inverse='_set_ext_product_category_id')

    # vat and prices
    vat_rate = fields.Float(string='PVM Procentas')
    vat_code = fields.Char(string='PVM kodas')
    sale_price = fields.Float(string='Vieneto kaina')
    payment_sum = fields.Float(string='Bendra kaina')
    discount = fields.Float(string='Nuolaida')

    # Our Fields
    pay_active = fields.Boolean(string='Mokėjimo tipo aktyvumas', compute='_compute_pay_active')
    product_id = fields.Many2one('product.product', compute='_compute_product_id', store=True, string='Produktas')
    cash_register_id = fields.Many2one('nsoft.cash.register', string='Kasos aparatas')
    nsoft_product_category_id = fields.Many2one('nsoft.product.category', string='nSoft produkto kategorija')

    invoice_id = fields.Many2one(
        'account.invoice', string='Sukurta sąskaita faktūra', compute='_compute_invoice_id', store=True)
    invoice_line_id = fields.Many2one('account.invoice.line')
    refund_id = fields.Many2one('account.invoice', string='Kreditinė sąskaita faktūra',
                                compute='_compute_refund_id', store=True)
    refund_line_id = fields.Many2one('account.invoice.line')
    correction_id = fields.Many2one('account.invoice', string='Pirminė sąskaita faktūra')
    correction_line_id = fields.Many2one('account.invoice.line')
    nsoft_invoice_id = fields.Many2one('nsoft.invoice', string=(_('Susijusi nSoft sąskaita')))
    state = fields.Selection([('imported', 'Pardavimo eilutė importuota'),
                              ('created', 'Sąskaita sukurta sistemoje'),
                              ('failed', 'Klaida kuriant sąskaitą'),
                              ('warning', 'Pardavimo eilutė importuota su įspėjimais')],
                             string='Būsena', default='imported', track_visibility='onchange')
    tax_id = fields.Many2one('account.tax', compute='_compute_tax_id', store=True, string='PVM')
    is_dated = fields.Boolean(compute='_compute_is_dated')
    nsoft_payment_ids = fields.Many2many('nsoft.payment', string='Apmokėjimai', inverse='_set_cash_register_id')
    payment_type_tag_text = fields.Text(string='Mokėjimo tipai', compute='_compute_payment_type_tag_text')

    # Fields are only used to preserve the data up to the change point
    payment_type_code = fields.Char(string='Išorinis mokėjimo kodas')
    pay_type_id = fields.Many2one('nsoft.payment.type', string='Mokėjimo tipas')

    # Computes / Inverses --------------------------------------------------

    @api.multi
    @api.depends('nsoft_payment_ids')
    def _compute_payment_type_tag_text(self):
        """
        Compute //
        Compute text for nsoft.sale.line tree tags widget
        :return: None
        """
        template = '<span class="badge" style="background-color: green;"><span class="o_badge_text">{}</span></span>'
        for rec in self:
            payment_types = rec.mapped('nsoft_payment_ids.pay_type_id')
            text = str()
            for pay_type in payment_types:
                text += template.format(pay_type.name)
            rec.payment_type_tag_text = text

    @api.multi
    def _set_ext_product_category_id(self):
        """Inverse"""
        for rec in self:
            rec.nsoft_product_category_id = self.env['nsoft.product.category'].search(
                [('external_id', '=', rec.ext_product_category_id)])

    @api.multi
    @api.depends('nsoft_payment_ids.pay_type_id.is_active')
    def _compute_pay_active(self):
        """Checks whether current sale payment type is active.
        Zero amount sales are always marked as active"""
        for rec in self:
            pay_active = False
            # Determine activity based on related payments
            if rec.nsoft_payment_ids:
                pay_active = any(x.pay_type_id.is_active for x in rec.nsoft_payment_ids)
            # Otherwise based on payment type code
            elif rec.payment_type_code:
                pay_active = self.env['nsoft.payment.type'].search(
                    [('ext_payment_type_code', '=', rec.payment_type_code)]
                ).is_active
            elif tools.float_is_zero(rec.sale_price, precision_digits=2):
                pay_active = True
            rec.pay_active = pay_active

    @api.multi
    @api.depends('sale_date')
    def _compute_is_dated(self):
        """Compute"""
        threshold = datetime.strptime(nt.DATED_SALE_DATE, tools.DEFAULT_SERVER_DATE_FORMAT)
        for rec in self:
            sale_date_dt = datetime.strptime(rec.sale_date, tools.DEFAULT_SERVER_DATE_FORMAT)
            rec.is_dated = True if sale_date_dt < threshold else False

    @api.multi
    @api.depends('invoice_line_id')
    def _compute_invoice_id(self):
        """Compute"""
        for rec in self:
            rec.invoice_id = rec.invoice_line_id.invoice_id

    @api.multi
    @api.depends('refund_line_id')
    def _compute_refund_id(self):
        """Compute"""
        for rec in self:
            rec.refund_id = rec.refund_line_id.invoice_id

    @api.multi
    @api.depends('sale_price')
    def _compute_line_type(self):
        """Compute"""
        for rec in self:
            if tools.float_compare(0.0, rec.sale_price, precision_digits=2) > 0:
                rec.line_type = 'out_refund'
            else:
                rec.line_type = 'out_invoice'

    @api.multi
    @api.depends('vat_rate')
    def _compute_tax_id(self):
        """Compute"""
        for rec in self:
            account_tax_forced = rec.nsoft_product_category_id.forced_tax_id
            account_tax = self.env['account.tax'].search([
                ('amount', '=', rec.vat_rate),
                ('type_tax_use', '=', 'sale'),
                ('price_include', '=', True)], limit=1)
            if account_tax_forced and account_tax and not tools.float_compare(
                    account_tax_forced.amount, account_tax.amount, precision_digits=2):
                if account_tax_forced.type_tax_use != 'sale' or not account_tax_forced.price_include:
                    account_tax_forced = account_tax_forced.find_matching_tax_varying_settings(type_tax_use='sale')
                account_tax = account_tax_forced
            rec.tax_id = account_tax

    @api.multi
    def _set_cash_register_id(self):
        """Inverse"""
        reg_obj = self.env['nsoft.cash.register'].sudo()
        for rec in self.filtered(lambda x: not x.cash_register_id):
            cash_register = self.env['nsoft.cash.register']
            for payment in rec.nsoft_payment_ids:
                if payment.pay_type_id.internal_code in ['web', 'trans']:
                    cash_register = reg_obj.search(
                        [('spec_register', '=', payment.pay_type_id.internal_code)]).id
                    if not cash_register:
                        cash_register = reg_obj.create_cash_register(payment.pay_type_id.internal_code)
                    break
            if not cash_register and rec.cash_register_number:
                cash_register = reg_obj.search([('cash_register_number', '=', rec.cash_register_number)]).id
                if not cash_register:
                    cash_register = reg_obj.create({
                        'cash_register_number': rec.cash_register_number,
                        'ext_id': rec.ext_cash_register_id,
                    })
            rec.cash_register_id = cash_register

    @api.multi
    def _set_nsoft_invoice_id(self):
        """Inverse"""
        for rec in self:
            if rec.receipt_id and rec.product_code not in nt.NON_INVOICED_PRODUCT_CODES:
                rec.nsoft_invoice_id = self.env['nsoft.invoice'].sudo().search(
                    [('receipt_id', '=', rec.receipt_id)], limit=1)

    @api.multi
    @api.depends('product_code')
    def _compute_product_id(self):
        """Inverse"""
        accounting_type = self.sudo().env.user.company_id.nsoft_accounting_type
        for rec in self:
            if (not accounting_type or accounting_type in ['detail']) and rec.product_code:
                product = self.env['product.product'].sudo().search(
                    [('default_code', '=', rec.product_code)], limit=1
                )
                if not product:
                    product_template = self.env['product.template'].sudo().search(
                        [('default_code', '=', rec.product_code)], limit=1
                    )
                    if product_template.product_variant_ids:
                        product = product_template.product_variant_ids[0]
                rec.product_id = product
            elif accounting_type in ['sum'] and rec.nsoft_product_category_id:
                rec.product_id = rec.nsoft_product_category_id.parent_product_id

    @api.multi
    def recompute_fields(self):
        """
        Re-compute/Re-inverse necessary fields for account invoice creation
        :return: None
        """
        self._compute_pay_active()
        self._compute_is_dated()
        self._compute_line_type()
        self._compute_tax_id()
        self._compute_product_id()
        self._set_cash_register_id()
        self._set_ext_product_category_id()
        self._set_nsoft_invoice_id()

    # Actions --------------------------------------------------------------

    @api.model
    def create_invoice_action(self):
        """
        Action method, used in nsoft.sale.line tree view to create
        account.invoices by hand
        :return: None
        """
        action = self.env.ref('nsoft.create_invoices_action')
        if action:
            action.create_action()

    # Misc methods ---------------------------------------------------------

    @api.multi
    def name_get(self):
        """Change record name get"""
        return [(rec.id, '%s' % rec.product_code) for rec in self]

    @api.multi
    def unlink(self):
        """Do not allow unlink if record has system invoice"""
        for rec in self:
            if rec.invoice_id or rec.invoice_line_id:
                raise exceptions.UserError(
                    _('Negalima ištrinti eilutės kuri pririšta prie sisteminės sąskaitos!'))
        return super(NsoftSale, self).unlink()

    @api.model
    def send_bug(self, body):
        """
        Send bug report to IT support
        :param body: bug body (str)
        :return: None
        """
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'error_message': body,
        })

    @api.model
    def post_message(self, l_body=str(), i_body=str(), state=None, lines=None, ext_invoice=None):
        """
        Post message to nsoft.sale.line or/and nsoft.invoice
        :param l_body: message to-be posted to nsoft.sale.line (str)
        :param i_body: message to-be-psoted to nsoft.invoice (str)
        :param state: object state (str)
        :param lines: nsoft.sale.line records
        :param ext_invoice: nsoft.invoice record
        :return: None
        """
        if lines is None:
            lines = self.env['nsoft.sale.line']
        if ext_invoice is None:
            ext_invoice = self.env['nsoft.invoice']
        if lines:
            if state:
                lines.write({'state': state})
            for line in lines:
                line.message_post(body=l_body)

        if ext_invoice:
            if state:
                ext_invoice.state = state
            ext_invoice.message_post(body=i_body)

    # Main methods ---------------------------------------------------------

    @api.model
    def validator(self, nsoft_sales=None, nsoft_invoices=None, return_invoices=False):
        """
        validate whether passed data (sales/invoices) meet the criteria to be created as an account_invoice
        :param nsoft_sales: nsoft.sale.line records
        :param nsoft_invoices: nsoft.invoice records
        :param return_invoices: returns only filtered invoices
        :return:
        """
        error_template = _('Klaida kuriant sąskaitą, ')
        nsoft_sales = self.env['nsoft.sale.line'] if nsoft_sales is None else nsoft_sales
        nsoft_invoices = self.env['nsoft.invoice'] if nsoft_invoices is None else nsoft_invoices
        filtered_sales = self.env['nsoft.sale.line']
        filtered_invoices = self.env['nsoft.invoice']
        nsoft_sales.recompute_fields()
        nsoft_invoices.recompute_fields()
        # Recompute payments
        nsoft_sales.mapped('nsoft_payment_ids').recompute_fields()
        nsoft_invoices.mapped('nsoft_payment_ids').recompute_fields()

        for nsoft_sale in nsoft_sales.filtered(
                lambda x: not x.nsoft_invoice_id and not x.invoice_id and not x.invoice_line_id
                and x.pay_active and not x.is_dated):
            body = str()
            if not nsoft_sale.cash_register_id.journal_id:
                body += error_template + _('eilutės kasos aparatas neturi žurnalo !\n')
            if not nsoft_sale.cash_register_id.location_id:
                body += error_template + _('eilutės kasos aparatas neturi lokacijos !\n')
            if not tools.float_is_zero(nsoft_sale.sale_price, precision_digits=2) and (
                    not nsoft_sale.nsoft_payment_ids or any(
                    x.pay_type_id.state != 'working' or x.state == 'warning' for x in nsoft_sale.nsoft_payment_ids)
            ):
                body += error_template + _(
                    'nerasti susiję apmokėjimai arba nesukonfigūruoti jų mokėjimo būdai bei mokėjimo datos!\n')
            if not nsoft_sale.tax_id:
                body += error_template + _('neegzistuoja PVM!\n')
            if not nsoft_sale.product_id:
                body += error_template + _('produktas neegzistuoja sistemoje!\n')
            if not nsoft_sale.cash_register_id.partner_id and not nsoft_sale.nsoft_invoice_id.partner_id:
                body += error_template + _('nerastas partneris!\n')
            if body:
                self.post_message(lines=nsoft_sale, l_body=body, state='failed')
            else:
                filtered_sales += nsoft_sale
        for nsoft_invoice in nsoft_invoices.filtered(lambda x: not x.invoice_id and x.pay_active and not x.is_dated):
            body = str()
            line_warnings = False
            amount_total_lines = 0.0
            lines = nsoft_invoice.sale_line_ids
            if not lines:
                body += error_template + _('nerastos sąskaitos eilutės!\n')
            else:
                lines.recompute_fields()
                if nsoft_invoice.cash_register_id and nsoft_invoice.cash_register_id.id \
                        != lines[0].cash_register_id.id:
                    lines.write({'cash_register_id': nsoft_invoice.cash_register_id.id})
                if not nsoft_invoice.partner_id:
                    body += error_template + _('nerastas sąskaitos partneris!\n')
                if not nsoft_invoice.cash_register_id:
                    body += error_template + _('nerastas kasos aparato numeris!\n')
                if not nsoft_invoice.nsoft_payment_ids or any(
                        x.pay_type_id.state != 'working' or
                        x.state == 'warning' for x in nsoft_invoice.nsoft_payment_ids):
                    body += error_template + _(
                        'nerasti susiję apmokėjimai arba nesukonfigūruoti jų mokėjimo būdai bei mokėjimo datos!\n')
                for line in nsoft_invoice.sale_line_ids:
                    amount_total_lines += line.sale_price * line.quantity
                    if not self._context.get('correction'):
                        if line.invoice_id or line.invoice_line_id or line.state == 'created':
                            line_warnings = True
                            nsoft_invoice.state = 'failed'
                    if not line.tax_id:
                        body += error_template + _('bent vienoje eilutėje neegzistuoja PVM!\n')
                        line_warnings = True
                    if not line.product_id:
                        body += error_template + _('bent vienos eilutės produktas neegzistuoja sistemoje!\n')
                        line_warnings = True
                if amount_total_lines and tools.float_compare(
                        abs(amount_total_lines), abs(nsoft_invoice.sum_with_vat), precision_digits=2) != 0:
                    diff = tools.float_round(
                        abs(nsoft_invoice.sum_with_vat) - abs(amount_total_lines), precision_digits=2)
                    if diff > nt.ALLOWED_TAX_CALC_ERROR:
                        body += _('nSoft Sąskaitos ir pardavimo eilučių galutinės sumos nesutampa (%s != %s).\n') % (
                            amount_total_lines, nsoft_invoice.sum_with_vat)
                if line_warnings:
                    body += _('Rasta įspėjimų, patikrinkite sąskaitos eilutes!\n')
            if body:
                self.post_message(ext_invoice=nsoft_invoice, i_body=body, state='failed')
            if not body and not line_warnings:
                filtered_invoices += nsoft_invoice
        self.env.cr.commit()
        if return_invoices:
            return filtered_invoices
        return filtered_sales, filtered_invoices

    @api.multi
    def invoice_creation_prep(self, sale_line_ids=None, nsoft_invoice_ids=None):
        """
        Prepare nsoft.sale.line objects and nsoft.invoice objects for account invoice creation
        :param sale_line_ids: nsoft.sale.line objects
        :param nsoft_invoice_ids: nsoft.invoice objects
        :return: None
        """
        # Needed objects
        NSoftSaleLine = self.env['nsoft.sale.line'].sudo()
        NsoftInvoice = self.env['nsoft.invoice'].sudo()

        sale_line_ids = NSoftSaleLine if sale_line_ids is None else sale_line_ids
        nsoft_invoice_ids = NsoftInvoice if nsoft_invoice_ids is None else nsoft_invoice_ids

        sale_line_ids, nsoft_invoice_ids = self.validator(nsoft_sales=sale_line_ids, nsoft_invoices=nsoft_invoice_ids)
        if nsoft_invoice_ids:
            for ext_invoice in nsoft_invoice_ids:
                self.create_invoices(ext_invoice=ext_invoice)

        # Check whether any payment type has individual invoice creation bool set
        individual_invoice_payments = self.env['nsoft.payment.type'].search_count(
            [('create_individual_invoices', '=', True)])

        if sale_line_ids:
            # This way of looping is way faster than filtered
            grouped_lines = {}
            for line in sale_line_ids:
                # Loop through lines and build dict of dicts with following mapping
                c_reg = line.cash_register_id
                s_date = line.sale_date
                l_type = line.line_type

                # Check whether line has payment type that demands individual invoice
                # creation for it. Only execute the check if at least one payment
                # has this boolean set, because this grouping is resource heavy
                p_grouping = False
                if individual_invoice_payments:
                    payment_type = line.nsoft_payment_ids.mapped('pay_type_id')
                    # We only group if there's one payment type that demands individual creation
                    if len(payment_type) == 1 and payment_type.create_individual_invoices:
                        p_grouping = payment_type

                # Build the grouped structure
                grouped_lines.setdefault(c_reg, {})
                grouped_lines[c_reg].setdefault(s_date, {})
                grouped_lines[c_reg][s_date].setdefault(l_type, {})
                grouped_lines[c_reg][s_date][l_type].setdefault(p_grouping, NSoftSaleLine)
                grouped_lines[c_reg][s_date][l_type][p_grouping] |= line

            # Loop through the grouped structure and create invoices
            for cash_reg, by_cash_reg in grouped_lines.items():
                for sale_date, by_sale_date in by_cash_reg.items():
                    for line_type, by_payment_split in by_sale_date.items():
                        for p_group, sale_lines in by_payment_split.items():
                            # Add forced partner to the context if payment group exists and partner is set
                            if p_group and p_group.forced_partner_id:
                                self = self.with_context(forced_partner_id=p_group.forced_partner_id.id)

                            # Execute consignation split and create invoices
                            res = self.consignation_split(sale_lines)
                            if res.get('split'):
                                self.with_context(consignation=True).create_invoices(
                                    res.get('consignation_data'), NsoftInvoice)
                            self.create_invoices(res.get('data'), NsoftInvoice)

    @api.model
    def create_invoices(self, lines=None, ext_invoice=None, operation_type='create'):
        """
        Method used to create, credit or correct account.invoices based on nsoft.sale.line or nsoft.invoice.
        Workflow differs based on operation type and whether invoice is created based on lines or parent invoice
        :param lines: nsoft.sale.line object
        :param ext_invoice: nsoft.invoice object
        :param operation_type: operation type, expected types are 'create', 'refund', 'correct'
        :return: None
        """
        ext_invoice = self.env['nsoft.invoice'] if ext_invoice is None else ext_invoice
        lines = ext_invoice.sale_line_ids if lines is None else lines
        payments = ext_invoice.nsoft_payment_ids if ext_invoice else lines.mapped('nsoft_payment_ids')

        # Check if current batch consists only of zero sums
        zero_amount_batch = tools.float_is_zero(sum(lines.mapped('sale_price')), precision_digits=2)
        # If there's no lines or batch is non-zero and there's no payments - return
        if not lines or not zero_amount_batch and not payments:
            return

        default_obj = lines[0]
        invoice_obj = self.env['account.invoice'].sudo()
        account_obj = self.env['account.account'].sudo()
        account_account = account_obj.search([('code', '=', nt.STATIC_ACCOUNT_CODE)])
        forced_partner_id = self._context.get('forced_partner_id')

        # Prepare invoice values -------------------------------------------------------------------------------
        invoice_lines = []
        invoice_vals = {
            'imported_api': True,
            'external_invoice': True,
            'skip_global_reconciliation': True,
            'force_dates': True,
            'journal_id': default_obj.cash_register_id.journal_id.id,
            'account_id': account_account.id,
            'invoice_line_ids': invoice_lines,
            'price_include_selection': 'inc',
            'type': default_obj.line_type
        }
        if operation_type in ['refund']:
            invoice_vals.update({
                'number': 'K//{}'.format(default_obj.invoice_id.move_name),
                'move_name': 'K//{}'.format(default_obj.invoice_id.move_name),
                'partner_id': forced_partner_id or default_obj.invoice_id.partner_id.id,
                'date_invoice': default_obj.invoice_id.date_invoice,
                'type': 'out_refund',
            })
        else:
            # Determine partner to use
            partner_to_use = forced_partner_id or (
                ext_invoice.partner_id.id if ext_invoice else default_obj.cash_register_id.partner_id.id
            )
            invoice_vals.update({
                'number': ext_invoice.name if ext_invoice else None,
                'move_name': ext_invoice.name if ext_invoice else None,
                'partner_id': partner_to_use,
                'date_due': ext_invoice.date_due if ext_invoice else default_obj.payment_due,
                'date_invoice': ext_invoice.date_invoice if ext_invoice else default_obj.sale_date,
                'operacijos_data': ext_invoice.date_invoice if ext_invoice else default_obj.sale_date,
                'intrastat_country_id': ext_invoice.partner_id.country_id.id
                if ext_invoice else default_obj.cash_register_id.partner_id.country_id.id,
            })

        # Prepare invoice lines, sum matching products into one line --------------------------------------------
        amount_total = 0.0
        sum_lines = []
        company_id = self.sudo().env.user.company_id

        grouped_inv_lines = {}
        for line in lines:
            # Loop through lines and build dict of dicts with following mapping
            prod_id = line.product_id
            tax_id = line.tax_id
            s_price = abs(line.sale_price)

            grouped_inv_lines.setdefault(prod_id, {})
            grouped_inv_lines[prod_id].setdefault(tax_id, {})
            grouped_inv_lines[prod_id][tax_id].setdefault(s_price, self.env['nsoft.sale.line'])
            grouped_inv_lines[prod_id][tax_id][s_price] |= line

        for product, by_tax in iteritems(grouped_inv_lines):
            for tax, by_price in iteritems(by_tax):
                if company_id.nsoft_accounting_type and company_id.nsoft_accounting_type in ['sum']:
                    t_lines = self.env['nsoft.sale.line']
                    for batch in by_price.values():
                        t_lines |= batch
                    sum_line_total = sum(abs(x.sale_price) * x.quantity for x in t_lines)
                    sum_discount = sum(x.discount for x in t_lines)
                    self.prepare_sum_lines(sum_lines=sum_lines, group=t_lines, qty=1,
                                           sale_price=sum_line_total, discount=sum_discount)
                    amount_total += sum_line_total
                else:
                    for price, p_lines in iteritems(by_price):
                        normalized = [abs(x) for x in p_lines.mapped('quantity')]
                        qty = sum(normalized)
                        self.prepare_sum_lines(sum_lines=sum_lines, group=p_lines, qty=qty)
                        amount_total += price * qty

        key = 'nsoft_refund_line_ids' if operation_type == 'refund' else 'nsoft_sale_line_ids'
        for sale_line in sum_lines:
            line_vals = {
                'product_id': sale_line['product_id'],
                'name': sale_line['name'],
                'quantity': sale_line['quantity'],
                'price_unit': sale_line['price_unit'],
                'uom_id': sale_line['uom_id'],
                'discount': sale_line['discount'],
                'account_id': sale_line['account_id'],
                'invoice_line_tax_ids': sale_line['invoice_line_tax_ids'],
                key: sale_line['nsoft_sale_line_ids']
            }
            invoice_lines.append((0, 0, line_vals))

        try:
            invoice = invoice_obj.create(invoice_vals)
        except Exception as e:
            self.env.cr.rollback()
            body = _('Nepavyko sukurti sąskaitos, sisteminė klaida %s') % str(e.args[0])
            self.post_message(lines=lines, ext_invoice=ext_invoice, i_body=body, l_body=body, state='failed')
            self.env.cr.commit()
            return 1

        # Validate amount tax, amount untaxed and amount total ----------------------------------------------------
        if ext_invoice:
            invoice.force_invoice_tax_amount(ext_invoice.items_vat_sum)
            amount_data = [
                ('amount_total', ext_invoice.sum_with_vat, True),
                ('amount_tax', ext_invoice.items_vat_sum, False),
                ('amount_untaxed', ext_invoice.sum_wo_vat, True)
            ]
        else:
            amount_data = [
                ('amount_total', amount_total, True),
            ]
        body = invoice.check_invoice_amounts(amount_data)
        if body:
            self.env.cr.rollback()
            self.post_message(lines=lines, ext_invoice=ext_invoice, i_body=body, l_body=body, state='failed')
            self.env.cr.commit()
            return 1

        # Force partner data and open the invoice and write post data ---------------------------------------------
        try:
            invoice.partner_data_force()
            invoice.action_invoice_open()
        except Exception as e:
            self.env.cr.rollback()
            body = _('Nepavyko sukurti sąskaitos, sisteminė klaida %s') % str(e.args[0])
            self.post_message(lines=lines, ext_invoice=ext_invoice, i_body=body, l_body=body, state='failed')
            self.env.cr.commit()
            return 1

        self.post_op_write(lines, ext_invoice, operation_type=operation_type)

        # Create delivery if robo_stock is installed -------------------------------------------------------------
        location_id = default_obj.cash_register_id.location_id or ext_invoice.cash_register_id.location_id
        res = invoice.create_nsoft_delivery(location_id=location_id)
        if res:
            self.post_message(ext_invoice=ext_invoice, lines=lines, i_body=res, l_body=res)
        # Create account move ------------------------------------------------------------------------------------
        lines.move_creation_prep(operation_type)

        invoice.accountant_validated = True
        if operation_type in ['create']:
            self.env.cr.commit()
        return

    @api.model
    def prepare_sum_lines(self, sum_lines, group, qty, sale_price=None, discount=None):
        """
        Create summed account.invoice.lines and append to passed dictionary
        :param sum_lines: passed dictionary
        :param group: group of objects of same type depending on global nsoft accounting
        :param qty: quantity of the passed objects
        :param sale_price: price of the passed objects
        :param discount: discount of the passed objects
        :return: None
        """
        group_obj = group[0]
        sale_price = abs(group_obj.sale_price) if sale_price is None else sale_price
        discount = abs(group_obj.discount) if discount is None else discount
        product_account = group_obj.product_id.get_product_income_account(return_default=True)
        sum_lines.append({
            'product_id': group_obj.product_id.id,
            'name': group_obj.product_id.name,
            'quantity': qty,
            'price_unit': sale_price,
            'uom_id': group_obj.product_id.product_tmpl_id.uom_id.id,
            'discount': discount,
            'account_id': product_account.id,
            'invoice_line_tax_ids': [(6, 0, group_obj.tax_id.ids)],
            'nsoft_sale_line_ids': [(6, 0, group.ids)]
        })

    @api.multi
    def move_creation_prep(self, operation_type='create'):
        """
        Prepare for account.move creation, in case of refund, reconcile refund invoice_id and original invoice_id
        :param operation_type: 'refund' reconciles, while other types just create moves
        :return: None
        """
        invoice = self.mapped('invoice_id')
        # On refund operation type unlink the artificial payment moves created for the
        # original invoice if they exist, and create new payments from the new parent invoice
        if operation_type in ['refund']:
            original_invoice = self.mapped('correction_id')
            batch_line_ids = self.ids
            # If original_invoice not singleton, it's data anomaly ant we want it to crash
            nsoft_payment_ids = original_invoice.nsoft_payment_move_ids
            # Filter those payments that have any of their sale lines in current batch
            filtered_payments = nsoft_payment_ids.filtered(
                lambda x: any(ln.id in batch_line_ids for ln in x.nsoft_sale_line_ids))

            # Remove reconciliations, moves and payments themselves - corrected invoice
            # has a new nsoft payment record associated with it
            for payment in filtered_payments:
                payment.mapped('move_id.line_ids').remove_move_reconcile()
                payment.move_id.button_cancel()
                payment.move_id.unlink()
            all_refunds = filtered_payments.mapped('nsoft_sale_line_ids.refund_id') | self.mapped('refund_id')
            filtered_payments.unlink()

            # Reconcile all possible refunds and corrections together if original invoice has residual
            base_line_ids = original_invoice.move_id.line_ids.filtered(
                lambda r: r.account_id.id == original_invoice.account_id.id)
            for refund in all_refunds:
                if not tools.float_is_zero(original_invoice.residual, precision_digits=2):
                    line_ids = base_line_ids | refund.move_id.line_ids.filtered(
                        lambda r: r.account_id.id == refund.account_id.id)
                    if len(line_ids) > 1:
                        line_ids.with_context(reconcile_v2=True).reconcile()
        else:
            payments = self.mapped('nsoft_payment_ids').filtered(lambda x: x.pay_type_id.do_reconcile)
            payments |= self.mapped('nsoft_invoice_id.nsoft_payment_ids').filtered(lambda x: x.pay_type_id.do_reconcile)
            for payment in payments:
                payment.create_nsoft_moves(invoice.partner_id, forced_amount=payment.payment_sum)
                payment.reconcile_with_invoice(invoice)

    @api.model
    def post_op_write(self, sales, ext_invoice, operation_type='create'):
        """Write necessary data to sale_lines and nsoft_invoices after account invoice creation"""
        if operation_type in ['create', 'correct']:
            record = sales.mapped('invoice_id')
            sales.write({'state': 'created'})
            ext_invoice.write({'state': 'created', 'invoice_id': record.id})
        if operation_type in ['refund']:
            original_invoice = sales.mapped('invoice_id')
            # Rewrite links
            sales.write({'invoice_id': False, 'invoice_line_id': False,
                         'state': 'imported', 'correction_id': original_invoice.id})

    @api.model
    def consignation_split(self, grouped_sales):
        """
        Check whether consignation module is installed and if it is, split sales into consignation and
        non consignation ones
        :param grouped_sales:
        :return: dict of split/un-split data
        """
        rec = self.sudo().env['ir.module.module'].search([('name', '=', 'robo_konsignacija')])
        if rec and rec.state in ['installed', 'to upgrade']:
            consignation_product_ids = grouped_sales.filtered(lambda r: r.product_id.consignation)
            non_consignation_product_ids = grouped_sales.filtered(lambda r: not r.product_id.consignation)
            return {
                'split': True,
                'consignation_data': consignation_product_ids,
                'data': non_consignation_product_ids
            }
        else:
            return {
                'split': False,
                'data': grouped_sales
            }

    @api.multi
    def credit_sales(self):
        """
        Create refund invoices for nsoft.sale.line in self
        :return: None
        """
        invoices = self.mapped('invoice_id')
        for invoice in invoices:
            corresponding_sales = self.filtered(lambda x: x.invoice_id == invoice)
            res = self.create_invoices(corresponding_sales, operation_type='refund')
            if res is not None:
                return res

    @api.multi
    def button_create_invoices(self):
        """
        Method called from the button in sale.line view to create_invoices
        :return: None
        """
        self.invoice_creation_prep(sale_line_ids=self)

