# -*- coding: utf-8 -*-

from odoo import models, fields, exceptions, _


class RasoImportWizard(models.TransientModel):

    _name = 'raso.import.wizard'
    data_type = fields.Selection([('0', 'Parduotuvių sąrašas'),
                                  ('1', 'Partnerių sąrašas'),
                                  ('2', 'Produktų kategorijų sąrašas'),
                                  ('3', 'Produktai'),
                                  ('4', 'Produktų kainos'),
                                  ('5', 'Produktų nuolaidos'),
                                  ('6', 'Produktų kategorijų nuolaidos'),
                                  ('7', 'Terminuotos produktų kainos')], default='0', required=True, string='Duomenų tipas')

    import_shop_ids = fields.Many2many('raso.shoplist', string='Importuojamos parduotuvės')
    import_partner_ids = fields.Many2many('res.partner', string='Importuojami partneriai')
    import_category_ids = fields.Many2many('product.category', string='Importuojamos kategorijos')
    import_product_ids = fields.Many2many('product.template', string='Importuojami produktai')
    import_price_ids = fields.Many2many('product.template.prices', string='Importuojamos terminuotos/neterminuotos kainos')
    import_discount_ids = fields.Many2many('product.template.discounts', string='Importuojamos prekių nuolaidos')
    import_g_discount_ids = fields.Many2many('product.category.discounts', string='Importuojamos kategorijų nuolaidos')
    full_sync = fields.Boolean(string='Pilnas sinchronizavimas', default=False)

    def _push(self, ids, data_type):
        import_obj = self.env['sync.data.import'].sudo().create({
            'data_type': '0',
            data_type: [(4, val) for val in ids],
            'full_sync': self.full_sync
        })
        res = import_obj.format_xml()
        if res and res[0]:
            return res, import_obj

    def push_data(self):
        if self.data_type == '0':
            if self.import_shop_ids:
                ids = self.import_shop_ids.ids
                res = self._push(ids, 'shop_ids')
            else:
                raise exceptions.UserError(_('Nepaduoti įrašai!'))
        elif self.data_type == '1':
            if self.import_partner_ids:
                ids = self.import_partner_ids.ids
                res = self._push(ids, 'partner_ids')
            else:
                raise exceptions.UserError(_('Nepaduoti įrašai!'))
        elif self.data_type == '2':
            if self.import_category_ids:
                ids = self.import_category_ids.ids
                res = self._push(ids, 'category_ids')
            else:
                raise exceptions.UserError(_('Nepaduoti įrašai!'))
        elif self.data_type == '3':
            if self.import_product_ids:
                ids = self.import_product_ids.ids
                res = self._push(ids, 'product_ids')
            else:
                raise exceptions.UserError(_('Nepaduoti įrašai!'))
        elif self.data_type == '4':
            if self.import_price_ids:
                ids = self.import_price_ids.filtered(lambda x: x.data_type == '4').ids
                res = self._push(ids, 'price_ids')
            else:
                raise exceptions.UserError(_('Nepaduoti įrašai, arba paduotos terminuotos kainos!'))
        elif self.data_type == '5':
            if self.import_discount_ids:
                ids = self.import_discount_ids.ids
                res = self._push(ids, 'discount_ids')
            else:
                raise exceptions.UserError(_('Nepaduoti įrašai!'))
        elif self.data_type == '7':
            if self.import_price_ids:
                ids = self.import_price_ids.filtered(lambda x: x.data_type == '7').ids
                res = self._push(ids, 'price_ids')
            else:
                raise exceptions.UserError(_('Nepaduoti įrašai, arba paduotos neterminuotos kainos!'))
        else:
            if self.import_g_discount_ids:
                ids = self.import_g_discount_ids.ids
                res = self._push(ids, 'group_discount_ids')
            else:
                raise exceptions.UserError(_('Nepaduoti įrašai!'))

        if res:
            return {
                'type': 'ir.actions.act_url',
                'url': '/web/binary/download?res_model=sync.data.import&res_id=%s&attach_id=%s' % (
                    res[1].id, res[0][0].id),
                'target': 'self',
            }


RasoImportWizard()
