# -*- encoding: utf-8 -*-
from odoo import models, fields, _, api, exceptions


class CashReceipt(models.Model):

    _name = 'cash.receipt'
    _inherit = ['mail.thread']
    _order = 'payment_date DESC'
    _default_field_sequence = 100

    def default_cashier_id(self):
        cashier = self.env.user.employee_ids
        return cashier[0].id if cashier else False

    def default_journal_id(self):
        return self.env.user.company_id.cash_receipt_journal_id

    cashier_id = fields.Many2one('hr.employee', string='Pinigus priimantis asmuo', required=True, readonly=True,
                                 states={'draft': [('readonly', False)]}, default=default_cashier_id,
                                 track_visibility='onchange')
    partner_id = fields.Many2one('res.partner', required=True, string='Partneris')
    amount = fields.Monetary(string='Suma', required=True, track_visibility='onchange')
    payment_date = fields.Date(string='Payment Date', default=fields.Date.context_today, required=True, copy=False,
                               track_visibility='onchange', lt_string='Mokėjimo data')
    journal_id = fields.Many2one('account.journal', string='Payment Journal', required=True, lt_string='Mokėjimo žurnalas',
                                 domain=[('type', 'in', ('bank', 'cash'))], default=default_journal_id)
    destination_account_id = fields.Many2one('account.account', compute='_compute_destination_account_id',
                                             readonly=True)
    force_destination_account_id = fields.Many2one('account.account', string='Priverstinė darbuotojo DK sąskaita',
                                                   readonly=True, states={'draft': [('readonly', False)]})
    source_account_id = fields.Many2one('account.account', compute='_compute_source_account_id', readonly=True)
    force_source_account_id = fields.Many2one('account.account', string='Priverstinė partnerio DK sąskaita',
                                              readonly=True, states={'draft': [('readonly', False)]})

    check_number = fields.Integer(string='Check Number', readonly=True, copy=False,
                                  help="The selected journal is configured to print check numbers. If your pre-printed check paper already has numbers "
                                       "or if the current numbering is wrong, you can change it in the journal configuration page.")

    company_id = fields.Many2one('res.company', related='journal_id.company_id', string='Įmonė', lt_string='Įmonė', readonly=True, store=True)

    name = fields.Char(readonly=True, string='Pavadinimas', copy=False, default=_('Juodraštis'))  # The name is attributed upon post()
    state = fields.Selection([('draft', 'Juodraštis'), ('posted', 'Patvirtintas')],
                             readonly=True, default='draft', copy=False, string='Status', lt_string='Būsena',
                             track_visibility='onchange')

    payment_type = fields.Selection([('inbound', 'Priėmimo'), ('outbound', 'Išdavimo')], required=True,
                                    string='Payment Method Type')
    move_name = fields.Char(string='Journal Entry Name', readonly=True,
                            default=False, copy=False,
                            help="Technical field holding the number given to the journal entry, automatically set when the statement line is reconciled then stored to set the same number again if the line is cancelled, set to draft and re-processed again.")

    invoice_ids = fields.Many2many('account.invoice', 'account_invoice_receipt_rel', 'receipt_id', 'invoice_id',
                                   string='Invoices', lt_string='Sąskaitos', copy=False, readonly=True)
    has_invoices = fields.Boolean(compute="_get_has_invoices", help="Technical field used for usability purposes")

    move_line_ids = fields.One2many('account.move.line', 'receipt_id', readonly=True, copy=False, ondelete='restrict')

    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                  default=lambda self: self.env.user.company_id.currency_id)
    communication = fields.Char(string='Memo')

    @api.multi
    def print_receipt(self):
        self.ensure_one()
        return self.env['report'].get_action(self, 'l10n_lt.report_pinigu_kvitas_template')

    @api.one
    @api.depends('invoice_ids')
    def _get_has_invoices(self):
        self.has_invoices = bool(self.invoice_ids)

    @api.multi
    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if not rec.amount > 0.0:
                raise exceptions.ValidationError(_('Suma privalo būti teigiamas skaičius.'))

    def _compute_total_invoices_amount(self):
        """ Compute the sum of the residual of invoices, expressed in the payment currency """
        payment_currency = self.currency_id or self.journal_id.currency_id or self.journal_id.company_id.currency_id
        invoices = self._get_invoices()

        if all(inv.currency_id == payment_currency for inv in invoices):
            total = sum(invoices.mapped('residual_signed'))
        else:
            total = 0
            for inv in invoices:
                if inv.company_currency_id != payment_currency:
                    total += inv.company_currency_id.with_context(date=self.payment_date).compute(
                        inv.residual_company_signed, payment_currency)
                else:
                    total += inv.residual_company_signed
        return abs(total)


    @api.model
    def default_get(self, fields):
        rec = super(CashReceipt, self).default_get(fields)
        invoice_defaults = self.resolve_2many_commands('invoice_ids', rec.get('invoice_ids'))
        if invoice_defaults and len(invoice_defaults) == 1:
            invoice = invoice_defaults[0]
            rec['communication'] = invoice['reference'] or invoice['name'] or invoice['number']
            rec['currency_id'] = invoice['currency_id'][0]
            rec['payment_type'] = invoice['type'] in ('out_invoice', 'in_refund') and 'inbound' or 'outbound'
            rec['partner_id'] = invoice['partner_id'][0]
            rec['amount'] = invoice['residual']
        return rec

    def _get_invoices(self):
        return self.invoice_ids

    @api.multi
    def button_journal_entries(self):
        return {
            'name': _('Journal Items'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move.line',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('receipt_id', 'in', self.ids)],
        }

    @api.multi
    def button_invoices(self):
        return {
            'name': _('Paid Invoices'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.invoice',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', [x.id for x in self.invoice_ids])],
        }

    @api.multi
    def unreconcile(self):
        """ Set back the payments in 'posted' or 'sent' state, without deleting the journal entries.
            Called when cancelling a bank statement line linked to a pre-registered payment.
        """
        for rec in self:
            rec.write({'state': 'posted'})

    @api.multi
    def cancel(self):
        self.check_access_rights('write')
        for rec in self:
            for move in rec.sudo().move_line_ids.mapped('move_id'):
                if rec.invoice_ids:
                    move.line_ids.remove_move_reconcile()
                move.button_cancel()
                move.unlink()
            rec.state = 'draft'

    @api.multi
    def unlink(self):
        if any(bool(rec.move_line_ids) for rec in self):
            raise exceptions.UserError(_("Negalite ištrinti patvirtintų įrašų."))
        if any(bool(rec.move_name) for rec in self):
            raise exceptions.UserError(_("Negalite ištrinti anksčiau patvirtintų įrašų. Pašalinkite kvito numerį."))
        return super(CashReceipt, self).unlink()

    @api.multi
    def post(self):
        """ Create the journal items for the payment and update the payment's state to 'posted'.
            A journal entry is created containing an item in the source liquidity account (selected journal's default_debit or default_credit)
            and another in the destination reconciliable account (see _compute_destination_account_id).
            If invoice_ids is not empty, there will be one reconciliable move line per invoice to reconcile with.
            If the payment is a transfer, a second journal entry is created in the destination journal to receive money from the transfer account.
        """
        for rec in self:
            if rec.state != 'draft':
                raise exceptions.UserError(_("Kvitas gali būti patvirtintas tik juodraščio būsenoje"))
            if any(inv.state != 'open' for inv in rec.invoice_ids):
                raise exceptions.ValidationError(_("Kvitas negali būti patvirtintas, nes susijusi sąskaita faktūra nėra patvirtinta arba jau apmokėta"))
            if not rec.move_name:
                if rec.journal_id.sequence_id:
                    sequence_code = rec.journal_id.sequence_id.code
                else:
                    sequence_code = 'cash.receipt.inbound' if rec.payment_type == 'inbound' else 'cash.receipt.outbound'
                rec.name = self.env['ir.sequence'].with_context(ir_sequence_date=rec.payment_date).next_by_code(
                    sequence_code)

            # Create the journal entry
            amount = rec.amount * (-1 if self.payment_type == 'inbound' else 1)
            move = rec.sudo()._create_payment_entry(amount)

            # In case of a transfer, the first journal entry created debited the source liquidity account and credited
            # the transfer account. Now we debit the transfer account and credit the destination liquidity account.
            rec.write({'state': 'posted', 'move_name': move.name})

    def _create_payment_entry(self, amount):
        """ Create a journal entry corresponding to a payment, if the payment references invoice(s) they are reconciled.
            Return the journal entry.
        """
        aml_obj = self.env['account.move.line'].with_context(check_move_validity=False)
        invoice_currency = False
        if self.invoice_ids and all([x.currency_id == self.invoice_ids[0].currency_id for x in self.invoice_ids]):
            # if all the invoices selected share the same currency, record the paiement in that currency too
            invoice_currency = self.invoice_ids[0].currency_id
        debit, credit, amount_currency, currency_id = aml_obj.with_context(
            date=self.payment_date).compute_amount_fields(amount, self.currency_id, self.company_id.currency_id,
                                                          invoice_currency)

        move = self.env['account.move'].create(self._get_move_vals())

        # Write line corresponding to invoice payment
        counterpart_aml_dict = self._get_shared_move_line_vals(debit, credit, amount_currency, move.id, False)
        counterpart_aml_dict.update(self._get_counterpart_move_line_vals(self.invoice_ids))
        counterpart_aml_dict.update({'currency_id': currency_id})
        counterpart_aml = aml_obj.create(counterpart_aml_dict)

        self.invoice_ids.register_payment(counterpart_aml)

        # Write counterpart lines
        if not self.currency_id != self.company_id.currency_id:
            amount_currency = 0
        liquidity_aml_dict = self._get_shared_move_line_vals(credit, debit, -amount_currency, move.id, False)
        liquidity_aml_dict.update(self._get_liquidity_move_line_vals(-amount))
        aml_obj.create(liquidity_aml_dict)

        move.post()
        return move

    @api.one
    @api.depends('invoice_ids', 'payment_type', 'partner_id', 'force_destination_account_id')
    def _compute_source_account_id(self):  # todo
        if self.payment_type == 'inbound':
            if self.force_source_account_id:
                self.source_account_id = self.force_source_account_id.id
            elif self.partner_id.is_employee:
                self.source_account_id = self.sudo().company_id.cash_advance_account_id.id
            else:
                self.source_account_id = self.partner_id.property_account_receivable_id.id
        else:
            if self.force_source_account_id:
                self.source_account_id = self.force_source_account_id.id
            elif self.invoice_ids:
                self.source_account_id = self.invoice_ids[0].account_id.id
            else:
                self.source_account_id = self.sudo().company_id.cash_advance_account_id.id

    @api.one
    @api.depends('invoice_ids', 'payment_type', 'partner_id', 'force_destination_account_id')
    def _compute_destination_account_id(self):  # todo
        if self.payment_type == 'inbound':
            if self.force_destination_account_id:
                self.destination_account_id = self.force_destination_account_id.id
            # elif self.invoice_ids:
            #     self.destination_account_id = self.invoice_ids[0].account_id.id
            else:
                self.destination_account_id = self.sudo().company_id.cash_advance_account_id.id
        else:
            if self.force_destination_account_id:
                self.destination_account_id = self.force_destination_account_id.id
            else:
                self.destination_account_id = self.sudo().company_id.cash_advance_account_id.id

    def _get_move_vals(self, journal=None):
        """ Return dict to create the payment move
        """
        journal = journal or self.journal_id
        if not journal.sequence_id:
            raise exceptions.UserError(_('Configuration Error !') + _('The journal %s does not have a sequence, please specify one.') % journal.name)
        if not journal.sequence_id.active:
            raise exceptions.UserError(_('Configuration Error !') + _('The sequence of journal %s is deactivated.') % journal.name)
        name = self.move_name or self.cash_receipt_name or journal.with_context(ir_sequence_date=self.payment_date).sequence_id.next_by_id()
        return {
            'name': name,
            'date': self.payment_date,
            'ref': self.communication or '',
            'company_id': self.company_id.id,
            'journal_id': journal.id,
        }

    def _get_shared_move_line_vals(self, debit, credit, amount_currency, move_id, invoice_id=False):
        """ Returns values common to both move lines (except for debit, credit and amount_currency which are reversed)
        """
        return {
            # 'partner_id': self.partner_d.id,
            'invoice_id': invoice_id and invoice_id.id or False,
            'move_id': move_id,
            'debit': debit,
            'credit': credit,
            'amount_currency': amount_currency or False,
        }

    def _get_counterpart_move_line_vals(self, invoice=False):
        name = self.name or _('Payment')
        if invoice:
            name += ': '
            for inv in invoice:
                if inv.move_id:
                    name += inv.number + ', '
            name = name[:len(name)-2]
        return {
            'name': name,
            'account_id': self.source_account_id.id,
            'journal_id': self.journal_id.id,
            'currency_id': self.currency_id != self.company_id.currency_id and self.currency_id.id or False,
            'receipt_id': self.id,
            'partner_id': self.partner_id.id,
        }

    def _get_liquidity_move_line_vals(self, amount):
        name = self.name
        account_id = self.destination_account_id.id
        if not account_id:
            raise exceptions.UserError(_('Nerasta sąskaita'))
        vals = {
            'name': name,
            'account_id': account_id,
            'receipt_id': self.id,
            'journal_id': self.journal_id.id,
            'currency_id': self.currency_id != self.company_id.currency_id and self.currency_id.id or False,
            'partner_id': self.cashier_id.address_home_id.id,
        }
        # If the journal has a currency specified, the journal item need to be expressed in this currency
        if self.journal_id.currency_id and self.currency_id != self.journal_id.currency_id:
            amount = self.currency_id.with_context(date=self.payment_date).compute(amount, self.journal_id.currency_id)
            debit, credit, amount_currency, dummy = self.env['account.move.line'].with_context(date=self.payment_date).compute_amount_fields(amount, self.journal_id.currency_id, self.company_id.currency_id)
            vals.update({
                'amount_currency': amount_currency,
                'currency_id': self.journal_id.currency_id.id,
            })
        return vals
