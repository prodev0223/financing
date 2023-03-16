# -*- encoding: utf-8 -*-
from __future__ import division
from odoo import models, fields, api, tools, exceptions, _
from lxml import etree
import base64
from ..tools.pdftools import get_embedded_xml_from_pdf


class EInvoiceWizard(models.TransientModel):
    _name = 'e.invoice.wizard'

    xml_data = fields.Binary(string='eSąskaita', required=True)
    xml_name = fields.Char(string='eSąskaitos pavadinimas', size=128, required=False)
    embedded_pdf = fields.Boolean(string='Embedded in PDF')

    @api.multi
    def data_import(self):
        self.ensure_one()
        data = base64.b64decode(self.xml_data)
        if self.embedded_pdf:
            __, data = get_embedded_xml_from_pdf(data)

        invoices = self.parse_einvoice_xml_data(data)
        domain = [('id', 'in', invoices.ids)]
        #FIXME: this handles only out_invoice but use purchase journal ?
        ctx = {
            'activeBoxDomain': "[('state','!=','cancel')]",
            'default_type': "out_invoice",
            'force_order': "recently_updated DESC NULLS LAST",
            'journal_type': "purchase",
            'lang': "lt_LT",
            'limitActive': 0,
            'params': {'action': self.env.ref('robo.open_client_invoice').id},
            'robo_create_new': self.env.ref('robo.new_client_invoice').id,
            'robo_menu_name': self.env.ref('robo.menu_pajamos').id,
            'robo_subtype': "pajamos",
            'robo_template': "RecentInvoices",
            'search_add_custom': False,
            'type': "in_invoice",
            'robo_header': {},
        }
        return {
            'context': ctx,
            'display_name': _('Pajamos'),
            'domain': domain,
            'name': _('Pajamos'),
            'res_model': 'account.invoice',
            'target': 'current',
            'type': 'ir.actions.act_window',
            'header': self.env.ref('robo.robo_button_pajamos').id,
            'view_id': self.env.ref('robo.pajamos_tree').id,
            'view_mode': 'tree_expenses_robo,form,kanban',
            'views': [[self.env.ref('robo.pajamos_tree').id, 'tree_expenses_robo'],
                      [self.env.ref('robo.pajamos_form').id, 'form'],
                      [self.env.ref('robo.pajamos_kanban').id, 'kanban']],
            'with_settings': True,
        }

    @api.model
    def parse_einvoice_xml_data(self, data):
        """
        Convert eInvoice XML to create invoice records
        :param data: eInvoice XML as a str
        :return: AccountInvoice recordset created from the data
        """
        try:
            root = etree.fromstring(data, parser=etree.XMLParser(recover=True))
        except Exception as e:
            raise exceptions.Warning(_('Netinkamas failo formatas. Klaidos pranešimas %s') % e)
        invoices = root.findall('Invoice')
        invoice_ids = self.env['account.invoice']
        AccountAccount = self.env['account.account']

        for invoice in invoices:
            info_block = invoice.find('InvoiceInformation')
            type_block = info_block.find('Type')
            invoice_number = info_block.find('InvoiceNumber').text
            if self.env['account.invoice'].search_count([('move_name', '=', invoice_number)]):
                continue
            partner_block = invoice.find('InvoiceParties')
            partner_id, inv_type_head = self.parse_partner_info(partner_block)
            inv_type = inv_type_head + 'invoice' if type_block.attrib.get('type', 'DEB') == 'DEB' else 'refund'#TODO read type tag CRE/DEB
            sum_block = invoice.find('InvoiceSumGroup')
            # amount_total = float(sum_block.find('TotalSum').text)
            currency_code = sum_block.find('Currency').text
            currency_id = self.env['res.currency'].search([('name', '=', currency_code)])
            #TODO: account should come after we guess who is who ; and should come from journal
            account_id = AccountAccount.search([('code', '=', '2410' if inv_type.startswith('out_') else '4430')])
            journal_id = self.env['account.journal'].search([('type', '=', 'sale' if inv_type.startswith('out_') else 'purchase')], limit=1)
            invoice_lines = []
            invoice_vals = {
                'number': invoice_number if inv_type.startswith('out_') else False,
                'reference': False if inv_type.startswith('out_') else invoice_number,
                'move_name': invoice_number if inv_type.startswith('out_') else False,
                'date_invoice': info_block.find('InvoiceDate').text,
                'date_due': info_block.find('DueDate').text, #seems to be ignored when creating invoice
                'partner_id': partner_id.id,
                'invoice_line_ids': invoice_lines,
                'account_id': account_id.id,
                'journal_id': journal_id.id,
                'currency_id': currency_id.id,
                'external_invoice': True,
                'type': inv_type,
            }
            lines = []
            for group in invoice.find('InvoiceItem').findall('InvoiceItemGroup'):
                lines.extend(group.findall('ItemEntry'))
            for line in lines:
                product_name = line.find('Description').text
                price_unit = float(line.find('ItemDetailInfo').find('ItemPrice').text)
                qty = float(line.find('ItemDetailInfo').find('ItemAmount').text)
                line_total = float(line.find('ItemTotal').text)
                taxes = self.env['account.tax']
                for vat_block in line.findall('VAT'):
                    attrib = vat_block.tag
                    if attrib == 'NOTTAX':
                        tax_id = self.env['account.tax'].search([
                            ('code', '=', 'Ne PVM'),
                            ('type_tax_use', '=', 'purchase' if inv_type_head == 'in_' else 'sale'),
                        ], limit=1)
                    elif attrib == 'TAXEX':
                        tax_id = self.env['account.tax'].search([
                            ('code', '=', 'PVM5'),
                            ('type_tax_use', '=', 'purchase' if inv_type_head == 'in_' else 'sale'),
                        ], limit=1)

                    else:
                        tax_id = self.vat_parser(vat_block, line_total, 'purchase' if inv_type_head == 'in_' else 'sale')
                    if tax_id:
                        taxes |= tax_id

                if not taxes:
                    taxes = self.env['account.tax'].search([
                        ('code', '=', 'PVM1'),
                        ('type_tax_use', '=', 'purchase' if inv_type_head == 'in_' else 'sale')], limit=1)

                product_id = self.env['product.product'].search([('name', '=', 'Paslauga')], limit=1)
                if not product_id:
                    product_vals = {
                        'name': product_name,
                        'acc_product_type': 'service',
                        'type': 'service'
                    }
                    product_id = self.env['product.product'].create(product_vals)

                if inv_type_head == 'out_':
                    product_account = product_id.get_product_income_account(return_default=True)
                else:
                    product_account = product_id.get_product_expense_account(return_default=True)

                line = {
                    'product_id': product_id.id,
                    'name': product_name,
                    'quantity': qty,
                    'price_unit': price_unit,
                    'uom_id': product_id.product_tmpl_id.uom_id.id,
                    'account_id': product_account.id,
                    'invoice_line_tax_ids': [(6, 0, taxes.ids)],
                }
                invoice_lines.append((0, 0, line))

            invoice_id = self.env['account.invoice'].create(invoice_vals)
            body = str()

            # if amount_total and tools.float_compare(amount_total, abs(invoice_id.reporting_amount_total),
            #                                  precision_digits=2) != 0:
            #     body += _('Sukurtos sąskaitos ir importuojamos sąskaitos galutinės sumos nesutampa: %s != %s') % \
            #             (amount_total, invoice_id.reporting_amount_total) todo: skip for now
            if body:
                self.env.cr.rollback()
                continue
            invoice_id.partner_data_force()
            invoice_id.with_context(skip_attachments=True).action_invoice_open()
            self.env.cr.commit() #TODO should we keep that ?
            invoice_ids |= invoice_id
        return invoice_ids

    def parse_partner_info(self, partner_block):
        """
        Parse the Partner info from the InvoiceParties XML block
        :param partner_block: XML block for InvoiceParties
        :return: ResPartner record, invoice type header
        """
        company_code = self.env.user.company_id.company_registry
        seller_block = partner_block.find('SellerParty')
        seller_code = seller_block.find('RegNumber').text
        buyer_block = partner_block.find('BuyerParty')
        buyer_code = buyer_block.find('RegNumber').text

        if company_code == seller_code:
            partner_info = buyer_block
            inv_type_head = 'out_'
        elif company_code == buyer_code:
            partner_info = seller_block
            inv_type_head = 'in_'
        else:
            raise exceptions.UserError(_('Neatitikimas tarp kompanijų!'))

        partner_id = self.env['res.partner'].search([('kodas', '=', partner_info.find('RegNumber').text)])

        if not partner_id and not self._context.get('from_document_processing'):
            partner_id = self.create_partner(partner_info)

        return partner_id, inv_type_head

    def create_partner(self, party):
        """
        Create a partner record from XML party block
        :param party: XML from e-invoice SellerPartyRecord or BillPartyRecord type
        :return: res.partner record
        """
        try:
            full_address = party.find('ContactData').find('LegalAddress').find('PostalAddress1').text
            address_split = full_address.split(',')
        except:
            address_split = None
        try:
            country_id = self.env['res.country'].search([('name', '=', address_split[2].strip())])
        except:
            country_id = self.env['res.country'].sudo().search([('code', '=', 'LT')], limit=1)
        partner_vals = {
            'name': party.find('Name').text,
            'is_company': True,  #TODO:always?
            'kodas': party.find('RegNumber') and party.find('RegNumber').text,
            'street': address_split[0] if address_split is not None else False,
            'city': address_split[1].split(' ')[1] if address_split is not None else False,
            'zip': address_split[1].split(' ')[0] if address_split is not None else False,
            'country_id': country_id.id,
            'property_account_receivable_id': self.env['account.account'].sudo().search(
                [('code', '=', '2410')], limit=1).id,
            'property_account_payable_id': self.env['account.account'].sudo().search(
                [('code', '=', '4430')], limit=1).id,
        }
        partner_id = self.env['res.partner'].create(partner_vals)
        return partner_id

    def vat_parser(self, vat_block, line_total, type_tax_use='sale'):
        """
        Find a matching account.tax record
        :param vat_block: XML VATRecord block
        :param line_total: amount total including tax
        :param type_tax_use: 'sale' or 'purchase'
        :return: account.tax record
        """
        #TODO: maybe use the field SumAfterVAT from XML instead of line_total if it exists ?
        rate = float(vat_block.find('VATRate').text) if vat_block.find('VATRate') is not None else False
        vat_sum = float(vat_block.find('VATSum').text) if vat_block.find('VATSum') is not None else False
        code = False
        for extension in vat_block.findall('Reference'):
            name = extension.find('InformationName')
            if name is None:
                continue
            name = name.text
            if name == 'Code':
                content = extension.find('InformationContent')
                code = content.text
                continue
        tax_id = False
        if rate:
            domain = [('amount', '=', rate),
                      ('type_tax_use', '=', type_tax_use),
                      ('price_include', '=', False)]
            if code:
                tax_id = self.env['account.tax'].search(domain + [('code', '=', code)], limit=1)
            if not tax_id:
                tax_id = self.env['account.tax'].search(domain, limit=1)
        if not tax_id and code:
            tax_id = self.env['account.tax'].search([('code', '=', code),
                                                     ('type_tax_use', '=', type_tax_use),
                                                     ('price_include', '=', False)], limit=1)
        if not tax_id:
            if vat_sum:
                sum_wo_vat = line_total - vat_sum
                # P3:DivOK - both fields are float
                percentage = round(((line_total / sum_wo_vat) - 1) * 100, 0)
            else:
                percentage = 0
            tax_id = self.env['account.tax'].search([('amount', '=', percentage),
                                                     ('type_tax_use', '=', type_tax_use),
                                                     ('price_include', '=', False)], limit=1)
        return tax_id

