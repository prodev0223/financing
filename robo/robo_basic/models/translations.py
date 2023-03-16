# -*- coding: utf-8 -*-

import logging

import odoo
from odoo.tools import amount_to_text_en
from odoo import SUPERUSER_ID, models, api, exceptions, _
from odoo.tools import num2words as n2w
from odoo.models import BaseModel
from six import iteritems


@api.guess
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
BaseModel._convert_sum_to_words = _convert_sum_to_words

_logger = logging.getLogger(__name__)


def trans_load_data(cr, val_list, lang, module_name=None, context=None):

    env = odoo.api.Environment(cr, SUPERUSER_ID, context or {})
    Translation = env['ir.translation'].with_context(overwrite=True)
    irt_cursor = Translation._get_import_cursor()
    def process_row(vals):
        """Process a single PO (or POT) entry."""
        # dictionary which holds values for this line of the csv file
        # {'lang': ..., 'type': ..., 'name': ..., 'res_id': ...,
        #  'src': ..., 'value': ..., 'module':...}
        dic = dict.fromkeys(('type', 'name', 'res_id', 'src', 'value',
                             'comments', 'imd_model', 'imd_name', 'module'))
        dic['lang'] = lang
        dic.update(vals)

        # This would skip terms that fail to specify a res_id
        res_id = dic['res_id']
        if not res_id:
            return

        if isinstance(res_id, (int, long)) or \
                (isinstance(res_id, basestring) and res_id.isdigit()):
            dic['res_id'] = int(res_id)
            if module_name:
                dic['module'] = module_name
        else:
            # res_id is an xml id
            dic['res_id'] = None
            dic['imd_model'] = dic['name'].split(',')[0]
            if '.' in res_id:
                dic['module'], dic['imd_name'] = res_id.split('.', 1)
            else:
                dic['module'], dic['imd_name'] = module_name, res_id

        irt_cursor.push(dic)
    for vals in val_list:
        process_row(vals)
    irt_cursor.finish()
    Translation.clear_caches()


class IrTranslation(models.Model):
    _inherit = "ir.translation"

    @api.model
    def import_manual_translations(self, lang, val_list, module_name=None):
        Lang = self.env['res.lang'].sudo()
        if not Lang.search_count([('code', '=', lang)]):
            raise exceptions.UserError(_('Language %s not found') % lang)
        trans_load_data(self._cr, val_list, lang, module_name=module_name, context=self._context)

    @api.model
    def change_translation_of_fields(self, lang, values):
        '''val_list: [(module_name, field_name): 'value']
        E.G.
        lang = 'lt_LT'
        values = {('account.analytic.line', 'project_id'): 'Projektas'}
        '''
        res = []
        for (model_name, field_name), translation_value in iteritems(values):
            field_rec = self.env['ir.model.fields'].search([('model', '=', model_name), ('name', '=', field_name)])
            if len(field_rec) != 1:
                raise exceptions.UserError(_('field %s %s not found') % (model_name, field_name))
            self._cr.execute('SELECT field_description '
                             '  FROM ir_model_fields '
                             '  WHERE id = %s', (field_rec.id,))
            src = self._cr.fetchall()[0][0]
            vals = {'type': 'field',
                    'name': '%s,%s' % (model_name, field_name),
                    'res_id': field_rec.id,
                    'src': src,
                    'value': translation_value,
                    'comments': ''}
            res.append(vals)
        self.import_manual_translations(lang, res)

    @api.model_cr_context
    def load_module_terms(self, modules, langs):
        res = super(IrTranslation, self).load_module_terms(modules, langs)
        if 'lt_LT' in langs:
            try:
                self.update_lithuanian_field_translations(modules)
            except:
                pass
        return res

    @api.model
    def update_lithuanian_field_translations(self, modules):
        field_ids = self.env['ir.model.data'].search(
            [('module', 'in', modules), ('model', '=', 'ir.model.fields')]).mapped('res_id')
        fields = self.env['ir.model.fields'].search([('id', 'in', field_ids)])
        values_to_update = {}
        for field_rec in fields:
            model = field_rec.model
            field_name = field_rec.name
            if model in self.env and field_name in self.env[model]._fields:
                field = self.env[model]._fields[field_name]
                lt_value = getattr(field, 'lt_string', None)
                if lt_value:
                    values_to_update[(model, field_name)] = lt_value
        self.env['ir.translation'].change_translation_of_fields('lt_LT', values_to_update)

IrTranslation()
