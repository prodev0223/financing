# -*- coding: utf-8 -*-
from odoo import fields, models, api, _, tools, exceptions
from odoo.tools.misc import formatLang


class Invoice(models.Model):
    _inherit = 'account.invoice'

    @api.multi
    def print_darbu_aktas(self):
        self.ensure_one()
        return self.env['report'].get_action(self, 'iprojektavimas.report_darbu_aktas_tmp')


Invoice()


class DarbuAktas(models.AbstractModel):
    _name = 'report.iprojektavimas.report_darbu_aktas_tmp'
    _inherit = 'report.saskaitos.report_invoice'

    @api.multi
    def render_html(self, doc_ids, data=None):
        # self.env.context = {}
        report_obj = self.env['report']
        report = report_obj._get_report_from_name('iprojektavimas.report_darbu_aktas_tmp')
        discount_type = self.env.user.company_id.sudo().invoice_print_discount_type or 'perc'
        docs = self.env[report.model].browse(doc_ids)
        partner_balance = 0.0
        if report.model == 'account.invoice' and len(docs) == 1:
            partner_balance = self._partner_debt_overpayment_balance(docs.partner_id)
        docargs = {
            'doc_ids': doc_ids,
            'doc_model': report.model,
            'docs': self.env[report.model].browse(doc_ids),
            'suma': self._suma,
            'ieskoti': self._ieskoti,
            'detect_tax_lines': self._detect_tax_lines,
            'tax_names': self._tax_names,
            'tax_descriptions': self._tax_descriptions,
            'formatLang': lambda *a, **kw: formatLang(self.env, *a, **kw),
            'discount_type': discount_type,
            'partner_balance': partner_balance,
            'company_currency_symbol': self.get_company_currency_symbol,
            'float_compare_custom': self.float_compare_custom
        }
        return report_obj.render('iprojektavimas.report_darbu_aktas_tmp', docargs)


DarbuAktas()

