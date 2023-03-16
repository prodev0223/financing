# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _


class RasoCashRegisters(models.Model):
    _name = 'raso.shoplist.registers'

    is_generic = fields.Boolean(default=False, readonly=True, string='Bendroji kasa')
    pos_no = fields.Char(string='Kasos aparato numeris', inverse='create_partner')
    shop_id = fields.Many2one('raso.shoplist', string='Susieta Parduotuvė')
    location_id = fields.Many2one('stock.location', compute='get_location', string='Kasos aparato lokacija')
    name = fields.Char(string='Kasos aparato pavadinimas')
    partner_id = fields.Many2one('res.partner', string='Susietas partneris')
    journal_id = fields.Many2one('account.journal', string='Žurnalas',
                                 default=lambda self: self.env['account.journal'].search(
                                     [('type', '=', 'sale')], limit=1))

    @api.multi
    @api.constrains('pos_no', 'shop_id')
    def _check_pos_no_consistency(self):
        """Ensures that POS number for the same shop is unique"""
        for rec in self.filtered(lambda x: x.pos_no and x.shop_id):
            if self.search_count([('pos_no', '=', rec.pos_no), ('shop_id', '=', rec.shop_id.id)]) > 1:
                raise exceptions.ValidationError(
                    _('Shop {} already has POS with code {}.').format(rec.shop_id.shop_no, rec.pos_no)
                )

    @api.multi
    def open_register(self):
        self.ensure_one()
        return {
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'raso.shoplist.registers',
                'res_id': self.id,
                'view_id': self.env.ref('raso_retail.raso_shoplist_register_form').id,
                'type': 'ir.actions.act_window',
                'target': 'current',
        }

    @api.multi
    def unlink(self):
        if not self._context.get('parent_unlink') and any(rec.is_generic for rec in self):
            raise exceptions.UserError('Negalite ištrinti numatytojo kasos aparato!')
        self.mapped('partner_id').unlink()
        return super(RasoCashRegisters, self).unlink()

    @api.depends('shop_id')
    @api.one
    def get_location(self):
        if self.shop_id:
            self.location_id = self.shop_id.location_id

    @api.one
    def create_partner(self):
        if self.pos_no and self.shop_id:
            if self.is_generic:
                self.partner_id = self.env['res.partner'].search([('kodas', '=', self.pos_no)])
                self.name = self.pos_no + ' Parduotuvė/Bendra kasa'
                code = self.pos_no
            else:
                self.partner_id = self.env['res.partner'].search([('kodas', '=', self.pos_no + self.shop_id.shop_no)])
                code = self.pos_no + self.shop_id.shop_no
                self.name = self.shop_id.shop_no + ' Parduotuvės/' + self.pos_no + ' Kasos pardavimai'

            if not self.partner_id:
                country_id = self.env['res.country'].sudo().search([('code', '=', 'LT')], limit=1)
                partner_vals = {
                    'name': self.name,
                    'is_company': True,
                    'kodas': code,
                    'country_id': country_id.id,
                    'property_account_receivable_id': self.env['account.account'].sudo().search(
                        [('code', '=', '2410')], limit=1).id,
                    'property_account_payable_id': self.env['account.account'].sudo().search(
                        [('code', '=', '4430')], limit=1).id,
                }
                partner = self.env['res.partner'].sudo().create(partner_vals).id
                self.write({'partner_id': partner})
            else:
                self.partner_id.name = self.name
                self.partner_id.kodas = code
