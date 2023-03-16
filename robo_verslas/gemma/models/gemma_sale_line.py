# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, tools, exceptions
from datetime import datetime
from dateutil.relativedelta import relativedelta
from six import iteritems
import logging
import gemma_tools

_logger = logging.getLogger(__name__)


class GemmaSaleLine(models.Model):
    _name = 'gemma.sale.line'
    _inherit = ['mail.thread', 'gemma.base']

    ext_sale_id = fields.Integer(string='Išorinis pardavimo numeris')
    ext_product_code = fields.Char(string='Išorinis produkto kodas')
    ext_product_name = fields.Char(string='Išorinis produkto pavadinimas')
    buyer_id = fields.Char(string='Pirkėjo numeris', inverse='get_partner')
    price_list = fields.Char(string='Kainoraštis')
    price_list_text = fields.Text(string='Kainoraščio komentaras')
    qty = fields.Float(string='Kiekis')
    price = fields.Float(string='Suma')
    receipt_total = fields.Float(string='Čekio suma')
    sale_date = fields.Datetime(string='Pardavimo data')
    sale_day = fields.Date(compute='get_sale_day')
    receipt_id = fields.Integer(string='Čekio numeris')
    ext_payment_id = fields.Integer(string='Mokėjimo numeris')
    line_type = fields.Char(compute='compute_line_type')
    ext_id_second = fields.Char(string='Išorinis pardavimo numeris (papildomas)')
    ext_sale_db_id = fields.Integer(string='Išorinis skolos ID')
    is_gp = fields.Boolean(compute='get_is_gp')
    rehabilitation_sale = fields.Boolean(compute='_rehabilitation_sale')
    ext_invoice_id = fields.Many2one('gemma.invoice', string='Susieta sąskaita faktūra')
    payment_id = fields.Many2one('gemma.payment', string='Susijęs mokėjimas', compute='get_payment_id', store=True)
    product_id = fields.Many2one('product.product', string='Produktas', compute='get_product', store=True)

    invoice_id = fields.Many2one('account.invoice', string='Sisteminė sąskaita', compute='get_system_invoice',
                                 store=True, copy=False)
    invoice_line_id = fields.Many2one('account.invoice.line', copy=False)

    state = fields.Selection([('imported', 'Pardavimo eilutė importuota'),
                              ('created', 'Sąskaita sukurta sistemoje'),
                              ('failed', 'Klaida kuriant sąskaitą'),
                              ('warning', 'Pardavimo eilutė importuota su įspėjimais'),
                              ('canceled', 'Atšauktas'),
                              ('cancel_locked', 'Atšauktas Polyje | Neatšauktas ROBO dėl užrakinimo datų'),
                              ('awaiting', 'Laukiama Guldymo Datos'),
                              ('awaiting_rehab', 'Laukiama Reabilitacijos Datos')
                              ],
                             string='Būsena', default='imported', track_visibility='onchange')
    cash_register_id = fields.Many2one('gemma.cash.register',
                                       string='Kasos aparatas', compute='get_cash_register', store=True)
    correction_id = fields.Many2one('account.invoice', string='Pataisyta sąskaita faktūra',
                                    compute='get_invoice_corrected', store=True, copy=False)
    correction_line_id = fields.Many2one('account.invoice.line', copy=False)

    refund_id = fields.Many2one('account.invoice', string='Kreditinė sąskaita faktūra',
                                compute='get_invoice_refund', store=True, copy=False)
    refund_line_id = fields.Many2one('account.invoice.line', copy=False)

    partner_id = fields.Many2one('res.partner', string='Partneris')

    is_canceled = fields.Boolean(string='Atšaukta', default=False)
    cancel_date = fields.Datetime(string='Atšaukimo data')
    vat_code = fields.Char(string='Gemma PVM kodas')
    tax_id = fields.Many2one('account.tax', string='PVM', compute='_compute_tax_id', store=True)
    bed_day_date = fields.Datetime(string='Guldymo data', track_visibility='onchange')
    rehabilitation_date = fields.Datetime(string='Reabilitacijos data', track_visibility='onchange')
    active = fields.Boolean(string='Aktyvus', default=True)
    batch_excluded = fields.Boolean(string='Netraukti į bendrą sąskaitą')
    ext_sale_done = fields.Boolean(string='Atlikta Polije', inverse='_set_ext_sale_done', track_visibility='onchange')
    inform_accountant = fields.Boolean(string='Informuoti buhalterį')

    @api.multi
    def _set_ext_sale_done(self):
        """
        Inverse // If sale is marked as done in external system
        and we do not have bed_day_date OR rehabilitation_date on specific sales
        we force sale_date to corresponding spec date field.
        After setting of dates, check whether current sale is duplicate GP sale
        """
        for rec in self.filtered(lambda x: x.ext_sale_done):
            if rec.rehabilitation_sale and not rec.rehabilitation_date:
                rec.rehabilitation_date = rec.sale_date
            if rec.is_gp and not rec.bed_day_date:
                rec.bed_day_date = rec.sale_date
            self.check_duplicate_gp_sale(rec)

    @api.one
    @api.depends('product_id')
    def _rehabilitation_sale(self):
        rehab_threshold = datetime(2020, 01, 13)
        sale_date = datetime.strptime(
            self.sale_date, tools.DEFAULT_SERVER_DATETIME_FORMAT) if self.sale_date else datetime(2020, 01, 01)
        self.rehabilitation_sale = True \
            if self.product_id and self.product_id.default_code in gemma_tools.rehabilitation_products and \
            sale_date >= rehab_threshold else False

    @api.multi
    def get_date_to_use(self):
        self.ensure_one()
        potential_date = date_to_use = False
        if self.is_gp:
            date_to_use = self.bed_day_date
        elif self.rehabilitation_sale:
            date_to_use = self.rehabilitation_date
        if date_to_use:
            company = self.sudo().env.user.company_id
            lock_date = company.get_user_accounting_lock_date()
            if date_to_use > lock_date:
                potential_date = date_to_use
        if not potential_date:
            potential_date = self.sale_date
        return potential_date

    @api.multi
    @api.constrains('ext_sale_db_id')
    def constrain_unique_ext_id(self):
        for rec in self:
            if self.env['gemma.sale.line'].search_count(
                    [('ext_sale_db_id', '=', rec.ext_sale_db_id), ('id', '!=', rec.id), ('active', '=', True)]):
                raise exceptions.ValidationError(_('Išorinis skolos ID negali kartotis'))

    @api.one
    @api.depends('product_id')
    def get_is_gp(self):
        self.is_gp = True if self.product_id and 'GP' in self.product_id.default_code else False

    @api.multi
    def open_sale(self):
        self.ensure_one()
        return {
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'gemma.sale.line',
                'res_id': self.id,
                'view_id': self.env.ref('gemma.gemma_sale_line_form').id,
                'type': 'ir.actions.act_window',
                'target': 'current',
        }

    @api.one
    def fields_compute(self):
        self.get_payment_id()
        self.get_product()
        self.get_system_invoice()
        self.get_cash_register()
        self.get_invoice_corrected()
        self._compute_tax_id()
        self.get_partner()
        self.get_is_gp()

    @api.one
    def get_partner(self):
        self.get_partner_base(self.buyer_id)
        if self.payment_id and self.partner_id and self.partner_id != self.payment_id.partner_id:
            self.payment_id.with_context(skip_inverse=True).write(
                {'partner_id': self.partner_id.id, 'payer_id': self.buyer_id})

    @api.model
    def server_action_invoices(self):
        action = self.env.ref('gemma.server_action_invoice')
        if action:
            action.create_action()

    @api.model
    def server_action_cancel_sales_f(self):
        action = self.env.ref('gemma.server_action_cancel_sales')
        if action:
            action.create_action()

    @api.model
    def server_action_cancel_sales_pay_f(self):
        action = self.env.ref('gemma.server_action_cancel_sales_pay')
        if action:
            action.create_action()

    @api.multi
    def cancel_records(self):
        if self.env.user.is_gemma_manager():
            include_payments = self._context.get('include_payments', False)
            corresponding_sales = self.filtered(lambda x: x.state not in ['canceled'])

            cancel_date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            corresponding_sales.credit_sales()
            corresponding_sales.write({
                'cancel_date': cancel_date,
                'state': 'canceled',
                'is_canceled': True
            })
            if include_payments:
                corresponding_payments = corresponding_sales.mapped('payment_id')
                corresponding_payments.reverse_moves()
                corresponding_payments.write({
                    'cancel_date': cancel_date,
                    'state': 'canceled',
                    'is_canceled': True
                })

    @api.one
    @api.depends('correction_line_id')
    def get_invoice_corrected(self):
        if self.correction_line_id:
            self.correction_id = self.correction_line_id.invoice_id.id

    @api.one
    @api.depends('refund_line_id')
    def get_invoice_refund(self):
        if self.refund_line_id:
            self.refund_id = self.refund_line_id.invoice_id.id

    @api.one
    @api.depends('sale_date', 'bed_day_date')
    def get_sale_day(self):
        if self.is_gp and self.bed_day_date:
            self.sale_day = self.bed_day_date[:10]
        elif self.rehabilitation_sale and self.rehabilitation_date:
            self.sale_day = self.rehabilitation_date[:10]
        else:
            self.sale_day = self.sale_date[:10]

    @api.one
    @api.depends('invoice_line_id')
    def get_system_invoice(self):
        if self.invoice_line_id:
            self.invoice_id = self.invoice_line_id.invoice_id.id

    @api.multi
    def invoice_action(self):
        receipts = list(set(self.mapped('receipt_id')))
        if 0 not in receipts:
            sale_ids = self.env['gemma.sale.line'].search([('receipt_id', 'in', receipts), ('active', '=', True)])
        else:
            sale_ids = self
        self.with_context(validate=True).invoice_creation_prep(self.env['gemma.invoice'], sale_ids)

    @api.one
    @api.depends('price')
    def compute_line_type(self):
        if self.price > 0:  # todo
            self.line_type = 'out_invoice'
        else:
            self.line_type = 'out_refund'

    @api.one
    @api.depends('ext_payment_id')
    def get_payment_id(self):
        if self.ext_payment_id:
            self.payment_id = self.env['gemma.payment'].search([('ext_payment_id', '=', self.ext_payment_id)])

    @api.multi
    def name_get(self):
        return [(rec.id, _('Pardavimas ') + str(rec.ext_sale_id)) for rec in self]

    @api.one
    @api.depends('ext_product_code')
    def get_product(self):
        if self.ext_product_code:
            self.product_id = self.env['product.product'].sudo().search(
                [('default_code', '=', self.ext_product_code)], limit=1).id

    @api.one
    @api.depends('payment_id.cash_register_id')
    def get_cash_register(self):
        self.cash_register_id = self.payment_id.cash_register_id

    @api.one
    @api.depends('vat_code', 'cash_register_id', 'product_id')
    def _compute_tax_id(self):
        """
        Compute //
        Find related account.tax record based on:
            -static value mapped to product code OR
            -static value mapped to cash.register OR
            -ext. system vat code mapped to this system vat code OR
            -gemma.sale.line with the same product OR
            -account.tax record related to product.product record
        :return: None
        """
        account_tax = self.env['account.tax']
        if self.ext_product_code:
            tax_code = gemma_tools.universal_product_tax_mapping.get(self.ext_product_code, False)
            account_tax = self.find_account_tax(tax_code)
        if not account_tax and self.cash_register_id:
            account_tax = self.cash_register_id.vat_mappers.filtered(lambda tax: tax.ext_code == self.vat_code).tax_id
        if not account_tax:
            tax_code = gemma_tools.universal_vat_mapper.get(self.vat_code, False)
            account_tax = self.find_account_tax(tax_code)
        if not account_tax:
            sale = self.env['gemma.sale.line'].search(
                [('product_id', '=', self.product_id.id), ('tax_id', '!=', False)], limit=1)
            account_tax = sale.tax_id
        if not account_tax:
            account_tax = self.product_id.taxes_id if len(self.product_id.taxes_id) == 1 else False
            if account_tax and not account_tax.price_include:
                account_tax = self.find_account_tax(account_tax.code)
        self.tax_id = account_tax

    @api.model
    def find_account_tax(self, code):
        """
        Search for corresponding account.tax record based on provided code
        Record must include price and must be of type 'sale'
        :param code: account.tax code value
        :return: account.tax record
        """
        account_tax = self.env['account.tax']
        if code:
            account_tax = account_tax.search(
                [('code', '=', code), ('type_tax_use', '=', 'sale'), ('price_include', '=', True)], limit=1)
        return account_tax

    @api.multi
    def force_sale_state(self):
        """
        Force waiting sale states based on the condition
        :return: None
        """
        for rec in self:
            if not rec.ext_sale_done:
                if rec.is_gp and not rec.bed_day_date:
                    rec.state = 'awaiting'
                elif rec.rehabilitation_sale and not rec.rehabilitation_date:
                    rec.state = 'awaiting_rehab'
            else:
                if not rec.invoice_id and rec.state not in ['created', 'canceled', 'cancel_locked']:
                    rec.state = 'imported'

    @api.model
    def check_duplicate_gp_sale(self, sale_line):
        """
        Check whether externally done GP sale line already exists for the same partner
        on the same bed day, if it does, cancel the newly received sale line, and inform findir
        :param sale_line: gemma.sale.line record
        :return: True if duplicate exists, else False
        """
        check_for_duplicates = \
            sale_line.is_gp and sale_line.bed_day_date and sale_line.partner_id and \
            sale_line.ext_sale_done and not sale_line.is_canceled

        if check_for_duplicates:
            existing_sales = self.search(
                [('partner_id', '=', sale_line.partner_id.id),
                 ('state', 'not in', ['canceled', 'cancel_locked']),
                 ('id', '!=', sale_line.id),
                 ('ext_sale_done', '=', True),
                 ])

            # Check if some GP sales for the same day do exist
            # Using filtered because of computes, and date substring checks
            duplicates = existing_sales.filtered(
                lambda f: f.is_gp and f.bed_day_date and
                f.bed_day_date[:10] == sale_line.bed_day_date[:10])

            if duplicates:
                # If duplicates do exist - cancel newly received sale line
                sale_line.write({'state': 'canceled', 'is_canceled': True, 'inform_accountant': True})

    @api.multi
    def inform_about_duplicate_gp_sale(self):
        """
        Inform accountant about duplicate GP sales
        by sending an email
        :return: None
        """
        report = str()
        for rec in self:
            # Do not use filtered, since it re-browses records
            if rec.inform_accountant and rec.ext_sale_done:
                report += _('Partneris - %s | Guldymo data - %s\n') % (rec.partner_id.name, rec.bed_day_date)
                rec.post_message(lines=rec, l_body=_('Pardavimas atšauktas | Lovadienis dublikuotas'))
                rec.inform_accountant = False
        if report:
            report = _('Gemma lovadienių dublikatai | Gauti lovadieniai toms pačioms dienoms: \n\n') + report
            self.env['gemma.data.import'].inform_findir(message=report, inform_type='email')

    def delayed_invoice_prep(self, invoice_ids):
        force_creation = True  # Temporally force create
        if not gemma_tools.assert_creation_weekday() and not force_creation:
            return
        delay_date = gemma_tools.delay_date()
        if not force_creation:
            invoice_ids = invoice_ids.filtered(lambda r: r.date_invoice <= delay_date)
        non_dated = self.env['gemma.invoice']
        for ext_invoice in invoice_ids:
            earliest_sale = ext_invoice.sale_line_ids.sorted(lambda x: x.sale_date)[0]
            sale_date_dt = datetime.strptime(earliest_sale.sale_date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            invoice_date_dt = datetime.strptime(ext_invoice.date_invoice, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            delta = relativedelta(sale_date_dt, invoice_date_dt)
            if abs(delta.months) in [1, 0]:
                non_dated += ext_invoice

        # Comparing lock date without using check_locked_accounting so it's not fetched on each loop
        lock_date = self.env.user.company_id.get_user_accounting_lock_date()
        for ext_invoice in non_dated:
            if self.env['account.invoice'].search([('move_name', '=', ext_invoice.name),
                                                   ('type', 'in', ['out_invoice', 'out_refund'])]):
                continue
            invoices_to_credit = ext_invoice.sale_line_ids.mapped('invoice_id')
            ext_invoice_lines = ext_invoice.sale_line_ids
            min_date = min([x.sale_day for x in ext_invoice_lines])
            if min_date <= lock_date:
                body = 'Nepavyko sukurti sąskaitos. Tėvinės sąskaitos eilutės turi padienines sąskaitas ir ' \
                       'bent viena iš šių eilučių yra užrakintame periode.'
                self.post_message(invoice=ext_invoice, i_body=body)
                continue
            for invoice in invoices_to_credit:
                corresponding_lines = ext_invoice_lines.filtered(lambda x: x.invoice_id.id == invoice.id)
                dummy = self.env['gemma.invoice']
                self.with_context(correction=True).create_invoices(corresponding_lines, dummy)
                corresponding_lines.write({'invoice_line_id': False,
                                           'correction_line_id': False,
                                           'refund_line_id': False,
                                           'is_canceled': False})
            self.with_context(corrected_external=True).create_invoices(ext_invoice_lines, ext_invoice)

    def invoice_creation_prep(self, invoice_ids, sale_ids):
        force_creation = True  # Temporally force create
        if not gemma_tools.assert_creation_weekday() and not force_creation:
            return
        delay_date = gemma_tools.delay_date()
        do_validate = self._context.get('validate', False)
        invoice_ids = invoice_ids.filtered(
            lambda x: x.ext_invoice_id and not x.invoice_id)

        s_lines = sale_ids.filtered(
            lambda x: not x.ext_invoice_id and not x.invoice_id and not
            x.invoice_line_id and not x.is_canceled and x.state
            not in ['awaiting', 'canceled', 'awaiting_rehab'] and x.ext_sale_done)
        if not force_creation:
            s_lines = s_lines.filtered(lambda x: x.sale_day <= delay_date)
            invoice_ids = invoice_ids.filtered(lambda x: x.date_invoice <= delay_date)

        if do_validate:
            s_lines, invoice_ids = self.validator(sales=s_lines, invoices=invoice_ids)
        if invoice_ids:
            for invoice in invoice_ids:
                lines = invoice.sale_line_ids
                if True not in lines.mapped('is_canceled') and 'awaiting' not in lines.mapped('state') \
                        and 'awaiting_rehab' not in lines.mapped('state'):
                    self.create_invoices(lines, invoice)
        if s_lines:
            self.force_partner(s_lines)
            dummy = self.env['gemma.invoice']
            grouped_lines = {}
            for line in s_lines:
                # Loop through lines and build dict of dicts with following mapping
                partner = line.partner_id
                s_day = line.sale_day
                l_type = line.line_type
                b_exc = line.batch_excluded

                grouped_lines.setdefault(partner, {})
                grouped_lines[partner].setdefault(s_day, {})
                grouped_lines[partner][s_day].setdefault(l_type, {})
                grouped_lines[partner][s_day][l_type].setdefault(b_exc, self.env['gemma.sale.line'])
                grouped_lines[partner][s_day][l_type][b_exc] |= line

            for partner, by_partner in iteritems(grouped_lines):
                for s_day, by_sale_day in iteritems(by_partner):
                    for l_type, by_line_type in iteritems(by_sale_day):
                        for b_exc, by_b_exc in iteritems(by_line_type):
                            if b_exc:
                                for ex_line in by_b_exc:
                                    self.create_invoices(ex_line, dummy)
                            else:
                                self.create_invoices(by_b_exc, dummy)

    def create_invoices(self, line_ids, ext_invoice):
        correction = self._context.get('correction', False)
        corrected_external = self._context.get('corrected_external', False)
        default_journal = self.env['account.journal'].search([('type', '=', 'sale')], limit=1)
        default_location = self.env['stock.location'].search(
            [('usage', '=', 'internal')], order='create_date desc', limit=1)
        invoice_type = line_ids[0].line_type
        partner_id = line_ids[0].partner_id
        invoice_obj = self.env['account.invoice'].sudo()
        account_obj = self.env['account.account'].sudo()
        delivery_wizard = self.env['invoice.delivery.wizard'].sudo()
        invoice_lines = []
        account_id = account_obj.search([('code', '=', '2410')])
        p_include = 'exc' if self._context.get('price_exclude', False) else 'inc'
        invoice_values = {
            'external_invoice': True,
            'force_dates': True,
            'account_id': account_id.id,
            'partner_id': partner_id.id,
            'journal_id': default_journal.id,
            'invoice_line_ids': invoice_lines,
            'type': invoice_type,
            'price_include_selection': p_include,
            'imported_api': True,
        }
        if ext_invoice:
            invoice_values['number'] = ext_invoice.name
            invoice_values['move_name'] = ext_invoice.name
            invoice_values['date_invoice'] = invoice_values['operacijos_data'] = ext_invoice.date_invoice
        else:
            invoice_values['date_invoice'] = invoice_values['operacijos_data'] = line_ids[0].get_date_to_use()

        amount_total = 0.0
        grouped_lines = []
        grouped_inv_lines = {}
        for line in line_ids:
            # Loop through lines and build dict of dicts with following mapping
            prod = line.product_id
            price = line.price
            tax = line.tax_id

            grouped_inv_lines.setdefault(prod, {})
            grouped_inv_lines[prod].setdefault(price, {})
            grouped_inv_lines[prod][price].setdefault(tax, self.env['gemma.sale.line'])
            grouped_inv_lines[prod][price][tax] |= line

        for product, by_product in iteritems(grouped_inv_lines):
            for price, by_price in iteritems(by_product):
                for tax, final_lines in iteritems(by_price):
                    quantity = sum(tax.qty for tax in final_lines)
                    default = final_lines[0]
                    product_account = default.product_id.get_product_income_account(return_default=True)
                    grouped_lines.append({
                        'product_id': default.product_id.id,
                        'name': default.product_id.name,
                        'quantity': quantity,
                        'price_unit': abs(default.price),
                        'uom_id': default.product_id.product_tmpl_id.uom_id.id,
                        'account_id': product_account.id,
                        'invoice_line_tax_ids': [(6, 0, default.tax_id.ids)],
                        'gemma_sale_line_ids': [(6, 0, final_lines.ids)]
                    })
        if correction:
            key = 'gemma_refund_line_ids'
        elif corrected_external:
            key = 'gemma_correction_line_ids'
        else:
            key = 'gemma_sale_line_ids'

        for sale_line in grouped_lines:
            line_vals = {
                'product_id': sale_line['product_id'],
                'name': sale_line['name'],
                'quantity': sale_line['quantity'],
                'price_unit': sale_line['price_unit'],
                'uom_id': sale_line['uom_id'],
                'account_id': sale_line['account_id'],
                'invoice_line_tax_ids': sale_line['invoice_line_tax_ids'],
                key: sale_line['gemma_sale_line_ids']
            }
            invoice_lines.append((0, 0, line_vals))
            amount_total += abs(sale_line['quantity'] * sale_line['price_unit'])

        if correction:
            invoice_values['type'] = 'out_refund'
            invoice_values.pop('number', None)
            invoice_values['move_name'] = self.env['ir.sequence'].next_by_code('G_INV_CRED')
            if 'message_follower_ids' in invoice_values:
                invoice_values.pop('message_follower_ids')
            try:
                credit_invoice_id = invoice_obj.create(invoice_values)
            except Exception as e:
                self.env.cr.rollback()
                body = _('Nepavyko sukurti korekcijos sąskaitų, sisteminė klaida %s') % e
                self.post_message(lines=line_ids, invoice=ext_invoice, i_body=body, l_body=body, state='failed')
                self.env.cr.commit()
                return 1
            try:
                credit_invoice_id.partner_data_force()
                credit_invoice_id.action_invoice_open()
                lines = credit_invoice_id.move_id.line_ids.filtered(lambda r: r.account_id.code == '2410')
                lines2 = line_ids.mapped('invoice_id').move_id.line_ids.filtered(lambda r: r.account_id.code == '2410')
                lines2.remove_move_reconcile()
                lines |= lines2
                lines.with_context(reconcile_v2=True).reconcile()

            except Exception as e:
                self.env.cr.rollback()
                body = _('Nepavyko sukurti sąskaitos, sisteminė klaida %s') % e.args[0] if e.args else e
                self.post_message(lines=line_ids, invoice=ext_invoice, i_body=body, l_body=body, state='failed')
                self.env.cr.commit()
                return 1

            types = credit_invoice_id.mapped('invoice_line_ids.product_id.type')
            credit_invoice_id.write({'accountant_validated': True})
            if 'product' in types:
                wizard_id = delivery_wizard.with_context(invoice_id=credit_invoice_id.id).create(
                    {'location_id': default_location.id})
                wizard_id.create_delivery()
                if credit_invoice_id.picking_id and credit_invoice_id.picking_id.state != 'done':
                    try:
                        credit_invoice_id.picking_id.action_assign()
                    except Exception as e:
                        body = _('Nepavyko rezervuoti prekių sukurtai korekcinei sąskaitai, klaidos pranešimas: %s') % e
                        self.post_message(invoice=credit_invoice_id, i_body=body)
                    if credit_invoice_id.picking_id.state == 'assigned':
                        credit_invoice_id.picking_id.do_transfer()

        else:
            try:
                invoice_id = invoice_obj.create(invoice_values)
            except Exception as e:
                self.env.cr.rollback()
                body = _('Sąskaitos kūrimo klaida. Klaidos pranešimas %s') % e
                self.post_message(lines=line_ids, invoice=ext_invoice, i_body=body, l_body=body, state='failed')
                self.env.cr.commit()
                return 1

            if ext_invoice:
                ext_invoice.invoice_id = invoice_id
                ext_invoice.state = 'created'
            line_ids.write({'state': 'created'})
            if amount_total and tools.float_compare(amount_total, abs(invoice_id.reporting_amount_total),
                                                    precision_digits=2) != 0:
                if round(abs(invoice_id.reporting_amount_total - amount_total), 2) > gemma_tools.allowed_calc_error:
                    self.env.cr.rollback()
                    body = _('Gemma sąskaitos galutinė suma nesutampa su paskaičiuota suma (%s != %s).\n'
                             ) % (amount_total, invoice_id.reporting_amount_total)
                    self.post_message(lines=line_ids, invoice=ext_invoice, i_body=body, l_body=body, state='failed')
                    self.env.cr.commit()
                    return 1
            types = invoice_id.mapped('invoice_line_ids.product_id.type')

            try:
                invoice_id.partner_data_force()
                invoice_id.action_invoice_open()
            except Exception as e:
                self.env.cr.rollback()
                body = _('Nepavyko sukurti sąskaitos, sisteminė klaida %s') % e.args[0] if e.args else e
                self.post_message(lines=line_ids, invoice=ext_invoice, i_body=body, l_body=body, state='failed')
                self.env.cr.commit()
                return 1

            invoice_id.write({'accountant_validated': True})
            if 'product' in types:
                rec = self.sudo().env['ir.module.module'].search([('name', '=', 'robo_stock')])
                if rec and rec.state in ['installed', 'to upgrade']:
                    wizard_id = delivery_wizard.with_context(invoice_id=invoice_id.id).create(
                        {'location_id': default_location.id})
                    wizard_id.create_delivery()
                    if invoice_id.picking_id and invoice_id.picking_id.state != 'done':
                        try:
                            invoice_id.picking_id.action_assign()
                        except Exception as e:
                            body = _('Nepavyko rezervuoti prekių sukurtai sąskaitai, klaidos pranešimas: %s') % e
                            self.post_message(invoice=invoice_id, i_body=body)
                        if invoice_id.picking_id.state == 'assigned':
                            invoice_id.picking_id.do_transfer()

            if ext_invoice:
                ext_invoice.invoice_id = invoice_id

        self.env.cr.commit()
        return 0

    def post_message(self, lines=None,
                     l_body=None, state=None, invoice=None, i_body=None):
        if lines is None:
            lines = self.env['gemma.sale.line']
        if invoice is None:
            invoice = self.env['gemma.invoice']
        if lines:
            msg = {'body': l_body}
            for line in lines:
                line.message_post(**msg)
            if state is not None:
                lines.write({'state': state})
        if invoice:
            msg = {'body': i_body}
            invoice.message_post(**msg)
            if state is not None:
                invoice.state = state

    def validator(self, sales, invoices):
        filtered_sales = self.env['gemma.sale.line']
        filtered_invoices = self.env['gemma.invoice']
        sales.get_product()
        sales._compute_tax_id()
        sales.get_payment_id()
        sales.get_cash_register()
        sales.get_partner()

        for sale_id in sales.filtered(lambda x: x.ext_sale_done):
            if sale_id.is_gp and not sale_id.bed_day_date:
                continue
            elif sale_id.rehabilitation_sale and not sale_id.rehabilitation_date:
                continue
            sale_id.payment_id.get_payment_type()
            if not sale_id.tax_id and sale_id.payment_id:
                sale_id.tax_id = self.env['account.tax'].search(
                        [('amount', '=', sale_id.payment_id.vat_rate), ('type_tax_use', '=', 'sale'),
                         ('price_include', '=', True)], limit=1).id
            body = str()
            if not sale_id.tax_id:
                body += _('Klaida kuriant sąskaitą, neegzistuoja PVM!\n')

            if not sale_id.product_id:
                body += _('Klaida kuriant sąskaitą, produktas neegzistuoja sistemoje!\n')

            if not sale_id.partner_id:
                body += _('Klaida kuriant sąskaitą, nerastas partneris!\n')
            if body:
                self.post_message(lines=sale_id, l_body=_(body), state='failed')
            else:
                filtered_sales += sale_id

        for invoice_id in invoices:
            body = str()
            line_warnings = False
            if not invoice_id.sale_line_ids:
                body += _('Klaida kuriant sąskaitą, nerastos sąskaitos eilutės!\n')
            else:
                invoice_id.sale_line_ids.get_product()
                invoice_id.sale_line_ids._compute_tax_id()
                invoice_id.sale_line_ids.get_payment_id()
                invoice_id.sale_line_ids.get_cash_register()
                invoice_id.sale_line_ids.get_partner()
                for line in invoice_id.sale_line_ids:
                    if line.invoice_id or line.invoice_line_id or line.state == 'created':
                        line_warnings = True
                        invoice_id.state = 'failed'
                    if not line.tax_id:
                        body += _('Klaida kuriant sąskaitą, bent vienoje eilutėje neegzistuoja PVM!\n')
                        line_warnings = True
                    if not line.product_id:
                        body += _('Klaida kuriant sąskaitą, bent vienos eilutės produktas neegzistuoja sistemoje!\n')
                        line_warnings = True
                if line_warnings:
                    body += _('Rasta įspėjimų, patikrinkite sąskaitos eilutes!\n')
            if body:
                self.post_message(invoice=invoice_id, i_body=_(body), state='failed')
            if not body and not line_warnings:
                filtered_invoices += invoice_id

        self.env.cr.commit()
        return filtered_sales, filtered_invoices

    def send_bug(self, body):
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'error_message': body,
        })

    @api.multi
    def credit_sales(self):
        for sale in self:
            sale.state = 'canceled'
            sale.is_canceled = True
        non_credited = self.filtered(lambda d: not d.refund_id)
        invoices = non_credited.mapped('invoice_id')
        for invoice in invoices:
            corresponding_sales = self.filtered(lambda x: x.invoice_id.id == invoice.id)
            dummy = self.env['gemma.invoice']
            self.with_context(correction=True).create_invoices(line_ids=corresponding_sales, ext_invoice=dummy)

    @api.model
    def cron_recreate(self):
        """
        Recreate, re-reconcile the data and inform accountant on duplicates.
        Data: -Gemma invoices, -Gemma sale lines, -Gemma payments
        After re-creation process reconcile everything that can be reconciled
        :return: None
        """

        # Inform findir on duplicates and commit, so if it fails later, we do not spam
        duplicate_sales = self.env['gemma.sale.line'].search([('inform_accountant', '=', True)])
        duplicate_sales.inform_about_duplicate_gp_sale()
        self.env.cr.commit()

        # Invoices and sale lines
        invoices = self.env['gemma.invoice'].search([('invoice_id', '=', False),
                                                     ('sale_line_ids.invoice_id', '=', False)])

        sales = self.env['gemma.sale.line'].search([('invoice_id', '=', False), ('active', '=', True),
                                                    ('state', 'in', ['failed', 'imported', 'warning']),
                                                    ('ext_sale_done', '=', True)])
        self.with_context(validate=True).invoice_creation_prep(invoices, sales)
        self.env.cr.commit()

        # Payments
        payments = self.env['gemma.payment'].search([('move_id', '=', False),
                                                     ('state', 'in', ['active', 'warning', 'failed']),
                                                     '|',
                                                     ('payment_type_id.is_active', '=', True),
                                                     ('cash_operation_type', '=', 'out')])
        payments.with_context(validate=True).move_creation_prep()
        self.env.cr.commit()

        reconcilable = self.env['gemma.payment'].search([('move_id', '!=', False),
                                                         ('state', 'in', ['open', 'partially_reconciled']),
                                                         ('type', '!=', 'cash_operations'),
                                                         ('payment_type_id.do_reconcile', '=', True)])
        reconcilable.re_reconcile()

    @api.model
    def cron_fetch_create(self):
        if datetime.utcnow().weekday() not in [5, 6]:
            wizard = self.env['gemma.data.import']
            wizard.with_context(cron_job=True).data_import_cron()

    @api.multi
    def unlink(self):
        if not self.env.user.is_accountant():
            raise exceptions.UserError(_('Negalima ištrinti Gemma pardavimo eilutės!'))
        if self.mapped('invoice_id') or self.mapped('invoice_line_id'):
            raise exceptions.UserError(_('Negalima ištrinti eilutės kuri pririšta prie sisteminės sąskaitos!'))
        return super(GemmaSaleLine, self).unlink()

    def force_partner(self, line_ids):
        no_partner = line_ids.filtered(lambda x: not x.partner_id)
        for line in no_partner:
            if line.payment_id.partner_id:
                line.write({'partner_id': line.payment_id.partner_id.id})


GemmaSaleLine()
