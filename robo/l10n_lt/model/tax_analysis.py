# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools


class TaxAnalysis(models.Model):
    _name = 'tax.analysis'
    _description = 'Tax Analysis'
    _auto = False

    partner_id = fields.Many2one('res.partner', string='Partner')
    vat = fields.Char(string='VAT code', lt_string='PVM kodas')
    kodas = fields.Char(string='Company/Person code')
    country_code = fields.Char(string='Country Code')
    date_invoice = fields.Date(string='Invoice Date')
    inv_type = fields.Char(string='ISAF Invoice Type')
    full_inv_type = fields.Selection([
        ('out_invoice', 'Customer Invoice'),
        ('in_invoice', 'Vendor Bill'),
        ('out_refund', 'Customer Refund'),
        ('in_refund', 'Vendor Refund'),
    ], string='Sąskaitos tipas')
    taxable_value = fields.Float(string='Taxable Value')
    tax_code = fields.Char(string='Tax Code')
    amount = fields.Float(string='Tax Amount')
    invoice_id = fields.Many2one('account.invoice', string='Invoice')
    company_id = fields.Many2one('res.company', string='Company')

    @api.model_cr
    def init(self):
        tools.drop_view_if_exists(self._cr, 'tax_analysis')
        self._cr.execute('''
            create or replace view tax_analysis as (
            SELECT
              ROW_NUMBER() OVER (order by invoice_id) AS id,
              foo.invoice_id,
              foo.vat,
              foo.kodas,
              foo.country_code,
              foo.date_invoice,
              foo.inv_type,
              foo.full_inv_type,
              foo.taxable_value,
              foo.tax_code,
              foo.amount,
              foo.company_id,
              foo.partner_id
            FROM (
            select 	inv.id as invoice_id,
                        part.name,
                        part.vat,
                        part.kodas,
                        inv.number,
                        country.code as country_code,
                        inv.date_invoice,
                        CASE WHEN inv.type = 'out_invoice' or inv.type = 'out_refund' THEN 'sale'
                            ELSE CASE WHEN inv.type = 'in_invoice' or inv.type = 'in_refund' THEN 'purchase' ELSE inv.type END END as doc_type,
                        CASE inv.type
                            WHEN 'out_refund' THEN 'KS'
                            WHEN 'in_refund' THEN 'KS'
                            WHEN 'in_invoice' THEN 'SF'
                            WHEN 'out_invoice' THEN 'SF' END as inv_type,
                        inv.type as full_inv_type,
                        false as special_taxation,
                        inv.date_invoice as VATPointDate,
                        SUM(CASE WHEN inv.type in ('in_refund', 'out_refund') then -inv_tax.base_signed ELSE inv_tax.base_signed END) as taxable_value,
                        tax.code as tax_code,
                        abs(tax.amount) as tax_percentage,
                        SUM(CASE WHEN inv.type in ('in_refund', 'out_refund') then -inv_tax.amount_signed ELSE inv_tax.amount_signed END ) as amount,
                        part.id as partner_id,
                        '1900-01-01' as VATPointDate2,
                        inv.company_id
                    from account_invoice inv
                        inner join res_partner part on part.id = inv.partner_id
    	                left join res_country country on country.id = part.country_id
                        inner join account_invoice_tax inv_tax on inv.id = inv_tax.invoice_id
                        inner join account_tax tax on inv_tax.tax_id = tax.id
                    where inv.state in ('open', 'paid') and inv.move_id is not null
                    group by country.code, inv.date_invoice, inv.type, part.vat, part.id, inv.number, tax.code, tax.amount, inv.id, inv.company_id
                    union all
                    select av.id as invoice_id,
                        part.name,
                        part.vat,
                        part.kodas,
                        CASE WHEN av.voucher_type = 'purchase' and COALESCE(av.reference, '') != '' THEN av.reference ELSE av.number END as number,
                        country.code as country_code,
                        av.date as date_invoice,
                        av.voucher_type as doc_type,
                        'SF' as inv_type,
                        Null as full_inv_type,
                        false as special_taxation,
                        av.date as VATPointDate,
                        SUM(avl.price_subtotal_signed) as taxable_value,
                        tax.code as tax_code,
                        abs(tax.amount) as tax_percentage,
                        SUM(avl.price_subtotal_signed) * (abs(tax.amount) / 100) as amount,
                        part.id as partner_id,
                        '1900-01-01' as VATPointDate2,
                        avl.company_id
                    from account_voucher av
                    inner join res_partner part on part.id = av.partner_id
                    left join res_country country on country.id = part.country_id
                    inner join account_voucher_line avl on avl.voucher_id = av.id
                    inner join account_tax_account_voucher_line_rel tax_rel on tax_rel.account_voucher_line_id = avl.id
                    inner join account_tax tax on tax.id = tax_rel.account_tax_id
                    where av.state = 'posted'
                    group by country.code, av.date, av.voucher_type, av.reference, part.vat, part.id, av.number, av.id, tax.code, tax.amount, avl.company_id
                    order by doc_type
            ) as foo order by foo.date_invoice desc )
            ''')
