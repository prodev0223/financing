# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools, exceptions, _
from datetime import datetime


class RasoPayments(models.Model):
    """
    Model that holds raso.payment records
    Account moves are created from Raso payments and
    Later they are reconciled with invoices
    """
    _name = 'raso.payments'
    _inherit = ['mail.thread']

    raso_invoice_id = fields.Many2one('raso.invoices', string='Sąskaita kuriai skirtas mokėjimas', readonly=True)
    move_id = fields.Many2one('account.move', string='Buhalterinis įrašas', readonly=True)
    payment_type_id = fields.Many2one('raso.payment.type', string='Mokėjimo tipas')
    code = fields.Char(string='Mokėjimo tipo kodas', inverse='create_payment_type')
    amount = fields.Float(string='Mokėjimo suma')
    residual = fields.Float(string='Mokėjimo likutis', compute='get_residual')
    qty = fields.Float(string='Kiekis')
    state = fields.Selection([('open', 'Sukurta, Laukiama sudengimo'),
                              ('reconciled', 'Mokėjimas sudengtas'),
                              ('partially_reconciled', 'Mokėjimas sudengtas dalinai'),
                              ('active', 'Panaudojamas'),
                              ('warning', 'Trūksta konfigūracijos'),
                              ], string='Būsena', compute='set_state', store=True)
    partner_id = fields.Many2one('res.partner', compute='_compute_partner_id', store=True, string='Susietas partneris')
    shop_no = fields.Char(required=True, string='Parduotuvės numeris', inverse='get_shop_pos')
    pos_no = fields.Char(string='Kasos numeris', inverse='get_shop_pos')
    shop_id = fields.Many2one('raso.shoplist', string='Susieta Parduotuvė', readonly=True)
    pos_id = fields.Many2one('raso.shoplist.registers', string='Susieta Kasa', readonly=True)
    payment_date = fields.Date(string='Mokėjimo data')
    refund_payment = fields.Boolean(compute='_compute_refund_payment')

    @api.multi
    @api.depends('amount')
    def _compute_refund_payment(self):
        """
        Compute //
        Decide whether raso payment is refund payment
        Criteria -- Amount is less than zero
        :return: None
        """
        for rec in self:
            if tools.float_compare(0, rec.amount, precision_digits=2) > 0:
                rec.refund_payment = True

    @api.multi
    def recompute_fields(self):
        self._compute_partner_id()
        self.get_residual()
        self.set_state()

    @api.one
    def get_shop_pos(self):
        if not self.shop_no:
            return
        shop = self.env['raso.shoplist'].search([('shop_no', '=', self.shop_no)])
        if not shop:
            shop = self.env['raso.shoplist'].create({
                'shop_no': self.shop_no,
                'location_id': False,
            })
        self.shop_id = shop
        if self.pos_no:
            pos = self.env['raso.shoplist.registers'].search([('shop_id', '=', shop.id),
                                                              ('pos_no', '=', self.pos_no)])
            if len(pos) > 1:
                raise exceptions.ValidationError(_('Konfigūracijos klaida: '
                                                   'rasti keli kasos aparatai %s parduotuvėje %s')
                                                 % (self.pos_no, self.shop_no))
            if not pos:
                pos = self.env['raso.shoplist.registers'].create({
                    'pos_no': self.pos_no,
                    'shop_id': self.shop_id.id
                })
            self.pos_id = pos
        else:
            pos = self.shop_id.generic_pos
            if not pos:
                pos = self.env['raso.shoplist.registers'].search([('pos_no', '=', 'Generic')])
            if not pos:
                self.shop_id.create_generic_pos()
                pos = self.shop_id.generic_pos
            if not pos:
                raise exceptions.ValidationError(_('Konfigūracijos klaida: Nerastas kasos '
                                                   'aparatas parduotuvei %s') % self.shop_no)
            self.pos_id = pos

    @api.multi
    @api.depends('raso_invoice_id', 'payment_type_id')
    def _compute_partner_id(self):
        """Compute payment partner, take it from related invoice if it exists, otherwise from the POS or shop"""
        for rec in self:
            payment_partner = self.env['res.partner']
            # Take the partner from the invoice
            if rec.raso_invoice_id:
                payment_partner = rec.raso_invoice_id.partner_id
            # If partner is not set, take it from the POS/Shop
            if not payment_partner:
                payment_partner = rec.pos_id.partner_id if rec.pos_id else rec.shop_id.generic_pos.partner_id
            rec.partner_id = payment_partner

    @api.one
    def create_payment_type(self):
        payment_type_mapping = {
            '0': 'Raso Grynieji',
            '2': 'Raso Bankinės kortelės',
            '3': 'Raso Dovanų Kuponai',
            '7': "Raso 'Compensa' Apmokėjimas",
        }
        payment_journal_mapping = {
            '0': 'RSCSH',
            '2': 'RSCRD',
            '3': 'RSGFT',
            '7': 'RSTRA',
        }
        payment_type_id = self.env['raso.payment.type']
        if self.code:
            payment_type_id = self.env['raso.payment.type'].search(
                [('payment_type_code', '=', self.code)])

        if not payment_type_id and self.code:
            payment_type_id = self.env['raso.payment.type'].search(
                [('payment_type_name', '=', self.code)])

        if not payment_type_id:
            name = payment_type_mapping.get(self.code, False)
            journal_id = self.env['account.journal'].search([('code', '=', payment_journal_mapping.get(self.code))], limit=1).id
            payment = {
                'payment_type_code': self.code,
                'payment_type_name': name,
                'journal_id': journal_id,
                'do_reconcile': True,
            }
            self.payment_type_id = self.env['raso.payment.type'].create(payment)
        else:
            self.payment_type_id = payment_type_id

    @api.one
    @api.depends('payment_type_id.journal_id', 'move_id', 'residual', 'partner_id')
    def set_state(self):
        if not self.move_id:
            if self.payment_type_id.journal_id and self.partner_id:
                self.state = 'active'
            else:
                self.state = 'warning'
        else:
            if tools.float_compare(self.residual, self.amount, precision_digits=2) == 0:
                self.state = 'open'
            elif tools.float_compare(self.residual, 0.0, precision_digits=2) == 0:
                self.state = 'reconciled'
            else:
                self.state = 'partially_reconciled'

    @api.one
    @api.depends('move_id', 'amount',
                 'move_id.line_ids.currency_id', 'move_id.line_ids.amount_residual')
    def get_residual(self):
        account = self.env['account.account'].search([('code', '=', '2410')])
        if self.move_id:
            residual = 0.0
            lines = self.move_id.line_ids.filtered(lambda x: x.account_id.id == account.id)
            if not lines:
                self.residual = self.amount
            else:
                for line in lines:
                    if line.account_id.id == account.id:
                        residual += line.amount_residual
                self.residual = abs(residual)
        else:
            self.residual = self.amount

    @api.multi
    def validator(self):
        """
        Validate Raso payment records before account move creation
        :return: validated payment list
        """
        valid_payments = self.env['raso.payments']
        self.recompute_fields()

        for rec in self:
            error_template = str()
            if not rec.payment_type_id:
                error_template += _('Nerastas susijęs mokėjimo tipas\n')
            if rec.payment_type_id.state in ['warning']:
                error_template += _('Nesukonfigūruotas mokėjimo tipas\n')
            if not rec.payment_type_id.journal_id.default_debit_account_id:
                error_template += _('Nesukonfigūruota mokėjimo tipo žurnalo debeto sąskaita\n')
            if not rec.payment_type_id.journal_id.default_credit_account_id:
                error_template += _('Nesukonfigūruota mokėjimo tipo žurnalo kredito sąskaita\n')
            if not rec.partner_id:
                error_template += _('Nerastas mokėjimo partneris!\n')
            if error_template:
                error_template = _('Nepavyko sukurti mokėjimo dėl šių problemų: \n\n') + error_template
                rec.post_message(error_template, 'warning')
            else:
                valid_payments |= rec
        return valid_payments

    @api.multi
    def move_creation_prep(self):
        """
        Prepare raso.payment records for account.move record creation
        :return: None
        """
        payments = self.filtered(
            lambda x: not x.move_id and x.state in ['active', 'warning'] and x.payment_type_id.is_active)
        validated_payments = payments.validator()

        # Create moves for validated payments
        validated_payments.create_moves()
        # Reconcile moves of the payments with account invoice moves
        validated_payments.reconcile_payments()

    @api.multi
    def reconcile_payments(self):
        """
        Reconcile account.move records, that are created from raso.payment, with
        account.invoice records in the system. If forced reconciliation bool
        is checked, search for any move lines that can be reconciled together
        ignoring the raso.payments records
        :return: None
        """
        def reconcile_lines(payment_rec, invoice_rec):
            """
            Reconcile lines inner
            :param payment_rec: raso.payment record
            :param invoice_rec: account.invoice record
            :return: None
            """
            # Try to reconcile payment and it's related invoice move lines together
            move_lines = payment_rec.move_id.line_ids.filtered(
                lambda r: r.account_id.id == invoice_rec.account_id.id)
            move_lines |= invoice_rec.move_id.line_ids.filtered(
                lambda r: r.account_id.id == invoice_rec.account_id.id)
            if len(move_lines) > 1:
                move_lines.with_context(reconcile_v2=True).reconcile()

        # Filter passed payment IDs and prepare them for reconciliation
        payments = self.filtered(
            lambda x: x.move_id and x.state in ['partially_reconciled', 'open']
            and x.payment_type_id.is_active and x.payment_type_id.do_reconcile
            and not tools.float_is_zero(x.residual, precision_digits=2))

        for payment in payments:
            # Check whether raso payment has related account_invoice record
            related_invoice = payment.raso_invoice_id.invoice_id
            if related_invoice:
                # Recompute payment's partner ID if it has a related invoice
                payment._compute_partner_id()
                if not payment.partner_id:
                    continue
                # Try to reconcile payment and it's related invoice move lines together
                reconcile_lines(payment, related_invoice)
            else:
                invoice_type = 'out_refund' if payment.refund_payment else 'out_invoice'

                # Search for the invoices that match the partner and type of the payment
                invoices = self.env['account.invoice'].search(
                    [('partner_id', '=', payment.partner_id.id), ('residual', '>', 0),
                     ('invoice_type', '=', invoice_type), ('state', '=', 'open')], order='date_invoice asc')

                for invoice in invoices:
                    reconcile_lines(payment, invoice)
            # Commit changes after each loop
            self.env.cr.commit()

    @api.multi
    def create_moves(self):
        """
        Create account.move records from passed raso.payments records
        Commit changes after each round of move creation
        :return: None
        """
        account = self.env['account.account'].search(
            [('code', '=', self._context.get('account_code', '2410'))])
        for payment in self:
            if tools.float_is_zero(payment.amount, precision_digits=2):
                continue

            # Prepare base move values
            move_lines = []
            payment_date = payment.payment_date or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            move_name = _('Mokėjimas už {}').format(payment.raso_invoice_id.invoice_no or _('pardavimus'))

            # Prepare debit and credit lines
            credit_line = {
                'name': move_name,
                'date': payment_date,
                'partner_id': payment.partner_id.id,
                'account_id': account.id
            }
            debit_line = credit_line.copy()

            if payment.refund_payment:
                # If payment is refund, abs it's amount
                debit_line['credit'] = credit_line['debit'] = abs(payment.amount)
                debit_line['debit'] = credit_line['credit'] = 0.0
                debit_line['account_id'] = payment.payment_type_id.journal_id.default_credit_account_id.id
            else:
                debit_line['debit'] = credit_line['credit'] = payment.amount
                debit_line['credit'] = credit_line['debit'] = 0.0
                debit_line['account_id'] = payment.payment_type_id.journal_id.default_debit_account_id.id

            move_lines.append((0, 0, credit_line))
            move_lines.append((0, 0, debit_line))
            move_vals = {
                'line_ids': move_lines,
                'journal_id': payment.payment_type_id.journal_id.id,
                'date': payment_date,
            }
            # Create and post account move record
            account_move = self.env['account.move'].sudo().create(move_vals)
            account_move.post()
            payment.write({'move_id': account_move.id})
            self.env.cr.commit()

    @api.multi
    def button_reconcile_payments(self):
        """
        Method that calls payment reconciliation from a button.
        Used because calling method from a form fills default args with
        JS values.
        :return: None
        """
        self.reconcile_payments()

    @api.multi
    def open_pay_line(self):
        self.ensure_one()
        return {
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'raso.payments',
                'res_id': self.id,
                'view_id': self.env.ref('raso_retail.raso_payments_form').id,
                'type': 'ir.actions.act_window',
                'target': 'current',
        }

    @api.multi
    def name_get(self):
        return [(pay.id, pay.code) for pay in self]

    @api.multi
    def unlink(self):
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Negalite ištrinti įrašų!'))
        if any(rec.move_id for rec in self):
            raise exceptions.UserError(_('Negalima ištrinti sukurto arba sudengto mokėjimo!'
                                         ' Panaikinkite atitinkamus įrašus ir bandykite vėl'))
        return super(RasoPayments, self).unlink()

    @api.multi
    def post_message(self, body, state):
        send = {
            'body': body,
        }
        self.write({'state': state})
        for line in self:
            line.message_post(**send)


RasoPayments()
