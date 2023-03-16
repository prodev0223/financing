# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, tools, _

# TODO: If need arises, we can allow multiple rules
# TODO: with validity date functionality


class RKeeperModifierRule(models.Model):
    _name = 'r.keeper.modifier.rule'
    _description = '''
    Model that stores rKeeper modifier records
    '''
    # Modifier that rule is applied to
    modifier_id = fields.Many2one('r.keeper.modifier', string='Modifikatorius')

    # Action product is either added to the modified BOM, removed or swapped
    # to swap_product_id based on the applied action in the current modifier
    modified_product_id = fields.Many2one(
        'product.product', string='Modifikuojamas produktas (komplektacija)',
        compute='_compute_modified_product_id', store=True,
    )
    location_src_id = fields.Many2one('stock.location', string='Atsargų vieta')
    remove_product_id = fields.Many2one('product.product', string='Šalinamas produktas')
    add_product_id = fields.Many2one('product.product', string='Pridedamas produktas')
    action_quantity = fields.Float(string='Pridedamas kiekis')
    applied_action = fields.Selection(
        [('add', 'Pridėti produktą'),
         ('remove', 'Pašalinti produktą'),
         ('swap', 'Sukeisti produktą'),
         ('no_action', 'Jokio veiksmo'),
         ], string='Taisyklės veiksmas')

    # Rule is only used if configured flag is set
    configured = fields.Boolean(
        string='Sukonfigūruota', store=True,
        compute='_compute_configured',
    )
    configured_text = fields.Text(
        compute='_compute_configured',
    )

    @api.multi
    @api.depends('modifier_id', 'modifier_id.product_id')
    def _compute_modified_product_id(self):
        """Get modified product from modifier"""
        for rec in self:
            rec.modified_product_id = rec.modifier_id.product_id

    @api.multi
    @api.depends('applied_action', 'remove_product_id', 'add_product_id')
    def _compute_configured(self):
        """Check whether current rule is configured"""
        for rec in self:
            configured = (rec.applied_action == 'add' and rec.add_product_id) or \
                    (rec.applied_action == 'remove' and rec.remove_product_id) or \
                    (rec.applied_action == 'swap' and rec.remove_product_id and rec.add_product_id) \
                    or rec.applied_action == 'no_action'
            rec.configured = configured
            rec.configured_text = _('Sėkmingai sukonfigūruota') if configured else _('Trūksta konfigūracijos')

    @api.multi
    @api.constrains('modifier_id')
    def _check_modifier_id(self):
        """Ensure that there's one rule per modifier"""
        for rec in self:
            if self.search_count([('modifier_id', '=', rec.modifier_id.id)]) > 1:
                raise exceptions.ValidationError(
                    _('Modifikatorius {} jau turi priskirtą taisyklę').format(rec.display_name)
                )

    @api.multi
    @api.constrains('action_quantity', 'applied_action')
    def _check_action_quantity(self):
        """Ensures that add quantity is not zero if action is to swap or to add a product"""
        # Skip execution on superuser
        if not self.env.user.has_group('base.group_system'):
            for rec in self:
                if rec.applied_action in ['add', 'swap'] \
                        and tools.float_is_zero(rec.action_quantity, precision_digits=2):
                    raise exceptions.ValidationError(
                        _('Privalote nurodyti pridedamą kiekį')
                    )

    @api.multi
    @api.constrains('add_product_id')
    def _check_add_product_id(self):
        """Ensure that add product ID is not the same as modified product ID"""
        for rec in self.filtered('add_product_id'):
            if rec.add_product_id == rec.modified_product_id:
                raise exceptions.ValidationError(
                    _('Negalite pridėti to paties produkto, kaip kad modifikuojamas produktas')
                )

    @api.multi
    def name_get(self):
        """Custom name get for modifier rule"""
        return [(x.id, _('Taisyklė [{}]{} -- {}').format(
            x.applied_action, x.remove_product_id.name or str(), x.modified_product_id.display_name)) for x in self]

    @api.multi
    def unlink(self):
        """Forbid unlinking modifier rules if it's the last rule for specific modifier"""
        if not self.env.user.has_group('base.group_system'):
            for rec in self:
                if not self.env['r.keeper.modifier.rule'].search_count(
                        [('id', '!=', rec.id), ('modifier_id', '=', rec.modifier_id.id)]
                ):
                    raise exceptions.ValidationError(
                        _('Negalite ištrinti paskutinės konkretaus modifikatoriaus taisyklės')
                    )
        return super(RKeeperModifierRule, self).unlink()
