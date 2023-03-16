# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, tools, exceptions
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class GemmaInvoice(models.Model):
    _name = 'gemma.invoice'
    _inherit = ['mail.thread', 'gemma.base']

    name = fields.Char(string='Sąskaitos numeris')
    ext_invoice_id = fields.Integer(string='Išorinis sąskaitos numeris')
    payment_numbers = fields.Char(inverse='get_payments')
    date_invoice = fields.Datetime(string='Sąskaitos data')
    company_id = fields.Integer(string='Kompanijos numeris')
    partner_code = fields.Char(string='Pirkėjo asmens kodas')
    partner_name = fields.Char(string='Pirkėjo vardas')
    partner_surname = fields.Char(string='Pirkėjo pavardė')
    partner_birthday = fields.Datetime(string='Pirkėjo gimimo data')
    invoice_total = fields.Float(string='Sąskaitos suma', compute='get_total')
    buyer_id = fields.Char(string='Pirkėjo numeris', inverse='get_partner')

    partner_id = fields.Many2one('res.partner', string='Partneris')
    sale_line_ids = fields.One2many('gemma.sale.line', 'ext_invoice_id', string='Sąskaitos faktūros eilutės')
    payment_ids = fields.One2many('gemma.payment', 'ext_invoice_id', string='Susije Mokėjimai')

    state = fields.Selection([('imported', 'Sąskaita importuota'),
                              ('created', 'Sąskaita sukurta sistemoje'),
                              ('failed', 'Klaida kuriant sąskaitą'),
                              ('warning', 'Sąskaita importuota su įspėjimais')],
                             string='Būsena', default='imported', track_visibility='onchange')

    invoice_id = fields.Many2one('account.invoice', string='Sukurta sąskaita faktūra')
    correction_id = fields.Many2one('account.invoice', string='Koreguota sąskaita faktūra')

    @api.model
    def server_action_invoices_i(self):
        action = self.env.ref('gemma.server_action_invoice_i')
        if action:
            action.create_action()

    @api.multi
    def invoice_action(self):
        delayed_invoices = self.filtered(lambda x: x.sale_line_ids.mapped('invoice_id') and not x.invoice_id)
        invoices = self.filtered(lambda x: not x.sale_line_ids.mapped('invoice_id') and not x.invoice_id)
        if invoices:
            self.env['gemma.sale.line'].with_context(
                validate=True).invoice_creation_prep(invoice_ids=self, sale_ids=self.env['gemma.sale.line'])
        if delayed_invoices:
            self.env['gemma.sale.line'].delayed_invoice_prep(invoice_ids=delayed_invoices)

    @api.one
    @api.depends('sale_line_ids')
    def get_total(self):
        if self.sale_line_ids:
            self.invoice_total = sum(abs(line.price * line.qty) for line in self.sale_line_ids)

    @api.one
    def get_partner(self):
        self.get_partner_base(self.buyer_id)

    @api.one
    def get_payments(self):
        if self.payment_numbers:
            if ',' in self.payment_numbers:
                pay_ids = self.payment_numbers.split(',')
                pay_ids = list(map(int, pay_ids))
                lines = self.env['gemma.payment'].search([('ext_payment_id', 'in', pay_ids)])
                if lines:
                    for payment in lines:
                        payment.ext_invoice_id = self.id
                        for sale in payment.sale_line_ids:
                            sale.ext_invoice_id = self.id
            else:
                payment = self.env['gemma.payment'].search([('ext_payment_id', '=', int(self.payment_numbers))])
                payment.write({'ext_invoice_id': self.id})
                for sale in payment.sale_line_ids:
                    sale.ext_invoice_id = self.id

    @api.multi
    def name_get(self):
        return [(rec.id, _('Sąskaita ') + str(rec.ext_invoice_id)) for rec in self]

    @api.multi
    def unlink(self):
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Negalima ištrinti Gemma sąskaitos faktūros!'))
        if self.mapped('invoice_id'):
            raise exceptions.UserError(_('Negalima ištrinti sąskaitos kuri pririšta prie sisteminės sąskaitos!'))
        return super(GemmaInvoice, self).unlink()

    def send_bug(self, body):
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'error_message': body,
        })

    def post_message(self, lines=None,
                     l_body=None, state=None, invoice=None, i_body=None):
        if lines is None:
            lines = self.env['gemma.sale.line']
        if invoice is None:
            invoice = self.env['gemma.invoice']
        if lines:
            msg = {'body': l_body}
            for line in lines:
                line.message_post(**msg)
            if state is not None:
                lines.write({'state': state})
        if invoice:
            msg = {'body': i_body}
            invoice.message_post(**msg)
            if state is not None:
                invoice.state = state

    @api.multi
    def unlink(self):
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Negalite ištrinti įrašų!'))
        return super(GemmaInvoice, self).unlink()


GemmaInvoice()
