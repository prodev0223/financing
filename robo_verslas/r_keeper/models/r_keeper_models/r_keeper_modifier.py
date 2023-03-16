# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _


class RKeeperModifier(models.Model):
    _name = 'r.keeper.modifier'
    _description = '''
    Model that stores rKeeper modifier records
    '''

    composed_identifier = fields.Char(
        string='Identifikatorius', store=True,
        compute='_compute_composed_identifier'
    )
    # O2m for potential future expansion
    modifier_rule_ids = fields.One2many(
        'r.keeper.modifier.rule', 'modifier_id',
        string='Modifikatoriaus taisyklės'
    )
    product_id = fields.Many2one(
        'product.product', string='Modifikuojamas produktas',
        compute='_compute_product_id', store=True
    )
    # Modifier information
    modifier_code = fields.Char(string='Modifikatoriaus kodas', inverse='_set_modifier_code')
    modifier_name = fields.Char(string='Modifikatoriaus pavadinimas')
    product_code = fields.Char(string='Modifikuojamo produkto kodas')

    @api.multi
    @api.depends('modifier_code', 'product_code')
    def _compute_composed_identifier(self):
        """Computes unique ID based on product and modifier codes"""
        for rec in self:
            rec.composed_identifier = '[{}]-[{}]'.format(rec.modifier_code, rec.product_code)

    @api.multi
    @api.depends('product_code')
    def _compute_product_id(self):
        """
        Related current modifier's product to system
        product based on passed code
        :return: None
        """
        for rec in self.filtered(lambda x: x.product_code):
            rec.product_id = self.env['product.product'].sudo().search(
                [('default_code', '=', rec.product_code)], limit=1
            )

    @api.multi
    def _set_modifier_code(self):
        """Create base rule on inverse if it does not exist"""
        for rec in self:
            if not rec.modifier_rule_ids:
                base_modifier_rule = [(0, 0, {
                    'applied_action': 'add',
                })]
                rec.write({'modifier_rule_ids': base_modifier_rule})

    @api.multi
    @api.constrains('composed_identifier')
    def _check_composed_identifier(self):
        """Ensure composed ID uniqueness"""
        for rec in self:
            if self.search_count([('composed_identifier', '=', rec.composed_identifier)]) > 1:
                raise exceptions.ValidationError(_('Jau egzistuoja modifikatorius su šiuo ID'))

    @api.multi
    def name_get(self):
        """Custom name get for modifiers"""
        return [(x.id, _('[{}]{} -- Modifikuojama: {}').format(
            x.modifier_code, x.modifier_name, x.product_id.display_name)) for x in self]

    @api.multi
    def unlink(self):
        """Forbid unlinking of modifiers that have sales with productions"""
        if not self.env.user.has_group('base.group_system'):
            for rec in self:
                if self.env['r.keeper.sale.line.modifier'].search_count(
                        [('r_keeper_modifier_id', '=', rec.id)]):
                    raise exceptions.ValidationError(
                        _('Negalite ištrinti modifikatoriaus kuris turi susijusių pardavimų')
                    )
        return super(RKeeperModifier, self).unlink()
