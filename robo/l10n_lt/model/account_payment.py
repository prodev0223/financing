# -*- encoding: utf-8 -*-
from odoo import models, fields, _, api, exceptions, tools
from odoo.tools import amount_to_text_en
from odoo.tools import num2words as n2w
from datetime import datetime


class AccountPayment(models.Model):

    _name = 'account.payment'
    _inherit = ['account.payment', 'mail.thread']

    @api.model
    def default_get(self, field_list):
        res = super(AccountPayment, self).default_get(field_list)
        res['name'] = _('Nepatvirtinta operacija')
        if 'journal_id' not in res or not res['journal_id']:
            journal_id = self.env['account.journal'].search([('type', '=', 'cash'), ('code', '=like', 'CSH%')], limit=1)
            res['journal_id'] = journal_id.id if journal_id else False
        if self._context.get('cash_reg_view') and ('partner_id' not in res or not res['partner_id']):
            res['partner_id'] = self.env.user.partner_id.id
        return res

    def default_cashier_id(self):
        if self._context.get('cash_reg_view'):
            return self.env.user.employee_ids[0].id if self.env.user.employee_ids else False
        else:
            cashier_id = self.env.user.company_id.sudo().cashier_id
            return cashier_id.id if cashier_id else False

    cashier_id = fields.Many2one('hr.employee', string='Kasininkas', readonly=True,  default=default_cashier_id,
                                 states={'draft': [('readonly', False)]}, track_visibility='onchange')
    state = fields.Selection(selection_add=[('canceled', 'Anuliuota')],
                             track_visibility='onchange')
    payment_type = fields.Selection(selection_add=[('advance', 'Per avansinės apyskaitos asmenį')],
                                    track_visibility='onchange')
    payment_date = fields.Date(track_visibility='onchange')
    destination_account_id = fields.Many2one('account.account', compute='_compute_destination_account_id',
                                             readonly=True)
    force_destination_account_id = fields.Many2one('account.account', string='Priverstinė DK sąskaita',
                                                   readonly=True, states={'draft': [('readonly', False)]})
    advance_payment = fields.Boolean(string='Advance payment', default=False, readonly=True)
    signed_employee_id = fields.Many2one('hr.employee', string='Vadovas arba įgaliotas asmuo')

    show_future_payment_date_banner = fields.Boolean(compute='_compute_show_future_payment_date_banner')

    # ROBO: overridden method
    @api.onchange('payment_type')
    def _onchange_payment_type(self):
        if not self.invoice_ids:
            # Set default partner type for the payment type
            if self.payment_type == 'inbound':
                self.partner_type = 'customer'
            elif self.payment_type == 'outbound':
                self.partner_type = 'supplier'
        # Set payment method domain
        res = self._onchange_journal()
        if not res.get('domain', {}):
            res['domain'] = {}
        res['domain']['journal_id'] = self.payment_type == 'inbound' and [('at_least_one_inbound', '=', True)] or [
            ('at_least_one_outbound', '=', True)]
        res['domain']['journal_id'].append(('type', '=', 'cash'))
        if self._context.get('cash_reg_view'):
            res['domain']['journal_id'] += [('code', '!=', 'KVIT'), ('code', 'not like', 'CSH')]
        return res

    # Method used in template render
    def _convert_sum_to_words(self, amount, lang='lt', iso='EUR'):
        lang = lang.upper()
        if lang and '_' in lang:
            lang = lang.split('_')[0]
        lang_command = 'lang_' + lang
        if hasattr(n2w, lang_command):
            lang_module = getattr(n2w, lang_command)
            if hasattr(lang_module, 'to_currency'):
                return lang_module.to_currency(amount, iso)
        if lang in ['lt', 'lt_LT']:
            try:
                return n2w.lang_LT.to_currency(amount, iso)
            except:
                return ''
        else:
            return amount_to_text_en.amount_to_text(amount, 'en', iso)

    # FIXME: This method seems to require a rewrite
    @api.one
    @api.depends('invoice_ids', 'payment_type', 'partner_type', 'partner_id', 'force_destination_account_id')
    def _compute_destination_account_id(self):
        if self.invoice_ids:
            self.destination_account_id = self.invoice_ids[0].account_id.id
        elif self.payment_type == 'transfer':
            if not self.company_id.transfer_account_id.id:
                raise exceptions.UserError(_('Nenurodyta pinigų perkėlimo DK sąskaita.'))
            self.destination_account_id = self.company_id.transfer_account_id.id
        elif self.partner_id:
            if self.sudo().env['hr.employee'].search_count([('advance_accountancy_partner_id', '=', self.partner_id.id)]):
                #FIXME: updating another field in a compute function. Should not happen
                self.advance_payment = True
            elif self.partner_type == 'customer':
                self.destination_account_id = self.partner_id.property_account_receivable_id.id
            else:
                self.destination_account_id = self.partner_id.property_account_payable_id.id
        if self.advance_payment: #FIXME: advance_payment is not in the 'depends' statement
            self.destination_account_id = self.company_id.sudo().cash_advance_account_id.id
        if self.force_destination_account_id:
            self.destination_account_id = self.force_destination_account_id.id


    @api.multi
    @api.depends('name', 'state')
    def _compute_display_name(self):
        """
        Override display_name method.
        If payment is canceled, append a signifier to the display name
        :return: None
        """
        for rec in self:
            display_name = rec.name
            if rec.state == 'canceled':
                display_name = _('{} (Anuliuota)').format(display_name)
            rec.display_name = display_name

    @api.multi
    @api.depends('payment_date')
    def _compute_show_future_payment_date_banner(self):
        current_date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        for rec in self:
            rec.show_future_payment_date_banner = rec.payment_date > current_date

    @api.multi
    @api.constrains('name')
    def _check_name(self):
        """
        Constraints //
        Name must be unique for account payments of cash journal.
        :return: None
        """
        for rec in self.filtered(
                lambda x: x.journal_id.type == 'cash' and x.journal_id.code.startswith('CSH') and x.state != 'draft'):
            if self.env['account.payment'].search_count([('name', '=', rec.name), ('id', '!=', rec.id)]):
                raise exceptions.ValidationError(_('Kasos operacijos turi turėti unikalų numerį!'))

    @api.multi
    def button_action_draft(self):
        """
        Call cancel method on button draft click
        (already sets the state to draft)
        :return: None
        """
        self.cancel()

    @api.multi
    def button_action_cancel(self):
        """
        Call cancel method on button cancel click
        and then set the state to canceled
        :return: None
        """
        self.cancel()
        self.write({'state': 'canceled'})

    @api.multi
    def post(self):
        """ Create the journal items for the payment and update the payment's state to 'posted'.
            A journal entry is created containing an item in the source liquidity account (selected journal's default_debit or default_credit)
            and another in the destination reconciliable account (see _compute_destination_account_id).
            If invoice_ids is not empty, there will be one reconciliable move line per invoice to reconcile with.
            If the payment is a transfer, a second journal entry is created in the destination journal to receive money from the transfer account.
        """
        for rec in self:
            if rec.payment_type == 'advance' and not self.cashier_id:
                raise exceptions.Warning(_('Nenurodytas pinigus priėmęs asmuo'))
            if rec.state != 'draft':
                raise exceptions.UserError(_("Klaida. Bandykite iš naujo."))

            if any(inv.state not in ['open', 'proforma', 'proforma2'] for inv in rec.invoice_ids):
                raise exceptions.ValidationError(_("Sąskaita statusas nėra laukiantis mokėjimo."))

            if not rec.move_name:
                # Use the right sequence to set the name
                if rec.payment_type == 'transfer':
                    sequence_code = 'account.payment.transfer'
                elif rec.payment_type == 'advance':
                    sequence_code = 'account.payment.advance'
                elif rec.payment_type == 'inbound' and rec.partner_type:
                    sequence_code = rec.journal_id.sequence_id.code or 'account.payment.customer.invoice'
                elif rec.payment_type == 'outbound' and rec.partner_type:
                    sequence_code = rec.journal_id.refund_sequence_id.code or 'account.payment.supplier.invoice'
                # do not trigger new sequence with account.move post by writing move_name straight away
                rec.name = rec.move_name = self.env['ir.sequence'].with_context(ir_sequence_date=rec.payment_date).next_by_code(
                    sequence_code)

            # Create the journal entry
            amount = rec.amount * (rec.payment_type in ('outbound', 'transfer') and 1 or -1)
            skip_reconciliation = True if rec.force_destination_account_id and not \
                rec.force_destination_account_id.reconcile else False

            if self.env['account.move'].check_access_rights('create') and not self.env.user.is_manager():
                # If user is not manager, but it has the rights to create account moves, execute the same
                # operations using sudo(), so record rules are skipped (they take long time to be applied)
                move = rec.sudo().with_context(skip_reconcilation=skip_reconciliation)._create_payment_entry(amount)
                # Post a message to keep track of who registered a payment
                msg = _('Payment registered by %s') % self.env.user.name
                for invoice in rec.invoice_ids.sudo():
                    invoice.message_post(body=msg, message_type='notification', subtype='mail.mt_note')
            else:
                move = rec.with_context(skip_reconcilation=skip_reconciliation)._create_payment_entry(amount)

            # In case of a transfer, the first journal entry created debited the source liquidity account and credited
            # the transfer account. Now we debit the transfer account and credit the destination liquidity account.
            if rec.payment_type == 'transfer':
                transfer_credit_aml = move.line_ids.filtered(
                    lambda r: r.account_id == rec.company_id.transfer_account_id)
                transfer_debit_aml = rec._create_transfer_entry(amount)
                (transfer_credit_aml + transfer_debit_aml).reconcile()

            rec.write({'state': 'posted', 'move_name': move.name})
