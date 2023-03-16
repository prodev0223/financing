# -*- coding: utf-8 -*-

from odoo import models, fields, _, api, tools
from . import nsoft_tools
import logging

_logger = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    nsoft_payment_move_ids = fields.Many2many('nsoft.payment', string='nSoft Sąskaitos mokėjimai')
    nsoft_line_ids = fields.One2many('nsoft.sale.line', 'invoice_id',
                                     string='nSoft pardavimų eilutės')
    nsoft_refund_line_ids = fields.One2many('nsoft.sale.line', 'refund_id',
                                            string='nSoft pardavimų eilutės kred.')
    nsoft_correction_line_ids = fields.One2many('nsoft.sale.line', 'correction_id',
                                                string='nSoft pardavimų eilutės kor.')
    nsoft_inv_line_ids = fields.One2many('nsoft.invoice.line', 'invoice_id', string='nSoft sąskaitos eilutė')

    # Field is only used to preserve the data up to the change point
    nsoft_payment_move = fields.Many2one('account.move', string='nSoft mokėjimo įrašas')

    @api.multi
    def action_invoice_open(self):
        """
        Call action invoice open on two different record-sets:
        attachments are skipped for integration_purchase_invoices (type 'in..' and external_invoice = True)
        other invoices are processed without any changes
        :return: True/False
        """
        res = False
        integration_purchase_invoices = self.filtered(
            lambda x: x.type in ['in_invoice', 'in_refund'] and x.sudo().external_invoice)
        other_invoices = self.filtered(lambda x: x.id not in integration_purchase_invoices.ids)
        if integration_purchase_invoices:
            res = super(AccountInvoice, integration_purchase_invoices.with_context(
                skip_attachments=True)).action_invoice_open()
        if other_invoices:
            res &= super(AccountInvoice, other_invoices).action_invoice_open()
        return res

    @api.multi
    def create_nsoft_delivery(self, location_id):
        """
        Create and confirm picking if robo_stock is installed
        :param location_id: picking location_source_id
        :return: None
        """

        delivery_wizard = self.env['invoice.delivery.wizard'].sudo()
        for invoice_id in self:
            rec = self.sudo().env['ir.module.module'].search([('name', '=', 'robo_stock')])
            if rec and rec.state in ['installed', 'to upgrade']:
                wizard_id = delivery_wizard.with_context(invoice_id=invoice_id.id).create(
                    {'location_id': location_id.id})
                wizard_id.create_delivery()
                if invoice_id.picking_id and invoice_id.picking_id.state != 'done':
                    try:
                        invoice_id.picking_id.action_assign()
                    except Exception as e:
                        body = _('Nepavyko rezervuoti prekių sukurtai sąskaitai, '
                                 'klaidos pranešimas: %s') % str(e.args[0])
                        return body
                    if invoice_id.picking_id.state == 'assigned':
                        invoice_id.picking_id.do_transfer()
                if self._context.get('consignation', False):
                    picks = self.env['stock.picking'].search([('origin', '=', self.number)])
                    picks |= invoice_id.picking_id
                    picks = picks.filtered(lambda x: x.state in ['partially_available', 'confirmed'])
                    for picking_id in picks:
                        picking_id.force_assign()
                        picking_id.do_transfer()

    @api.multi
    def force_invoice_tax_amount(self, forced_tax_amount):
        """
        Force eligible tax amount to account.invoice record by adding the difference to the tax lines
        and subtracting it from the account invoice line.
        :param forced_tax_amount: eligible tax amount in the account.invoice
        :return: None
        """
        for rec in self.filtered(
                lambda x: x.tax_line_ids and tools.float_compare(x.amount_tax, forced_tax_amount, precision_digits=2)):
            diff = tools.float_round(forced_tax_amount - rec.amount_tax, precision_digits=2)
            # Try to apply the normalization up to three times,
            # since sometimes values are lost due to lots of roundings
            for it in range(3):
                line = rec.invoice_line_ids[0]
                new_amount = line.amount_depends - diff
                line.write({
                    'amount_depends': new_amount,
                    'price_subtotal_make_force_step': True,
                    'price_subtotal_save_force_value': new_amount
                })
                line.with_context(direct_trigger_amount_depends=True).onchange_amount_depends()
                rec.tax_line_ids[0].write({'amount': rec.tax_line_ids[0].amount + diff})
                rec.write({'force_taxes': True})

                # Break the loop if difference is evened out
                diff = tools.float_round(forced_tax_amount - rec.amount_tax, precision_digits=2)
                if tools.float_is_zero(diff, precision_digits=2):
                    break

    @api.multi
    def check_invoice_amounts(self, amount_data):
        """
        Compare external invoice amounts with account invoice amounts
        if amounts to not match and error is not allowed, or if error is allowed, but
        mismatch exceeds allowed amount -- add error string to parent error_body
        :param amount_data: list of tuples containing:
            -account.invoice field name (str)
            -external invoice amount (float)
            -is error allowed (bool)
        :return: error_body (str)
        """
        self.ensure_one()
        error_body = str()
        for key, ext_amount, allow_error in amount_data:
            invoice_amount = abs(getattr(self, key))
            ext_amount = abs(ext_amount)
            if (tools.float_compare(ext_amount, invoice_amount, precision_digits=2) != 0 and not allow_error) or \
                    (allow_error and tools.float_compare(
                        abs(invoice_amount - ext_amount), nsoft_tools.ALLOWED_TAX_CALC_ERROR, precision_digits=2) > 0):
                error_body += _('Importuotos ir sukurtos sisteminės sąskaitos sumos nesutampa (%s != %s) -- %s\n') % (
                    abs(ext_amount), abs(invoice_amount), nsoft_tools.FIELD_TO_READABLE_MAPPING[key])
        return error_body

    @api.multi
    def confirm_related_pickings(self):
        """
        Confirm (assign or transfer)
        related pickings of account.invoice records
        :return: None
        """
        pickings = self.mapped('picking_id')
        for picking in pickings:
            self.env.cr.commit()
            if picking.state in ['confirmed']:
                picking.action_assign()
            if picking.state in ['assigned', 'partially_available']:
                try:
                    picking.do_transfer()
                except Exception as exc:
                    self.env.cr.rollback()
                    _logger.info(exc.args[0])


AccountInvoice()
