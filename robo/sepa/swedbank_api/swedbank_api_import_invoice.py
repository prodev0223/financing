# -*- encoding: utf-8 -*-
from __future__ import division
from odoo import fields, models, _, api, exceptions, tools
from datetime import datetime
import os
import subprocess32 as subprocess
from lxml import etree, objectify
from dateutil.relativedelta import relativedelta
from odoo.addons.sepa import api_bank_integrations as abi
import swedbank_tools as st


class SwedBankAPIImportInvoice(models.TransientModel):
    _name = 'swed.bank.api.import.invoice'
    _description = 'Transient model that is used for automatic bank statement exports from SwedBank using API solutions'

    def _export_line_ids(self):
        line_ids = []
        if self._context.get('invoice_ids', False):
            invoice_ids = self._context.get('invoice_ids', False)
            invoices_to_pay = self.env['account.invoice'].browse(invoice_ids).filtered(
                lambda r: r.state in ['open'] and r.currency_id.name == 'EUR' and r.type in ['out_invoice'])
            for invoice_id in invoices_to_pay:
                vals = {
                    'partner_id': invoice_id.partner_id.id,
                    'invoice_id': invoice_id.id,
                    'amount': invoice_id.residual,
                    'name': invoice_id.move_name or invoice_id.number
                }
                line = self.env['e.invoice.export.line'].create(vals)
                line_ids.append(line.id)
        return [(6, 0, line_ids)]

    @api.model
    def _company_bank_account(self):
        res = self.env['account.journal'].search(
            [('api_integrated_bank', '=', True),
             ('currency_id', '=', False),
             ('api_bank_type', '=', 'swed_bank')], limit=1)
        if not res:
            raise exceptions.Warning(_('Operacija negalima, kompanija neturi "Swedbank" sąskaitos!'))
        return res

    export_line_ids = fields.Many2many('e.invoice.export.line', string='Mokėjimai', default=_export_line_ids)
    company_bank_account = fields.Many2one('account.journal', string='Kompanijos banko sąskaita',
                                           domain=[('api_integrated_bank', '=', True),
                                                   ('currency_id', '=', False),
                                                   ('api_bank_type', '=', 'swed_bank')],
                                           default=_company_bank_account, required=True)
    outstanding_invoice_names = fields.Text(compute='_outstanding_invoice_names')

    @api.one
    @api.depends('export_line_ids')
    def _outstanding_invoice_names(self):
        text = str()
        for invoice_id in self.export_line_ids.mapped('invoice_id').filtered(lambda x: x.has_outstanding):
            name = invoice_id.reference if invoice_id.reference else \
                invoice_id.number or invoice_id.proforma_number
            text += ', {}'.format(name) if text else '{}'.format(name)
        self.outstanding_invoice_names = text

    @api.multi
    def check_e_invoice_constraints(self, mode='raise'):
        filtered_records = self.env['e.invoice.export.line']
        agr_id = self.env.user.sudo().company_id.swed_bank_agreement_id
        global_e_invoice_agreement_id = self.env.user.sudo().company_id.global_e_invoice_agreement_id
        e_invoice_agreement_date = self.env.user.sudo().company_id.e_invoice_agreement_date
        date_today = datetime.now() + relativedelta(hour=0, minute=0, second=0, microsecond=0)
        body = global_errors = str()
        if not agr_id:
            global_errors += _('Nesukonfigūruotas Swedbank susitarimo identifikatorius!\n')
        if not global_e_invoice_agreement_id:
            global_errors += _('Nesukonfigūruotas Swedbank susitarimo identifikatorius!\n')
        if not e_invoice_agreement_date:
            global_errors += _('Nesukonfigūruota eSąskaitų aktyvavimo data!\n')
        if not self.export_line_ids:
            global_errors += _('Nepaduota nė viena sąskaita\n')
        # Make a separate variable for global errors and append
        # it to the composite message body after the checks
        body += global_errors
        for e_line in self.export_line_ids:
            line_body = str()
            # Triggered if amounts do not match
            if tools.float_is_zero(e_line.invoice_id.residual, precision_digits=2):
                line_body += _('Negalima eksportuoti apmokėtos sąskaitos %s \n' % e_line.invoice_id.move_name)
            if not e_line.res_partner_bank_id:
                line_body += _('Sąskaita %s neturi pasirinkto partnerio banko sąskaitos '
                               'numerio \n' % e_line.invoice_id.move_name)
            if not e_line.invoice_id.date_due:
                line_body += _('Sąskaita %s neturi mokėjimo termino datos \n' % e_line.invoice_id.move_name)
            if e_line.invoice_id.bank_export_state not in abi.EXPORTABLE_STATES:
                line_body += _("Sąskaitos %s banko eksportavimo būsena yra '%s'. Eksportas galimas tik šiose "
                               "būsenose - 'Neeksportuota', 'Atmesta'\n" %
                               (e_line.invoice_id.move_name, e_line.invoice_id.bank_export_state))
            if e_line.invoice_id.date_due and e_invoice_agreement_date:
                date_due_dt = datetime.strptime(e_line.invoice_id.date_due, tools.DEFAULT_SERVER_DATE_FORMAT)
                e_invoice_agreement_date_dt = datetime.strptime(e_invoice_agreement_date,
                                                                tools.DEFAULT_SERVER_DATE_FORMAT)
                delta = (date_due_dt - date_today).days
                if date_due_dt < e_invoice_agreement_date_dt:
                    line_body += _('Sąskaitos %s mokėjimo terminas yra ankstesnis negu eSąskaitų aktyvavimo '
                                   'data\n %s' % (e_line.invoice_id.move_name, e_invoice_agreement_date))
                    body += line_body
                if date_today < e_invoice_agreement_date_dt:
                    line_body += _('eSąskaitų aktyvavymo data yra vėlesnė nei šiandiena')
                    body += line_body
                if delta < 3:
                    line_body += _('Sąskaitos %s mokėjimo terminas turi būti vėlesnis bent trimis '
                                   'dienomis už šiandienos data \n' % e_line.invoice_id.move_name)
            if e_line.invoice_id.type == 'out_refund':
                line_body += _('Negalima generuoti kreditinių eSąskaitų - Sąskaita %s \n' % e_line.invoice_id.move_name)
            body += line_body
            # If there's no line level errors and no global errors,
            # append the line to filtered records
            if not line_body and not global_errors:
                filtered_records += e_line
            # Otherwise post the error with global errors and line errors to the invoice
            elif mode == 'filter':
                e_line.invoice_id.message_post(
                    body='Nepavyko automatiškai sugeneruoti eSąskaitos. Pranešimas: ' + global_errors + line_body)
        if mode == 'raise':
            if body:
                error_message = 'Eksportavimas nepavyko dėl šių priežaščių: \n' + body
                raise exceptions.ValidationError(error_message)
        elif mode == 'filter':
            return filtered_records

    @api.multi
    def format_e_invoice_xml(self, forced_data=None):
        """
        Method that is used to generate eInvoice xml | eInvoice version - 1.1.
        Validation file is eInvoice-1.1-LT.xsd schema
        :return: eInvoice XML in str format, eInvoice request XML in str format
        """
        data_to_use = forced_data if forced_data is not None else self.export_line_ids
        if not data_to_use:
            return

        def set_node(node, key, value, skip_empty=False):
            if skip_empty and not value:
                return
            if not skip_empty and not value and not isinstance(value, tuple([int, float, long])):
                raise exceptions.Warning('Tuščia reikšmė privalomam elementui %s' % key)
            el = etree.Element(key)
            if isinstance(value, tuple([int, float, long])) and not isinstance(value, bool):
                value = str(value)
            if value:
                el.text = value
            setattr(node, key, el)

        def set_tag(node, tag, value):
            if isinstance(value, (float, int)) and not isinstance(value, bool):
                value = str(value)
            node.attrib[tag] = value

        company_id = self.env.user.sudo().company_id
        agr_id = company_id.swed_bank_agreement_id
        global_e_invoice_agreement_id = self.env.user.sudo().company_id.global_e_invoice_agreement_id
        if not agr_id:
            raise exceptions.Warning(_('Nėra aktyvuota Swedbank Gateway paslauga!'))

        e_xml_template = '''<?xml version="1.0" encoding="UTF-8"?>
                                <E_Invoice xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
                                </E_Invoice>
                                '''
        e_root = objectify.fromstring(e_xml_template)
        e_head = objectify.Element('Header')
        e_root.append(e_head)
        db_name = self.env.cr.dbname
        file_id = self.env['ir.sequence'].next_by_code('swed.bank.e.invoice.seq') + '__' + db_name  # maybe commit
        date = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        set_node(e_head, 'Date', date)
        set_node(e_head, 'FileId', file_id)
        set_node(e_head, 'AppId', 'EINVOICE')
        set_node(e_head, 'Version', '1.1')

        total_inv_number = 0
        total_amount = 0.0
        for e_line in data_to_use:
            if e_line.invoice_id.state not in ['open', 'paid']:
                raise exceptions.Warning('Negalima įkelti juodraštinių sąskaitų')
            # Use residual amount as the amount to be invoiced
            amount_to_invoice = e_line.invoice_id.residual
            e_invoice = objectify.Element('Invoice')
            global_code = str(e_line.invoice_id.id) + '__' + db_name
            number = e_line.invoice_id.number or e_line.invoice_id.move_name
            set_tag(e_invoice, 'invoiceId', number)
            set_tag(e_invoice, 'serviceId', e_line.partner_id.sudo().e_invoice_service_id or e_line.partner_id.id)
            set_tag(e_invoice, 'regNumber', e_line.invoice_id.partner_id.kodas or '')
            set_tag(e_invoice, 'channelId', e_line.res_partner_bank_id.bank_id.bic)
            set_tag(e_invoice, 'channelAddress', e_line.res_partner_bank_id.acc_number)
            set_tag(e_invoice, 'presentment', 'YES')
            set_tag(e_invoice, 'invoiceGlobUniqId', global_code)
            set_tag(e_invoice, 'globalSellerContractId', global_e_invoice_agreement_id)
            set_tag(e_invoice, 'sellerRegNumber', company_id.company_registry)

            # -Invoice parties
            ei_parties = objectify.Element('InvoiceParties')
            s_party = objectify.Element('SellerParty')
            b_party = objectify.Element('BuyerParty')

            ei_parties.append(s_party)
            ei_parties.append(b_party)

            total_inv_number += 1
            total_amount += amount_to_invoice

            # --Seller party
            set_node(s_party, 'Name', company_id.name)
            set_node(s_party, 'RegNumber', company_id.company_registry)
            set_node(s_party, 'VATRegNumber', company_id.vat, skip_empty=True)
            s_party_ai = objectify.Element('AccountInfo')
            set_node(s_party_ai, 'IBAN', self.company_bank_account.bank_acc_number)
            s_party.append(s_party_ai)

            # --Buyer party
            set_node(b_party, 'Name', e_line.invoice_id.partner_id.name)
            set_node(b_party, 'RegNumber', e_line.invoice_id.partner_id.kodas)
            set_node(b_party, 'VATRegNumber', e_line.invoice_id.partner_id.vat, skip_empty=True)
            e_invoice.append(ei_parties)

            # -Invoice information
            ei_info = objectify.Element('InvoiceInformation')
            ei_type = objectify.Element('Type')
            set_tag(ei_type, 'type', 'CRE' if 'refund' in e_line.invoice_id.type else 'DEB')
            ei_info.append(ei_type)
            set_node(ei_info, 'DocumentName', 'E_INV')
            set_node(ei_info, 'InvoiceNumber', number)
            set_node(ei_info, 'InvoiceDate', e_line.invoice_id.date_invoice)
            set_node(ei_info, 'DueDate', e_line.invoice_id.date_due)
            e_invoice.append(ei_info)

            # -Invoice sum group
            ei_sum = objectify.Element('InvoiceSumGroup')
            set_node(ei_sum, 'InvoiceSum', e_line.invoice_id.amount_untaxed)
            set_node(ei_sum, 'TotalVATSum', e_line.invoice_id.amount_tax)
            set_node(ei_sum, 'TotalSum', amount_to_invoice)
            set_node(ei_sum, 'Currency', e_line.invoice_id.currency_id.name)
            e_invoice.append(ei_sum)

            # -Invoice invoice item
            ei_item = objectify.Element('InvoiceItem')

            vat_payer = company_id.sudo().with_context(date=e_line.invoice_id.get_vat_payer_date()).vat_payer
            for en, line in enumerate(e_line.invoice_id.invoice_line_ids, 1):
                ei_group = objectify.Element('InvoiceItemGroup')
                ei_item.append(ei_group)
                set_tag(ei_group, 'groupId', line.id)

                ei_entry = objectify.Element('ItemEntry')
                ei_group.append(ei_entry)

                set_node(ei_entry, 'RowNo', en)
                set_node(ei_entry, 'SerialNumber', line.product_id.default_code, skip_empty=True)
                set_node(ei_entry, 'SellerProductId', line.product_id.id, skip_empty=True)
                set_node(ei_entry, 'Description', line.name)
                set_node(ei_entry, 'EAN', line.product_id.barcode, skip_empty=True)
                det_info = objectify.Element('ItemDetailInfo')

                if not tools.float_is_zero(line.quantity, precision_digits=2):
                    # P3:DivOK
                    item_price = tools.float_round(line.price_subtotal / line.quantity, precision_digits=2)
                else:
                    item_price = line.price_subtotal

                set_node(det_info, 'ItemAmount', line.quantity)
                set_node(det_info, 'ItemPrice', item_price)
                ei_entry.append(det_info)
                set_node(ei_entry, 'ItemSum', line.price_subtotal)

                for tax in line.invoice_line_tax_ids:
                    code = tax.code or ''
                    if code.startswith('A') or code.startswith('S'):
                        continue
                    vat_info = objectify.Element('VAT')
                    set_node(vat_info, 'VATRate', tax.amount)
                    if not vat_payer:
                        set_tag(vat_info, 'vatId', 'NOTTAX')
                    elif tools.float_is_zero(tax.amount, precision_digits=2):
                        set_tag(vat_info, 'vatId', 'TAXEX')
                    else:
                        set_tag(vat_info, 'vatId', 'TAX')

                    code_info = objectify.Element('Reference')
                    set_node(code_info, 'InformationName', 'Code')
                    set_node(code_info, 'InformationContent', code)
                    vat_info.append(code_info)
                    ei_entry.append(vat_info)

                set_node(ei_entry, 'ItemTotal', line.total_with_tax_amount)
                ei_g_entry = objectify.Element('GroupEntry')
                ei_group.append(ei_g_entry)
                set_node(ei_g_entry, 'GroupAmount', line.quantity)
                set_node(ei_g_entry, 'GroupSum', line.price_subtotal)

            ei_group_tot = objectify.Element('InvoiceItemTotalGroup')
            ei_item.append(ei_group_tot)
            e_invoice.append(ei_item)
            set_node(ei_group_tot, 'InvoiceItemTotalSum', e_line.invoice_id.amount_untaxed)
            # set_node(ei_group_tot, 'InvoiceItemTotalAmount', invoice.amount_total)

            # -Invoice payment info
            ei_pmt_info = objectify.Element('PaymentInfo')
            set_node(ei_pmt_info, 'Currency', e_line.invoice_id.currency_id.name)
            set_node(ei_pmt_info, 'PaymentRefId', e_line.name or '')
            set_node(ei_pmt_info, 'Payable', 'YES')
            set_node(ei_pmt_info, 'PayDueDate', e_line.invoice_id.date_due)
            set_node(ei_pmt_info, 'PaymentTotalSum', amount_to_invoice)
            set_node(ei_pmt_info, 'PaymentId', e_line.invoice_id.move_name)
            set_node(ei_pmt_info, 'PayToAccount', self.company_bank_account.bank_acc_number)
            set_node(ei_pmt_info, 'PayToName', company_id.name)
            e_invoice.append(ei_pmt_info)

            set_node(ei_sum, 'InvoiceSum', e_line.invoice_id.amount_untaxed)
            set_node(ei_sum, 'TotalVATSum', e_line.invoice_id.amount_tax)
            set_node(ei_sum, 'TotalSum', amount_to_invoice)
            e_root.append(e_invoice)

        e_foot = objectify.Element('Footer')
        e_root.append(e_foot)
        set_node(e_foot, 'TotalNumberInvoices', total_inv_number)
        set_node(e_foot, 'TotalAmount', total_amount)

        date = datetime.utcnow().strftime('%m-%d-%Y_%H%M%S')

        filename = 'e_invoices_' + db_name + '__' + date + '.xml'
        objectify.deannotate(e_root)
        etree.cleanup_namespaces(e_root)
        string_repr = etree.tostring(e_root, xml_declaration=True, encoding='utf-8')
        req_filename = 'e_invoices_' + db_name + '__' + date + '-request.xml'

        req_xml_template = '''<?xml version="1.0" encoding="UTF-8"?>
                                <EinvoiceIncoming>
                                </EinvoiceIncoming>
                                '''
        req_root = objectify.fromstring(req_xml_template)
        set_node(req_root, 'Filename', filename)
        set_node(req_root, 'CountryCode', 'LT')
        set_node(req_root, 'ContractId', global_e_invoice_agreement_id)
        objectify.deannotate(req_root)
        etree.cleanup_namespaces(req_root)
        req_string_repr = etree.tostring(req_root, xml_declaration=True, encoding='utf-8')
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'xsd_schemas')) + '/eInvoice-1.1-LT.xsd'
        validated, error = abi.xml_validator(string_repr, path)
        if validated:
            return {
                'payload_xml': string_repr,
                'payload_filename': filename,
                'req_xml': req_string_repr,
                'req_filename': req_filename,
                'file_id': file_id
            }
        else:
            body = 'SwedBank -- eInvoice Fail fail: Failed to validate ' \
                   'XML XSD schema, error message: %s' % error
            self.send_bug(body=body, subject='SwedBank eInvoice -- Failed to validate XSD')
            return {}

    @api.multi
    def upload_e_invoice_prep(self):
        """
        Method that is used to upload eInvoices to Banks (for now its only SwedBank).
        eInvoice XML is formed and is passed to Bank API.
        :return: None
        """
        self.ensure_one()

        forced_data = self.export_line_ids
        if self._context.get('strict'):
            forced_data = self.check_e_invoice_constraints(mode='filter')
            export_data = self.format_e_invoice_xml(forced_data=forced_data)
            if not export_data:
                return
        else:
            self.check_e_invoice_constraints()
            export_data = self.format_e_invoice_xml()
            if not export_data:
                raise exceptions.ValidationError(
                    _('Nepavyko išeksportuoti sąskaitos. Sistemos administratoriai informuoti.')
                )

        for e_line in forced_data:
            self.env['bank.export.job'].create_e_invoice_export_job(data={
                'invoice': e_line.invoice_id,
                'journal': self.company_bank_account,
                'export_data': export_data,
                'global_unique_id': str(e_line.invoice_id.id) + '__' + self.env.cr.dbname,
            })

        # Upload the invoice
        invoice_uploaded = self.upload_e_invoice(export_data)
        if not invoice_uploaded:
            return

        # Upload method commits, thus if no_warning is not passed,
        # we raise an error as an information that action is completed
        self.env.cr.commit()
        if not self._context.get('no_warning'):
            raise exceptions.ValidationError(_('Sąskaita sėkmingai įkelta'))

    @api.model
    def upload_e_invoice(self, invoice_data):
        """
        Uploads passed eInvoice data to the bank
        :param invoice_data: invoice data (dict)
        :return: True if invoice is uploaded else False
        """

        agr_id = self.env.user.sudo().company_id.swed_bank_agreement_id
        # Check needed eInvoice values exist
        payload_xml = invoice_data.get('payload_xml')
        payload_filename = invoice_data.get('payload_filename')
        req_xml = invoice_data.get('req_xml')
        req_filename = invoice_data.get('req_filename')
        if not payload_xml or not payload_filename or not req_xml or not req_filename or not agr_id:
            return False

        # Get needed paths
        sd = st.get_swed_data(self.env)
        abs_path_payload = sd.get('directory_path') + '/sendingInvoices/' + payload_filename
        abs_path_req = sd.get('directory_path') + '/sendingInvoices/' + req_filename
        sending_path = sd.get('directory_path') + '/sendingInvoices'

        if not os.path.isdir(sending_path):
            os.mkdir(sending_path)
        with open(abs_path_payload, 'w+') as fh:
            fh.write(payload_xml)
        with open(abs_path_req, 'w+') as fh:
            fh.write(req_xml)
        os.chdir(sd.get('directory_path'))

        # Execute sending command
        command = './send.sh url=%s agreementId=%s file=sendingInvoices/%s file=sendingInvoices/%s erpCert=certs/%s transportCert=certs/%s ' \
                  'dir=receivedInvoices ' \
                  'validateXML=false' % (sd.get('main_url'), str(agr_id), payload_filename, req_filename,
                                         sd.get('cert_path'), sd.get('cert_path'))
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=None, executable='/bin/bash', shell=True)
        st.handle_timeout(process)
        return True

    def send_bug(self, body, subject):
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'subject': subject + ' [%s]' % self._cr.dbname,
            'error_message': body,
        })

    @api.model
    def cron_push_e_invoices(self):
        if not self.env['account.journal'].search(
                [('api_integrated_bank', '=', True),
                 ('currency_id', '=', False),
                 ('api_bank_type', '=', 'swed_bank')], limit=1):
            return
        agr_id = self.env.user.sudo().company_id.swed_bank_agreement_id
        global_e_invoice_agreement_id = self.env.user.sudo().company_id.global_e_invoice_agreement_id
        e_invoice_agreement_date = self.env.user.sudo().company_id.e_invoice_agreement_date
        if not agr_id or not global_e_invoice_agreement_id or not e_invoice_agreement_date:
            return
        partner_ids = self.env['res.partner'].search([('send_e_invoices', '=', True),
                                                      ('e_invoice_application_date', '!=', False)])
        batch = self.env['account.invoice']
        for partner_id in partner_ids:
            date = partner_id.e_invoice_application_date if partner_id.e_invoice_application_date \
                else datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            to_e_invoice = self.env['account.invoice'].search(
                [('partner_id', '=', partner_id.id),
                 ('date_invoice', '>=', date),
                 ('periodic_id', '=', False),
                 ('bank_export_state', 'in', ['rejected', 'no_action']),
                 ('state', '=', 'open'),
                 ('paid_using_online_payment_collection_system', '=', False),
                 ])
            batch |= to_e_invoice
        if batch:
            ctx = self._context.copy()
            ctx.update({'invoice_ids': batch.ids, 'custom_name_get': True, 'cron_push_e_invoices': True})
            wizard_id = self.env['swed.bank.api.import.invoice'].with_context(ctx).create({})
            wizard_id.with_context(no_warning=True, strict=True).upload_e_invoice_prep()

    @api.model
    def cron_crud_automated_e_invoice_payments(self):
        """
        Method that is used to upload Automated Payment Agreements to Banks (for now its only SwedBank).
        Automated payment XML is formed and is passed to Bank API. DELETE/CREATE Operations for now
        :return: None
        """
        states = {'ADD': 'requested_add', 'DEL': 'requested_del'}
        agr_id = self.env.user.sudo().company_id.swed_bank_agreement_id
        global_e_invoice_agreement_id = self.env.user.sudo().company_id.global_e_invoice_agreement_id
        e_invoice_agreement_date = self.env.user.sudo().company_id.e_invoice_agreement_date
        if not agr_id or not global_e_invoice_agreement_id or not e_invoice_agreement_date:
            return
        data_operation_mapper = [
            ('ADD', self.env['res.partner'].search([('automated_payment_agreed', '=', True),
                                                    ('automated_e_invoice_payment_state', '=', 'non_automated')])),
            ('DEL', self.env['res.partner'].search([('automated_payment_agreed', '=', False),
                                                    ('automated_e_invoice_payment_state', '=', 'automated')])),
        ]
        for operation, data in data_operation_mapper:
            data = data.check_automated_agreement_constraints()
            export_data = data.format_automated_payment_xml(operation=operation)
            if not export_data:
                continue
            for partner in data:
                partner.automated_e_invoice_payment_state = states.get(operation)
                self.env['bank.export.job'].create_e_invoice_export_job(data={
                    'partner': partner,
                    'global_unique_id': str(partner.id) + '__' + self.env.cr.dbname,
                    'export_data': export_data,
                }, export_type='automatic_e_invoice_payment')

            payload_xml = export_data.get('payload_xml')
            payload_filename = export_data.get('payload_filename')
            req_xml = export_data.get('req_xml')
            req_filename = export_data.get('req_filename')
            sd = st.get_swed_data(self.env)
            abs_path_payload = sd.get('directory_path') + '/sendingAutomatedPayments/' + payload_filename
            abs_path_req = sd.get('directory_path') + '/sendingAutomatedPayments/' + req_filename
            sending_path = sd.get('directory_path') + '/sendingAutomatedPayments'
            if not os.path.isdir(sending_path):
                os.mkdir(sending_path)
            with open(abs_path_payload, 'w+') as fh:
                fh.write(payload_xml)
            with open(abs_path_req, 'w+') as fh:
                fh.write(req_xml)
            os.chdir(sd.get('directory_path'))
            command = './send.sh url=%s agreementId=%s file=sendingAutomatedPayments/%s ' \
                      'file=sendingAutomatedPayments/%s erpCert=certs/%s transportCert=certs/%s ' \
                      'dir=receivedInvoices ' \
                      'validateXML=false' % (sd.get('main_url'), str(agr_id), payload_filename, req_filename,
                                             sd.get('cert_path'), sd.get('cert_path'))
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=None, executable='/bin/bash', shell=True)
            st.handle_timeout(process)
