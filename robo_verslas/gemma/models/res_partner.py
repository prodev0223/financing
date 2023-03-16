# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, exceptions


class ResPartner(models.Model):
    _inherit = 'res.partner'

    gemma_register = fields.Boolean(string='Gemma kasos aparatas', default=False)
    gemma_ext_id = fields.Char(string='Išorinis POLIS partnerio identifikatorius')
    gemma_lock_date = fields.Date(string='Gemma užrakinimo data')

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = [] if args is None else args[:]
        if name:
            recs = self.search([('gemma_ext_id', 'ilike', name)] + args, limit=limit)
            if not recs:
                recs = self.search([('name', operator, name)] + args, limit=limit)
        else:
            recs = self.search(args, limit=limit)
        return recs.name_get()

    @api.multi
    def unlink(self):
        if not self.env.user.has_group('base.group_system') and any(self.mapped('gemma_register')):
            raise exceptions.UserError(_('Negalite ištrinti Gemma kasos partnerio!'))
        return super(ResPartner, self).unlink()

    @api.onchange('name')
    def onchange_partner_name(self):
        if self.name:
            rec = self.search([('name', '=', self.name)], limit=1)
            if rec:
                return {'warning': {'title': _('Įspėjimas'),
                                    'message': _('Egzistuoja partneris su tokiu pačiu vardu! '
                                                 'Ignoruokite pranešimą jeigu norite tęsti.')}}


ResPartner()
