# -*- coding: utf-8 -*-


from odoo import _, api, exceptions, fields, models


class CategoryMapping(models.Model):
    _name = 'category.mapping'

    partner_id = fields.Many2one('res.partner', string='Tiekėjas', required=True)
    category = fields.Char(string='Kategorija', compute='_category', store=True)
    category_id = fields.Many2one('product.category', string='Išlaidų kategorija', required=True)
    confirmed = fields.Boolean(string='Patvirtinta buhalterio', default=False, readonly=True)
    active = fields.Boolean(string='Aktyvus', default=True)

    @api.one
    @api.depends('category_id.name')
    def _category(self):
        self.category = self.category_id.name

    @api.multi
    def approve(self):
        self.ensure_one()
        if self.env.user.is_accountant():
            self.write({'confirmed': True})

    @api.multi
    def decline(self):
        self.ensure_one()
        self.sudo().write({'confirmed': False, 'active': False})

    @api.multi
    @api.constrains('partner_id', 'category')
    def constraint_unique(self):
        for rec in self:
            if self.search_count(
                    [('partner_id', '=', rec.partner_id.id), ('category_id', '=', rec.category_id.id)]) > 1:
                raise exceptions.ValidationError(_('Toks išlaidų skirstymas jau pridėtas.'))

    @api.multi
    def write(self, vals):
        if 'confirmed' in vals and not self.env.user.is_accountant():
            vals.pop('confirmed')
        for rec in self:
            if not self.env.user.is_accountant() and rec.confirmed and vals:
                raise exceptions.UserError(
                    _('Patvirtintų išlaidų kategorijų keisti nebegalima. Spauskite mygtuką panaikinti.'))
        return super(CategoryMapping, self).write(vals)
