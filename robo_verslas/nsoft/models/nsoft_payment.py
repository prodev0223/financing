# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, tools
from datetime import datetime
from dateutil.relativedelta import relativedelta


STATIC_ACCOUNT_CODE = '2410'


class NsoftPayment(models.Model):
    """
    Model that holds nSoft payment information
    Payments are created as account.move objects in the system
    """
    _name = 'nsoft.payment'

    ext_payment_type_id = fields.Integer(string='Išorinis mokėjimo tipo ID')
    payment_sum = fields.Float(string='Mokėjimo suma')
    receipt_id = fields.Integer(string='Mokėjimo čekis')
    payment_type_code = fields.Char(inverse='_set_payment_type', string='Išorinis mokėjimo kodas')
    payment_date = fields.Date(string='Mokėjimo data', compute='_compute_payment_date', store=True)
    state = fields.Selection([('open', 'Sukurta, Laukiama sudengimo'),
                              ('reconciled', 'Mokėjimas sudengtas'),
                              ('partially_reconciled', 'Mokėjimas sudengtas dalinai'),
                              ('active', 'Panaudojamas'),
                              ('warning', 'Trūksta konfigūracijos'),
                              ], string='Būsena', compute='_compute_state', store=True)
    residual = fields.Float(string='Mokėjimo likutis', compute='_compute_residual', store=True)
    # Relational fields
    nsoft_sale_line_ids = fields.Many2many('nsoft.sale.line', string='Apmokamos pardavimo eilutės')
    nsoft_invoice_ids = fields.Many2many('nsoft.invoice', string='Apmokamos sąskaitos')
    pay_type_id = fields.Many2one('nsoft.payment.type', string='Mokėjimo tipas')
    move_id = fields.Many2one('account.move', string='Įrašas apskaitoje')
    invoice_ids = fields.Many2many('account.invoice', string='Apmokamos sąskaitos (ROBO)')
    refund = fields.Boolean(compute='_compute_refund')

    @api.multi
    @api.depends('nsoft_sale_line_ids', 'nsoft_invoice_ids')
    def _compute_refund(self):
        """
        Compute //
        Determine whether nsoft.payment is of refund type
        criteria - if any of the related lines/invoices are of refund type
        payment is refund
        :return: None
        """
        for rec in self:
            if any(x.line_type == 'out_refund' for x in rec.nsoft_sale_line_ids):
                rec.refund = True
            if any(tools.float_compare(0.0, x.sum_with_vat, precision_digits=2) > 0 for x in rec.nsoft_invoice_ids):
                rec.refund = True

    @api.multi
    @api.depends('move_id', 'payment_sum',
                 'move_id.line_ids.currency_id', 'move_id.line_ids.amount_residual')
    def _compute_residual(self):
        """
        Compute //
        Calculate nsoft.payment residual amount based on the related account.move residual
        :return: None
        """
        account = self.env['account.account'].search([('code', '=', STATIC_ACCOUNT_CODE)])
        for rec in self:
            if rec.move_id:
                lines = rec.move_id.line_ids.filtered(lambda x: x.account_id.id == account.id)
                if not lines:
                    rec.residual = rec.payment_sum
                else:
                    residual = 0.0
                    for line in lines:
                        if line.account_id.id == account.id:
                            residual += line.amount_residual
                    rec.residual = abs(residual)
            else:
                rec.residual = rec.payment_sum

    @api.multi
    @api.depends('pay_type_id.journal_id', 'move_id', 'residual', 'payment_date')
    def _compute_state(self):
        """
        Compute //
        Determine nsoft.payment state
        :return: None
        """
        for rec in self:
            if rec.move_id:
                if tools.float_compare(rec.residual, rec.payment_sum, precision_digits=2) == 0:
                    rec.state = 'open'
                elif tools.float_is_zero(rec.residual, precision_digits=2):
                    rec.state = 'reconciled'
                else:
                    rec.state = 'partially_reconciled'
            else:
                if rec.payment_date and (rec.pay_type_id.journal_id or not rec.pay_type_id.do_reconcile):
                    rec.state = 'active'
                else:
                    rec.state = 'warning'

    @api.multi
    @api.depends('nsoft_sale_line_ids.payment_date', 'nsoft_invoice_ids.payment_date')
    def _compute_payment_date(self):
        """
        Compute //
        :return: None
        """
        day_end_threshold = self.sudo().env['ir.config_parameter'].get_param('nsoft_day_end_hour_threshold')
        # Try to convert the day_end_threshold value to integer
        try:
            day_end_threshold = int(day_end_threshold)
        except ValueError:
            pass

        for rec in self:
            payment_date = False
            if rec.nsoft_sale_line_ids:
                payment_date = rec.nsoft_sale_line_ids[0].payment_date
            elif rec.nsoft_invoice_ids:
                payment_date = rec.nsoft_invoice_ids[0].payment_date
            if payment_date and day_end_threshold and isinstance(day_end_threshold, int):
                payment_date_dt = datetime.strptime(payment_date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                if 0 <= payment_date_dt.hour < day_end_threshold:
                    payment_date_dt = payment_date_dt - relativedelta(days=1)
                payment_date = payment_date_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            rec.payment_date = payment_date

    @api.multi
    def _set_payment_type(self):
        """
        Inverse
        Check for payment type and create corresponding default registers for special payment types WEB/TRANSFER
        :return: None
        """
        for rec in self:
            if rec.payment_type_code:
                pay_type = self.env['nsoft.payment.type'].search(
                    [('ext_payment_type_code', '=', rec.payment_type_code)])
                if not pay_type:
                    values = {
                        'ext_payment_type_code': rec.payment_type_code,
                        'journal_id': False,
                    }
                    pay_type = self.env['nsoft.payment.type'].sudo().create(values)
                rec.pay_type_id = pay_type
            else:
                rec.pay_type_id = self.env['nsoft.payment.type'].search(
                    [('ext_payment_type_code', '=', 'P')])

    @api.multi
    def recompute_fields(self):
        """
        Re-compute/Re-inverse necessary fields for account invoice creation
        :return: None
        """
        self._compute_payment_date()
        self._compute_state()
        self._compute_residual()

    @api.multi
    def name_get(self):
        """Custom name-get"""
        return [(rec.id, 'Mokėjimas %s' % rec.receipt_id) for rec in self]

    @api.multi
    def create_nsoft_moves(self, partner_id, forced_amount=0):
        """
        Create artificial payment for nsoft.sale.line or nsoft.invoice
        :param partner_id: res.partner that is used to create the move
        :param forced_amount: amount that can be forced to create partial payment move
        :return: None
        """
        account = self.env['account.account'].search([('code', '=', STATIC_ACCOUNT_CODE)])
        for payment in self.filtered(lambda x: not x.move_id):
            amount_to_use = forced_amount if forced_amount else payment.residual
            journal = payment.pay_type_id.journal_id
            name = 'Mokėjimas ' + payment.payment_date
            move_lines = []
            credit_line = {
                'name': name,
                'date': payment.payment_date,
            }
            debit_line = credit_line.copy()
            if payment.refund:
                debit_line['credit'] = credit_line['debit'] = amount_to_use
                debit_line['debit'] = credit_line['credit'] = 0.0
                debit_line['account_id'] = journal.default_credit_account_id.id
                credit_line['account_id'] = account.id
            else:
                debit_line['debit'] = credit_line['credit'] = amount_to_use
                debit_line['credit'] = credit_line['debit'] = 0.0
                debit_line['account_id'] = journal.default_debit_account_id.id
                credit_line['account_id'] = account.id

            move_lines.append((0, 0, credit_line))
            move_lines.append((0, 0, debit_line))
            move_vals = {
                'line_ids': move_lines,
                'journal_id': journal.id,
                'date': payment.payment_date,
                'partner_id': partner_id.id,
            }
            move = self.sudo().env['account.move'].create(move_vals)
            move.post()
            payment.move_id = move

    @api.model
    def re_reconcile(self):
        """
        Search for all nsoft.payments that are partially_reconciled or not
        reconciled as well as account.invoice records that were created
        from nsoft.sale.line or nsoft.invoice and try to reconcile everything
        :return: None
        """
        payments = self.search([('state', 'in', ['partially_reconciled', 'open'])])
        domain = [('invoice_id', '!=', False), ('invoice_id.residual', '>', 0)]
        invoices = self.env['nsoft.sale.line'].search(domain).mapped('invoice_id')
        invoices |= self.env['nsoft.invoice'].search(domain).mapped('invoice_id')
        for payment in payments:
            for invoice in invoices:
                payment.reconcile_with_invoice(invoice)

    @api.multi
    def reconcile_with_invoice(self, invoice):
        """
        Reconcile account.invoice with account.move created from nsoft.payment if
        both have residual and if corresponding partners match
        :param invoice: account.invoice record
        :return: None
        """
        self.ensure_one()
        if not tools.float_is_zero(self.residual, precision_digits=2) and not tools.float_is_zero(
                invoice.residual, precision_digits=2) and self.move_id.partner_id.id == invoice.partner_id.id:
            lines = self.move_id.line_ids.filtered(lambda r: r.account_id.id == invoice.account_id.id)
            lines |= invoice.move_id.line_ids.filtered(
                lambda r: r.account_id.id == invoice.account_id.id)
            if len(lines) > 1:
                lines.with_context(reconcile_v2=True).reconcile()
            self.write({'invoice_ids': [(4, invoice.id)]})
            invoice.write({'nsoft_payment_move_ids': [(4, self.id)]})

    @api.multi
    def action_open_journal_entries(self):
        """
        Return the action which opens related account move lines
        :return: action (dict)
        """
        return {
            'name': _('DK įrašai'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move.line',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', self.move_id.line_ids.ids)],
        }


NsoftPayment()
