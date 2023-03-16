# -*- coding: utf-8 -*-


from odoo import _, api, exceptions, fields, models


class ResCompanyMessage(models.Model):
    _name = 'res.company.message'
    _inherit = ['mail.thread']

    company_id = fields.Many2one('res.company')
    body = fields.Html(string='Tekstas', readonly=True)
    subject = fields.Char(string='Tema', readonly=True)

    @api.multi
    def name_get(self):
        return [(rec.id, _('Naujienos')) for rec in self]

    @api.multi
    def unlink(self):
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Negalite ištrinti įrašų!'))
        return super(ResCompanyMessage, self).unlink()
