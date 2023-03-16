# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _
from .. import rr_tools as rt


class RasoShopList(models.Model):
    _name = 'raso.shoplist'
    _inherit = ['mail.thread', 'importable.to.raso']

    shop_no = fields.Char(required=True, string='Parduotuvės kodas', inverse='create_generic_pos')
    shop_name = fields.Char(string='Parduotuvės pavadinimas')
    address = fields.Char(string='Parduotuvės adresas')
    city = fields.Char(string='Parduotuvės miestas')
    level = fields.Integer(string='Parduotuvės lygis')
    ip_address = fields.Char(string='Parduotuvės IP adresas')
    sco_address = fields.Char(string='Parduotuvės savitarnos serviso adresas')
    remarks = fields.Char(string='Pastabos')
    enabled = fields.Boolean(string='Įrašo galiojimas')

    generic_pos = fields.Many2one('raso.shoplist.registers', string='Bendrasis kasos aparatas',
                                  compute='set_generic_pos')
    pos_ids = fields.One2many('raso.shoplist.registers', 'shop_id', string='Parduotuvės kasos aparatai')
    imported_ids = fields.Many2many('sync.data.import', copy=False)
    price_ids = fields.One2many('product.template.prices', 'shop_id', string='Prekių kainos')
    discount_ids = fields.One2many('product.template.discounts', 'shop_id', string='Prekių nuolaidos')
    location_id = fields.Many2one('stock.location',
                                  default=lambda self: self.env['stock.location'].search(
                                      [('usage', '=', 'internal')], order='create_date desc', limit=1),
                                  domain="[('usage','=','internal')]", string='Parduotuvės lokacija')

    state = fields.Selection([('working', 'Parduotuvė sukonfigūruota'),
                              ('failed', 'Trūksta konfigūracijos (Kasos aparatas/ai, Lokacija)')],
                             string='Būsena', track_visibility='onchange', compute='compute_state')

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

    @api.one
    @api.depends('last_update_state', 'price_ids.last_update_state',
                 'discount_ids.last_update_state', 'revision_number')
    def _need_to_update(self):
        need_to_update = False
        for price_id in self.price_ids:
            if price_id.last_update_state in rt.UPDATE_IMPORT_STATES:
                need_to_update = True
                break
        for disc_id in self.discount_ids:
            if disc_id.last_update_state in rt.UPDATE_IMPORT_STATES:
                need_to_update = True
                break
        if not need_to_update:
            if self.last_update_state in rt.UPDATE_IMPORT_STATES:
                need_to_update = True
            else:
                need_to_update = False
        self.with_context(prevent_loop=True).need_to_update = need_to_update

    @api.multi
    def write(self, vals):
        res = super(RasoShopList, self).write(vals)
        for rec in self:
            if self._context.get('prevent_loop', False):
                self.with_context(prevent_loop=False)
                continue
            else:
                rec.with_context(prevent_loop=True).revision_number += 1
        return res

    @api.multi
    def open_shop(self):
        self.ensure_one()
        return {
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'raso.shoplist',
                'res_id': self.id,
                'view_id': self.env.ref('raso_retail.raso_shoplist_form').id,
                'type': 'ir.actions.act_window',
                'target': 'current',
        }

    @api.model
    def import_shops_action(self):
        action = self.env.ref('raso_retail.import_shops_action_rec')
        if action:
            action.create_action()

    @api.model
    def import_shops_action_force(self):
        action = self.env.ref('raso_retail.import_shops_action_rec_force')
        if action:
            action.create_action()

    @api.multi
    def unlink(self):
        self.mapped('pos_ids').with_context(parent_unlink=True).unlink()
        return super(RasoShopList, self).unlink()

    @api.multi
    def name_get(self):
        return [(shop.id, shop.shop_name or _('Parduotuvė #{}').format(shop.shop_no)) for shop in self]

    @api.constrains('shop_no')
    def number_constrain(self):
        for rec in self:
            if rec.shop_no:
                if self.env['raso.shoplist'].search_count([('id', '!=', rec.id), ('shop_no', '=', rec.shop_no)]):
                    raise exceptions.ValidationError(_('Parduotuvė jau egzistuoja!'))

    @api.one
    @api.depends('pos_ids', 'location_id')
    def compute_state(self):
        if self.pos_ids and self.location_id:
            self.state = 'working'
        else:
            self.state = 'failed'

    @api.one
    @api.depends('pos_ids')
    def set_generic_pos(self):
        if self.pos_ids.filtered(lambda x: x.is_generic):
            self.generic_pos = self.pos_ids.filtered(lambda x: x.is_generic)[0]

    @api.one
    def create_generic_pos(self):
        generic = self.env['raso.shoplist.registers'].search([('shop_id', '=', self.id), ('is_generic', '=', True)])
        if not generic:
            self.env['raso.shoplist.registers'].create({
                'is_generic': True,
                'pos_no': self.shop_no + '/Generic' if self.shop_no else 'Generic',
                'shop_id': self.id,
            })
        else:
            generic.write({'pos_no': self.shop_no + '/Generic' if self.shop_no else 'Generic'})

    @api.multi
    def import_shops(self):
        if self._context.get('force', False):
            shops_to_import = self
            prices_to_import = self.mapped('price_ids')
            discounts_to_import = self.mapped('discount_ids')
        else:
            shops_to_import = self.env['raso.shoplist']
            for rec in self:
                latest_num = rec.get_last_import_revision_num()
                if not latest_num or latest_num != rec.revision_number:
                    shops_to_import += rec

            prices_to_import = self.env['product.template.prices']
            for price_id in self.mapped('price_ids'):
                if price_id.last_update_state in ['rejected', 'out_dated', 'not_tried']:
                    prices_to_import += price_id
                if price_id.last_update_state in ['waiting']:
                    latest_num = price_id.get_last_import_revision_num()
                    if not latest_num or latest_num != price_id.revision_number:
                        prices_to_import += price_id

            discounts_to_import = self.env['product.template.discounts']
            for discount_id in self.mapped('discount_ids'):
                if discount_id.last_update_state in ['rejected', 'out_dated', 'not_tried']:
                    discounts_to_import += discount_id
                if discount_id.last_update_state in ['waiting']:
                    latest_num = discount_id.get_last_import_revision_num()
                    if not latest_num or latest_num != discount_id.revision_number:
                        discounts_to_import += discount_id

        if shops_to_import:
            import_obj = self.env['sync.data.import'].sudo().create({
                'data_type': '0',
                'shop_ids': [(4, shop) for shop in shops_to_import.ids],
                'full_sync': self._context.get('full_sync', False)
            })
            import_obj.format_xml()
            shops_to_import._need_to_update()

        if prices_to_import:
            prices_4 = prices_to_import.filtered(lambda x: x.data_type == '4')
            if prices_4:
                import_obj = self.env['sync.data.import'].sudo().create({
                    'data_type': '4',
                    'prices_ids': [(4, price) for price in prices_4.ids],
                    'full_sync': self._context.get('full_sync', False)
                })
                import_obj.format_xml()
                prices_4._need_to_update()

            prices_7 = prices_to_import.filtered(lambda x: x.data_type == '7')
            if prices_7:
                import_obj = self.env['sync.data.import'].sudo().create({
                    'data_type': '7',
                    'prices_ids': [(4, price) for price in prices_7.ids],
                    'full_sync': self._context.get('full_sync', False)
                })
                import_obj.format_xml()
                prices_7._need_to_update()

        if discounts_to_import:
            import_obj = self.env['sync.data.import'].sudo().create({
                'data_type': '5',
                'discount_ids': [(4, disc) for disc in discounts_to_import.ids],
                'full_sync': self._context.get('full_sync', False)
            })
            import_obj.format_xml()
            discounts_to_import._need_to_update()


RasoShopList()
