# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, tools
from datetime import datetime
from dateutil.relativedelta import relativedelta
from six import itervalues
# import calendar


class InvoiceRegistryReport(models.AbstractModel):

    _name = 'report.saskaitos.report_invoice_registry'

    @api.multi
    def render_html(self, doc_ids, data):
        return self.with_context(lang=self.env.user.company_id.partner_id.lang).env['report'].render(
            'saskaitos.report_invoice_registry', values=self.get_report_data(doc_ids, data)
        )

    @api.model
    def get_report_data(self, doc_ids, data):
        if data:
            company_id = data['form']['company_id']
            report_group_by = data['form']['report_group_by']
            company_address = data['form']['company_address']
            date_from = data['form']['date_start']
            date_end = data['form']['date_end']
            include_contact_info = data['form']['include_contact_info']
            type = data['form']['type']
            draft = data['form']['draft']
            refund = data['form']['refund']
            include_canceled = data['form']['include_canceled']
            print_in_company_currency = data['form']['print_in_company_currency']
            partner_ids = data['form']['partner_ids']
            state = ['open', 'paid']
            types = []
            if draft:
                state.append('draft')
            if type in ['in', 'all']:
                types.append('in_invoice')
                if refund:
                    types.append('in_refund')
            if type in ['out', 'all']:
                types.append('out_invoice')
                if refund:
                    types.append('out_refund')
            domain = [('state', 'in', state),
                      ('type', 'in', types),
                      ('date_invoice', '>=', date_from),
                      ('date_invoice', '<=', date_end),
                      ]
            if partner_ids:
                domain += [('partner_id', 'in', partner_ids)]
            invoice_ids = self.env['account.invoice'].search(domain)

            if type in ['out', 'all']:
                if include_canceled:
                    canceled_domain = [('state', 'in', ['cancel']),
                                       ('type', 'in', types),
                                       ('type', 'in', ['out_invoice', 'out_refund']),
                                       ('move_name', '!=', False),
                                       ('date_invoice', '>=', date_from),
                                       ('date_invoice', '<=', date_end)]
                    if partner_ids:
                        canceled_domain += [('partner_id', 'in', partner_ids)]
                    c_invoice_ids = self.env['account.invoice'].search(canceled_domain)
                    invoice_ids += c_invoice_ids
        else:
            include_contact_info = False
            report_group_by = self._context.get('report_group_by', False)
            company = self.env.user.company_id
            company_title = company.name
            if company.partner_id and company.partner_id.kodas:
                company_title += ', ' + company.partner_id.kodas
            company_id = [company.id, company_title]
            company_address = company.street
            print_in_company_currency = False
            date_from = False
            date_end = False
            invoice_ids = self.env['account.invoice'].browse(doc_ids)
            invtypes = set(invoice_ids.mapped('type'))
            exists_in = ('in_invoice' in invtypes or 'in_refund' in invtypes)
            exists_out = ('out_invoice' in invtypes or 'out_refund' in invtypes)
            if exists_in and exists_out:
                type = 'all'
            else:
                type = 'in' if exists_in else 'out'

        if type == 'out':
            invoice_ids = invoice_ids.sorted(lambda r: r.number, reverse=True)
        if type in ['all'] and invoice_ids:
            vat_account_ids = self.sudo().env.user.company_id.vat_account_ids
            self._cr.execute('''
                SELECT account_move_line.account_id, SUM(account_move_line.debit) AS debit, 
                    SUM(account_move_line.credit) AS credit 
                    FROM account_move_line
                    JOIN account_move ON account_move_line.move_id = account_move.id
                    JOIN account_invoice ON account_invoice.move_id = account_move.id
                    WHERE account_move.state='posted' 
                    AND account_invoice.id in %s
                    AND account_move_line.account_id in %s
                    GROUP BY account_move_line.account_id
                ''', (tuple(invoice_ids.ids), tuple(vat_account_ids.ids), ))
            result = self._cr.fetchall()
            values_by_account = {}
            for line in result:
                acc_id, debit, credit = line
                values_by_account[acc_id] = debit - credit
            payable_taxes = sum(itervalues(values_by_account))
        else:
            payable_taxes = 0.0

        invoice_data = self.get_data_from_invoices(invoice_ids, report_group_by)
        valiutos = invoice_data.get('currencies', {})
        pvm_kodai = invoice_data.get('vat_codes', {})
        tax_accounts = invoice_data.get('tax_accounts', {})
        vat_partial_invoices = invoice_data.get('vat_partial_invoices', {})

        docargs = {
            'doc_ids': invoice_ids.mapped('id'),
            'doc_model': 'account.invoice',
            'docs': invoice_ids,
            'date_from': date_from,
            'date_end': date_end,
            'type': type,
            'valiutos': valiutos,
            'pvm_kodai': pvm_kodai,
            'tax_accounts': tax_accounts,
            'report_group_by': report_group_by,
            'vat_partial_invoices': vat_partial_invoices,
            'company_id': company_id,
            'company_address': company_address,
            'print_in_company_currency': print_in_company_currency,
            'include_contact_info': include_contact_info,
            'payable_taxes': payable_taxes
        }
        return docargs

    @api.model
    def get_data_from_invoices(self, invoices, report_group_by=None):
        valiutos = {}
        pvm_kodai = {}
        tax_accounts = {}
        vat_partial_invoices = {}
        for invoice_id in invoices:
            if invoice_id['state'] not in ['cancel']:
                company_currency = invoice_id.company_id.currency_id
                # precision = invoice_id.currency_id.decimal_places
                # if invoice_id.company_id.tax_calculation_rounding_method == 'round_globally' or not bool(
                #         self.env.context.get("round", True)):
                #     precision += 5
                if 'refund' in invoice_id.type:
                    sign = -1
                else:
                    sign = 1
                amount_tax = sign * invoice_id.amount_tax
                amount_untaxed = sign * invoice_id.amount_untaxed
                if invoice_id.currency_id.name not in valiutos:
                    valiutos[invoice_id.currency_id.name] = {'pvm_suma': amount_tax,
                                                             'suma': amount_untaxed,
                                                             'currency_id': invoice_id.currency_id}
                else:
                    valiutos[invoice_id.currency_id.name]['pvm_suma'] += amount_tax
                    valiutos[invoice_id.currency_id.name]['suma'] += amount_untaxed
                for tax_line in invoice_id.tax_line_ids:
                    # !! base_signed and amount_signed are not signed, but currency converted
                    suma, pvm_suma = tax_line.base_signed, tax_line.amount_signed
                    suma *= sign
                    pvm_suma *= sign
                    code = tax_line.tax_id.code
                    account_name = tax_line.account_id.display_name
                    key_group_by = False
                    if code not in pvm_kodai:
                        pvm_kodai[code] = {
                            'pvm_suma': pvm_suma,
                            'suma': suma,
                        }
                    else:
                        pvm_kodai[code]['pvm_suma'] += pvm_suma
                        pvm_kodai[code]['suma'] += suma

                    if report_group_by and report_group_by in ['tax_group_by']:
                        key_group_by = code
                    elif report_group_by and report_group_by in ['tax_account_group_by']:
                        key_group_by = account_name
                        if key_group_by not in tax_accounts:
                            tax_accounts[key_group_by] = {
                                'pvm_suma': pvm_suma,
                                'suma': suma,
                            }
                        else:
                            tax_accounts[key_group_by]['pvm_suma'] += pvm_suma
                            tax_accounts[key_group_by]['suma'] += suma

                    if key_group_by:
                        if key_group_by not in vat_partial_invoices:
                            vat_partial_invoices[key_group_by] = {
                                'total_vat': 0,
                                'total_wo': 0,
                                'total_w': 0,
                                'invoices': {
                                }}
                        if invoice_id.id not in vat_partial_invoices[key_group_by]['invoices']:
                            vat_partial_invoices[key_group_by]['invoices'][invoice_id.id] = {
                                'vat_sum': 0,
                                'sum_wo': 0,
                                'sum_w': 0
                            }
                        vat_partial_invoices[key_group_by]['invoices'][invoice_id.id]['vat_sum'] += pvm_suma
                        vat_partial_invoices[key_group_by]['invoices'][invoice_id.id]['sum_wo'] += suma
                        vat_partial_invoices[key_group_by]['invoices'][invoice_id.id]['sum_w'] += (pvm_suma + suma)
                        vat_partial_invoices[key_group_by]['total_vat'] += pvm_suma
                        vat_partial_invoices[key_group_by]['total_wo'] += suma
                        vat_partial_invoices[key_group_by]['total_w'] += (pvm_suma + suma)

        return {
            'currencies': valiutos,
            'vat_codes': pvm_kodai,
            'tax_accounts': tax_accounts,
            'vat_partial_invoices': vat_partial_invoices
        }


