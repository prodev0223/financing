# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, tools, exceptions
from . import nsoft_tools as nt
from datetime import datetime


class NsoftInvoice(models.Model):
    _name = 'nsoft.invoice'
    _inherit = ['mail.thread']

    # nSoft fields
    ext_id = fields.Integer(string='Išorinis identifikatorius', readonly=True)
    name = fields.Char(string='Pavadinimas', required=True)
    date_invoice = fields.Date(string='Sąskaitos data')
    payment_date = fields.Datetime(string='Mokėjimo data')
    date_due = fields.Date(string='Mokėjimo terminas')
    partner_name = fields.Char(string='Pirkejas (Pavadinimas)', required=True, inverse='_set_partner_id')
    partner_address = fields.Char(string='Pirkejo adresas')
    partner_bank_account = fields.Char(string='Partnerio banko sąskaita')
    partner_bank_code = fields.Char(string='Partnerio banko kodas')
    partner_mobile = fields.Char(string='Pirkejo telefonas')
    partner_code = fields.Char(string='Pirkejo kodas')
    partner_vat = fields.Char(string='Pirkejo PVM kodas')
    cash_register_number = fields.Char(string='Kasos aparato numeris', inverse='_set_cash_register_id')
    receipt_id = fields.Char(string='Čekio numeris', inverse='_set_sale_lines')

    # Prices
    sum_wo_vat = fields.Float(string='Sąskaitos suma be PVM')
    items_vat_sum = fields.Float(string='PVM suma')
    item_amount = fields.Float(string='Prekių kiekis')
    sum_with_vat = fields.Float(string='Sąskaitos suma su PVM')

    # System  fields
    cash_register_id = fields.Many2one('nsoft.cash.register', inverse='_set_partner_id', string='Kasos aparatas')
    pay_active = fields.Boolean(string='Mokėjimo tipo aktyvumas', compute='_compute_pay_active')

    partner_id = fields.Many2one('res.partner', string='Pirkėjas')
    invoice_id = fields.Many2one('account.invoice', string='Sukurta sąskaita faktūra')
    refund_id = fields.Many2one('account.invoice', string='Kreditinė sąskaita faktūra')
    correction_id = fields.Many2one('account.invoice', string='Koreguota sąskaita faktūra')
    sale_line_ids = fields.One2many('nsoft.sale.line', 'nsoft_invoice_id', string='Pardavimų eilutės')
    state = fields.Selection([('imported', 'Sąskaita importuota'),
                              ('created', 'Sąskaita sukurta sistemoje'),
                              ('failed', 'Klaida kuriant sąskaitą'),
                              ('failed2', 'Sąskaita importuota su įspėjimais')],
                             string='Būsena', default='imported', track_visibility='onchange')
    inv_line_ids = fields.One2many('nsoft.invoice.line', 'nsoft_invoice_id', string='Pardavimų eilutės')
    is_dated = fields.Boolean(compute='_compute_is_dated')
    to_be_corrected = fields.Boolean(compute='_compute_to_be_corrected')

    nsoft_payment_ids = fields.Many2many('nsoft.payment', string='Apmokėjimai', inverse='_set_cash_register_id')
    payment_type_tag_text = fields.Text(string='Mokėjimo tipai', compute='_compute_payment_type_tag_text')

    # Used only on spec invoices
    payment_name = fields.Char(string='Išorinis mokėjimo pavadinimas', inverse='_set_pay_type_id')
    pay_type_id = fields.Many2one('nsoft.payment.type', string='nSoft mokėjimo tipas')

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
    @api.depends('sale_line_ids')
    def _compute_to_be_corrected(self):
        """Compute"""
        for rec in self:
            if not rec.invoice_id and rec.sale_line_ids.mapped('invoice_id'):
                rec.to_be_corrected = True

    @api.multi
    @api.depends('date_invoice')
    def _compute_is_dated(self):
        """Compute"""
        for rec in self:
            threshold = datetime.strptime(nt.DATED_SALE_DATE, tools.DEFAULT_SERVER_DATE_FORMAT)
            sale_date_dt = datetime.strptime(rec.date_invoice, tools.DEFAULT_SERVER_DATE_FORMAT)
            rec.is_dated = True if sale_date_dt < threshold else False

    @api.multi
    @api.depends('nsoft_payment_ids.pay_type_id.is_active')
    def _compute_pay_active(self):
        """Compute"""
        for rec in self:
            rec.pay_active = any(x.pay_type_id.is_active for x in rec.nsoft_payment_ids)

    @api.multi
    def _set_cash_register_id(self):
        """Inverse"""
        reg_obj = self.env['nsoft.cash.register'].sudo()
        for rec in self.filtered(lambda x: not x.cash_register_id):
            cash_register = self.env['nsoft.cash.register']
            for payment in rec.nsoft_payment_ids:
                if payment.pay_type_id.internal_code in ['web', 'trans', 'gft']:
                    cash_register = reg_obj.search(
                        [('spec_register', '=', payment.pay_type_id.internal_code)]).id
                    if not cash_register:
                        cash_register = reg_obj.create_cash_register(payment.pay_type_id.internal_code)
                    break
            if not cash_register and rec.cash_register_number:
                cash_register = reg_obj.search([('cash_register_number', '=', rec.cash_register_number)]).id
                if not cash_register:
                    cash_register = reg_obj.create({'cash_register_number': rec.cash_register_number})
            if not cash_register and not rec.receipt_id:
                cash_register = reg_obj.search([('spec_register', '=', 'no_receipt')]).id
                if not cash_register:
                    cash_register = reg_obj.create_cash_register('no_receipt')
            rec.cash_register_id = cash_register

    @api.multi
    def _set_sale_lines(self):
        """Inverse"""
        for rec in self:
            sale_lines = self.env['nsoft.sale.line'].sudo()
            if rec.receipt_id:
                receipts = list(set(rec.receipt_id.split(','))) if ',' in rec.receipt_id else [rec.receipt_id]
                for receipt in receipts:
                    sale_lines |= self.env['nsoft.sale.line'].sudo().search(
                        [('receipt_id', '=', receipt), ('product_code', 'not in', nt.NON_INVOICED_PRODUCT_CODES)])
            sale_lines.write({'nsoft_invoice_id': rec.id})

    @api.multi
    def _set_partner_id(self):
        """Inverse"""
        for rec in self.filtered(lambda x: not x.partner_id):
            if rec.partner_name:
                partner = self.env['res.partner'].search([('name', '=', rec.partner_name)], limit=1)
                if not partner and rec.partner_code:
                    partner = self.env['res.partner'].search([('kodas', '=', rec.partner_code)], limit=1)
                if not partner:
                    country = self.env['res.country'].sudo().search([('code', '=', 'LT')], limit=1)
                    partner_vals = {
                        'name': rec.partner_name,
                        'is_company': True if rec.partner_code else False,
                        'kodas': rec.partner_code,
                        'phone': rec.partner_mobile,
                        'vat': rec.partner_vat,
                        'street': rec.partner_address or ' ',
                        'country_id': country.id,
                    }
                    try:
                        partner = self.env['res.partner'].sudo().create(partner_vals).id
                    except Exception as e:
                        body = 'Klaida, netinkami partnerio duomenys, klaidos pranešimas %s' % str(e.args[0])
                        rec.post_message(i_body=body, state='failed', ext_invoice=self)
                rec.partner_id = partner
            elif rec.cash_register_id:
                rec.partner_id = rec.cash_register_id.partner_id
        if self._context.get('force_commit', False):
            self.env.cr.commit()

    @api.multi
    def _set_pay_type_id(self):
        """Inverse"""
        for rec in self:
            if rec.payment_name:
                pay_type_id = self.env['nsoft.payment.type'].search([('name', '=', rec.payment_name)])
                if not pay_type_id:
                    pay_type_id = self.env['nsoft.payment.alt.names'].search(
                        [('alternative_name', '=', rec.payment_name)]).pay_type_id
                rec.pay_type_id = pay_type_id

    @api.multi
    def recompute_fields(self):
        self.force_cash_register()
        self._compute_to_be_corrected()
        self._compute_is_dated()
        self._compute_pay_active()
        self._set_cash_register_id()
        self._set_sale_lines()
        self._set_partner_id()
        self._set_pay_type_id()

    # Main methods ---------------------------------------------------------

    @api.multi
    def force_cash_register(self):
        """Force cash register to related invoice_lines"""
        for rec in self:
            if rec.cash_register_id:
                registers = rec.inv_line_ids.mapped('cash_register_id')
                if len(registers) > 1 or (len(registers) == 1 and registers != rec.cash_register_id):
                    rec.inv_line_ids.write({'cash_register_id': rec.cash_register_id.id})

    @api.multi
    def create_invoices(self):
        """
        Create invoices action in form. Three types of invoices, standard invoices, spec invoices (that use different
        sale line objects) and invoices to be corrected (nsoft parent invoices that have sale lines with robo invoice)
        :return: None
        """
        default_obj = self.sudo().env['nsoft.sale.line']
        corresponding_invoices = self.filtered(lambda x: not x.invoice_id and x.state not in ['created'])

        spec_invoices = corresponding_invoices.filtered(lambda x: not x.receipt_id)
        if spec_invoices:
            for spec_invoice in spec_invoices.filtered(lambda x: not x.inv_line_ids):
                self.sudo().env['nsoft.import.base'].fetch_remaining_lines(spec_invoice.mapped('ext_id'))
            spec_invoices.spec_invoice_creation_prep()

        to_be_corrected = corresponding_invoices.filtered(lambda x: x.receipt_id and x.to_be_corrected)
        if to_be_corrected:
            to_be_corrected.create_correction_invoices()

        standard_invoices = corresponding_invoices.filtered(lambda x: x.receipt_id and not x.to_be_corrected)
        if standard_invoices:
            default_obj.invoice_creation_prep(nsoft_invoice_ids=standard_invoices)

    @api.multi
    def validator(self):
        """
        Validate whether passed invoices meet the criteria to be created as an account_invoice
        :return: filtered nsoft.invoice records
        """
        filtered_invoices = self.env['nsoft.invoice']
        error_template = _('Klaida kuriant sąskaitą, ')

        # Filter out the invoices and recompute their fields
        ext_invoices = self.filtered(lambda x: not x.invoice_id and x.pay_active and not x.is_dated)
        ext_invoices.with_context(force_commit=True).recompute_fields()

        for ext_invoice in ext_invoices:
            body = str()
            line_warnings = False
            amount_total_lines = 0.0
            if not ext_invoice.inv_line_ids:
                body += error_template + _('nerastos sąskaitos eilutės!\n')
            else:
                ext_invoice.inv_line_ids.recompute_fields()
                if not ext_invoice.partner_id:
                    body += error_template + _('nerastas sąskaitos partneris!\n')
                if not ext_invoice.cash_register_id:
                    body += error_template + _('nerastas kasos aparato numeris!\n')
                if not ext_invoice.cash_register_id.journal_id:
                    body += error_template + _('nerastas bilietų žurnalas!\n')
                for line in ext_invoice.sale_line_ids:
                    amount_total_lines += line.vat_price * line.quantity
                    if not line.tax_id:
                        body += error_template + _('bent vienoje eilutėje neegzistuoja PVM!\n')
                        line_warnings = True
                    if not line.product_id:
                        body += error_template + _('bent vienos eilutės produktas neegzistuoja sistemoje!\n')
                        line_warnings = True
                if tools.float_compare(abs(amount_total_lines), abs(ext_invoice.sum_with_vat), precision_digits=2):
                    diff = abs(ext_invoice.sum_with_vat) - abs(amount_total_lines)
                    if tools.float_compare(diff, nt.ALLOWED_TAX_CALC_ERROR, precision_digits=2) > 0:
                        body += _('nSoft Sąskaitos ir pardavimo eilučių galutinės sumos nesutampa (%s != %s).\n') % (
                            amount_total_lines, ext_invoice.sum_with_vat)
                if line_warnings:
                    body += _('Rasta įspėjimų, patikrinkite sąskaitos eilutes!\n')
            if body:
                self.post_message(ext_invoice=ext_invoice, i_body=body, state='failed')
            else:
                filtered_invoices += ext_invoice
        return filtered_invoices

    @api.multi
    def spec_invoice_creation_prep(self):
        """
        Prepare special (different line object)
        nsoft invoices for creation
        :return: None
        """
        validated_invoices = self.validator()
        for rec in validated_invoices:
            rec.create_invoices_spec()

    @api.multi
    def create_invoices_spec(self):
        """
        Fetch and create nsoft.invoices that use different line objects (nsoft.invoice.line instead of nsoft.sale.line)
        that must be pre-fetched from nSoft DB's extra table
        :return: None
        """
        self.ensure_one()
        # Prepare invoice values -------------------------------------------------------------------------------
        lines = self.inv_line_ids
        invoice_obj = self.env['account.invoice'].sudo()
        account_obj = self.env['account.account'].sudo()
        invoice_lines = []
        inv_values = {
            'external_invoice': True,
            'force_dates': True,
            'imported_api': True,
            'skip_global_reconciliation': True,
            'number': self.name,
            'move_name': self.name,
            'journal_id': self.cash_register_id.journal_id.id,
            'date_invoice': self.date_invoice,
            'operacijos_data': self.date_invoice,
            'date_due': self.date_due,
            'account_id': account_obj.search([('code', '=', '2410')]).id,
            'partner_id': self.partner_id.id,
            'invoice_line_ids': invoice_lines,
            'price_include_selection': 'inc'
        }
        if self.sum_with_vat > 0:
            inv_values['type'] = 'out_invoice'
        else:
            inv_values['type'] = 'out_refund'

        # Prepare invoice lines -------------------------------------------------------------------------------
        total_tax = 0.0
        total_untaxed = 0.0
        for line in lines:
            product_account = line.product_id.get_product_income_account(return_default=True)
            line_values = {
                'product_id': line.product_id.id,
                'name': line.product_id.name,
                'quantity': abs(line.quantity),
                'price_unit': abs(line.price_unit),
                'uom_id': line.product_id.product_tmpl_id.uom_id.id,
                'discount': line.discount,
                'account_id': product_account.id,
                'invoice_line_tax_ids': [(6, 0, line.tax_id.ids)],
                'nsoft_inv_line_ids': [(6, 0, line.ids)]
            }
            invoice_lines.append((0, 0, line_values))
            total_tax += tools.float_round(line.vat_sum + line.item_sum, precision_digits=2)
            total_untaxed += line.item_sum

        try:
            invoice = invoice_obj.create(inv_values)
        except Exception as e:
            self.env.cr.rollback()
            body = _('Siteminė klaida kuriant sąskaitą %s') % str(e.args[0])
            self.send_bug(body)
            self.post_message(lines=lines, ext_invoice=self, i_body=body, l_body=body, state='failed')
            self.env.cr.commit()
            return

        # Validate amount tax, amount untaxed and amount total --------------------------------------------------
        invoice.force_invoice_tax_amount(self.items_vat_sum)
        amount_data = [
            ('amount_total', self.items_vat_sum, True),
            ('amount_tax', self.items_vat_sum, False),
            ('amount_untaxed', self.sum_wo_vat, True)
        ]
        body = invoice.check_invoice_amounts(amount_data)
        if body:
            self.env.cr.rollback()
            self.post_message(lines=lines, ext_invoice=self, i_body=body, l_body=body, state='failed')
            self.env.cr.commit()
            return

        try:
            invoice.partner_data_force()
            invoice.action_invoice_open()
        except Exception as e:
            self.env.cr.rollback()
            body = _('Nepavyko sukurti sąskaitos, sisteminė klaida %s') % str(e.args[0])
            self.post_message(lines=lines, ext_invoice=self, i_body=body, l_body=body, state='failed')
            self.env.cr.commit()
            return

        # Post create writes -----------------------------------------------------------
        self.post_op_write(invoice_id=invoice)
        invoice.write({'accountant_validated': True})

        # Create delivery if robo_stock is installed ------------------------------------
        res = invoice.create_nsoft_delivery(location_id=self.cash_register_id.location_id)
        if res:
            self.post_message(ext_invoice=self, lines=lines, i_body=res, l_body=res)

        for payment in self.nsoft_payment_ids:
            payment.create_nsoft_moves(invoice.partner_id, forced_amount=payment.payment_sum)
            payment.reconcile_with_invoice(invoice)

        invoice.accountant_validated = True
        self.env.cr.commit()

    @api.multi
    def post_op_write(self, invoice_id):
        """Write necessary data to invoice_lines and nsoft_invoices after account invoice creation"""
        self.ensure_one()
        lines = self.mapped('inv_line_ids')
        lines.write({'state': 'created'})
        self.write({'state': 'created', 'invoice_id': invoice_id.id})

    @api.multi
    def create_correction_invoices(self):
        """
        If nsoft.sale.lines get the nsoft invoice object after they are
        created in ROBO as an account invoice, we credit the original
        account invoice and create the new account invoice
        from the parent nsoft invoice object
        :return: None
        """

        # Ref needed objects
        invoices = self
        NsoftSaleLine = self.env['nsoft.sale.line'].sudo()

        if not invoices:
            # We filter out all the invoices that are not created, but have sale lines with created invoice
            invoices = self.search(
                [('state', 'not in', ['created']), ('sale_line_ids.invoice_id', '!=', False)])
            invoices = invoices.filtered(lambda x: x.pay_active)

        # We then validate these invoices, and call the method to credit sales
        invoices = NsoftSaleLine.with_context(correction=True).validator(
            nsoft_invoices=invoices, return_invoices=True)
        for ext_invoice in invoices:
            res = ext_invoice.sale_line_ids.credit_sales()
            if res is not None:
                continue
            self.env['nsoft.sale.line'].create_invoices(ext_invoice=ext_invoice, operation_type='correct')
            self.env.cr.commit()

    @api.model
    def spec_invoice_creation_preprocess(self):
        """
        Fetch and create nsoft invoices that use different line objects
        (nsoft.invoice.line instead of nsoft.sale.line)
        that must be pre-fetched from nSoft DB's extra table
        :return: None
        """
        ext_invoices = self.search(
            ['|', ('receipt_id', '=', False), ('receipt_id', '=', ''), ('invoice_id', '=', False)])
        if ext_invoices:
            external_ids = ext_invoices.mapped('ext_id')
            nsoft_invoice_lines = self.sudo().env['nsoft.import.base'].fetch_remaining_lines(external_ids)
            nsoft_invoices = nsoft_invoice_lines.mapped('nsoft_invoice_id')
            nsoft_invoices.spec_invoice_creation_prep()

    # Actions -----------------------------------------------------------------

    @api.model
    def create_invoice_action_inv(self):
        """
        Action method, used in nsoft.sale.invoice view to create
        account.invoices by hand
        :return: None
        """
        action = self.env.ref('nsoft.create_invoices_action_inv')
        if action:
            action.create_action()

    # Constraints -------------------------------------------------------------

    @api.multi
    @api.constrains('ext_id')
    def _check_ext_id(self):
        for rec in self:
            if rec.ext_id:
                if self.env['nsoft.invoice'].search_count([('id', '!=', rec.id), ('ext_id', '=', rec.ext_id)]):
                    raise exceptions.ValidationError(_('Išorinis sąskaitos identifikatorius egzistuoja sistemoje!'))

    # Misc Methods ------------------------------------------------------------

    @api.multi
    def unlink(self):
        """
        Don't allow unlink if account.invoice is already created.
        Otherwise unlink related objects
        :return: None
        """
        for rec in self:
            if rec.invoice_id:
                raise exceptions.UserError(_('Negalima ištrinti sąskaitos kuri pririšta prie sisteminės sąskaitos!'))
            rec.sale_line_ids.unlink()
            rec.inv_line_ids.unlink()
        return super(NsoftInvoice, self).unlink()

    @api.model
    def send_bug(self, body):
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'error_message': body,
        })

    @api.model
    def post_message(self, l_body=str(), i_body=str(), state=None, lines=None, ext_invoice=None):
        """
        Post message to nsoft.invoice and related lines
        :param l_body: nsoft.invoice.line text to be posted
        :param i_body: nsoft.invoice text to be posted
        :param state: nsoft object state
        :param lines: related invoice lines
        :param ext_invoice: nsoft.invoice
        :return: None
        """
        if lines is None:
            lines = self.env['nsoft.invoice.line']
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


NsoftInvoice()
