# -*- coding: utf-8 -*-


from odoo import _, api, exceptions, fields, models


class ProductCategory(models.Model):
    _inherit = 'product.category'

    active = fields.Boolean(string='Aktyvus', default=True)
    icon = fields.Char(string='Ikona')
    color = fields.Char(string='Spalva')
    ultimate_icon = fields.Char(string='Ikona', compute='_ultimate_info', store=True)
    ultimate_color = fields.Char(string='Spalva', compute='_ultimate_info', store=True)
    ultimate_name = fields.Char(string='Pavadinimas', compute='_ultimate_info', store=True)
    full_name = fields.Char(string='Visas pavadinimas', compute='_full_name', store=True)
    ultimate_id = fields.Many2one('product.category', compute='_ultimate_id', store=True)

    @api.multi
    @api.constrains('name')
    def unique_category_name(self):
        for rec in self:
            if self.search([('name', '=', rec.name)], count=True) > 1:
                if self.env.user.has_group('base.group_system'):
                    raise exceptions.ValidationError(
                        _('Kategorijos pavadinimas privalo būti unikalus. Pasikartojanti kategorija %s.') % rec.name)
                raise exceptions.ValidationError(_('Kategorijos pavadinimas privalo būti unikalus.'))

    @api.one
    @api.depends('name', 'parent_id.name')
    def _full_name(self):
        parent_id = self
        temp = parent_id.name
        while parent_id.parent_id:
            parent_id = parent_id.parent_id
            temp = parent_id.name + ' / ' + temp
        self.full_name = temp

    @api.one
    @api.depends('parent_id')
    def _ultimate_id(self):
        parent_id = self
        temp = parent_id.id
        while parent_id.parent_id:
            parent_id = parent_id.parent_id
            temp = parent_id.id
        self.ultimate_id = temp

    @api.one
    @api.depends('parent_id.icon', 'parent_id.color', 'parent_id.name', 'icon', 'color', 'name')
    def _ultimate_info(self):
        parent_id = self
        while parent_id.parent_id:
            parent_id = parent_id.parent_id
        self.ultimate_color = parent_id.color
        self.ultimate_icon = parent_id.icon
        self.ultimate_name = parent_id.name

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        if not args:
            args = []
        if name:
            categories = self.search([('full_name', operator, name)], limit=limit)
        else:
            categories = self.search(args, limit=limit)
        return categories.name_get()
