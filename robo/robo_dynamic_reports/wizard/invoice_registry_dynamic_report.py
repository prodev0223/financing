# -*- coding: utf-8 -*-
import json

from six import iteritems

from odoo import _, models, fields, api, exceptions


class InvoiceRegistryDynamicReport(models.TransientModel):
    _name = 'invoice.registry.dynamic.report'
    _inherit = ['dynamic.report', 'invoice.registry.wizard']

    _dr_base_name = _('Supplier invoice registry')
    _report_tag = 'dynamic.ir'

    @api.multi
    def name_get(self):
        res = list()
        for rec in self:
            if rec.type == 'in':
                report_name = _("Supplier Invoice Registry")
            elif rec.type == 'out':
                report_name = _("Customer Invoice Registry")
            else:
                report_name = _("Invoice Registry")

            if rec.date_from:
                report_name += ' {} {}'.format(_('from'), rec.date_from)
            if rec.date_to:
                report_name += ' {} {}'.format(_('to'), rec.date_to)
            res.append((rec.id, report_name))
        return res

    partner_ids = fields.Many2many('res.partner', domain=[], dynamic_report_front_filter=True)
    refund = fields.Boolean(dynamic_report_front_filter=True)
    draft = fields.Boolean(dynamic_report_front_filter=True)
    include_canceled = fields.Boolean(dynamic_report_front_filter=True)
    type = fields.Selection(dynamic_report_front_filter=True)
    date_range = fields.Selection(default='last_month')
    invoice_ids = fields.Many2many('account.invoice', string='Related Invoices', readonly=True)

    @api.multi
    def _get_related_invoices(self):
        self.ensure_one()
        if self.invoice_ids and not self.refresh_data:
            return self.invoice_ids
        data = self.preprocess_report_data()
        report_data = self.env['report.saskaitos.report_invoice_registry'].get_report_data(self.ids, data)
        invoices = report_data.get('docs')
        self.write({'invoice_ids': [(6, 0, invoices.ids)]})  # Store invoices of the report
        return invoices

    @api.multi
    def _get_report_data(self):
        self.ensure_one()
        self = self._update_self_with_report_language()

        # Determine report group by identifier
        grouped_by_identifiers = self.group_by_field_ids.mapped('identifier')
        grouped_by_tax_code = 'tax_code' in grouped_by_identifiers
        grouped_by_tax_account = 'tax_account' in grouped_by_identifiers

        # Adjust report group by. Needed for get_report_data to group data correctly
        report_group_by = 'no_group_by'
        if grouped_by_tax_code:
            report_group_by = 'tax_group_by'
        elif grouped_by_tax_account:
            report_group_by = 'tax_account_group_by'
        self.write({'report_group_by': report_group_by})

        report_data = None
        if grouped_by_tax_code or grouped_by_tax_account:
            data = self.preprocess_report_data()
            report_data = self.env['report.saskaitos.report_invoice_registry'].get_report_data(self.ids, data)

        if grouped_by_tax_code:
            return self._get_data_by_partial_invoices(report_data, 'tax_code')
        elif grouped_by_tax_account:
            return self._get_data_by_partial_invoices(report_data, 'tax_account')
        else:
            invoices = self._get_related_invoices()
            return self._get_data_from_invoices(invoices)

    @api.multi
    def _get_data_from_invoices(self, invoices):
        self.ensure_one()
        company_currency_id = self.env.user.company_id.currency_id.id
        data = list()

        out_invoice_action = self.env.ref('robo.open_client_invoice')
        in_invoice_action = self.env.ref('robo.robo_expenses_action')

        for invoice in invoices:
            invoice_currency_id = invoice.currency_id.id
            sign = -1 if 'refund' in invoice.type else 1
            if self.print_in_company_currency:
                amount_without_vat = invoice.amount_untaxed_signed
                vat_amount = invoice.amount_tax_signed
                amount_with_vat = invoice.amount_total_company_signed
                unpaid_amount = invoice.residual_company_signed
                display_currency = company_currency_id
            else:
                amount_without_vat = invoice.amount_untaxed * sign
                vat_amount = invoice.amount_tax * sign
                amount_with_vat = invoice.amount_total * sign
                unpaid_amount = invoice.residual * sign
                display_currency = invoice_currency_id

            report_invoice_state = 'cancelled' if invoice.state == 'cancel' else 'not_cancelled'
            report_invoice_state_name = _('INVOICE REGISTRY')
            if report_invoice_state == 'cancelled':
                report_invoice_state_name = _('CANCELLED') + ' ' + report_invoice_state_name

            action_id = in_invoice_action.id if invoice.type in ('in_invoice', 'in_refund') else out_invoice_action.id

            data.append({
                '__record_data__': {
                    'record_model': 'account.invoice',
                    'record_ids': [invoice.id],
                    'action_id': action_id,
                },
                'date': {
                    'value': invoice.date_invoice
                },
                'date_of_receipt': {
                    'value': invoice.registration_date
                },
                'number': {
                    'value': invoice.reference or invoice.number
                },
                'partner_id': {
                    'value': invoice.partner_id.parent_id.name or invoice.partner_id.name
                },
                'email': {
                    'value': invoice.partner_id.email
                },
                'phone': {
                    'value': invoice.partner_id.phone
                },
                'company_code': {
                    'value': invoice.partner_id.parent_id.kodas or invoice.partner_id.kodas
                },
                'vat_payer_code': {
                    'value': invoice.partner_id.parent_id.vat or invoice.partner_id.vat
                },
                'amount_without_vat': {
                    'display_value': amount_without_vat,
                    'display_currency_id': display_currency,
                    'currency_id': company_currency_id,
                    'value': invoice.amount_untaxed_signed,
                },
                'vat_amount': {
                    'display_value': vat_amount,
                    'display_currency_id': display_currency,
                    'currency_id': company_currency_id,
                    'value': invoice.amount_tax_signed,
                },
                'amount_with_vat': {
                    'display_value': amount_with_vat,
                    'display_currency_id': display_currency,
                    'currency_id': company_currency_id,
                    'value': invoice.amount_total_company_signed,
                },
                'unpaid_amount': {
                    'display_value': unpaid_amount,
                    'display_currency_id': display_currency,
                    'currency_id': company_currency_id,
                    'value': invoice.residual_company_signed,
                },
                'report_invoice_state': {
                    'value': report_invoice_state,
                    'display_value': report_invoice_state_name,
                },
            })
        return data

    @api.multi
    def _get_data_by_partial_invoices(self, report_data, group_by):
        self.ensure_one()
        data = list()
        company_currency_id = self.env.user.company_id.currency_id.id
        vat_partial_invoices = report_data.get('vat_partial_invoices')
        all_invoices = report_data.get('docs', self.env['account.invoice'])
        for (key, tax_data) in iteritems(vat_partial_invoices):
            invoice_ids_for_tax_key = tax_data.get('invoices', {}).keys()
            invoices = all_invoices.filtered(lambda i: i.id in invoice_ids_for_tax_key)

            # Determine group by name
            group_by_name_type = _('VAT code') if group_by == 'tax_code' else _('Account')
            group_by_name_type = group_by_name_type.upper()
            group_by_name = '{}: {}'.format(group_by_name_type, key)

            # Get basic data such as reference, date for all of the invoices
            invoice_data = self._get_data_from_invoices(invoices)
            for invoice in invoice_data:
                # Adjust each invoice to only have the amount by tax code or tax account (based on group_by)
                invoice_id = invoice.get('__record_data__', {})['record_ids'][0]
                vat_parital_invoice_data = vat_partial_invoices[key]['invoices'][invoice_id]
                amount_without_vat = vat_parital_invoice_data.get('sum_wo', 0.0)
                vat_amount = vat_parital_invoice_data.get('vat_sum', 0.0)
                amount_with_vat = vat_parital_invoice_data.get('sum_w', 0.0)

                # The original report does not take into consideration print in company currency when grouping by tax
                # account or tax code. Setting company currency for each amount.
                invoice.update({
                    group_by: {
                        'value': key,
                        'name': group_by_name
                    },
                    'amount_without_vat': {
                        'currency_id': company_currency_id,
                        'value': amount_without_vat,
                    },
                    'vat_amount': {
                        'currency_id': company_currency_id,
                        'value': vat_amount,
                    },
                    'amount_with_vat': {
                        'currency_id': company_currency_id,
                        'value': amount_with_vat,
                    },
                    # Set unpaid amount to nothing since we're grouping by tax data
                    'unpaid_amount': {
                        'currency_id': None,
                        'value': '',
                    }
                })

            data += invoice_data

        return data

    @api.multi
    def get_pdf_header(self):
        self.ensure_one()
        company = self.env.user.company_id
        company_partner = company.partner_id

        company_info = ', '.join([x for x in [company_partner.name, company_partner.kodas] if x])
        company_address = ', '.join([x for x in [company.street, company.street2, company.city] if x])

        try:
            show_report_title = 'report_invoice_state' != json.loads(self.group_by_field_identifiers)[0]
        except (TypeError, IndexError):
            show_report_title = True

        return self.env['ir.qweb'].with_context(lang=self.determine_language_code()).render(
            'robo_dynamic_reports.InvoiceRegistryDynamicReportHeader', {
                'company_info': company_info,
                'company_address': company_address,
                'date_from': self.date_from,
                'date_to': self.date_to,
                'report_type': self.type,
                'show_report_title': show_report_title
            }
        )

    @api.multi
    def get_pdf_footer(self):
        self.ensure_one()

        invoices = self._get_related_invoices()
        if not invoices:
            return ''

        lang = self.determine_language_code()

        report_data = self.env['report.saskaitos.report_invoice_registry'].with_context(
            report_group_by=self.report_group_by
        ).get_report_data(doc_ids=invoices.ids, data=None)

        footer_content = ''

        company_currency = self.env.user.company_id.currency_id

        currencies = report_data.get('valiutos', {})
        if currencies:
            footer_content += self.env['ir.qweb'].with_context(lang=lang).render(
                'robo_dynamic_reports.InvoiceRegistryDynamicReportAmountsByCurrency', {
                    'currencies': currencies,
                }
            )

        # Render taxes by tax code
        footer_content += self.env['ir.qweb'].with_context(lang=lang).render(
            'robo_dynamic_reports.InvoiceRegistryDynamicReportAmountsByVATCode', {
                'vat_amounts': report_data.get('pvm_kodai', {}),
                'company_currency': company_currency,
            }
        )
        if self.report_group_by == 'tax_account_group_by':
            # Additionally render taxes by tax account
            footer_content += self.env['ir.qweb'].with_context(lang=lang).render(
                'robo_dynamic_reports.InvoiceRegistryDynamicReportAmountsByVATAccount', {
                    'tax_accounts': report_data.get('tax_accounts', {}),
                    'company_currency': company_currency,
                }
            )

        if self.type == 'all':
            footer_content += self.env['ir.qweb'].with_context(lang=lang).render(
                'robo_dynamic_reports.InvoiceRegistryDynamicReportTotalVATAmount', {
                    'total_vat_payable': report_data.get('payable_taxes', 0.0),
                    'company_currency': company_currency,
                }
            )

        return self.env['ir.qweb'].with_context(lang=lang).render(
            'robo_dynamic_reports.InvoiceRegistryDynamicReportFooter', {
                'footer_data': footer_content,
            }
        )

    @api.constrains('group_by_field_ids')
    def _check_group_by_field_ids(self):
        for rec in self:
            identifiers = rec.group_by_field_ids.mapped('identifier')
            if 'tax_code' in identifiers and 'tax_account' in identifiers:
                raise exceptions.UserError(_('This report only allows grouping by tax code or tax account. Grouping by '
                                             'both is not possible. Please choose one of the two group by fields.'))

    @api.multi
    def _action_xlsx(self):
        self.ensure_one()
        action = super(InvoiceRegistryDynamicReport, self)._action_xlsx()

        invoices = self._get_related_invoices()
        if not invoices:
            return action

        # Get additional data for rendering vat amount and tax account data
        report_data = self.env['report.saskaitos.report_invoice_registry'].with_context(
            report_group_by=self.report_group_by
        ).get_report_data(doc_ids=invoices.ids, data=None)

        company_currency_key = self.env.user.company_id.currency_id.name

        currencies = report_data.get('valiutos', {})
        for currency_key in currencies.keys():
            # Remove currency from currencies due to object not being JSON serializable
            currencies[currency_key].pop('currency_id')

        action['datas'].update({
            'currencies': report_data.get('valiutos', {}),
            'company_currency_key': company_currency_key,
            'vat_amounts': report_data.get('pvm_kodai', {}),
        })

        if self.report_group_by == 'tax_account_group_by':
            action['datas']['tax_accounts'] = report_data.get('tax_accounts', {})

        action['report_name'] = 'robo_dynamic_reports.invoice_registry_xlsx_report'
        return action
