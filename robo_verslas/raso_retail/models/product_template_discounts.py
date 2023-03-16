# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _
from .. import rr_tools as rt

TRIGGER_FIELDS = [
    'product_id', 'shop_id', 'name', 'status', 'quantity', 'price', 'discount_amount',
    'amount', 'weekdays', 'starts_at', 'ends_at', 'card_required', 'applies_to_product',
    'discount_from_product', 'type', 'aid', 'enabled',
]
M2O_TRIGGER_FIELDS = [
    'product_id', 'shop_id',
]


class ProductTemplateDiscounts(models.Model):
    _name = 'product.template.discounts'
    _inherit = ['mail.thread', 'importable.to.raso']

    def default_product(self):
        parent_id = self._context.get('active_id')
        if parent_id:
            return self.env['product.template'].browse(parent_id).id

    product_id = fields.Many2one('product.template', string='Produktas', required=True, default=default_product, ondelete='cascade')
    shop_id = fields.Many2one('raso.shoplist', string='Parduotuvė kuriai galioja nuolaida')
    all_shop_discount = fields.Boolean(compute='_all_shop_discount', string='Nuolaida galioja visoms parduotuvėms')
    name = fields.Char(string='Nuolaidos pavadinimas')
    status = fields.Integer(string='Statusas')
    quantity = fields.Float(string='Kiekis')
    price = fields.Float(string='Kaina', help='Jei daugiau nei 0, nurodoma nauja prekės kaina')
    discount_amount = fields.Float(string='Nuolaida procentais')
    amount = fields.Float(string='Antrinis kiekis', help='Jei < 100 - šios prekės kiekis kvite iki kurio galioja nuolaida. '
                                                'Jei >=100 - šitų prekių suma kvite iki kurios galioja nuolaida.')
    weekdays = fields.Char(string='Savaitės dienos')
    starts_at = fields.Datetime(string='Galiojimo pradžios data')
    ends_at = fields.Datetime(string='Galiojimo pradžios pabaiga')
    card_required = fields.Boolean(string='Ar reikalinga lojalumo kortelė')
    applies_to_product = fields.Boolean(string='Nuolaida taikoma šiam produktui')
    discount_from_product = fields.Boolean(string='Nuolaida taikoma kai kvite yra šis produktas')
    type = fields.Selection([('1', '1 Tipas'),
                             ('5', '2 Tipas'),
                             ('7', '3 Tipas')],
                            string='Nuolaidos tipas', default='5', required=True)
    aid = fields.Integer(string='Nuolaida susijusiu produktų identifikatorius')
    enabled = fields.Boolean(string='Įgalintas')
    revision_number = fields.Integer(string='Įrašo versija', copy=False)
    imported_ids = fields.Many2many('sync.data.import', copy=False)

    state = fields.Selection(
        [('working', 'Nuolaida sukonfigūruota'),
         ('failed', 'Trūksta konfigūracijos')],
        string='Būsena', track_visibility='onchange',
        compute='_compute_state',
    )
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
    def _all_shop_discount(self):
        if not self.shop_id:
            self.all_shop_discount = True

    @api.multi
    def open_discounts(self):
        self.ensure_one()
        return {
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'product.template.discounts',
                'res_id': self.id,
                'view_id': self.env.ref('raso_retail.raso_discounts_form').id,
                'type': 'ir.actions.act_window',
                'target': 'current',
        }

    @api.model
    def import_discounts_action(self):
        action = self.env.ref('raso_retail.import_discounts_action_rec')
        if action:
            action.create_action()

    @api.multi
    def import_product_discount_inline(self):
        self.ensure_one()
        if not self.importable_to_raso:
            raise exceptions.ValidationError('Produktas susijęs su šia nuolaida nėra importuojamas į RASO')
        self.import_product_discounts()
        self.env.cr.commit()
        raise exceptions.ValidationError('Nuolaida sėkmingai importuota! Laukiama atsakymo iš RASO')

    @api.multi
    def import_product_discounts(self):
        discounts = self.filtered(lambda x: x.importable_to_raso)
        if discounts:
            import_obj = self.env['sync.data.import'].sudo().create({
                'data_type': '5',
                'discount_ids': [(4, disc) for disc in discounts.ids],
                'full_sync': self._context.get('full_sync', False)
            })
            import_obj.format_xml()
            discounts._need_to_update()

    @api.multi
    @api.depends('product_id')
    def _compute_state(self):
        for rec in self:
            rec.state = 'working' if rec.product_id else 'failed'

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

        return super(ProductTemplateDiscounts, self).write(vals)
