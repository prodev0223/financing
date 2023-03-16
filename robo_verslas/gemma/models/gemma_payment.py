# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, tools, exceptions
from datetime import datetime
import logging
import gemma_tools

_logger = logging.getLogger(__name__)


class GemmaPayment(models.Model):
    _name = 'gemma.payment'
    _inherit = ['mail.thread', 'gemma.base']

    ext_payment_type_id = fields.Integer(string='Mokėjimo tipo kodas', inverse='create_payment_type')
    payment_type_text = fields.Char(string='Mokėjimo tipo pavadinimas')
    department_id = fields.Integer(string='Kasos/Departamento numeris', inverse='get_cash_register')
    department_desc = fields.Char(string='Departamento pavadinimas')
    vat_rate = fields.Float(string='PVM procentai')
    payment_date = fields.Datetime(string='Mokėjimo data')
    vat_class = fields.Float(string='PVM klasifikatorius')
    payer_id = fields.Char(string='Mokėtojo numeris', inverse='get_partner')
    payment_sum = fields.Float(string='Mokėjimo suma')
    receipt_id = fields.Integer(string='Čekio numeris')
    ext_payment_id = fields.Integer(string='Mokėjimo numeris', inverse='get_sale_line')
    journal_id = fields.Many2one('account.journal', string='Žurnalas', compute='get_journal', store=True)
    sale_line_ids = fields.One2many('gemma.sale.line', 'payment_id', string='Eilutė už kurią mokama')
    payment_type_id = fields.Many2one('gemma.payment.type', string='Mokėjimo tipas')
    move_id = fields.Many2one('account.move', string='Žurnalo įrašas')
    reverse_move_id = fields.Many2one('account.move', string='Atvirkštinis įrašas')
    state = fields.Selection([('open', 'Sukurta, Laukiama sudengimo'),
                              ('cash_done', 'Sukurta'),
                              ('reconciled', 'Mokėjimas sudengtas'),
                              ('partially_reconciled', 'Mokėjimas sudengtas dalinai'),
                              ('active', 'Panaudojamas'),
                              ('warning', 'Trūksta konfigūracijos'),
                              ('canceled', 'Atšauktas'),
                              ('failed', 'Klaida kuriant įrašą'),
                              ('cancel_locked', 'Atšauktas Polyje | Neatšauktas ROBO dėl užrakinimo datų')
                              ], string='Būsena', compute='set_state', store=True)
    is_canceled = fields.Boolean(string='Atšaukta', default=False)
    cancel_date = fields.Datetime(string='Atšaukimo data')
    ext_invoice_id = fields.Many2one('gemma.invoice', string='Susijusi Sąskaita')
    cash_register_id = fields.Many2one('gemma.cash.register', string='Kasos aparatas')
    partner_id = fields.Many2one('res.partner', string='Mokėtojas')
    type = fields.Selection([('cash_operations', 'Inkasacija'),
                             ('related', 'Turi susijusiu pardavimų'),
                             ('unrelated', 'Be susijusiu pardavimų'),
                             ('missing_data', 'Laukiama parnerio/mokėjimo eilučių')
                             ], string='Tipas', compute='get_type', store=True)

    cash_operation_type = fields.Selection([('out', 'Pinigų išėmimas'),
                                            ('in', 'Pinigų įnešimas'),
                                            ('other', 'Kita'),
                                            ('unused', 'Nenaudojamas')],
                                           string='Kasos operacijos tipas', default='unused', readonly=True)
    cash_operation_code = fields.Char(string='Kasos operacijos kodas', inverse='set_cash_op_type')
    residual = fields.Float(string='Mokėjimo likutis', compute='get_residual', store=True)

    @api.one
    def check_sale_partner(self):
        if self.sale_line_ids:
            partner_id = self.sale_line_ids.mapped('partner_id')
            partner_code = self.sale_line_ids.mapped('buyer_id')
            if len(partner_id) == 1 and (partner_id.id != self.partner_id.id or partner_code != self.payer_id):
                self.with_context(skip_inverse=True).write({'partner_id': partner_id.id,
                                                            'payer_id': partner_code[0]})

    @api.model
    def server_action_cancel_payments_f(self):
        action = self.env.ref('gemma.server_action_cancel_payments')
        if action:
            action.create_action()

    @api.model
    def server_action_cancel_payments_sale_f(self):
        action = self.env.ref('gemma.server_action_cancel_payments_sale')
        if action:
            action.create_action()

    @api.multi
    def cancel_records(self):
        if self.env.user.is_gemma_manager():
            include_sales = self._context.get('include_sales', False)
            corresponding_payments = self.filtered(lambda x: x.state not in ['canceled'])

            cancel_date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            corresponding_payments.reverse_moves()
            corresponding_payments.write({
                'cancel_date': cancel_date,
                'state': 'canceled'
            })
            if include_sales:
                sales = corresponding_payments.mapped('sale_line_ids')
                sales.credit_sales()
                sales.write({
                    'cancel_date': cancel_date,
                    'state': 'canceled'
                })

    @api.one
    @api.depends('move_id', 'payment_sum', 'partner_id',
                 'move_id.line_ids.currency_id', 'move_id.line_ids.amount_residual', 'type')
    def get_residual(self):
        if self.type == 'cash_operations':
            account = self.env['account.account'].search([('code', '=', '273')])
        else:
            account = self.env['account.account'].search([('code', '=', '2410')])
        if self.move_id:
            residual = 0.0
            lines = self.move_id.line_ids.filtered(lambda x: x.account_id.id == account.id)
            if not lines:
                self.residual = self.payment_sum
            else:
                for line in lines:
                    if line.account_id.id == account.id:
                        residual += line.amount_residual
                self.residual = abs(residual)
        else:
            self.residual = self.payment_sum

    @api.one
    def set_cash_op_type(self):
        if self.cash_operation_code in ['in', 'out']:
            self.cash_operation_type = self.cash_operation_code
        elif self.cash_operation_code:
            self.cash_operation_type = 'other'
        else:
            self.cash_operation_type = 'unused'

    @api.multi
    @api.depends('payment_type_id', 'sale_line_ids', 'partner_id')
    def get_journal(self):
        for rec in self:
            if not rec.payment_type_id and not rec.sale_line_ids and not rec.partner_id:
                rec.journal_id = self.env['account.journal'].search([('code', '=', 'GMINC')])
            else:
                rec.journal_id = rec.payment_type_id.journal_id

    @api.model
    def server_action_moves(self):
        action = self.env.ref('gemma.server_action_move')
        if action:
            action.create_action()

    @api.multi
    @api.depends('sale_line_ids', 'partner_id', 'cash_operation_type')
    def get_type(self):
        for rec in self:
            if rec.partner_id:
                rec.type = 'related' if rec.sale_line_ids else 'unrelated'
            elif rec.sale_line_ids:
                rec.type = 'related'
            elif rec.cash_operation_type == 'unused':
                rec.type = 'missing_data'
            else:
                rec.type = 'cash_operations'

    @api.one
    def get_sale_line(self):
        if self.ext_payment_id:
            sale_line_ids = self.env['gemma.sale.line'].search(
                [('ext_payment_id', '=', self.ext_payment_id), ('active', '=', True)])
            for sale in sale_line_ids:
                sale.payment_id = self.id

    @api.multi
    def name_get(self):
        return [(rec.id, 'Mokėjimas ' + str(rec.ext_payment_id)) for rec in self]

    @api.one
    @api.depends('journal_id', 'move_id', 'residual', 'is_canceled', 'partner_id', 'type')
    def set_state(self):
        if self.is_canceled:
            self.state = 'canceled'
        else:
            if not self.move_id:
                if self.journal_id:
                    self.state = 'warning' if self.type != 'cash_operations' and not self.partner_id else 'active'
                else:
                    self.state = 'warning'
            else:
                if self.type != 'cash_operations':
                    if tools.float_compare(self.residual, self.payment_sum, precision_digits=2) == 0:
                        self.state = 'open'
                    elif tools.float_compare(self.residual, 0.0, precision_digits=2) == 0:
                        self.state = 'reconciled'
                    else:
                        self.state = 'partially_reconciled'
                else:
                    self.state = 'cash_done'

    @api.one
    def get_cash_register(self):
        if self.department_id:
            cash_register_id = self.env['gemma.cash.register'].sudo().search(
                [('number', '=', self.department_id)]).id
            if cash_register_id:
                self.cash_register_id = cash_register_id
            else:
                values = {
                    'number': self.department_id,
                    'name': self.department_desc if self.department_desc else 'Gemma ' + str(self.department_id),
                    'location_id': False,
                    'journal_id': False,
                }
                self.cash_register_id = self.env['gemma.cash.register'].sudo().create(values)

    @api.multi
    def unlink(self):
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Negalima ištrinti Gemma mokėjimo!'))
        if self.mapped('move_id'):
            raise exceptions.UserError(_('Negalima sudengto mokėjimo!'))
        return super(GemmaPayment, self).unlink()

    @api.one
    def create_payment_type(self):
        if self.ext_payment_type_id:
            self.payment_type_id = self.env['gemma.payment.type'].search(
                [('ext_type_id', '=', self.ext_payment_type_id)])
            if not self.payment_type_id:
                payment = {
                    'ext_type_id': self.ext_payment_type_id,
                    'name': self.payment_type_text,
                    'journal_id': False,
                    'do_reconcile': False,
                }
                self.payment_type_id = self.env['gemma.payment.type'].create(payment)

    @api.one
    def get_payment_type(self):
        self.payment_type_id = self.env['gemma.payment.type'].search(
            [('ext_type_id', '=', self.ext_payment_type_id)])

    @api.multi
    def re_reconcile(self):
        unrelated = self.filtered(lambda x: x.type == 'unrelated' and x.residual and x.payment_type_id.do_reconcile)
        related = self.filtered(lambda x: x.type == 'related' and x.residual and x.payment_type_id.do_reconcile)
        for payment in related:
            payment.get_residual()
            if payment.residual:
                invoice_ids = payment.sale_line_ids.mapped('invoice_id').filtered(lambda x: x.residual > 0)
                for invoice_id in invoice_ids:
                    if payment.residual:
                        line_ids = payment.move_id.line_ids.filtered(
                            lambda r: r.account_id.id == invoice_id.account_id.id)
                        line_ids |= invoice_id.move_id.line_ids.filtered(
                            lambda r: r.account_id.id == invoice_id.account_id.id)
                        if len(line_ids) > 1:
                            line_ids.with_context(reconcile_v2=True).reconcile()
                        payment.get_residual()
            self.env.cr.commit()

        self.reconcile_with_unrelated(unrelated)

        # related payments that still have residual are reconciled with unrelated
        reconcilable = self.env['gemma.payment'].search([('move_id', '!=', False),
                                                         ('state', 'in', ['open', 'partially_reconciled']),
                                                         ('type', '=', 'related'),
                                                         ('payment_type_id.do_reconcile', '=', True)])
        self.reconcile_with_unrelated(reconcilable)

        # reconcile with other accounting entries
        invoice_ids = self.env['account.invoice'].search([('residual', '>', 0)],
                                                         order='date_invoice asc')
        for invoice in invoice_ids:

            if invoice.state in ['open']:
                domain = [('account_id', '=', invoice.account_id.id),
                          ('partner_id', '=', invoice.partner_id.id),
                          ('reconciled', '=', False), ('amount_residual', '!=', 0.0)]
                if invoice.type in ('out_invoice', 'in_refund'):
                    domain.extend([('credit', '>', 0), ('debit', '=', 0)])
                else:
                    domain.extend([('credit', '=', 0), ('debit', '>', 0)])
                line_ids = self.env['account.move.line'].search(domain)
                line_ids |= invoice.move_id.line_ids.filtered(
                    lambda r: r.account_id.id == invoice.account_id.id)
                if len(line_ids) > 1:
                    line_ids.with_context(reconcile_v2=True).reconcile()

    @api.model
    def reconcile_with_unrelated(self, payments):
        for payment in payments:
            payment.get_residual()
            if payment.residual:
                sale_partner = payment.sale_line_ids.mapped('partner_id') if payment.sale_line_ids else False
                payment_partner = payment.partner_id
                if sale_partner and sale_partner != payment_partner:
                    if len(sale_partner) > 1:
                        _logger.info('Gemma: Payment has no partner and '
                                     'related sales have several... Skipping reconciliation')
                        continue
                    partner_id = sale_partner
                    payment.write({'partner_id': partner_id.id})
                    if payment.move_id:
                        payment.move_id.write({'partner_id': partner_id.id})
                        payment.move_id.line_ids.write({'partner_id': partner_id.id})
                else:
                    partner_id = payment_partner
                invoice_ids = self.env['account.invoice'].search([('partner_id', '=', partner_id.id),
                                                                  ('residual', '>', 0)],
                                                                 order='date_invoice asc')
                for invoice_id in invoice_ids:
                    if payment.residual:
                        line_ids = payment.move_id.line_ids.filtered(
                            lambda r: r.account_id.id == invoice_id.account_id.id)
                        line_ids |= invoice_id.move_id.line_ids.filtered(
                            lambda r: r.account_id.id == invoice_id.account_id.id)
                        if len(line_ids) > 1:
                            line_ids.with_context(reconcile_v2=True).reconcile()
                        payment.get_residual()
            self.env.cr.commit()

    @api.multi
    def move_creation_prep(self):
        force_creation = True  # Temporally force create
        delay_date = gemma_tools.delay_date()
        do_validate = self._context.get('validate', False)
        payment_ids = self.filtered(
            lambda x: not x.move_id and x.state in ['active', 'warning', 'failed'] and x.payment_type_id.is_active)
        if not force_creation:
            payment_ids = payment_ids.filtered(lambda x: x.payment_date <= delay_date)
        if do_validate:
            payment_ids = self.validator(payment_ids)

        cash_operations = self.filtered(
            lambda x: x.type == 'cash_operations' and x.payment_sum and x.cash_operation_type in ['out'])
        unrelated = payment_ids.filtered(lambda x: x.type == 'unrelated')
        related = payment_ids.filtered(lambda x: x.type == 'related')

        if cash_operations:
            self.with_context(account_code='273', cash_ops=True).create_moves(cash_operations)
        if related:
            self.with_context(do_reconcile=True, use_partner=True, related=True).create_moves(related)
        if unrelated:
            self.with_context(do_reconcile=True, use_partner=True).create_moves(unrelated)

    @api.model
    def create_moves(self, payment_ids):
        do_reconcile = self._context.get('do_reconcile', False)
        use_partner = self._context.get('use_partner', False)
        related = self._context.get('related', False)
        account_code = self._context.get('account_code', '2410')
        account_move_obj = self.env['account.move'].sudo()
        for payment in payment_ids:
            if tools.float_is_zero(payment.payment_sum, precision_digits=2):
                continue
            partner_id = payment.partner_id.id
            partner = payment.sale_line_ids.mapped('invoice_id.partner_id')
            partner_code = payment.sale_line_ids.mapped('buyer_id')
            if len(partner) == 1 and related:
                if payment.partner_id.id != partner.id:
                    partner_id = partner.id
                    payment.with_context(skip_inverse=True).write(
                        {'partner_id': partner.id, 'payer_id': partner_code[0]})
            if not partner_id and not self._context.get('cash_ops', False):
                continue
            if not payment.journal_id:
                continue
            account = self.env['account.account'].search([('code', '=', account_code)])
            move_lines = []
            credit_line = {
                'name': 'Mokėjimas ' + str(payment.ext_payment_id),
            }
            if payment.payment_sum > 0 and payment.cash_operation_type != 'out':
                credit_line['credit'] = payment.payment_sum
                credit_line['debit'] = 0.0
                credit_line['account_id'] = account.id
            else:
                credit_line['debit'] = payment.payment_sum
                credit_line['credit'] = 0.0
                credit_line['account_id'] = account.id

            debit_line = {
                'name': 'Mokėjimas ' + str(payment.ext_payment_id),
            }
            if payment.payment_sum > 0 and payment.cash_operation_type != 'out':
                debit_line['debit'] = payment.payment_sum
                debit_line['credit'] = 0.0
                debit_line['account_id'] = payment.journal_id.default_debit_account_id.id
            else:
                debit_line['credit'] = payment.payment_sum
                debit_line['debit'] = 0.0
                debit_line['account_id'] = payment.journal_id.default_credit_account_id.id

            if use_partner:
                credit_line['partner_id'] = partner_id
                debit_line['partner_id'] = partner_id

            move_lines.append((0, 0, credit_line))
            move_lines.append((0, 0, debit_line))
            move_vals = {
                'line_ids': move_lines,
                'journal_id': payment.journal_id.id,
                'date': payment.payment_date,
            }
            move_id = account_move_obj.create(move_vals)
            try:
                move_id.post()
            except Exception as e:
                self.env.cr.rollback()
                body = _('Nepavyko sukurti mokėjimo įrašo, sisteminė klaida: %s') % e.args[0]
                self.post_message(payment=payment, body=body)
                self.env.cr.commit()
                continue

            payment.move_id = move_id.id
            if do_reconcile and payment.payment_type_id.do_reconcile:
                partner_id = payment.partner_id
                if related:
                    payment.get_residual()
                    if payment.residual:
                        invoice_ids = payment.sale_line_ids.mapped('invoice_id').filtered(lambda x: x.residual > 0)
                        for invoice_id in invoice_ids:
                            if payment.residual:
                                line_ids = move_id.line_ids.filtered(
                                    lambda r: r.account_id.id == invoice_id.account_id.id)
                                line_ids |= invoice_id.move_id.line_ids.filtered(
                                    lambda r: r.account_id.id == invoice_id.account_id.id)
                                if len(line_ids) > 1:
                                    line_ids.with_context(reconcile_v2=True).reconcile()
                                payment.get_residual()
                else:
                    payment.get_residual()
                    if payment.residual:
                        invoice_ids = self.env['account.invoice'].search(
                            [('partner_id', '=', partner_id.id), ('residual', '>', 0)], order='date_invoice asc')
                        for invoice_id in invoice_ids:
                            if payment.residual:
                                line_ids = move_id.line_ids.filtered(
                                    lambda r: r.account_id.id == invoice_id.account_id.id)
                                line_ids |= invoice_id.move_id.line_ids.filtered(
                                    lambda r: r.account_id.id == invoice_id.account_id.id)
                                if len(line_ids) > 1:
                                    line_ids.with_context(reconcile_v2=True).reconcile()
                                payment.get_residual()
            self.env.cr.commit()

    @api.multi
    def reverse_moves(self):
        use_cancel_date = self._context.get('use_cancel_date', False)
        for rec in self:
            if rec.state in ['reconciled', 'partially_reconciled']:
                un_reconcile = True
            else:
                un_reconcile = False
            if rec.move_id and not rec.reverse_move_id:
                credit_lines = rec.move_id.line_ids.filtered(lambda x: x.credit)
                debit_lines = rec.move_id.line_ids.filtered(lambda x: x.debit)
                credit = sum(x.credit for x in credit_lines)
                debit = sum(x.debit for x in debit_lines)
                account_id = rec.env['account.account'].search([('code', '=', '2410')])
                aml = []
                rev_credit = {
                    'name': 'Reverse ' + debit_lines.name,
                    'credit': debit,
                    'debit': 0.0,
                    'account_id': debit_lines.mapped('account_id').id
                }
                rev_debit = {
                    'name': 'Reverse ' + credit_lines.name,
                    'credit': 0.0,
                    'debit': credit,
                    'account_id': credit_lines.mapped('account_id').id
                }
                aml.append((0, 0, rev_credit))
                aml.append((0, 0, rev_debit))
                inverse_vals = {
                    'line_ids': aml,
                    'journal_id': rec.journal_id.id,
                    'partner_id': rec.move_id.partner_id.id,
                    'name': rec.move_id.name + '/Reverse',
                    'date': rec.cancel_date if use_cancel_date else rec.move_id.date
                }
                reverse_move_id = self.env['account.move'].create(inverse_vals)
                try:
                    reverse_move_id.post()
                except Exception as e:
                    self.env.cr.rollback()
                    body = _('Nepavyko sukurti kreditinio mokėjimo įrašo, sisteminė klaida: %s') % e.args[0]
                    self.post_message(payment=rec, body=body)
                    self.env.cr.commit()
                    continue
                if un_reconcile:
                    rec.move_id.mapped('line_ids').remove_move_reconcile()

                line_ids = rec.move_id.line_ids.filtered(lambda r: r.account_id.id == account_id.id)
                line_ids |= reverse_move_id.line_ids.filtered(lambda r: r.account_id.id == account_id.id)
                if len(line_ids) > 1:
                    line_ids.with_context(reconcile_v2=True).reconcile()
                rec.reverse_move_id = reverse_move_id.id
            rec.write({'is_canceled': True})

    def validator(self, payments):
        filtered_payments = self.env['gemma.payment']
        payments.get_journal()
        payments.get_type()
        payments.get_sale_line()
        for payment in payments:
            body = str()
            if payment.type not in ['cash_operations']:
                if not payment.partner_id:
                    sale_partner = payment.sale_line_ids.mapped('partner_id') if payment.sale_line_ids else False
                    payment_partner = payment.partner_id
                    if sale_partner and sale_partner != payment_partner:
                        payment.write({'partner_id': sale_partner.id})
                    if not payment.partner_id:
                        body += _('Klaida kuriant žurnalo įrašą, nerastas partneris!\n')
            if not payment.journal_id:
                body += _('Klaida kuriant žurnalo įrašą, nerastas žurnalas!\n')

            if body:
                msg = {'body': body}
                payment.message_post(**msg)
                payment.state = 'warning'
            else:
                filtered_payments += payment
        return filtered_payments

    @api.one
    def get_partner(self):
        if self._context.get('skip_inverse', False):
            return
        if self.payer_id:
            self.get_partner_base(self.payer_id)
        elif self.sale_line_ids:
            partner_id = self.sale_line_ids.mapped('partner_id')
            partner_code = self.sale_line_ids.mapped('buyer_id')
            if len(partner_id) > 1:
                _logger.info('Payment %s has sales with different partners' % self.ext_payment_id)
            else:
                self.with_context(skip_inverse=True).write({'payer_id': partner_code[0],
                                                            'partner_id': partner_id.id})

    def send_bug(self, body):
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'error_message': body,
        })

    @api.multi
    def unlink(self):
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Negalite ištrinti įrašų!'))
        return super(GemmaPayment, self).unlink()

    @api.multi
    def recompute_fields(self):
        self.set_cash_op_type()
        self.get_type()
        self.get_partner()
        self.get_residual()

    def post_message(self, payment=None, body=None, state='failed'):
        if payment:
            msg = {'body': body}
            payment.message_post(**msg)
            if state is not None:
                payment.write({'state': state})


GemmaPayment()
