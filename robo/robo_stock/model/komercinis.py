# -*- coding: utf-8 -*-

from odoo.tools import num2words as n2w
from odoo.tools import amount_to_text_en
from odoo import api, models
from odoo.tools.misc import formatLang


class CommercialOffer(models.AbstractModel):

    _name = 'report.robo_stock.report_sale_offer'

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

    def _detect_tax_lines(self, o):
        if len(o.order_line) > 1:
            line1 = o.order_line[0].mapped('tax_id.code')
            for l in o.order_line[1:]:
                line_cmp = l.mapped('tax_id.code')
                if len(set(line_cmp).difference(line1)) > 0 or len(line_cmp) != len(line1):
                    return True
        return False

    def _tax_names(self, l):
        types = list(set(l.tax_id.mapped('amount_type')))
        if len(types) == 1 and 'percent' in types:
            return formatLang(self.env, sum(t.amount for t in l.tax_id), digits=0) + '%'
        else:
            return ', '.join(map(lambda x: x.description if x.description else x.name, l.tax_id))

    @api.multi
    def render_html(self, doc_ids, data=None):
        report_obj = self.env['report']
        report = report_obj._get_report_from_name('robo_stock.report_sale_offer')
        discount_type = self.env.user.company_id.sudo().invoice_print_discount_type or 'perc'

        docargs = {
            'doc_ids': doc_ids,
            'doc_model': report.model,
            'docs': self.env[report.model].browse(doc_ids),
            'suma': self._suma,
            'detect_tax_lines': self._detect_tax_lines,
            'tax_names': self._tax_names,
            'formatLang': lambda *a, **kw: formatLang(self.env, *a, **kw),
            'discount_type': discount_type,
        }
        return report_obj.render('robo_stock.template_sale_offer_main', docargs)


CommercialOffer()
