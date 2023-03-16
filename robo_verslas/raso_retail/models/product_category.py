# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _
from .. import rr_tools as rt


class ProductCategory(models.Model):
    _name = 'product.category'
    _inherit = ['product.category', 'mail.thread', 'importable.to.raso']

    level = fields.Integer(string='Prekių kategorijos lygis')
    code = fields.Char(string='Kategorijos kodas', required=True)
    age = fields.Integer(string='Amžiaus apribojimai')
    refundable = fields.Boolean(string='Ar produktai grąžinami', default=True)

    cat_discount_ids = fields.One2many('product.category.discounts', 'category_id')
    imported_ids = fields.Many2many('sync.data.import', copy=False)
    parent_code = fields.Char(compute='get_parent_code')

    revision_number = fields.Integer(string='Įrašo versija', copy=False)
    need_to_update = fields.Boolean(string='Reikia atnaujinti', compute='_need_to_update', store=True)
    importable_to_raso = fields.Boolean(string='Importuojama į RASO', track_visibility='onchange')

    @api.multi
    @api.constrains('importable_to_raso')
    def constraints_importable(self):
        for rec in self:
            if not rec.importable_to_raso:
                if rec.last_update_state != 'not_tried':
                    raise exceptions.ValidationError(
                        _('Negalite pakeisti kategorijos į neimportuojamą. Kategorija jau yra įkelta į RASO')
                    )
            products = self.env['product.template'].search([('categ_id', '=', rec.id)])
            no_barcode_products = str()
            for product in products:
                if not rec.importable_to_raso and product.last_update_state != 'not_tried':
                    raise exceptions.ValidationError(
                        _('Negalite pakeisti kategorijos į neimportuojamą. '
                          'Kategorija turi bent vieną produktą kuris jau yra importuotas į RASO'))
                # If product does not have a barcode, append it to the display list
                if rec.importable_to_raso and not product.barcode:
                    no_barcode_products += '{}\n'.format(product.display_name)
            # Raise one global error if there are any products without barcode
            if no_barcode_products:
                raise exceptions.ValidationError(
                    _('Kategorija turi produktų kuriems nėra nustatytas barkodas. '
                      'Šis laukelis yra būtinas norint įkelti produktus į Raso serverį. '
                      'Pakoreguokite apačioje minimus produktus ir pakartokite veiksmą.\n\n{}'
                      ).format(no_barcode_products)
                )

    @api.one
    @api.depends('last_update_state', 'cat_discount_ids.last_update_state', 'importable_to_raso', 'revision_number')
    def _need_to_update(self):
        if not self.importable_to_raso:
            self.with_context(prevent_loop=True).need_to_update = False
        else:
            need_to_update = False
            for disc_id in self.cat_discount_ids:
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
        res = super(ProductCategory, self).write(vals)
        for rec in self:
            if self._context.get('prevent_loop', False):
                self.with_context(prevent_loop=False)
                continue
            else:
                if not self._context.get('skip_revision_increments', False):
                    rec.with_context(prevent_loop=True).revision_number += 1
        return res

    @api.model
    def import_raso_cats_action(self):
        action = self.env.ref('raso_retail.import_raso_categories_rec')
        if action:
            action.create_action()

    @api.model
    def import_raso_cats_action_force(self):
        action = self.env.ref('raso_retail.import_raso_categories_rec_force')
        if action:
            action.create_action()

    @api.one
    @api.depends('parent_id')
    def get_parent_code(self):
        if self.parent_id:
            self.parent_code = self.parent_id.code

    @api.multi
    def import_categories(self):
        if self._context.get('force', False):
            discounts_to_import = self.filtered(lambda x: x.importable_to_raso).mapped('cat_discount_ids')
            cats_to_import = self.filtered(lambda x: x.importable_to_raso)
        else:
            cats_to_import = self.env['product.category']
            for rec in self.filtered(lambda x: x.importable_to_raso):
                latest_num = rec.get_last_import_revision_num()
                if not latest_num or latest_num != rec.revision_number:
                    cats_to_import += rec

            discounts_to_import = self.env['product.category.discounts']
            for discount_id in self.filtered(lambda x: x.importable_to_raso).mapped('cat_discount_ids'):
                if discount_id.last_update_state in ['rejected', 'out_dated', 'not_tried']:
                    discounts_to_import += discount_id
                if discount_id.last_update_state in ['waiting']:
                    latest_num = discount_id.get_last_import_revision_num()
                    if not latest_num or latest_num != discount_id.revision_number:
                        discounts_to_import += discount_id

        if cats_to_import:
            import_obj = self.env['sync.data.import'].sudo().create({
                'data_type': '2',
                'category_ids': [(4, cat) for cat in cats_to_import.ids],
                'full_sync': self._context.get('full_sync', False)
            })
            import_obj.format_xml()
            cats_to_import._need_to_update()

        if discounts_to_import:
            import_obj = self.env['sync.data.import'].sudo().create({
                'data_type': '6',
                'group_discount_ids': [(4, disc) for disc in discounts_to_import.ids],
                'full_sync': self._context.get('full_sync', False)
            })
            import_obj.format_xml()
            discounts_to_import._need_to_update()

        self.env.cr.commit()
        if not self._context.get('full_sync', False):
            if len(self.filtered(lambda x: x.importable_to_raso)) != len(self):
                failed = self.filtered(lambda x: not x.importable_to_raso)
                msg = 'Nepavyko importuoti šių kategorijų nes jos pažymėtos kaip neimportuojamos į RASO\n'
                for cat in failed:
                    msg += cat.name + '\n'
                if cats_to_import:
                    msg += '\nVisos kitos kategorijos buvo importuotos sėkmingai. Laukiama atsakymo iš RASO'
                raise exceptions.ValidationError(msg)
            else:
                raise exceptions.ValidationError('Kategorijos importuotos sėkmingai! Laukiama atsakymo iš RASO')

    @api.multi
    @api.constrains('code')
    def code_constrain(self):
        for rec in self.filtered('code'):
            if self.env['product.category'].search_count([('id', '!=', rec.id), ('code', '=', rec.code)]):
                raise exceptions.UserError(_('Kategorija su šiuo kodu jau egzistuoja!'))
