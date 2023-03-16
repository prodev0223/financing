# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _, tools

_logger = logging.getLogger(__name__)


class NsoftPurchaseInvoice(models.Model):
    """
    Model that stores purchase invoice data fetched from external nSoft database
    -- USED IN SUM ACCOUNTING
    """
    _name = 'nsoft.purchase.invoice'
    _inherit = ['mail.thread']

    # Identifiers
    ext_invoice_id = fields.Integer(string='Išorinis sąskaitos numeris', required=True, inverse='_set_invoice_number')
    invoice_number = fields.Char(string='Sąskaitos numeris', required=True)

    # Sums
    amount_total_wo_vat = fields.Float(string='Suma (Be PVM)', compute='_compute_amounts')
    amount_total_w_vat = fields.Float(string='Suma (Su PVM)', compute='_compute_amounts')
    amount_vat = fields.Float(string='PVM suma', compute='_compute_amounts')
    is_refund = fields.Boolean(string='Grąžinimas', compute='_compute_amounts')

    # Dates
    date_invoice = fields.Date(string='Sąskaitos data')
    ext_create_date = fields.Datetime(string='Išorinė kūrimo data')

    # Partner Info
    partner_name = fields.Char(string='Pirkejas (Pavadinimas)', required=True, inverse='_set_partner_id')
    partner_code = fields.Char(string='Pirkejas (Kodas)')
    partner_vat = fields.Char(string='Pirkejas (PVM kodas)')

    # Other fields
    warehouse_name = fields.Char(string='Pristatymo sandėlis', inverse='_set_warehouse_data')
    warehouse_code = fields.Char(string='Sandėlio kodas', inverse='_set_warehouse_data')
    warehouse_id = fields.Many2one('nsoft.warehouse', string='Sandėlis')

    comments = fields.Text(string='Komentarai')
    payment_mode = fields.Selection(
        [('own_account', 'Asmeniniai grynieji'),
         ('company_cash', 'Kompanijos grynieji')],
        string='Apmokėjimo tipas', compute='_compute_payment_mode')
    state = fields.Selection([('imported', 'Sąskaita importuota'),
                              ('created', 'Sąskaita sukurta sistemoje'),
                              ('failed', 'Klaida kuriant sąskaitą')],
                             string='Būsena', default='imported', track_visibility='onchange')

    # Relational Fields
    invoice_id = fields.Many2one('account.invoice', string='Sukurta sąskaita faktūra')
    partner_id = fields.Many2one('res.partner', string='Pirkėjas')
    nsoft_purchase_invoice_line_ids = fields.One2many(
        'nsoft.purchase.invoice.line', 'nsoft_purchase_invoice_id', string='Sąskaitos eilutės')

    # Computes / Inverses --------------------------------------------------------------------------------

    @api.multi
    @api.depends('comments')
    def _compute_payment_mode(self):
        """
        Compute //
        Compute purchase invoice payment mode.
            -If {a} is in the comments - invoice is paid own account (ceo)
            -If {k} is in the comments - invoice is paid by company. If it contains 'grynieji', 'gryn'
            it means that its company cash, thus account.payment should be created
        """
        for rec in self.filtered(lambda x: x.comments):
            sanitized_comments = rec.comments.lower()
            if '{a}' in sanitized_comments:
                rec.payment_mode = 'own_account'
            elif '{k}' in sanitized_comments and 'gryn' in sanitized_comments:
                rec.payment_mode = 'company_cash'

    @api.multi
    def _set_warehouse_data(self):
        """Creates and/or relates nSoft warehouse record to current invoice"""
        nSoftWarehouse = self.env['nsoft.warehouse']
        for rec in self.filtered(lambda x: x.warehouse_name and x.warehouse_code):
            # Search for the related warehouse by code, if it doesnt exist - create it
            warehouse = nSoftWarehouse.search([('code', '=', rec.warehouse_code)])
            if not warehouse:
                warehouse = nSoftWarehouse.create({
                    'code': rec.warehouse_code,
                    'name': rec.warehouse_name,
                })
            rec.warehouse_id = warehouse

    @api.multi
    def _set_invoice_number(self):
        """Sanitize external invoice number by removing spaces"""
        for rec in self.filtered(lambda x: x.invoice_number):
            rec.invoice_number = rec.invoice_number.replace(' ', '')

    @api.multi
    @api.depends('nsoft_purchase_invoice_line_ids.amount_wo_vat',
                 'nsoft_purchase_invoice_line_ids.amount_w_vat', 'nsoft_purchase_invoice_line_ids.amount_vat')
    def _compute_amounts(self):
        """
        Compute //
        Compute total invoice amounts by summing related invoice lines,
        and check whether invoice is refund invoice or not
        :return: None
        """
        for rec in self:
            rec.amount_total_wo_vat = sum(x.amount_wo_vat for x in rec.nsoft_purchase_invoice_line_ids)
            rec.amount_total_w_vat = sum(x.amount_w_vat for x in rec.nsoft_purchase_invoice_line_ids)
            rec.amount_vat = sum(x.amount_vat for x in rec.nsoft_purchase_invoice_line_ids)
            if tools.float_compare(rec.amount_total_wo_vat, 0.0, precision_digits=2) >= 0:
                rec.is_refund = False
            else:
                rec.is_refund = True

    @api.multi
    def _set_partner_id(self):
        """
        Inverse //
        Search for related res.partner record, if not found -- create a new one
        :return: None
        """
        for rec in self:
            partner_id = self.env['res.partner']
            if rec.partner_name:
                partner_id = self.env['res.partner'].search([('name', '=', rec.partner_name)], limit=1)
            if not partner_id and rec.partner_code:
                partner_id = self.env['res.partner'].search([('kodas', '=', rec.partner_code.strip())], limit=1)
            if not partner_id and rec.partner_vat:
                # Search partner by VAT code
                partner_by_vat = self.env['res.partner'].search([('vat', '=', rec.partner_vat.strip())], limit=1)
                if partner_by_vat and (not rec.partner_code or not partner_by_vat.kodas):
                    # Make sure that the partner doesn't have a different company code set before using it.
                    partner_id = partner_by_vat
            if not partner_id:
                _logger.info("Trying to create partner for NSoft. Name: %s, Code: %s, VAT: %s.",
                             rec.partner_name or '', rec.partner_code or '', rec.partner_vat or '')
                partner_vals = {
                    'name': rec.partner_name,
                    'is_company': False if not rec.partner_code else True,
                    'kodas': rec.partner_code,
                    'vat': rec.partner_vat,
                    'property_account_receivable_id': self.env['account.account'].sudo().search(
                        [('code', '=', '2410')], limit=1).id,
                    'property_account_payable_id': self.env['account.account'].sudo().search(
                        [('code', '=', '4430')], limit=1).id,
                }
                partner_id = self.env['res.partner'].sudo().create(partner_vals)
                partner_id.vz_read()
            rec.partner_id = partner_id
            # Recompute forced taxes after partner is set
            rec.nsoft_purchase_invoice_line_ids._set_tax_id()
        if self._context.get('force_commit'):
            self.env.cr.commit()

    @api.multi
    def name_get(self):
        return [(rec.id, rec.invoice_number or 'Pirkimo sąskaita') for rec in self]

    @api.multi
    def recompute_fields(self):
        """
        Recalculate all compute and inverse fields
        :return:
        """
        self._set_partner_id()
        self._set_invoice_number()
        self._compute_amounts()

    # Actions --------------------------------------------------------------------------------------------

    @api.model
    def create_purchase_invoice_action_func(self):
        """
        Tree view function. Create action for multi record.set
        :return: None
        """
        action = self.env.ref('nsoft.create_purchase_invoice_action_act')
        if action:
            action.create_action()

    # Main methods ---------------------------------------------------------------------------------------

    @api.multi
    def validator(self):
        """
        Validate whether passed invoices meet the criteria to be created as an account_invoice
        :return: filtered nsoft.purchase.invoice records
        """
        filtered_invoices = self.env['nsoft.purchase.invoice']
        self.with_context(force_commit=True).recompute_fields()
        for purchase_invoice in self.filtered(lambda x: not x.invoice_id):
            body = str()
            failed_lines = self.env['nsoft.purchase.invoice.line']
            if not purchase_invoice.nsoft_purchase_invoice_line_ids:
                body += _('Klaida kuriant sąskaitą, nerastos pirkimo sąskaitos eilutės!\n')
            else:
                purchase_invoice.nsoft_purchase_invoice_line_ids.recompute_fields()
                if not purchase_invoice.partner_id:
                    body += _('Klaida kuriant sąskaitą, nerastas sąskaitos partneris!\n')
                for line in purchase_invoice.nsoft_purchase_invoice_line_ids:
                    if not line.tax_id:
                        body += _('Klaida kuriant sąskaitą, bent vienoje eilutėje neegzistuoja PVM!\n')
                        failed_lines |= line
                    if not line.nsoft_product_category_id.parent_product_id:
                        body += _('Klaida kuriant sąskaitą, bent viena sąskaitos eilutė neturi nSoft produkto '
                                  'kategorijos, arba jos produktas nėra sukonfigūruotas!\n')
                        failed_lines |= line
                if failed_lines:
                    body += _('Rasta įspėjimų, patikrinkite sąskaitos eilutes!\n')
            if body:
                self.post_message(ext_invoice=purchase_invoice, i_body=body, state='failed', lines=failed_lines)
            else:
                filtered_invoices |= purchase_invoice
        return filtered_invoices

    @api.multi
    def purchase_invoice_creation_prep(self):
        """
        Prepare nsoft.purchase.invoice records for account.invoice creation
        :return: None
        """
        purchase_invoice_ids = self.validator()
        purchase_invoice_ids.create_purchase_invoices()

    @api.multi
    def create_purchase_invoices(self):
        """
        Method used to create account.invoices type (in_refund, in_invoice) based on nsoft.purchase.invoice records.
        :return: None
        """

        # Defaults ----------------------------------------------------------------------------------------------
        default_journal_id = self.env['account.journal'].search([('type', '=', 'purchase')], limit=1)
        default_account_id = self.env['account.account'].search([('code', '=', '4430')])

        ceo_employee = self.env.user.company_id.vadovas
        # Separate search for this journal, so limit=1 behaves correctly in both cases
        cash_journal = self.env['account.journal'].search([('type', '=', 'cash')], limit=1)
        # Check if Robo analytic is installed
        robo_analytic_installed = self.sudo().env['ir.module.module'].search_count(
            [('name', '=', 'robo_analytic'), ('state', 'in', ['installed', 'to upgrade'])])
        for rec in self:
            # Get the default analytic from the invoice warehouse
            # only use it in the line if robo analytic is installed
            default_analytic = rec.warehouse_id.analytic_account_id
            # Prep values ---------------------------------------------------------------------------------------
            invoice_type = 'in_refund' if rec.is_refund else 'in_invoice'
            invoice_lines = []
            invoice_values = {
                'external_invoice': True,
                'account_id': default_account_id.id,
                'partner_id': rec.partner_id.id,
                'journal_id': default_journal_id.id,
                'invoice_line_ids': invoice_lines,
                'type': invoice_type,
                'price_include_selection': 'inc',
                'reference': rec.invoice_number,
                'date_invoice': rec.date_invoice,
                'operacijos_data': rec.date_invoice,
                'force_dates': True,
                'imported_api': True,
            }
            for line in rec.nsoft_purchase_invoice_line_ids:
                product = line.nsoft_product_category_id.parent_product_id
                product_account = product.get_product_expense_account(return_default=True)
                line_vals = {
                    'product_id': product.id,
                    'name': product.name or product.product_tmpl_id.name,
                    'quantity': 1,
                    'price_unit': line.amount_w_vat,
                    'uom_id': product.product_tmpl_id.uom_id.id,
                    'account_id': product_account.id,
                    'invoice_line_tax_ids': [(6, 0, line.tax_id.ids)],
                    'nsoft_purchase_line_ids': [(6, 0, line.ids)],
                    'amount_depends': line.amount_w_vat,
                    'price_subtotal_make_force_step': True,
                    'price_subtotal_save_force_value': line.amount_w_vat,
                }
                if robo_analytic_installed:
                    line_vals.update({'account_analytic_id': default_analytic.id})
                invoice_lines.append((0, 0, line_vals))

            # Create invoice ------------------------------------------------------------------------------------
            try:
                invoice = self.env['account.invoice'].create(invoice_values)
            except Exception as e:
                self.custom_rollback(msg=e.args[0], rec=rec)
                continue

            # Check invoice amounts
            invoice.force_invoice_tax_amount(rec.amount_vat)
            amount_data = [
                ('amount_total', rec.amount_total_w_vat, True),
                ('amount_tax', rec.amount_vat, False),
                ('amount_untaxed', rec.amount_total_wo_vat, True)
            ]
            body = invoice.check_invoice_amounts(amount_data)
            if body:
                self.custom_rollback(msg=body, rec=rec)
                continue

            # Force partner data and open the invoice and write post data ----------------------------------------
            try:
                invoice.partner_data_force()
                invoice.with_context(skip_attachments=True).action_invoice_open()
            except Exception as e:
                self.custom_rollback(msg=e.args[0], rec=rec)
                continue

            # Post create writes --------------------------------------------------------------------------------
            rec.write({'state': 'created', 'invoice_id': invoice.id})
            rec.nsoft_purchase_invoice_line_ids.write({'state': 'created'})

            # Check if purchase invoice is paid. Ceo employee is always used as the user
            # Since nSoft does not store this information
            if rec.payment_mode == 'own_account':
                invoice.update_payment_details(rec.payment_mode, ceo_employee)

            # TODO: This part is currently disabled (and False added)
            # TODO: either will be re-enabled or removed
            elif rec.payment_mode == 'company_cash' and False:
                wizard_vals = {
                    'journal_id': cash_journal.id,
                    'cashier_id': ceo_employee.id,
                    'currency_id': invoice.currency_id.id,
                    'amount': invoice.residual,
                    'payment_date': invoice.operacijos_data
                }
                # Invoice passed in the context, since that's how the wizard behaves
                payment_wizard = self.env['register.payment'].with_context(invoice_id=invoice.id).create(wizard_vals)
                payment_wizard.post()
            self.env.cr.commit()

    # Misc methods ---------------------------------------------------------------------------------------

    def custom_rollback(self, msg, rec):
        """
        Rollback current transaction, post message to the object and commit
        :return: None
        """
        self.env.cr.rollback()
        body = _('Nepavyko sukurti sąskaitos, sisteminė klaida: %s') % str(msg)
        self.post_message(
            ext_invoice=rec, i_body=body, state='failed', lines=rec.nsoft_purchase_invoice_line_ids)
        self.env.cr.commit()

    def post_message(self, i_body=str(), state=None, lines=None, ext_invoice=None):
        """
        Post message to nsoft.purchase.invoice and write state related lines
        :param i_body: nsoft.purchase.invoice text to be posted
        :param state: nsoft object state
        :param lines: related invoice lines
        :param ext_invoice: nsoft.purchase.invoice
        :return: None
        """
        if lines is None:
            lines = self.env['nsoft.purchase.invoice.line']
        if ext_invoice is None:
            ext_invoice = self.env['nsoft.purchase.invoice']
        if lines:
            if state:
                lines.write({'state': state})
        if ext_invoice:
            if state:
                ext_invoice.state = state
            ext_invoice.message_post(body=i_body)


NsoftPurchaseInvoice()
