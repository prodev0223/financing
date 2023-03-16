# -*- coding: utf-8 -*-

from odoo.tools import num2words as n2w
from odoo.tools import amount_to_text_en
from odoo import api, models, tools
from odoo.tools.misc import formatLang
from odoo.tools.translate import _

reversedVATs = ['PVM25', 'PVM26', 'PVM27']


class SaskaitaFaktura(models.AbstractModel):

    _name = 'report.saskaitos.report_invoice'

    def get_company_currency_symbol(self):
        """
        :return: company currency symbol (str)
        """
        return self.sudo().env.user.company_id.currency_id.symbol

    def float_compare_custom(self, num):
        """
        compare passed float with zero
        :return: float compare res
        """
        return tools.float_compare(num, 0.0, precision_digits=2)

    def _suma(self, amount, lang='lt', iso='EUR'):
        lang = lang.upper()
        if lang and '_' in lang:
            lang = lang.split('_')[0]
        lang_command = 'lang_' + lang
        if hasattr(n2w, lang_command):
            lang_module = getattr(n2w, lang_command)
            if hasattr(lang_module, 'to_currency'):
                return lang_module.to_currency(amount, iso)
        if lang in ['lt', 'lt_LT']:
            try:
                return n2w.lang_LT.to_currency(amount, iso)
            except:
                return ''
        else:
            return amount_to_text_en.amount_to_text(amount, 'en', iso)

    def _ieskoti(self, o):
        for l in o.tax_line_ids:
            for tag in l.tax_id.tag_ids:
                if tag.code == '12':
                    return True
        return False

    def _detect_tax_lines(self, o):
        if len(o.invoice_line_ids) > 1:
            line1 = o.invoice_line_ids[0].mapped('invoice_line_tax_ids.code')
            for l in o.invoice_line_ids[1:]:
                line_cmp = l.mapped('invoice_line_tax_ids.code')
                if len(set(line_cmp).difference(line1)) > 0 or len(line_cmp) != len(line1):
                    return True
        return False

    def _is_vat_object(self, l):
        if len(l.invoice_line_tax_ids) == 1 and any(t.non_vat_object for t in l.invoice_line_tax_ids):
            return False
        return True

    def _tax_names(self, l):
        types = list(set(l.invoice_line_tax_ids.mapped('amount_type')))
        if not self._is_vat_object(l):
            return _('Ne PVM objektas')
        elif len(types) == 1 and 'percent' in types:
            reverse_tax = l.invoice_line_tax_ids.filtered(lambda x: x.code in reversedVATs)
            if reverse_tax:
                return ', '.join(map(lambda x: x.description if x.description else x.name, reverse_tax))

            return formatLang(self.env, sum(t.amount for t in l.invoice_line_tax_ids), digits=0) + '%'
        else:
            return ', '.join(map(lambda x: x.description if x.description else x.name, l.invoice_line_tax_ids))

    def _tax_descriptions(self, o):
        codes = []
        res = []
        for tax in o.tax_line_ids.mapped('tax_id'):
            if tax.code not in codes:
                codes.append(tax.code)
                res.append(tax)
        return res

    def _partner_debt_overpayment_balance(self, partner_id):
        """
        Fetch and sum amount_residual from account move lines of passed partner
        :param partner_id: res.partner object
        :return: partner_balance (float)
        """
        partner_balance = 0.0
        show_balance_type = self.sudo().env.user.company_id.print_invoice_partner_balance
        if (not show_balance_type or show_balance_type in ['disabled']) or \
                (show_balance_type in ['enabled_partial'] and not partner_id.show_balance_account_invoice_document):
            return partner_balance
        if partner_id:
            self.env.cr.execute('''
            SELECT SUM(aml.amount_residual) FROM account_move_line as aml
            INNER JOIN account_move AS am ON am.id = aml.move_id
            INNER JOIN account_account AS ac ON aml.account_id = ac.id
            INNER JOIN account_account_type AS at ON at.id = ac.user_type_id
            WHERE aml.partner_id = %s AND am.state = 'posted' 
            AND at.type in ('receivable', 'payable') AND aml.amount_residual <> 0
            ''', (partner_id.id, ))
            res = self.env.cr.fetchone()
            if res and res[0] is not None:
                partner_balance = tools.float_round(res[0], precision_digits=2)
        return partner_balance

    def format_lang(self, *a, **kw):
        return formatLang(self.env, *a, **kw)

    def get_discount_type(self):
        """
        Gets the discount type for display in invoice printing
        :return: 'perc' or 'currency'
        """
        discount_type = 'perc'
        discount_conf = self.sudo().env['ir.config_parameter'].search([('key', '=', 'saskaitos.print_discount_type')])  # can be 'perc' or 'currency'
        if discount_conf:
            discount_type = discount_conf.value
        return discount_type

    @api.multi
    def render_html(self, doc_ids, data=None):
        # self.env.context = {}
        report_obj = self.env['report']
        report = report_obj._get_report_from_name('saskaitos.report_invoice')
        discount_type = self.get_discount_type()
        docs = self.env[report.model].browse(doc_ids)
        partner_balance = 0.0
        if report.model == 'account.invoice' and len(docs) == 1:
            partner_balance = self._partner_debt_overpayment_balance(docs.partner_id)

        partner_balance_in_invoice_currency = False
        if len(docs) == 1:
            company_currency = self.env.user.company_id.currency_id
            if not tools.float_is_zero(docs.currency_id.with_context(date=docs.date).rate or 0.0, precision_digits=2) \
                    and company_currency != docs.currency_id:
                partner_balance_in_invoice_currency = docs.currency_id.with_context(date=docs.date_invoice).compute(
                    partner_balance, company_currency
                )

        docargs = {
            'doc_ids': doc_ids,
            'doc_model': report.model,
            'docs': docs,
            'suma': self._suma,
            'ieskoti': self._ieskoti,
            'detect_tax_lines': self._detect_tax_lines,
            'is_vat_object': self._is_vat_object,
            'tax_names': self._tax_names,
            'tax_descriptions': self._tax_descriptions,
            'formatLang': self.format_lang,
            'discount_type': discount_type,
            'partner_balance': partner_balance,
            'partner_balance_in_invoice_currency': partner_balance_in_invoice_currency,
            'company_currency_symbol': self.get_company_currency_symbol,
            'float_compare_custom': self.float_compare_custom
        }
        return report_obj.render('saskaitos.report_invoice', docargs)


SaskaitaFaktura()
