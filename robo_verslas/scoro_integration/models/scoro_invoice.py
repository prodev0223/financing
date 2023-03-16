# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, tools

allowed_calc_error = 0.01


class ScoroInvoice(models.Model):
    _name = 'scoro.invoice'
    _inherit = ['mail.thread']

    # Scoro fields
    external_number = fields.Integer(string='Išorinis numeris', required=True)
    internal_number = fields.Char(compute='_internal_number')

    external_invoice_ref = fields.Char(string='Sąskaitos numeris')
    external_id = fields.Integer(string='Išorinis ID')

    payment_type = fields.Selection([('banktransfer', 'Pavedimu'),
                                     ('cash', 'Grynais'),
                                     ('cardpayment', 'Kortele'),
                                     ('credit', 'Kreditas'),
                                     ('barter', 'Užstatas')], string='Mokėjimo tipas',
                                    inverse='_inverse_payment_type')
    fine_percentage = fields.Char(string='Skolos procentas per dieną')

    # Simulated one2many separated by comma
    credited_invoices_ids_char = fields.Char(string='Kredituojamų sąskaitų ID',
                                             inverse='_inverse_credited_invoices_ids_char')

    company_name = fields.Char(string='Susijusi kompanija')
    person_name = fields.Char(string='Susijęs kontaktinis asmuo')
    project_name = fields.Char(string='Susijęs projekto pavadinimas')
    paid_sum = fields.Float(string='Sumokėta suma')
    receivable_sum = fields.Float(string='Gautina suma')

    # Exchange rate when invoice is issued. Indicates the invoice currency against the base currency.
    # For example if the base currency is EUR and invoice currency is GBP then 1 GBP = X EUR.
    currency_rate = fields.Float(string='Valiutos kursas sąskaitos Datai')
    # Only available in view_mode i.e. single invoice fetching

    real_estate_id = fields.Integer(string='Nekilnojamo turto ID')
    discount = fields.Float(string='Nuolaida')
    sum_wo_vat = fields.Float(string='Suma be PVM')  # after discounts
    vat_sum = fields.Float(string='PVM Suma')
    vat_rate = fields.Float(string='PVM tarifas')  # If not empty, then all lines have the same VAT
    vat_code_id = fields.Integer(string='PVM ID')
    invoice_based_tax = fields.Boolean(string='Bendri mokesčiai eilutėms', readonly=True)
    company_id = fields.Integer(string='Kliento ID', inverse='_inverse_company_id', track_visibility='onchange')
    person_id = fields.Integer(string='Kontaktinio asmens ID')
    company_address_id = fields.Integer(string='Kompanijos adreso ID')
    interested_party_id = fields.Integer(string='Suinteresuotos šalies ID')
    interested_party_address_id = fields.Integer(string='Suinteresuotos šalies adreso ID')
    project_id = fields.Integer(string='Projekto ID')
    currency_code = fields.Char(string='Valiutos kodas')
    date_invoice = fields.Date(string='Sąskaitos data')
    date_due = fields.Date(string='Mokėjimo terminas')

    paid_state = fields.Selection([('paid', 'Sumokėta'),
                                   ('unpaid', 'Nesumokėta')], string='Mokėjimo statusas')
    description = fields.Text(string='Sąskaitos aprašymas')
    is_deleted_scoro = fields.Boolean(string='Sąskaita ištrinta Scoro sistemoje')
    deleted_date = fields.Date(string='Sąskaita ištrinimo data')

    # System fields
    scoro_invoice_line_ids = fields.One2many('scoro.invoice.line', 'scoro_invoice_id', string='Scoro sąskaitos eilutės')
    credited_by_id = fields.Many2one('scoro.invoice', string='Kredituojanti sąskaita')
    scoro_credit_invoice_ids = fields.One2many('scoro.invoice', 'credited_by_id',
                                               string='Susijusios kredituojamos sąskaitos')
    pay_type_id = fields.Many2one('scoro.payment.type', string='Mokėjimo tipas')
    invoice_id = fields.Many2one('account.invoice', string='Sisteminė sąskaita')
    move_id = fields.Many2one('account.move', string='Mokėjimo įrašas')
    partner_id = fields.Many2one('res.partner', string='Susijęs partneris', track_visibility='onchange')
    state = fields.Selection([('imported', 'Sąskaita importuota'),
                              ('created', 'Sąskaita sukurta sistemoje'),
                              ('failed', 'Klaida kuriant sąskaitą')],
                             string='Būsena', default='imported', track_visibility='onchange')

    system_move_state = fields.Selection([('no_action', 'Nėra mokėjimo duomenų'),
                                          ('waiting', 'Mokėjimo įrašas nesukurtas'),
                                          ('created', 'Mokėjimo įrašas sukurtas'),
                                          ('reconciled', 'Mokėjimo įrašas sukurtas ir sudengtas'),
                                          ('failed', 'Nepavyko sukurti mokėjimo įrašo')],
                                         string='Mokėjimo būsena', default='no_action', track_visibility='onchange')
    invoice_type = fields.Char(compute='_invoice_type')

    @api.one
    @api.depends('external_number')
    def _internal_number(self):
        config_obj = self.sudo().env['ir.config_parameter']
        prefix = config_obj.get_param('scoro_invoice_number_prefix')
        length = config_obj.get_param('scoro_invoice_number_length')
        if self.external_number:
            external_num_str = str(self.external_number)
            if length:
                try:
                    length = int(length)
                    external_num_str = external_num_str.zfill(length)
                except ValueError:
                    pass
            if prefix and prefix.strip(' '):
                external_num_str = '{}-{}'.format(prefix, external_num_str)
            self.internal_number = external_num_str

    @api.one
    def _inverse_payment_type(self):
        if self.payment_type:
            self.pay_type_id = self.env['scoro.payment.type'].search([('internal_code', '=', self.payment_type)])

    @api.one
    @api.depends('credited_invoices_ids_char')
    def _invoice_type(self):
        if self.credited_invoices_ids_char:
            self.invoice_type = 'out_refund'
        else:
            self.invoice_type = 'out_invoice'

    @api.multi
    def name_get(self):
        return [(rec.id, _('Sąskaita ') + str(rec.external_number)) for rec in self]

    @api.one
    def _inverse_company_id(self):
        if self.company_id:
            partner_id = self.env['scoro.data.fetcher'].fetch_create_partner_single(self.company_id)
            if partner_id:
                self.partner_id = partner_id

    @api.one
    def _inverse_credited_invoices_ids_char(self):
        if self.credited_invoices_ids_char:
            scoro_invoice_ids = self.env['scoro.invoice']
            cred_ids = self.credited_invoices_ids_char.split(',')
            for cred_id in cred_ids:
                if cred_id:
                    try:
                        cred_id = int(cred_id)
                    except ValueError:
                        continue
                    scoro_invoice_ids |= self.env['scoro.invoice'].search([('external_id', '=', cred_id)])
            self.scoro_credit_invoice_ids = [(6, 0, scoro_invoice_ids.ids)]

    @api.multi
    def validator(self):

        """Validate whether scoro.invoice has all the required/correct values for account.invoice creation"""

        filtered_invoices = self.env['scoro.invoice']
        scoro_invoice_line_ids = self.mapped('scoro_invoice_line_ids')
        self._inverse_payment_type()
        self._invoice_type()
        self._inverse_company_id()
        scoro_invoice_line_ids.recompute_fields()
        self.env.cr.commit()
        filtered_records = self.filtered(
            lambda x: not x.invoice_id and x.state in ['imported', 'failed']).process_previous_invoice_version()
        for invoice_id in filtered_records:
            body = str()
            if not invoice_id.partner_id:
                body += _('Klaida kuriant sąskaitą, nerastas susijęs partneris!\n')
            if not invoice_id.pay_type_id:
                body += _('Klaida kuriant sąskaitą, produktas neegzistuoja sistemoje!\n')
            if not invoice_id.scoro_invoice_line_ids:
                body += _('Klaida kuriant sąskaitą, sąskaita neturi eilučių!\n')
            for line in invoice_id.scoro_invoice_line_ids:
                change_line_state = False
                if not line.tax_id:
                    body += _('Klaida kuriant sąskaitą, sąskaitos eilutė %s '
                              'neturi nurodytų mokesčių!\n' % str(line.external_id))
                    change_line_state = True
                if not line.product_id and self.env.user.company_id.scoro_stock_accounting:
                    body += _('Klaida kuriant sąskaitą, sąskaitos eilutė %s '
                              'neturi sisteminio produkto!\n' % str(line.external_id))
                    change_line_state = True
                if change_line_state:
                    line.write({'state': 'failed'})
            if body:
                self.post_message(invoice_ids=invoice_id, inv_body=body, state='failed')
            else:
                filtered_invoices += invoice_id
        self.env.cr.commit()
        return filtered_invoices

    @api.multi
    def create_invoices_prep(self):

        """Prepare scoro.invoice for account.invoice creation by sending them to validator"""

        do_validate = self._context.get('validate', True)
        invoice_ids = self.filtered(
            lambda x: x.external_id and not x.invoice_id)
        if do_validate:
            invoice_ids = invoice_ids.validator()
        invoice_ids.create_invoices()

    @api.multi
    def create_invoices(self):

        """Create account.invoice records from scoro invoice. If the invoice is paid, proceed to create account.move"""

        def get_amount_depends_vals(amt_depends):
            """returns invoice line amount depends vals with passed amount"""
            return {
                'amount_depends': amt_depends,
                'price_subtotal_save_force_value': amt_depends,
                'price_subtotal_make_force_step': True,
            }

        for scoro_invoice in self.filtered(lambda x: not x.invoice_id):
            invoice_obj = self.env['account.invoice'].sudo()
            account_obj = self.env['account.account'].sudo()

            default_journal = self.env['account.journal'].search([('type', '=', 'sale')], limit=1)
            default_location = self.env['stock.location'].search([('usage', '=', 'internal')],
                                                                 order='create_date desc', limit=1)
            delivery_wizard = self.env['invoice.delivery.wizard'].sudo()
            account_id = account_obj.search([('code', '=', '2410')])
            partner_id = scoro_invoice.partner_id
            invoice_lines = []
            currency_id = self.env['res.currency'].search([('name', '=', scoro_invoice.currency_code)])
            invoice_values = {
                'external_invoice': True,
                'imported_api': True,
                'account_id': account_id.id,
                'partner_id': partner_id.id,
                'journal_id': default_journal.id,
                'invoice_line_ids': invoice_lines,
                'type': scoro_invoice.invoice_type,
                'date_invoice': scoro_invoice.date_invoice,
                'date_due': scoro_invoice.date_due,
                'force_dates': True,
                'price_include_selection': 'exc',
                'move_name': scoro_invoice.internal_number,
                'number': scoro_invoice.internal_number,
                'currency_id': currency_id.id,
                'payment_term_id': False
            }
            sum_wo_vat = scoro_invoice.sum_wo_vat
            vat_sum = scoro_invoice.vat_sum
            for line in scoro_invoice.scoro_invoice_line_ids.filtered(
                    lambda x: not tools.float_is_zero(x.quantity, precision_digits=2)):
                inv_line = {
                    'name': line.line_name or 'Paslauga',
                    'quantity': line.quantity,
                    'price_unit': line.price_unit,
                    'discount': line.discount or scoro_invoice.discount,
                    'invoice_line_tax_ids': [(6, 0, line.tax_id.ids)],
                    'scoro_line_id': line.id
                }
                # Compare two amounts, total sum received from Scoro
                # and quantity * price unit. If they differ, update amount depends
                calculated_amount = line.quantity * line.price_unit
                factual_diff = line.sum_wo_vat - calculated_amount
                if not tools.float_is_zero(factual_diff, precision_digits=3):
                    new_amount = tools.float_round(calculated_amount + factual_diff, precision_digits=3)
                    inv_line.update(get_amount_depends_vals(new_amount))

                if line.product_id:
                    product_account = line.product_id.get_product_income_account(return_default=True)
                    inv_line.update({
                        'product_id': line.product_id.id,
                        'uom_id': line.product_id.product_tmpl_id.uom_id.id,
                        'account_id': product_account.id,
                    })
                else:
                    product_account = account_obj.search(
                        [('code', '=', '5001'), ('company_id', '=', self.env.user.company_id.id)], limit=1)
                    inv_line.update({
                        'account_id': product_account.id,
                    })
                invoice_lines.append((0, 0, inv_line))

            try:
                invoice_id = invoice_obj.create(invoice_values)
            except Exception as e:
                self.env.cr.rollback()
                body = _('Nepavyko sukurti sąskaitos, sisteminė klaida %s') % e
                self.post_message(invoice_ids=scoro_invoice, inv_body=body, state='failed')
                self.env.cr.commit()
                continue
            try:
                invoice_id.partner_data_force()
                invoice_id.action_invoice_open()
            except Exception as e:
                self.env.cr.rollback()
                body = _('Nepavyko patvirtinti sąskaitos, sisteminė klaida %s') % e
                self.post_message(invoice_ids=scoro_invoice, inv_body=body, state='failed')
                self.env.cr.commit()
                continue

            body = str()
            # Check the difference between passed total amount and invoice untaxed amount
            sum_difference = tools.float_round(sum_wo_vat - invoice_id.amount_untaxed, precision_digits=2)
            if not tools.float_is_zero(sum_difference, precision_digits=2):
                # Its fine to check sum difference with simple < here, since it's float rounded ->
                # If invoice contains discount and we have a difference less than 1, re-force amount depends
                # Calculations in this block differ from previous amount depends assigning, since here
                # we do not have specific line with differences, we just write diff to first line (more rare case)
                if not tools.float_is_zero(scoro_invoice.discount, precision_digits=2) and abs(sum_difference) < 1.0:
                    inv_line = invoice_id.invoice_line_ids[0]
                    new_amount = tools.float_round(
                        inv_line.amount_depends + sum_difference, precision_digits=2
                    )
                    # Write new values to the invoice line
                    inv_line.write(get_amount_depends_vals(new_amount))
                    # Trigger amount depends re-computations
                    inv_line.with_context(direct_trigger_amount_depends=True).onchange_amount_depends()
                else:
                    if tools.float_compare(sum_difference, allowed_calc_error, precision_digits=2) > 0:
                        body += _('Sąskaitos suma be mokesčių nesutampa su paskaičiuota suma (%s != %s).\n'
                                  ) % (sum_wo_vat, invoice_id.amount_untaxed)
            if body:
                self.env.cr.rollback()
                self.post_message(invoice_ids=scoro_invoice, inv_body=body, state='failed')
                self.env.cr.commit()
                continue

            if tools.float_compare(vat_sum, abs(invoice_id.amount_tax), precision_digits=2):
                diff = abs(invoice_id.amount_tax - vat_sum)
                if tools.float_compare(diff, allowed_calc_error, precision_digits=2) > 0:
                    body += _('Sąskaitos suma be mokesčių nesutampa su paskaičiuota suma (%s != %s).\n'
                              ) % (vat_sum, invoice_id.amount_tax)
            if body:
                self.env.cr.rollback()
                self.post_message(invoice_ids=scoro_invoice, inv_body=body, state='failed')
                self.env.cr.commit()
                continue

            rec = self.sudo().env['ir.module.module'].search([('name', '=', 'robo_stock')])
            if rec and rec.state in ['installed', 'to upgrade']:
                wizard_id = delivery_wizard.with_context(invoice_id=invoice_id.id).create(
                    {'location_id': default_location.id})
                wizard_id.create_delivery()
                if invoice_id.picking_id:
                    invoice_id.picking_id.action_assign()
                    if invoice_id.picking_id.state == 'assigned':
                        invoice_id.picking_id.do_transfer()
            scoro_invoice.write({'state': 'created', 'invoice_id': invoice_id.id})
            scoro_invoice.scoro_invoice_line_ids.write({'state': 'created'})
            self.env.cr.commit()
            scoro_invoice.create_account_move()

    @api.multi
    def unlink_system_invoice(self):
        """
        Cancels and unlinks system invoice/payments,
        that are related to scoro lines.
        scoro invoice and move states are reset
        to imported
        :return: None
        """
        self.ensure_one()

        # Cancel the invoice and reset numbers
        invoice = self.invoice_id
        invoice.action_invoice_cancel_draft()
        invoice.write({'move_name': False, 'number': False})

        # If robo stock is installed, and invoice has picking, create return
        robo_stock_installed = self.env['ir.module.module'].sudo().search_count(
            [('name', '=', 'robo_stock'), ('state', 'in', ['installed', 'to upgrade'])]
        )
        if robo_stock_installed:
            if invoice.picking_id and invoice.picking_id.state == 'done':
                picking_return = self.env['stock.return.picking'].sudo().with_context(
                    active_id=invoice.picking_id.id).create({'mistake_type': 'cancel', 'error': True})
                picking_return._create_returns()
            elif invoice.picking_id:
                invoice.picking_id.unlink()

        # Unlink the invoice
        invoice.unlink()
        # Write the states
        self.write({'state': 'imported'})
        self.scoro_invoice_line_ids.write({'state': 'imported'})

        # Check if move ID exists, unreconcile and unlink it
        if self.move_id:
            self.move_id.line_ids.remove_move_reconcile()
            self.move_id.button_cancel()
            self.move_id.unlink()
            # Force the state to waiting
            self.write({'system_move_state': 'waiting'})

    @api.multi
    def create_account_move(self):

        """Create account.move for account.invoice based on scoro.invoice paid sum"""

        self.ensure_one()
        if not tools.float_is_zero(self.paid_sum, precision_digits=2) and \
                not self.move_id and self.pay_type_id and self.pay_type_id.create_acc_entries and self.invoice_id:
            account = self.env['account.account'].search([('code', '=', '2410')])
            move_lines = []
            credit_line = {
                'name': 'Mokėjimas ' + str(self.external_number),
                'partner_id': self.partner_id.id,
                'account_id': account.id
            }
            debit_line = {
                'name': 'Mokėjimas ' + str(self.external_number),
                'partner_id': self.partner_id.id,
                'account_id':  self.pay_type_id.journal_id.default_credit_account_id.id
            }
            if self.currency_code != 'EUR':
                currency_id = self.env['res.currency'].search([('name', '=', self.currency_code)])
            else:
                currency_id = self.env['res.currency']

            if self.paid_sum > 0:
                if currency_id:
                    credit_line['currency_id'] = currency_id.id
                    credit_line['amount_currency'] = -self.paid_sum
                else:
                    credit_line['credit'] = self.paid_sum
                    credit_line['debit'] = 0.0
            else:
                if currency_id:
                    credit_line['currency_id'] = currency_id.id
                    credit_line['amount_currency'] = self.paid_sum
                else:
                    credit_line['debit'] = self.paid_sum
                    credit_line['credit'] = 0.0

            if self.paid_sum > 0:
                if currency_id:
                    debit_line['currency_id'] = currency_id.id
                    debit_line['amount_currency'] = self.paid_sum
                else:
                    debit_line['debit'] = self.paid_sum
                    debit_line['credit'] = 0.0
            else:
                if currency_id:
                    debit_line['currency_id'] = currency_id.id
                    debit_line['amount_currency'] = -self.paid_sum
                else:
                    debit_line['credit'] = self.paid_sum
                    debit_line['debit'] = 0.0

            move_lines.append((0, 0, credit_line))
            move_lines.append((0, 0, debit_line))
            move_vals = {
                'line_ids': move_lines,
                'journal_id': self.pay_type_id.journal_id.id,
                'date': self.date_invoice,
            }
            try:
                move_id = self.env['account.move'].create(move_vals)
                move_id.post()
                self.write({'move_id': move_id.id, 'system_move_state': 'created'})
            except Exception as e:
                self.env.cr.rollback()
                body = _('Nepavyko sukurti mokėjimo įrašo, sisteminė klaida: %s') % e.args[0]
                self.post_message(invoice_ids=self, inv_body=body)
                self.system_move_state = 'failed'
                self.env.cr.commit()
                return
            try:
                line_ids = move_id.line_ids.filtered(lambda r: r.account_id.id == self.invoice_id.account_id.id)
                line_ids |= self.invoice_id.move_id.line_ids.filtered(
                    lambda r: r.account_id.id == self.invoice_id.account_id.id)
                if len(line_ids) > 1:
                    line_ids.with_context(reconcile_v2=True).reconcile()
                self.system_move_state = 'reconciled'
            except Exception as e:
                self.env.cr.rollback()
                body = _('Nepavyko sudengti mokėjimo įrašo, sisteminė klaida: %s') % e.args[0]
                self.post_message(invoice_ids=self, inv_body=body)
                self.env.cr.commit()
                return
            self.env.cr.commit()

    @api.multi
    def process_previous_invoice_version(self):
        """
        Potential situation -- Invoice is created in Scoro system:
        Number - IN55, Ext ID - 789
        Later that invoice is deleted, and new one is created:
        Number - IN55, Ext ID - 999
        The first one is already in Robo, and we get the second invoice with the same number but
        different ext ID, thus we delete initial account.invoice record together with scoro.invoice record
        and create the new invoice
        :return: filtered scoro.invoice record set
        """
        filtered_records = self.env['scoro.invoice']
        for rec in self:
            scoro_invoice = self.search([('external_number', '=', rec.external_number), ('id', '!=', rec.id)])
            if scoro_invoice:
                account_invoice = scoro_invoice.invoice_id
                try:
                    account_invoice.action_invoice_cancel_draft()
                    account_invoice.write({'move_name': False, 'number': False})
                    account_invoice.unlink()
                    scoro_invoice.scoro_invoice_line_ids.unlink()
                    scoro_invoice.unlink()
                    filtered_records |= rec
                except Exception as exc:
                    self.env.cr.rollback()
                    body = 'Gauta Scoro sąskaita su numeriu %s. Sąskaita su šiuo numeriu jau egzistuoja ' \
                           'ROBO sistemoje, tačiau ji buvo ištrinta Scoro sistemoje ir perkurta naujai. ' \
                           'Nepavyko automatiškai atšaukti senos sąskaitos, ' \
                           'klaidos pranešimas %s' % (rec.internal_number, exc.args[0])
                    self.env['scoro.data.fetcher'].inform_accountant(
                        report=body, subject='Scoro // Sąskaitos Dublikatas')
            else:
                filtered_records |= rec
        return filtered_records

    @api.model
    def post_message(self, invoice_ids=None, inv_body='', state=''):
        invoice_ids = self.env['scoro.invoice'] if not invoice_ids else invoice_ids
        send = {
            'body': inv_body,
        }
        for invoice_id in invoice_ids:
            invoice_id.message_post(**send)
        invoice_ids.write({'state': state})


ScoroInvoice()
