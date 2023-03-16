# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, tools, _
from .. import rr_tools as rt

vat_code_mapper = {
    1: 21,
    2: 5,
    3: 0
}

TRIGGER_FIELDS = [
    'barcode', 'name', 'min_price', 'max_price', 'vat_code', 'dep_no',
    'uom_id', 'extra_qty', 'extra_code', 'group_code', 's_date', 's_number',
    'text', 'age', 'refundable', 'comment_required', 'is_weighing', 'scale',
    'use_up', 'supplier_code', 'supplier_name', 'discount_status', 'disc_points_status',
    'start_time', 'end_time',
]

M2M_TRIGGER_FIELDS = [
    'price_ids', 'discount_ids',
]


class ProductTemplate(models.Model):
    _name = 'product.template'
    _inherit = ['product.template', 'mail.thread', 'importable.to.raso']

    # barcode = fields.Char('Barcode', oldname='ean13', related='product_variant_ids.barcode', required=True)
    max_dic = fields.Float(string='Maksimali nuolaida')
    vat_code = fields.Selection([(1, '21%'),
                                 (2, '5%'),
                                 (3, '0%')],
                                string='Prekės mokesčio lentelė', default=1)
    list_price = fields.Float(inverse='_set_list_price')
    dep_no = fields.Integer(string='Prekės skyriaus numeris')
    extra_qty = fields.Float(string='Prekių kiekis pakuotėje')
    extra_code = fields.Char(string='Prekei priskirtos taros kodas')
    s_date = fields.Datetime(string='Prekės sertifikato data')
    min_price = fields.Float(string='Minimali kaina')
    max_price = fields.Float(string='Maksimali kaina')
    s_number = fields.Char(string='Prekės sertifikato numeris')
    age = fields.Integer(string='Amžius')
    refundable = fields.Boolean(string='Grąžinamas', default=True)
    comment_required = fields.Boolean(string='Ar reikalingas komentaras')
    is_weighing = fields.Boolean(string='Sveriamas')
    scale = fields.Integer(string='Svarstyklių numeris (Sveriamam produktui)')
    use_up = fields.Integer(string='Produkto suvartojimo laikas dienomis (Sveriamam produktui)')
    supplier_code = fields.Char(string='Tiekėjo kodas')
    supplier_name = fields.Char(string='Tiekėjo pavadinimas')

    text = fields.Text(string='Papildoma informacija')
    discount_status = fields.Selection([('0', 'Nuolaida taikoma'),
                                        ('1', 'Taikoma maksimali nuolaida'),
                                        ('2', 'Nuolaida netaikoma')],
                                       string='Nuolaidos taikymas', default='0')
    disc_points_status = fields.Selection([('0', 'Skiriami'),
                                           ('2', 'Neskiriami')],
                                          string='Ar skiriami taškai už prekę', default='2')
    start_time = fields.Datetime(string='Prekės galiojimo pradžios data')
    end_time = fields.Datetime(string='Prekės galiojimo pabaigos data')

    imported_ids = fields.Many2many('sync.data.import', copy=False)
    price_ids = fields.One2many('product.template.prices', 'product_id')
    discount_ids = fields.One2many('product.template.discounts', 'product_id')
    group_code = fields.Char(compute='_compute_group_code', string='Kategorijos kodas')

    revision_number = fields.Integer(string='Įrašo versija', copy=False)
    need_to_update = fields.Boolean(string='Reikia atnaujinti', compute='_need_to_update', store=True)
    importable_to_raso = fields.Boolean(compute='_compute_importable_to_raso')

    @api.multi
    @api.depends('categ_id')
    def _compute_group_code(self):
        for rec in self:
            rec.group_code = rec.sudo().categ_id.code

    @api.multi
    @api.depends('categ_id.importable_to_raso')
    def _compute_importable_to_raso(self):
        """Move to compute instead of related, since related triggers categ_id field's constraints"""
        for rec in self:
            rec.importable_to_raso = rec.categ_id.importable_to_raso

    @api.multi
    def _set_list_price(self):
        if self.env.context.get('raso_bypass_listprice_sync'):
            return
        for rec in self:
            percentage = vat_code_mapper.get(rec.vat_code, 0)
            computed_price = tools.float_round(
                rec.list_price / 100 * percentage + rec.list_price, precision_digits=2
            )
            if rec.price_ids:
                rec.price_ids.write({'price': computed_price})
            else:
                rec.env['product.template.prices'].create({
                    'price': computed_price, 'product_id': rec.id, 'qty': 0
                })

    @api.multi
    @api.depends('last_update_state', 'price_ids.last_update_state', 'discount_ids.last_update_state',
                 'importable_to_raso', 'revision_number', 'categ_id.importable_to_raso')
    def _need_to_update(self):
        """Check whether product needs updating"""
        for rec in self:
            need_to_update = False
            if rec.importable_to_raso:
                need_to_update = rec.last_update_state in rt.UPDATE_IMPORT_STATES
                # Check related prices and discounts
                if not need_to_update:
                    need_to_update = any(x.last_update_state in rt.UPDATE_IMPORT_STATES for x in rec.price_ids)
                if not need_to_update:
                    need_to_update = any(x.last_update_state in rt.UPDATE_IMPORT_STATES for x in rec.discount_ids)
            rec.need_to_update = need_to_update

    @api.onchange('list_price')
    def onchange_list_price(self):
        return {'warning': {'title': _('Įspėjimas'),
                            'message': _('Nepamirškite patikrinti produkto kainos "Raso" skiltyje. '
                                         'Produkto kaina "Raso" skiltyje yra skaičiuojama automatiškai, taikant PVM. '
                                         'PVM procentas pateiktas žemiau, bloke "Raso informacija"')}}

    @api.onchange('barcode')
    def _onchange_barcode(self):
        """Strip whitespaces and ensure that barcode length is not less than 13"""
        if self.barcode:
            self.barcode = self.barcode.replace(' ', '').zfill(13)

    @api.multi
    @api.constrains('barcode')
    def constrains_barcode(self):
        for rec in self:
            if rec.barcode and len(rec.barcode) < 13:
                raise exceptions.ValidationError(_('Barkodas privalo būti bent 13 simbolių ilgio'))
            if rec.product_variant_ids and not rec.barcode and rec.importable_to_raso:
                raise exceptions.ValidationError(_('Barkodas yra privalomas!'))

    @api.multi
    @api.constrains('price_ids')
    def _constraint_price_ids(self):
        """
        Constraint to ensure that product does not contain more than one price that is applied to all shops
        or if it contains multiple prices, each price must be individual, for specific shop.
        :return: None
        """
        for rec in self:
            shop_count = len(rec.mapped('price_ids.shop_id'))
            if (not shop_count and len(rec.price_ids) > 1) or (shop_count and shop_count != len(rec.price_ids)):
                raise exceptions.ValidationError(_('Produktas turi bent vieną kainą kuri yra pritaikoma du kartus!'))

    @api.multi
    @api.constrains('discount_ids')
    def _constraint_discount_ids(self):
        """
        Constraint to ensure that product does not contain more than one discount that is applied to all shops
        or if it contains multiple discount, each discount must be individual, for specific shop.
        :return: None
        """
        for rec in self:
            shop_count = len(rec.mapped('discount_ids.shop_id'))
            if (not shop_count and len(rec.discount_ids) > 1) or (shop_count and shop_count != len(rec.discount_ids)):
                raise exceptions.ValidationError(_('Produktas turi bent vieną nuolaidą kuri yra pritaikoma du kartus!'))

    @api.multi
    @api.constrains('name')
    def _constraint_name_rr(self):
        """
        Constraint to ensure that name is not longer than 80 symbols if product
        belongs to the category that is importable to Raso Retail
        :return: None
        """
        for rec in self:
            if rec.categ_id.importable_to_raso and len(rec.name) > 80:
                raise exceptions.ValidationError(
                    _('Produktai kurie yra importuojami į Raso privalo turėti pavadinimą '
                      'trumpesnį nei 80 simbolių! Produkto "{}" pavadinimas yra {} simoblių ilgio').format(
                        rec.name, len(rec.name))
                )

    @api.multi
    def write(self, vals):
        for rec in self:
            # Barcode can't be changed if product was already imported
            if 'barcode' in vals and rec.last_update_state != 'not_tried':
                raise exceptions.ValidationError(
                    _('Negalima keisti produkto barkodo, jei jis jau buvo importuotas į RASO. '
                      'Jeigu pageidaujate keisti barkodą, susikurkite naują produkto kortelę.')
                )
            # Collect the fields that have unchanged values
            fields_to_pop = []
            for field, value in vals.items():
                if field in TRIGGER_FIELDS:
                    current_value = getattr(rec, field)
                    if field == 'uom_id':
                        current_value = current_value.id
                    if current_value == value:
                        fields_to_pop.append(field)
            # Pop the fields
            for field in fields_to_pop:
                vals.pop(field)

            # If any of the trigger fields is written to the line increase revision number as well
            if any(x in vals for x in TRIGGER_FIELDS + M2M_TRIGGER_FIELDS):
                vals['revision_number'] = rec.revision_number + 1

        res = super(ProductTemplate, self).write(vals)
        return res

    @api.multi
    def unlink(self):
        if self.env.user.has_group('stock.group_stock_manager') or self.env.user.is_premium_manager():
            self.mapped('price_ids').sudo().unlink()
            self.mapped('discount_ids').sudo().unlink()

        trigger_full_sync = any(x.imported_ids for x in self)
        res = super(ProductTemplate, self).unlink()
        if trigger_full_sync:
            self.sudo().env['sync.data.import'].full_sync_products()
        return res

    @api.multi
    def toggle_active(self):
        trigger_full_sync = any(x.imported_ids for x in self)
        res = super(ProductTemplate, self).toggle_active()
        if trigger_full_sync:
            self.sudo().env['sync.data.import'].full_sync_products()
        return res

    @api.model
    def import_raso_products_action(self):
        action = self.env.ref('raso_retail.import_raso_products_rec')
        if action:
            action.create_action()

    @api.model
    def import_raso_products_action_force(self):
        action = self.env.ref('raso_retail.import_raso_products_rec_force')
        if action:
            action.create_action()

    @api.multi
    def import_products(self):
        self.check_access_rights('write')
        # Filter out products that are importable to Raso
        prods_to_import = self.filtered(lambda x: x.importable_to_raso)
        prices_to_import = discounts_to_import = None
        # If skip_children is in the context, related objects are not updated
        if not self._context.get('skip_children'):
            prices_to_import = prods_to_import.mapped('price_ids')
            discounts_to_import = prods_to_import.mapped('discount_ids')
            # If 'force' is not in context, filter out child objects that explicitly need updating
            if not self._context.get('force'):
                prices_to_import = prices_to_import.filtered(lambda x: x.need_to_update)
                discounts_to_import = discounts_to_import.filtered(lambda x: x.need_to_update)
        # Simulate constraint, but change the name instead of the raise
        for product in prods_to_import:
            if len(product.name) > 80:
                # Ensure that the name is not longer than 80 chars
                # Static number described in Raso Retail documentation
                product.write({'name': product.name[:77] + '...'})

        if prods_to_import:
            import_obj = self.env['sync.data.import'].sudo().create({
                'data_type': '3',
                'product_ids': [(4, prod) for prod in prods_to_import.ids],
                'full_sync': self._context.get('full_sync', False)
            })
            import_obj.format_xml()
            prods_to_import._need_to_update()

        if prices_to_import:
            prices_4 = prices_to_import.filtered(lambda x: x.data_type == '4')
            if prices_4:
                import_obj = self.env['sync.data.import'].sudo().create({
                    'data_type': '4',
                    'prices_ids': [(4, price) for price in prices_4.ids],
                })
                import_obj.format_xml()
                prices_4._need_to_update()

            prices_7 = prices_to_import.filtered(lambda x: x.data_type == '7')
            if prices_7:
                import_obj = self.env['sync.data.import'].sudo().create({
                    'data_type': '7',
                    'prices_ids': [(4, price) for price in prices_7.ids],
                })
                import_obj.format_xml()
                prices_7._need_to_update()

        if discounts_to_import:
            import_obj = self.env['sync.data.import'].sudo().create({
                'data_type': '5',
                'discount_ids': [(4, disc) for disc in discounts_to_import.ids],
            })
            import_obj.format_xml()
            discounts_to_import._need_to_update()

        self.env.cr.commit()
        if not self._context.get('full_sync', False):
            if len(self.filtered(lambda x: x.importable_to_raso)) != len(self):
                failed = self.filtered(lambda x: not x.importable_to_raso)
                msg = 'Nepavyko importuoti šių produktų nes jų kategorija pažymėta kaip neimportuojama į RASO\n'
                for prod in failed:
                    msg += prod.name + '\n'
                if prods_to_import:
                    msg += '\nVisi kiti pasirinkti produktai buvo importuoti sėkmingai. Laukiama atsakymo iš RASO'
                raise exceptions.ValidationError(msg)
            else:
                raise exceptions.ValidationError('Produktai importuoti sėkmingai! Laukiama atsakymo iš RASO')
