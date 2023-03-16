# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions
from odoo.tools.translate import _


class ResPartner(models.Model):

    _inherit = 'res.partner'

    name = fields.Char(track_visibility='onchange')
    kodas = fields.Char(string='Kompanijos/fizinio asmens kodas', track_visibility='onchange', inverse='_set_kodas')
    kliento_kodas = fields.Char(string='Kliento kodas gavėjo sistemoje')
    notify_email = fields.Selection(default='none')
    is_person = fields.Boolean(compute='_is_person')

    @api.one
    @api.depends('is_company')
    def _is_person(self):
        self.is_person = not self.is_company

    @api.multi
    def _set_kodas(self):
        for rec in self:
            if rec.kodas and rec.kodas.strip() != rec.kodas:
                rec.kodas = rec.kodas.strip()

    @api.multi
    @api.constrains('kodas', 'company_type', 'country_id', 'vat')
    def kodas_constraint(self):
        if self._context.get('ignore_partner_code_duplicates'):
            return
        for rec in self:
            if rec.id == self.sudo().env.user.company_id.partner_id.id and not \
                    self.env.user.has_group('base.group_system'):
                raise exceptions.ValidationError(_('Negalite keisti šios įmonės kodo.'))
            if rec.sudo().user_ids and not self.env.user.has_group('base.group_system'):
                raise exceptions.ValidationError(
                    _('Negalite keisti sistemos vartotojų asmens kodų. Eikite į darbuotojo kortelę.')
                )
            if not rec.parent_id and not rec.kodas and rec.company_type == 'company' \
                    and (rec.customer or rec.supplier) and rec.country_id.code == 'LT':
                raise exceptions.ValidationError(
                    _('Lietuviškoms bendrovėms privaloma nurodyti įmonės kodą. (%s)') % rec.name
                )
            elif not rec.parent_id and rec.kodas and not self.env.context.get('merging_partners', False):
                if self.env['res.partner'].search_count([('kodas', '=', rec.kodas), ('parent_id', '=', False)]) > 1:
                    if not rec.vat or self.env['res.partner'].search_count(
                            [('kodas', '=', rec.kodas), ('parent_id', '=', False),
                             ('id', '!=', rec.id), '|', ('vat', '=', False), ('vat', '=', rec.vat)]):
                        raise exceptions.ValidationError(
                            _('Jau egzistuoja partneris su tuo pačiu įmonės kodu. Įmonės kodas: %s') % rec.kodas
                        )
                    if rec.vat:
                        country_code = rec.vat[:2]
                        if country_code.isalpha() and self.env['res.partner'].search_count([
                                ('kodas', '=', rec.kodas), ('parent_id', '=', False),
                                ('id', '!=', rec.id), ('vat', '=like', country_code + '%')]):
                            raise exceptions.ValidationError(
                                _('Jau egzistuoja partneris su tuo pačiu įmonės kodu ir skirtingas PVM kodas. Įmonės kodas: %s') % rec.kodas
                            )

    @api.onchange('kodas')
    def onchange_kodas(self):
        if self._context:
            kodas = self._context.get('kodas', False)
            if kodas:
                self.kodas = kodas
            vardas = self._context.get('vardas', False)
            if vardas:
                self.name = vardas

    @api.onchange('vat')
    def vat_change(self):
        if self.vat:
            self.vat_subjected = True
            self.vat = self.vat.upper()

    @api.multi
    def copy(self, default=None):
        self.ensure_one()
        default = dict(default or {})
        if self.kodas:
            default['kodas'] = _('%s (copy)') % self.kodas
        return super(ResPartner, self).copy(default)


ResPartner()


class ResCompany(models.Model):

    _inherit = 'res.company'

    company_registry = fields.Char(related='partner_id.kodas')

    @api.multi
    def write(self, vals):
        if 'company_registry' in vals and not self.env.user.has_group('base.group_system'):
            vals.pop('company_registry')
        return super(ResCompany, self).write(vals)


ResCompany()
