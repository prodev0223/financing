# -*- coding: utf-8 -*-


from odoo import api, fields, models, tools


class RegisterPayment(models.TransientModel):
    _name = 'register.payment'

    def default_journal(self):
        return self.env.user.sudo().employee_ids and self.env.user.sudo().employee_ids[
            0].department_id.default_cash_journal_id.id

    def default_cashier_id(self):
        """Default cashier -- If it's set, take it from res.company data, otherwise current user's employee record"""
        employees = self.env.user.employee_ids
        return self.env.user.company_id.cashier_id or employees[0] if employees else False

    def default_employee_id(self):
        cashier = self.env.user.employee_ids
        return cashier[0].id if cashier else False

    def default_invoice(self):
        return self._context.get('invoice_id', False)

    def default_communication(self):
        invoice_id = self.env['account.invoice'].browse(self._context.get('invoice_id', False))
        return invoice_id.reference or invoice_id.number

    journal_id = fields.Many2one('account.journal', string='Operacijų žurnalas', required=True,
                                 domain=[('type', '=', 'cash')], default=default_journal, ondelete='cascade')
    cashier_id = fields.Many2one('hr.employee', string='Kasininkas', default=default_cashier_id)
    employee_id = fields.Many2one('hr.employee', string='Pinigus priimantis asmuo', default=default_employee_id)
    amount = fields.Monetary(string='Suma', required=True)
    payment_date = fields.Date(string='Mokėjimo data', default=fields.Date.context_today, required=True)
    currency_id = fields.Many2one('res.currency', string='Valiuta', required=True,
                                  default=lambda self: self.env.user.company_id.currency_id, ondelete='cascade')
    communication = fields.Char(string='Mokėjimo paskirtis', required=True, default=default_communication)
    invoice_id = fields.Many2one('account.invoice', default=default_invoice, required=True, ondelete='cascade')
    payment_type = fields.Selection(
        [('order', 'Kasos orderis'), ('receipt', 'Pinigų priėmimo kvitas')], compute='_payment_type')
    payment_difference = fields.Monetary(compute='_compute_payment_difference', readonly=True)
    payment_difference_handling = fields.Selection(
        [('open', 'Palikti neapmokėtą'), ('reconcile', 'Apmokėti su nurašymu')],
        default='open', string="Neapmokėtas likutis")
    writeoff_account_id = fields.Many2one('account.account', string="Nurašyti į",
                                          domain=[('deprecated', '=', False)])

    @api.one
    @api.depends('journal_id')
    def _payment_type(self):
        if self.journal_id.code == 'KVIT':
            self.payment_type = 'receipt'
        else:
            self.payment_type = 'order'

    @api.one
    @api.depends('invoice_id', 'amount', 'payment_date', 'currency_id')
    def _compute_payment_difference(self):
        if not self.invoice_id:
            return
        if self.invoice_id.type in ['in_invoice', 'out_refund']:
            self.payment_difference = self.amount - self._compute_total_invoices_amount()
        else:
            self.payment_difference = self._compute_total_invoices_amount() - self.amount

    def _compute_total_invoices_amount(self):
        """ Compute the sum of the residual of invoices, expressed in the payment currency """
        payment_currency = self.currency_id or self.journal_id.currency_id or self.journal_id.company_id.currency_id
        invoices = self.invoice_id

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

    @api.multi
    def post(self):
        self.ensure_one()
        if self.payment_type == 'receipt':
            vals = {
                'journal_id': self.journal_id.id,
                'amount': self.amount,
                'currency_id': self.currency_id.id,
                'payment_date': self.payment_date,
                'cashier_id': self.employee_id.id,
                'payment_type': 'outbound' if self.invoice_id.type in ['in_invoice', 'out_refund'] else 'inbound',
                'invoice_ids': [(4, self.invoice_id.id)],
                'partner_id': self.invoice_id.partner_id.id,
                'communication': self.communication
            }
            cash_id = self.env['cash.receipt'].create(vals)
            cash_id.post()
            view_id = self.env.ref('robo.view_cash_receipt_form_front').id
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'cash.receipt',
                'view_mode': 'form',
                'view_type': 'form',
                'view_id': view_id,
                'res_id': cash_id.id,
                'target': 'self',
                'context': {'robo_header': {}}
            }
        else:
            vals = {
                'journal_id': self.journal_id.id,
                'amount': self.amount,
                'currency_id': self.currency_id.id,
                'payment_date': self.payment_date,
                'cashier_id': self.cashier_id.id,
                'payment_difference': self.payment_difference,
                'payment_difference_handling': self.payment_difference_handling,
                'writeoff_account_id': self.writeoff_account_id,
                'payment_type': 'outbound' if self.invoice_id.type in ['in_invoice', 'out_refund'] else 'inbound',
                'invoice_ids': [(4, self.invoice_id.id)],
                'partner_id': self.invoice_id.partner_id.id,
                'payment_method_id': self.env.ref(
                    'account.account_payment_method_manual_out').id if self.invoice_id.type in ['in_invoice',
                                                                                                'out_refund'] else self.env.ref(
                    'account.account_payment_method_manual_in').id,
                'partner_type': 'customer' if self.invoice_id.type in ['out_invoice', 'out_refund'] else 'supplier',
                'communication': self.communication
            }
            payment_id = self.env['account.payment'].create(vals)
            payment_id.post()
            if self.invoice_id.state in ['proforma', 'proforma2']:
                currencies_match = self.currency_id.id == self.invoice_id.currency_id.id
                amounts_match = tools.float_compare(self.amount, self.invoice_id.residual_signed,
                                                    precision_digits=2) == 0
                if currencies_match and amounts_match:
                    self.invoice_id.mark_proforma_paid()
            view_id = self.env.ref('robo.account_payment_form').id
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.payment',
                'view_mode': 'form',
                'view_type': 'form',
                'view_id': view_id,
                'res_id': payment_id.id,
                'target': 'self',
                'context': {'robo_header': {}}
            }
