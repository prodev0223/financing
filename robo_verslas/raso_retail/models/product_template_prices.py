# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _
from .. import rr_tools as rt


TRIGGER_FIELDS = [
    'product_id', 'shop_id', 'price_no', 'qty', 'price', 'date_from', 'date_to'
]
M2O_TRIGGER_FIELDS = [
    'product_id', 'shop_id',
]


class ProductTemplatePrices(models.Model):
    _name = 'product.template.prices'
    _inherit = ['mail.thread', 'importable.to.raso']

    def default_product(self):
        parent_id = self._context.get('active_id')
        if parent_id:
            return self.env['product.template'].browse(parent_id).id

    product_id = fields.Many2one(
        'product.template', string='Produktas',
        required=True, default=default_product, ondelete='cascade'
    )
    shop_id = fields.Many2one('raso.shoplist', string='Parduotuvė kuriai galioja kaina')
    all_shop_price = fields.Boolean(compute='_all_shop_price', string='Kaina galioja visoms parduotuvėms')
    price_no = fields.Integer(string='Kainos eilės numeris')
    qty = fields.Float(required=True, string='Nuo kokio kiekio galioja kaina')
    price = fields.Float(required=True, string='Kaina su PVM')
    date_from = fields.Datetime(string='Kainos galiojimo pradžios data')
    date_to = fields.Datetime(string='Kainos galiojimo pradžios data')

    imported_ids = fields.Many2many('sync.data.import', copy=False)
    is_terminated = fields.Boolean(compute='_compute_terminated_info', string='Ar kaina terminuota')
    data_type = fields.Char(compute='_compute_terminated_info')

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
    importable_to_raso = fields.Boolean(compute='_compute_importable_to_raso')

    @api.multi
    def _compute_importable_to_raso(self):
        """Move to compute instead of related, since related triggers categ_id field's constraints"""
        for rec in self:
            rec.importable_to_raso = rec.product_id.categ_id.importable_to_raso

    @api.multi
    @api.depends('last_update_state', 'importable_to_raso', 'revision_number')
    def _need_to_update(self):
        for rec in self:
            rec.need_to_update = rec.importable_to_raso and rec.last_update_state in rt.UPDATE_IMPORT_STATES

    @api.one
    @api.depends('shop_id')
    def _all_shop_price(self):
        if not self.shop_id:
            self.all_shop_price = True

    @api.multi
    def open_price(self):
        self.ensure_one()
        return {
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'product.template.prices',
                'res_id': self.id,
                'view_id': self.env.ref('raso_retail.raso_prices_form').id,
                'type': 'ir.actions.act_window',
                'target': 'current',
        }

    @api.multi
    @api.depends('date_from', 'date_to')
    def _compute_terminated_info(self):
        for rec in self:
            terminated = rec.date_from or rec.date_to
            rec.is_terminated = terminated
            rec.data_type = '7' if terminated else '4'

    @api.multi
    def name_get(self):
        return [(price.id, _('Produktas %s/Kaina %s') % (str(price.product_id.barcode), str(price.price))) for price in self]

    @api.model
    def import_prices_action(self):
        action = self.env.ref('raso_retail.import_prices_action_rec')
        if action:
            action.create_action()

    @api.model
    def import_prices_term_action(self):
        action = self.env.ref('raso_retail.import_prices_term_action_rec')
        if action:
            action.create_action()

    @api.multi
    def import_product_price_inline(self):
        self.ensure_one()
        if not self.importable_to_raso:
            raise exceptions.ValidationError('Produktas susijęs su šia kaina nėra importuojamas į RASO')
        if self.data_type == '4':
            self.import_product_prices()
        else:
            self.import_product_prices_terminated()
        self.env.cr.commit()
        raise exceptions.ValidationError('Kaina sėkmingai importuota! Laukiama atsakymo iš RASO')

    @api.multi
    def import_product_prices(self):
        prices = self.filtered(lambda x: x.data_type == '4' and x.importable_to_raso)
        if not prices:
            raise exceptions.UserError(_('Paduotos kainos/a yra terminuotos arba neimportuojamos!'))
        import_obj = self.env['sync.data.import'].sudo().create({
            'data_type': '4',
            'prices_ids': [(4, price) for price in prices.ids],
            'full_sync': False
        })
        import_obj.format_xml()
        prices._need_to_update()

    @api.multi
    def import_product_prices_terminated(self):
        prices = self.filtered(lambda x: x.data_type == '7' and x.importable_to_raso)
        if not prices:
            raise exceptions.UserError(_('Paduotos kainos/a nėra terminuotos arba yra neimportuojamos!'))
        import_obj = self.env['sync.data.import'].sudo().create({
            'data_type': '7',
            'prices_ids': [(4, price) for price in prices.ids],
            'full_sync': self._context.get('full_sync', False)
        })
        import_obj.format_xml()
        prices._need_to_update()

    @api.one
    @api.depends('barcode')
    def get_product(self):
        self.product_id = self.env['product.template'].sudo().search(
            [('barcode', '=', self.barcode)], limit=1).id

    @api.multi
    def write(self, vals):
        for rec in self:
            # Collect the fields that have unchanged values
            fields_to_pop = []
            for field, value in vals.items():
                if field in TRIGGER_FIELDS:
                    current_value = getattr(rec, field)
                    if field in M2O_TRIGGER_FIELDS:
                        current_value = current_value.id
                    if current_value == value:
                        fields_to_pop.append(field)
            # Pop the fields
            for field in fields_to_pop:
                vals.pop(field)

            # If any of the trigger fields is written to the line increase revision number as well
            if any(x in vals for x in TRIGGER_FIELDS):
                vals['revision_number'] = rec.revision_number + 1

        return super(ProductTemplatePrices, self).write(vals)

