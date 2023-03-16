# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, _
from odoo.addons.queue_job.job import job


class RKeeperPayment(models.Model):
    _name = 'r.keeper.payment'
    _inherit = ['mail.thread']
    _description = '''
    Model that stores rKeeper payment records,
    that are used to create account moves
    '''

    # Identification
    doc_number = fields.Char(string='Dokumento numeris')

    # Dates
    doc_date = fields.Date(string='Dokumento data')
    payment_date = fields.Date(string='Mokėjimo data')

    # Payment type information
    payment_type_code = fields.Char(string='Mokėjimo tipo kodas')
    payment_type_id = fields.Many2one(
        'r.keeper.payment.type', string='Mokėjimo tipas',
        compute='_compute_payment_type_id', store=True
    )

    # Amounts / Quantities
    amount = fields.Float(string='Mokėjimo suma')
    residual = fields.Float(
        string='Mokėjimo likutis',
        compute='_compute_residual',
        store=True, copy=False
    )

    # Point of sale info
    pos_code = fields.Char(string='Pardavimo taško kodas', inverse='_set_pos_code')
    point_of_sale_id = fields.Many2one('r.keeper.point.of.sale', string='Pardavimo taškas')

    # Other information
    state = fields.Selection([
        ('open', 'Sukurta, Laukiama sudengimo'),
        ('reconciled', 'Mokėjimas sudengtas'),
        ('partially_reconciled', 'Mokėjimas sudengtas dalinai'),
        ('active', 'Laukiama sukūrimo'),
        ('no_action', 'Nekūriama'),
        ('warning', 'Trūksta konfigūracijos'),
        ('canceled', 'Atšaukta buhalterio'),
        ('failed', 'Nepavyko sukurti įrašo'),
    ], string='Būsena', compute='_compute_state',
        store=True, track_visibility='onchange',
    )

    extra_data = fields.Text(string='Papildoma informacija')
    refund_payment = fields.Boolean(compute='_compute_refund_payment', string='Grąžinimas')
    move_id = fields.Many2one('account.move', string='Mokėjimo apskaitos įrašas', copy=False)

    refund_invoice_id = fields.Many2one('account.invoice', string='Kreditinė sąskaita', copy=False)
    refund_invoice_state = fields.Selection([
        ('no_action', 'Nekurta'),
        ('created', 'Kreditinė sąskaita sukurta'),
        ('failed', 'Nepavyko sukurti kreditinės sąskaitos'),
    ], string='Kreditinės sąskaitos kūrimo būsena', default='no_action', copy=False)
    let_create_refund_invoice = fields.Boolean(compute='_compute_let_create_refund_invoice')

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    @api.depends('refund_invoice_id', 'refund_invoice_state', 'payment_type_id.create_refund_invoice')
    def _compute_let_create_refund_invoice(self):
        """
        Check whether refund invoice creation
        for the current payment can be initiated
        from the form view
        :return: None
        """
        for rec in self:
            if rec.payment_type_id.create_refund_invoice and not \
                    rec.refund_invoice_id and rec.refund_invoice_state in ['no_action', 'failed']:
                rec.let_create_refund_invoice = True

    @api.multi
    @api.depends('move_id.line_ids.amount_residual')
    def _compute_residual(self):
        """
        Compute //
        Get amount residual for current payment
        based on related move lines residual
        :return: None
        """
        # Account 2410
        account = self.env.ref('l10n_lt.1_account_229')
        for rec in self:
            move_lines = rec.move_id.line_ids.filtered(lambda x: x.account_id.id == account.id)
            if move_lines:
                rec.residual = abs(
                    tools.float_round(
                        sum(move_lines.mapped('amount_residual')),
                        precision_digits=2
                    ))
            else:
                rec.residual = rec.amount

    @api.multi
    @api.depends('payment_type_id.configured', 'move_id', 'residual',
                 'point_of_sale_id.partner_id', 'payment_type_id.create_refund_invoice')
    def _compute_state(self):
        """
        Compute //
        Calculate state of the rKeeper payment
        :return: None
        """
        for rec in self:
            if rec.payment_type_id.create_refund_invoice:
                rec.state = 'no_action'
            elif not rec.move_id:
                # If record does not have move_id either configuration is missing or it's active
                rec.state = 'active' \
                    if rec.payment_type_id.configured and rec.point_of_sale_id.partner_id else 'warning'
            else:
                # Otherwise check residual amount, if it matches the payment amount - it's open
                # if it's zero - it's reconciled, else - partially_reconciled
                if not tools.float_compare(rec.residual, rec.amount, precision_digits=2):
                    rec.state = 'open'
                elif tools.float_is_zero(rec.residual, precision_digits=2):
                    rec.state = 'reconciled'
                else:
                    rec.state = 'partially_reconciled'

    @api.multi
    @api.depends('payment_type_code')
    def _compute_payment_type_id(self):
        """
        Compute //
        Find related rKeeper payment type
        based on passed payment type code
        :return: None
        """
        for rec in self.filtered(lambda x: x.payment_type_code):
            payment_type = self.env['r.keeper.payment.type'].search(
                [('code', '=', rec.payment_type_code)]
            )
            rec.payment_type_id = payment_type

    @api.multi
    @api.depends('amount')
    def _compute_refund_payment(self):
        """
        Compute //
        Decide whether rKeeper payment is refund payment
        Criteria -- Amount is less than zero
        :return: None
        """
        for rec in self:
            rec.refund_payment = tools.float_compare(0, rec.amount, precision_digits=2) > 0

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
        self._compute_residual()
        self._compute_state()
        self._compute_payment_type_id()
        self._compute_refund_payment()
        self._set_pos_code()

    # Main Methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def create_refund_payment_invoice_prep(self):
        """
        Creates refund payment invoice
        for passed payment set
        :return: None
        """
        payments = self.filtered(
            lambda x: x.payment_type_id.create_refund_invoice and not x.refund_invoice_id
            and x.refund_invoice_state in ['failed', 'no_action']
        )
        # Check constraints and filter records that have any warnings
        validated_payments = payments.check_refund_invoice_constraints()

        if validated_payments:
            # This way of looping is way faster than filtered
            grouped_lines = {}
            for line in validated_payments:
                # Loop through lines and build dict of dicts with following mapping
                pos = line.point_of_sale_id
                s_date = line.payment_date
                p_type = line.payment_type_id

                grouped_lines.setdefault(pos, {})
                grouped_lines[pos].setdefault(s_date, {})
                grouped_lines[pos][s_date].setdefault(p_type, self.env['r.keeper.payment'])
                grouped_lines[pos][s_date][p_type] |= line

            # Loop through grouped lines and create refund invoices for each batch
            for pos, by_pos in grouped_lines.items():
                for payment_date, by_payment_date in by_pos.items():
                    for payment_type, payments in by_payment_date.items():
                        payments.create_refund_payment_invoice()

    @api.multi
    def create_refund_payment_invoice(self):
        """
        Creates refund invoice for batch of payments
        that have create_refund_invoice bool set.
        Invoice product is taken from the payment type
        :return: None
        """

        default_obj = self.sorted(lambda r: r.payment_date, reverse=True)[0]
        invoice_obj = self.env['account.invoice'].sudo()
        # Account 2410
        default_account = self.env.ref('l10n_lt.1_account_229')

        # Get default values from POS
        default_journal = default_obj.point_of_sale_id.journal_id
        default_partner = default_obj.point_of_sale_id.partner_id
        default_analytic = default_obj.point_of_sale_id.analytic_account_id

        # Get other values
        product = default_obj.payment_type_id.refund_invoice_product
        tax = default_obj.payment_type_id.refund_invoice_tax

        # Prepare base invoice values
        invoice_lines = []
        invoice_values = {
            'external_invoice': True,
            'imported_api': True,
            'force_dates': True,
            'skip_isaf': True,
            'price_include_selection': 'inc',
            'account_id': default_account.id,
            'journal_id': default_journal.id,
            'partner_id': default_partner.id,
            'invoice_line_ids': invoice_lines,
            'type': 'out_refund',
            'date_invoice': default_obj.payment_date,
        }

        # Get the product account
        product_account = product.get_product_income_account(return_default=True)
        # Get the total value
        total_value = sum(self.mapped('amount'))
        line_vals = {
            'name': product.name,
            'product_id': product.id,
            'quantity': 1,
            'price_unit': total_value,
            'account_analytic_id': default_analytic.id,
            'account_id': product_account.id,
            'invoice_line_tax_ids': [(6, 0, tax.ids)],
        }
        invoice_lines.append((0, 0, line_vals))

        # Create the invoice. Invoices are not automatically validated,
        # they are left in a draft state for the review
        try:
            invoice = invoice_obj.create(invoice_values)
        except Exception as e:
            self.custom_rollback(e.args[0], action_type='ref_invoice_creation')
            return

        # Write state changes and commit
        self.write({'refund_invoice_state': 'created', 'refund_invoice_id': invoice.id})
        self.env.cr.commit()

    @api.multi
    def check_refund_invoice_constraints(self):
        """
        Validate related rKeeper payment records
        by checking various constrains before
        passing record-set to move creation
        :return: rKeeper payment record-set
        """
        valid_payments = self.env['r.keeper.payment']
        self.recompute_fields()

        for rec in self:
            error_template = str()
            if not rec.point_of_sale_id.configured:
                error_template += _('Nerastas arba nesukonfigūruotas susijęs pardavimo taškas\n')
            if not rec.payment_type_id.configured:
                error_template += _('Nerastas arba nesukonfigūruotas susijęs mokėjimo tipas\n')
            if not rec.payment_type_id.refund_invoice_product:
                error_template += _('Nesukonfigūruotas mokėjimo tipo grąžinimo sąskaitos produktas\n')
            if error_template:
                error_template = _('Nepavyko sukurti kreditinės sąskaitos dėl šių klaidų: \n\n') + error_template
                rec.post_message(error_template, refund_invoice_state='failed')
            else:
                valid_payments |= rec
        return valid_payments

    @api.multi
    def create_account_moves_prep(self):
        """
        Prepare rKeeper payment records
        for account move creation
        :return: None
        """
        payments = self.filtered(
            lambda x: not x.move_id and x.state in ['active', 'warning', 'failed']
            and x.payment_type_id.create_payment and not x.payment_type_id.create_refund_invoice
        )
        # Check constraints and filter records that have any warnings
        validated_payments = payments.check_move_creation_constraints()

        # Create moves for validated payments
        validated_payments.create_account_moves()
        # Reconcile moves of the payments with account invoice moves
        validated_payments.reconcile_payments()

    @api.multi
    def check_move_creation_constraints(self):
        """
        Validate related rKeeper payment records
        by checking various constrains before
        passing record-set to move creation
        :return: rKeeper payment record-set
        """
        valid_payments = self.env['r.keeper.payment']
        self.recompute_fields()

        for rec in self:
            error_template = str()
            if not rec.point_of_sale_id.configured:
                error_template += _('Nerastas arba nesukonfigūruotas susijęs pardavimo taškas\n')
            if not rec.payment_type_id.configured:
                error_template += _('Nerastas arba nesukonfigūruotas susijęs mokėjimo tipas\n')
            if error_template:
                error_template = _('Nepavyko sukurti mokėjimo dėl šių klaidų: \n\n') + error_template
                rec.post_message(error_template, state='failed')
            else:
                valid_payments |= rec
        return valid_payments

    @api.multi
    def create_account_moves(self):
        """
        Create account.move records from passed rKeeper payment records
        Commit changes after each round of move creation
        :return: None
        """
        # Account 2410
        account = self.env.ref('l10n_lt.1_account_229')

        for payment in self.filtered(lambda x: not tools.float_is_zero(x.amount, precision_digits=2)):
            move_lines = []
            # Prepare debit and credit lines
            credit_line = {
                'name': _('rKeeper mokėjimas'),
                'date': payment.payment_date,
                'partner_id': payment.point_of_sale_id.partner_id.id,
                'account_id': account.id
            }
            debit_line = credit_line.copy()

            # If current payment type is cash, give priority to POS cash journal
            journal = payment.payment_type_id.journal_id
            if payment.payment_type_id.cash_payment_type:
                journal = payment.point_of_sale_id.cash_journal_id or journal

            if payment.refund_payment:
                # If payment is refund, abs it's amount
                debit_line['credit'] = credit_line['debit'] = abs(payment.amount)
                debit_line['debit'] = credit_line['credit'] = 0.0
                debit_line['account_id'] = journal.default_credit_account_id.id
            else:
                debit_line['debit'] = credit_line['credit'] = payment.amount
                debit_line['credit'] = credit_line['debit'] = 0.0
                debit_line['account_id'] = journal.default_debit_account_id.id

            move_lines.append((0, 0, credit_line))
            move_lines.append((0, 0, debit_line))

            # Prepare base move values
            move_vals = {
                'line_ids': move_lines,
                'journal_id': journal.id,
                'date': payment.payment_date,
            }
            # Create and post account move record
            try:
                account_move = self.env['account.move'].sudo().create(move_vals)
                account_move.post()
            except Exception as e:
                payment.custom_rollback(e.args[0])
                continue

            # Write sequence name to the lines if it's cash payment
            if payment.payment_type_id.cash_payment_type:
                account_move.line_ids.write({'name': '{} - rKeeper'.format(account_move.name)})

            payment.move_id = account_move
            self.env.cr.commit()

    @api.multi
    @job
    def reconcile_payments(self, forcibly_reconcile=False):
        """
        Reconcile account moves that are created from rKeeper payments, with
        account invoice records in the system. If forced reconciliation bool
        is checked, search for any move lines that can be reconciled together
        ignoring the related rKeeper payment records
        :return: None
        """
        def reconcile_lines(payment_m, invoice_rec):
            """
            Reconcile lines inner
            :param payment_m: rKeeper payment account move
            :param invoice_rec: account invoice record
            """
            # If invoice residual amount is zero -- return
            if tools.float_is_zero(invoice_rec.residual, precision_digits=2):
                return
            # Try to reconcile payment and it's related invoice move lines together
            move_lines = payment_m.line_ids.filtered(
                lambda r: r.account_id.id == invoice_rec.account_id.id)
            move_lines |= invoice_rec.move_id.line_ids.filtered(
                lambda r: r.account_id.id == invoice_rec.account_id.id)
            move_lines = move_lines.filtered(lambda x: not x.reconciled)
            if len(move_lines) > 1:
                move_lines.with_context(reconcile_v2=True).reconcile()

        # Filter passed payment IDs and prepare them for reconciliation
        payments = self.filtered(
            lambda x: (x.move_id and x.state in ['partially_reconciled', 'open']
                       and x.payment_type_id.create_payment and x.payment_type_id.do_reconcile
                       and not tools.float_is_zero(x.residual, precision_digits=2))
            or (x.refund_invoice_id and not tools.float_is_zero(x.refund_invoice_id.residual, precision_digits=2))
        )
        if forcibly_reconcile:
            # Forcibly reconcile -- Try to reconcile every invoice with rKeeper payments
            for payment in payments:
                invoice_type = 'out_refund' if payment.refund_payment else 'out_invoice'
                # Search for the invoices that match the partner and type of the payment
                invoices = self.env['account.invoice'].search(
                    [('partner_id', '=', payment.point_of_sale_id.partner_id.id),
                     ('residual', '>', 0),
                     ('external_invoice', '=', True),
                     ('invoice_type', '=', invoice_type),
                     ('state', '=', 'open')],
                    order='date_invoice asc'
                )
                # Loop through invoices and reconcile everything
                for invoice in invoices:
                    reconcile_lines(payment, invoice)

        else:
            # If forcibly reconcile criteria is not passed, reconcile payments
            # with sale line invoices of the same batch number
            grouped_payments = {}
            for payment in payments:
                # Loop through lines and build dict of dicts with following mapping
                doc_n = payment.doc_number
                pos = payment.point_of_sale_id

                grouped_payments.setdefault(doc_n, {})
                grouped_payments[doc_n].setdefault(pos, self.env['r.keeper.payment'])
                grouped_payments[doc_n][pos] |= payment

            # Loop through batches
            for doc_number, by_doc in grouped_payments.items():
                for point_of_sale, payments, in by_doc.items():
                    # Collect all related invoices for this batch
                    related_lines = self.env['r.keeper.sale.line'].search(
                        [('doc_number', '=', doc_number),
                         ('point_of_sale_id', '=', point_of_sale.id)]
                    )
                    related_invoices = related_lines.mapped('invoice_id').filtered(
                        lambda x: not tools.float_is_zero(x.residual, precision_digits=2)
                    )
                    # Loop through payments and invoices and try to reconcile everything
                    if related_invoices:
                        for invoice in related_invoices:
                            for payment in payments:
                                residual_record = payment
                                # Get the corresponding account move based on payment
                                if payment.payment_type_id.create_refund_invoice:
                                    payment_move = payment.refund_invoice_id.move_id
                                    residual_record = payment.refund_invoice_id
                                else:
                                    payment_move = payment.move_id
                                # Check the residual amount here
                                if tools.float_is_zero(residual_record.residual, precision_digits=2):
                                    continue
                                reconcile_lines(payment_move, invoice)

    @api.multi
    def cancel_payment(self):
        """
        Method that is used to cancel rKeeper payment
        by un-reconciling and deleting current move.
        Payment state is also set to canceled
        :return: None
        """
        for payment in self.filtered(lambda x: x.state != 'canceled'):
            # Check whether current payment has a move,
            # un-reconcile the lines and delete it
            move = payment.move_id
            if move:
                move.line_ids.remove_move_reconcile()
                move.button_cancel()
                move.unlink()
            # Post the message and write the state
            body = _('Mokėjimas atšauktas buhalterio')
            payment.post_message(state='canceled', body=body)

    # Utility methods -------------------------------------------------------------------------------------------------

    @api.model
    def create_action_recompute_fields_multi_payment(self):
        """Creates action for multi-set recompute all"""
        action = self.env.ref('r_keeper.action_recompute_fields_multi_payment')
        if action:
            action.create_action()

    @api.model
    def create_action_cancel_payment_multi(self):
        """Creates action for multi-set cancel payment"""
        action = self.env.ref('r_keeper.action_cancel_payment_multi')
        if action:
            action.create_action()

    @api.multi
    def name_get(self):
        return [(rec.id, _('Mokėjimas #{}').format(rec.id)) for rec in self]

    @api.multi
    def button_reconcile_payments(self):
        """
        Method that calls payment reconciliation from a button.
        :return: None
        """
        self.reconcile_payments()

    @api.multi
    def button_create_account_moves_prep(self):
        """
        Method that calls account move creation prep from a button.
        :return: None
        """
        self.create_account_moves_prep()

    @api.multi
    def button_cancel_payment(self):
        """
        Method that calls payment cancellation from a button.
        :return: None
        """
        self.cancel_payment()

    @api.multi
    def custom_rollback(self, msg, action_type='move_creation'):
        """
        Rollback current transaction, post message to the object and commit
        :return: None
        """
        self.env.cr.rollback()
        if action_type == 'move_creation':
            body = _('Nepavyko sukurti žurnalo įrašo, sisteminė klaida: %s') % str(msg)
            self.post_message(body, state='failed')
        elif action_type == 'ref_invoice_creation':
            body = _('Nepavyko sukurti kreditinės sąskaitos, sisteminė klaida: {}').format(msg)
            self.post_message(body, refund_invoice_state='failed')
        self.env.cr.commit()

    @api.multi
    def post_message(self, body, state=None, refund_invoice_state=None):
        """
        Write passed state and post message to the record-set
        :param body: message (str)
        :param state: state (str)
        :param refund_invoice_state: refund_invoice_state (str)
        :return: None
        """
        if state:
            self.write({'state': state})
        if refund_invoice_state:
            self.write({'refund_invoice_state': state})
        for payment in self:
            payment.message_post(body=body)
