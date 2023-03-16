# -*- coding: utf-8 -*-
from odoo import api, models, fields, _
from odoo.tools import amount_to_text_en
from odoo.tools import num2words as n2w


class NurasymoAktas(models.AbstractModel):

    _name = 'report.nurasymo_aktas.report_nurasymo_aktas_templ'

    @api.multi
    def render_html(self, doc_ids, data=None):

        report_obj = self.env['report']
        report = report_obj._get_report_from_name('nurasymo_aktas.report_nurasymo_aktas_templ')
        docargs = {
            'doc_ids': doc_ids,
            'doc_model': report.model,
            'docs': self.env[report.model].browse(doc_ids),
        }

        return report_obj.render('nurasymo_aktas.report_nurasymo_aktas_templ', docargs)


NurasymoAktas()


class StockInventory(models.Model):

    _inherit = 'stock.inventory'

    komisija = fields.Many2one('alignment.committee', string='Komisija', required=False,
                               domain="[('state','=','valid'),('type','=','inventory')]", readonly=True,
                               states={'draft': [('readonly', False)], 'confirm': [('readonly', False)]})

    def _calc_total_value(self):
        total_suma = 0.00
        # invetory_value only in stock.quant model
        for move in self.move_ids:
            for quant in move.quant_ids:
                total_suma += quant.inventory_value
        return total_suma

    def _convert_sum_to_words(self, amount, lang='lt', iso='EUR'):
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


StockInventory()


class AlignmentCommittee(models.Model):

    _inherit = 'alignment.committee'

    type = fields.Selection(selection_add=[('inventory', 'Inventory Alignment')])


AlignmentCommittee()
