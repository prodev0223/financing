# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools, exceptions, _
from lxml import etree, objectify
from lxml.etree import tostring
from itertools import chain
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pyodbc
from pyodbc import OperationalError
from xml.etree.ElementTree import tostring
import pytz

allowed_calc_error = 0.01
vat_code_mapper = {
    1: 21,
    2: 5,
    3: 0
}


class RasoInvoices(models.Model):
    _name = 'raso.invoices'
    _inherit = ['mail.thread']

    shop_no = fields.Char(required=True, string='Parduotuvės numeris', inverse='_set_shop_no')
    pos_no = fields.Char(required=True, string='Kasos numeris')
    last_z = fields.Char(required=True, string='Z numeris')

    invoice_no = fields.Char(required=True, string='Saskaitos numeris', inverse='_set_partner_data')
    partner_code = fields.Char(required=True, string='Partnerio kodas', inverse='_set_partner_data')
    partner_name = fields.Char(required=True, string='Partnerio vardas', inverse='_set_partner_data')
    partner_vat = fields.Char(string='Partnerio PVM kodas')
    partner_address = fields.Char(required=True, string='Partnerio adresas')

    raso_invoice_line_ids = fields.One2many('raso.invoices.line', 'raso_invoice_id', string='Pardavimai')
    raso_payment_line_ids = fields.One2many('raso.payments', 'raso_invoice_id', string='Mokėjimai')

    partner_id = fields.Many2one('res.partner', string='Susietas Partneris', readonly=True)
    shop_id = fields.Many2one('raso.shoplist', string='Parduotuvė')
    pos_id = fields.Many2one('raso.shoplist.registers', string='Kasos aparatas')
    invoice_id = fields.Many2one('account.invoice', string='ROBO sąskaita')
    state = fields.Selection([('imported', 'Sąskaita importuota'),
                              ('created', 'ROBO Sąskaita sukurta sistemoje'),
                              ('failed', 'Klaida kuriant sąskaitą'),
                              ('warning', 'Sąskaita importuota su įspėjimais')],
                             string='Būsena', default='imported', track_visibility='onchange')

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    def _set_partner_data(self):
        """Method used to create or relate already existing partner record for the invoice"""
        # Ref needed objects
        ResPartner = self.env['res.partner'].sudo()
        base_country = self.env['res.country'].sudo().search([('code', '=', 'LT')], limit=1)

        # Ref needed accounts
        account_2410 = self.env.ref('l10n_lt.1_account_229')
        account_4430 = self.env.ref('l10n_lt.1_account_378')

        # Loop through data and create or assign the partners
        for rec in self.filtered(lambda x: not x.partner_id and x.partner_code and x.partner_name):
            partner = ResPartner.search([('kodas', '=', rec.partner_code)])
            if not partner:
                partner_vals = {
                    'name': self.partner_name,
                    'is_company': True,
                    'kodas': self.partner_code,
                    'vat': self.partner_vat,
                    'street': self.partner_address,
                    'country_id': base_country.id,
                    'property_account_receivable_id': account_2410.id,
                    'property_account_payable_id': account_4430.id,
                }
                partner = ResPartner.create(partner_vals)
            rec.partner_id = partner

    @api.multi
    def _set_shop_no(self):
        """On shop no change"""

        # Ref needed objects
        RasoShopList = self.env['raso.shoplist'].sudo()
        RasoShopListRegisters = self.env['raso.shoplist.registers'].sudo()

        for rec in self.filtered(lambda x: x.shop_no):
            pos_rec = RasoShopListRegisters

            # Try to find the shop record, and create it if it does not exist
            shop_rec = RasoShopList.search([('shop_no', '=', rec.shop_no)])
            if not shop_rec:
                shop_rec = RasoShopList.create({
                    'shop_no': self.shop_no,
                    'location_id': False,
                })
            # If shop does not have a generic point of sale, create it
            if not shop_rec.generic_pos:
                shop_rec.create_generic_pos()

            # Then check which pos should be assigned
            if rec.pos_no:
                pos_rec = RasoShopListRegisters.search([
                    ('shop_id', '=', shop_rec.id), ('pos_no', '=', rec.pos_no)])
                if not pos_rec:
                    pos_rec = RasoShopListRegisters.create({
                        'pos_no': rec.pos_no,
                        'shop_id': rec.shop_id.id
                    })

            # Assign the values to current point of sale
            rec.pos_id = pos_rec or shop_rec.generic_pos
            rec.shop_id = shop_rec

    @api.multi
    def recompute_fields(self):
        """Recompute/Re-inverse significant fields before invoice creation"""
        self._set_partner_data()
        self._set_shop_no()

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def validator(self):
        """
        Validates external Raso Retail invoices and filters out
        the data that has insufficient configuration
        :return: recordset: Filtered Raso invoice objects
        """
        RInvoices = self.env['raso.invoices']
        warning_sales_tax = warning_sales_product = warning_no_sales = \
            warning_rec_shop = warning_rec_pos = correct_invoices = RInvoices

        for rec in self:
            rec_lines = rec.raso_invoice_line_ids
            if not rec_lines:
                warning_no_sales |= rec
                continue
            rec_lines.get_has_man()
            rec_lines._compute_tax_id()
            rec_lines._compute_man_tax_id()
            rec_lines.get_product_id()

            if any(not x.tax_id and not tools.float_is_zero(
                    x.amount, precision_digits=2) or not x.man_tax_id and not tools.float_is_zero(
                x.amount_man, precision_digits=2) for x in rec_lines):
                warning_sales_tax |= rec
            elif not all(x.product_id for x in rec_lines):
                warning_sales_product |= rec
            elif not rec.shop_id.location_id:
                warning_rec_shop |= rec
            elif not rec.pos_id.journal_id or not rec.pos_id.partner_id:
                warning_rec_pos |= rec
            else:
                correct_invoices |= rec

        if warning_sales_tax:
            self.post_message(lines=warning_sales_tax.mapped('raso_invoice_line_ids'),
                              body='Eilutė neturi nustatytų mokesčių',
                              state='failed', invoices=warning_sales_tax,
                              inv_body='Bent viena iš sąskaitos eilučių neturi nustatytų mokesčių')
        if warning_sales_product:
            self.post_message(lines=warning_sales_product.mapped('raso_invoice_line_ids'),
                              body='Produktas nerastas sistemoje',
                              state='failed', invoices=warning_sales_product,
                              inv_body='Bent viena iš sąskaitos eilučių neturi produkto')
        if warning_no_sales:
            self.post_message(invoices=warning_no_sales, inv_body='Sąskaita neturi eilučių', state='failed')
        if warning_rec_shop:
            self.post_message(invoices=warning_rec_shop,
                              inv_body='Sąskaita neturi parduotuvės arba ji nėra sukonfigūruota', state='failed')
        if warning_rec_pos:
            self.post_message(invoices=warning_rec_pos,
                              inv_body='Sąskaita neturi kasos aparato arba jis nėra sukonfigūruota', state='failed')

        return correct_invoices

    @api.multi
    def create_invoices(self):
        invoices = self.validator()
        invoices = invoices.filtered(lambda inv: not inv.invoice_id)
        account = self.env['account.account'].sudo().search([('code', '=', '2410')], limit=1)

        # Ref needed objects
        InvoiceDeliveryWizard = self.env['invoice.delivery.wizard'].sudo()
        AccountInvoice = self.env['account.invoice'].sudo()

        # Get base tax record to use for sales with 0 amount that must be displayed
        # in invoices and do not have amounts that can be used to parse tax percentage.
        # It does not matter which tax record is used, since there's no taxable value
        # thus PVM1 is used in cases like this
        base_tax = self.env['account.tax'].search(
            [('code', '=', 'PVM1'), ('price_include', '=', True), ('type_tax_use', '=', 'sale')]
        )
        for ext_invoice in invoices:

            invoice_lines = []
            raso_inv_lines = ext_invoice.raso_invoice_line_ids
            inv_values = {
                'journal_id': ext_invoice.pos_id.journal_id.id,
                'move_name': ext_invoice.invoice_no,
                'number': ext_invoice.invoice_no,
                'invoice_line_ids': invoice_lines,
                'external_invoice': True,
                'price_include_selection': 'inc',
                'account_id': account.id,
                'type': raso_inv_lines[0].line_type,
                'partner_id': ext_invoice.partner_id.id or ext_invoice.pos_id.partner_id.id,
                'date_invoice': ext_invoice.raso_invoice_line_ids[0].sale_date,
                'operacijos_data': ext_invoice.raso_invoice_line_ids[0].sale_date,
                'imported_api': True,
                'force_dates': True,
            }
            amount_total = 0
            for sale_line in raso_inv_lines:
                product_account = sale_line.product_id.get_product_income_account(return_default=True)
                tax_to_use = sale_line.tax_id if sale_line.tax_id else sale_line.man_tax_id or base_tax
                qty_wo_discount = sale_line.qty
                qty_w_discount = sale_line.qty_man
                amount_to_add = sale_line.amount + sale_line.amount_man
                if qty_wo_discount:
                    line = {
                        'product_id': sale_line.product_id.id,
                        'name': sale_line.product_id.name,
                        'quantity': abs(qty_wo_discount),
                        'price_unit': abs(sale_line.price_unit),
                        'uom_id': sale_line.product_id.product_tmpl_id.uom_id.id,
                        'discount': sale_line.discount,
                        'account_id': product_account.id,
                        'invoice_line_tax_ids': [(6, 0, tax_to_use.ids)],
                        'raso_inv_line_id': sale_line.id
                    }
                    invoice_lines.append((0, 0, line))

                if qty_w_discount:
                    line = {
                        'product_id': sale_line.product_id.id,
                        'name': sale_line.product_id.name,
                        'quantity': abs(qty_w_discount),
                        'price_unit': abs(sale_line.price_unit_man),
                        'uom_id': sale_line.product_id.product_tmpl_id.uom_id.id,
                        'account_id': product_account.id,
                        'invoice_line_tax_ids': [(6, 0, tax_to_use.ids)],
                        'raso_inv_line_id': sale_line.id
                    }

                    invoice_lines.append((0, 0, line))
                amount_total += abs(amount_to_add)

            try:
                invoice = AccountInvoice.create(inv_values)
                msg = str()
                if tools.float_compare(amount_total, abs(invoice.reporting_amount_total), precision_digits=2):
                    diff = abs(invoice.reporting_amount_total - amount_total)
                    if tools.float_compare(diff, allowed_calc_error, precision_digits=2) > 0:
                        msg += _('RASO sąskaitos galutinė suma nesutampa su paskaičiuota suma(%s != %s).\n') % (
                            amount_total, invoice.reporting_amount_total)
                if msg:
                    self.env.cr.rollback()
                    self.post_message(raso_inv_lines, msg, 'failed', ext_invoice, msg)
                    self.env.cr.commit()
                    continue

                ext_invoice.invoice_id = invoice
                invoice.raso_invoice_id = ext_invoice.id
                ext_invoice.state = 'created'
                raso_inv_lines.write({'state': 'created'})
            except Exception as e:
                self.env.cr.rollback()
                body = _('Nepavyko sukurti sąskaitos, sisteminė klaida %s') % e
                self.post_message(raso_inv_lines, body, 'failed', ext_invoice, body)
                self.env.cr.commit()
                continue

            invoice.partner_data_force()
            invoice.action_invoice_open()

            wizard = InvoiceDeliveryWizard.with_context(invoice_id=invoice.id).create({
                'location_id': ext_invoice.shop_id.location_id.id,
            })
            wizard.create_delivery()
            if invoice.picking_id:
                invoice.picking_id.action_assign()
                if invoice.picking_id.state == 'assigned':
                    invoice.picking_id.do_transfer()
            ext_invoice.raso_payment_line_ids.move_creation_prep()
            self.env.cr.commit()

    @api.multi
    def create_payment_moves(self):
        for rec in self:
            payments = rec.raso_payment_line_ids.filtered(lambda x: not x.move_id)
            payments.move_creation_prep()

    # CRUD ------------------------------------------------------------------------------------------------------------

    @api.multi
    def unlink(self):
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Negalite ištrinti įrašų!'))
        if any(rec.invoice_id for rec in self):
            raise exceptions.UserError(_('Negalima ištrinti sąskaitos kuri pririšta prie sisteminės sąskaitos!'))
        self.mapped('raso_invoice_line_ids').unlink()
        self.mapped('raso_payment_line_ids').unlink()
        return super(RasoInvoices, self).unlink()

    # Helper Methods --------------------------------------------------------------------------------------------------

    @api.multi
    def name_get(self):
        return [(inv.id, inv.invoice_no) for inv in self]

    def post_message(self, lines=None, body=None, state=None, invoices=None, inv_body=None):
        if lines is None:
            lines = self.env['raso.invoices.line']
        if invoices is None:
            invoices = self.env['raso.invoices']

        send = {
            'body': body,
        }
        for line in lines:
            line.message_post(**send)
        lines.write({'state': state})

        send = {
            'body': inv_body,
        }
        for invoice in invoices:
            invoice.message_post(**send)
        invoices.write({'state': state})