InvoiceRegistryReport()


class InvoiceRegistryWizard(models.TransientModel):

    _name = 'invoice.registry.wizard'

    def default_date_from(self):
        return (datetime.now() + relativedelta(months=-1, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def default_date_to(self):
        return (datetime.now() + relativedelta(months=-1, day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    year = fields.Selection([(2013, '2013'), (2014, '2014'), (2015, '2015'), (2016, '2016'), (2017, '2017'),
                             (2018, '2018'), (2019, '2019'), (2020, '2020'), (2021, '2021'), (2022, '2022'),
                             (2023, '2023'), (2024, '2024')], string='Year', default=lambda self: datetime.utcnow().year)
    month = fields.Selection([(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5'), (6, '6'), (7, '7'),
                              (8, '8'), (9, '9'), (10, '10'), (11, '11'), (12, '12')], string='Month',
                             default=(datetime.utcnow().month - 1))  # todo year ir month nebenaudojami!
    type = fields.Selection([('in', 'Supplier invoices'), ('out', 'Customer invoices'), ('all', 'All')],
                            default='out', string='Invoice type', required=True)
    draft = fields.Boolean(string='Include draft invoices', default=False)
    refund = fields.Boolean(string='Include refunds', default=True)
    include_canceled = fields.Boolean(string='Įtraukti anuliuotas sąskaitas', default=True)
    date_from = fields.Date(string='Data nuo', required=True, default=default_date_from)
    date_to = fields.Date(string='Data iki', required=True, default=default_date_to)
    print_in_company_currency = fields.Boolean(string='Spausdinti naudojant vien kompanijos valiutą', default=False,
                                               lt_string='Spausdinti naudojant vien kompanijos valiutą')
    # field not used anymore
    group_by_vat = fields.Boolean(string='Grupuoti pagal PVM klasifikatoriaus kodus', default=False)
    # //

    report_group_by = fields.Selection([('no_group_by', 'Netaikyti grupavimo'),
                                        ('tax_group_by', 'Grupuoti pagal PVM klasifikatoriaus kodus'),
                                        ('tax_account_group_by', 'Grupuoti pagal buhalterinę PVM sąskaitą')],
                                       string='Grupuoti pagal')
    partner_ids = fields.Many2many('res.partner', string='Partneriai',
                                   help='Ataskaita išfiltruos tik nurodytus partnerius. Nenurodžius - bus įtraukti visi partneriai.')
    include_contact_info = fields.Boolean(string='Rodyti partnerio kontaktus', default=False)

    @api.multi
    def preprocess_report_data(self):
        data = {
            'model': 'res.partner',
            'form': {},
        }
        if self.date_to or self.date_from:
            date_header = ' / {} - {}'.format(self.date_from or '', self.date_to or '')
            self = self.with_context(date_header=date_header)
        company = self.env.user.company_id
        data['form']['date_start'] = self.date_from
        data['form']['date_end'] = self.date_to
        data['form']['type'] = self.type
        data['form']['draft'] = self.draft
        data['form']['refund'] = self.refund
        data['form']['include_canceled'] = self.include_canceled
        data['form']['print_in_company_currency'] = self.print_in_company_currency
        data['form']['include_contact_info'] = self.include_contact_info
        company_title = company.name
        if company.partner_id and company.partner_id.kodas:
            company_title += ', ' + company.partner_id.kodas
        data['form']['company_id'] = [company.id, company_title]
        data['form']['company_address'] = company.street
        data['form']['report_group_by'] = self.report_group_by
        data['form']['partner_ids'] = self.partner_ids.ids if self.partner_ids else False
        return data

    @api.multi
    def print_report(self):
        self.ensure_one()
        data = self.preprocess_report_data()
        res = self.env['report'].get_action(self, 'saskaitos.report_invoice_registry', data=data)
        if 'report_type' in res:
            if self._context.get('force_pdf'):
                res['report_type'] = 'qweb-pdf'
            if self._context.get('force_html'):
                res['report_type'] = 'qweb-html'
        return res


InvoiceRegistryWizard()
