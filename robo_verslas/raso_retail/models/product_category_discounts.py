# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from .. import rr_tools as rt


class ProductCategoryDiscounts(models.Model):
    _name = 'product.category.discounts'
    _inherit = ['mail.thread', 'importable.to.raso']

    shop_id = fields.Many2one('raso.shoplist', string='Parduotuvė kuriai galioja kaina')
    all_shop_discount = fields.Boolean(compute='_all_shop_discount', string='Nuolaida galioja visoms parduotuvėms')
    category_id = fields.Many2one('product.category', string='Produkto kategorija', required=True)
    sum_from = fields.Float(string='Suma, nuo kurios pradeda galioti')
    sum_to = fields.Float(string='Suma, iki kurios galioja')
    name = fields.Char(string='Nuolaidos pavadinimas')
    discount = fields.Float(string='Nuolaida procentais')
    status = fields.Selection([('G', 'Nuolaidų akcija prekių grupei'),
                               ('T', 'Nuolaidų akcija pirkimo laikui'),
                               ('U', 'Prekių grupės negalima parduoti'),
                               ('C', 'Akcija taikoma tik su nuolaidų kortele'),
                               ('L', 'Lipdukai'),
                               ('M1', 'Virtualios dovanos')], string='Tipas')
    discount_for_groups = fields.Boolean(string='Reali nuolaida')
    based_on_time = fields.Boolean(string='Ar tikrinamas laikas')
    sale_forbidden = fields.Boolean(string='Draudimas parduoti')
    card_required = fields.Boolean(string='Nuolaida galioja tik su kortele')
    dic_type = fields.Char(string='Procentinė nuolaida', default='P')
    weekdays = fields.Char(string='Savaitės dienos kuriomis galioja')
    starts_at = fields.Datetime(string='Galiojimo pradžia')
    ends_at = fields.Datetime(string='Galiojimo pabaiga')

    imported_ids = fields.Many2many('sync.data.import', copy=False)
    revision_number = fields.Integer(string='Įrašo versija', copy=False)
    revision_number_display = fields.Char(compute='get_display_revision', string='Įrašo versija')
    raso_revision = fields.Char(string='Įrašo statusas RASO serveryje', compute='get_raso_revision')
    last_update_state = fields.Selection([('waiting', 'info'),
                                          ('rejected', 'danger'),
                                          ('out_dated', 'warning'),
                                          ('newest', 'success'),
                                          ('not_tried', 'muted')
                                          ], string='Importavimo būsena', compute='get_raso_revision')
    need_to_update = fields.Boolean(string='Reikia atnaujinti', compute='_need_to_update', store=True)
    importable_to_raso = fields.Boolean(compute='_importable_to_raso')

    @api.one
    @api.depends('category_id.importable_to_raso')
    def _importable_to_raso(self):
        if self.category_id.importable_to_raso:
            self.importable_to_raso = True
        else:
            self.importable_to_raso = False

    @api.one
    @api.depends('last_update_state', 'importable_to_raso', 'revision_number')
    def _need_to_update(self):
        if not self.importable_to_raso:
            self.with_context(prevent_loop=True).need_to_update = False
        else:
            if self.last_update_state in rt.UPDATE_IMPORT_STATES:
                self.with_context(prevent_loop=True).need_to_update = True
            else:
                self.with_context(prevent_loop=True).need_to_update = False

    @api.one
    @api.depends('shop_id')
    def _all_shop_discount(self):
        if not self.shop_id:
            self.all_shop_discount = True

    @api.model
    def import_group_discounts_action(self):
        action = self.env.ref('raso_retail.import_group_discounts_action_rec')
        if action:
            action.create_action()

    @api.multi
    def import_category_discounts(self):
        discounts = self.filtered(lambda x: x.importable_to_raso)
        if discounts:
            import_obj = self.env['sync.data.import'].sudo().create({
                'data_type': '6',
                'group_discount_ids': [(4, cat_disc) for cat_disc in discounts.ids],
                'full_sync': self._context.get('full_sync', False)
            })
            import_obj.format_xml()
            discounts._need_to_update()

    @api.multi
    def write(self, vals):
        res = super(ProductCategoryDiscounts, self).write(vals)
        for rec in self:
            if self._context.get('prevent_loop', False):
                self.with_context(prevent_loop=False)
                continue
            else:
                rec.with_context(prevent_loop=True).revision_number += 1
        return res


ProductCategoryDiscounts()
