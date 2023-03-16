# -*- coding: utf-8 -*-
# (c) 2021 RoboLabs

from odoo import api, exceptions, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    country_id = fields.Many2one(inverse='_set_country_id')

    @api.multi
    def _set_country_id(self):
        lithuania = self.env.ref('base.lt')
        partners_to_notify = self.env['res.partner']
        for partner in self:
            if partner.country_id == lithuania:
                continue
            if partner.company_type != 'company':
                continue
            invoices = self.env['account.invoice'].search([('partner_id', '=', partner.id),
                                                           ('partner_country_id', '=', lithuania.id)], count=True)
            if invoices:
                partners_to_notify += partner

        if partners_to_notify:
            message = 'Valstybė buvo pakeista į kita iš Lietuvos šiems partneriams: '
            message += ', '.join(partners_to_notify.mapped('name'))
            try:
                ticket_obj = self.sudo()._get_ticket_rpc_object()
                vals = {
                    'ticket_dbname': self.env.cr.dbname,
                    'ticket_model_name': self._name,
                    'name': 'Sanity Check: Valstybė buvo pakeista į kita iš Lietuvos',
                    'description': message,
                    'ticket_type': 'accounting',
                    'user_posted': self.env.user.name,
                }

                res = ticket_obj.create_ticket(**vals)
                if not res:
                    raise exceptions.UserError('The distant method did not create the ticket.')
            except Exception as exc:
                message = 'Failed to create ticket for accountant\nException: %s' % (str(exc.args))
                self.env['robo.bug'].sudo().create({
                    'user_id': self.env.user.id,
                    'error_message': message,
                })
