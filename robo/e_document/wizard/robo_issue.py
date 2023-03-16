# -*- coding: utf-8 -*-
from odoo import api, fields, models


class RoboIssue(models.TransientModel):
    _name = 'robo.issue'

    def _default_name(self):
        return self._context.get('subject', '')

    name = fields.Char(string='Tema', default=_default_name)
    body = fields.Text(string='Aprašymas')
    file = fields.Binary(string='Prisegti dokumentą', attachment=True)
    name_attachment = fields.Char(string='Failo pavadinimas')
    mime_attachment = fields.Char(string='Failo tipas')

    @api.multi
    def submit(self):
        self.ensure_one()
        internal = self.env['res.company']._get_odoorpc_object()
        vals = {
            'name': self.name,
            'description': self.body,
            'email_from': self.env.user.email_formatted,
            'robo_company': self.sudo().env.user.company_id.name,
            'robo_company_code': self.sudo().env.user.company_id.company_registry,
        }
        if self.file:
            vals['attached_file'] = self.file
            vals['name_attachment'] = self.name_attachment
        internal.env['project.issue'].create(vals)
        return self.env.ref('e_document.robo_issue_action_done').read()[0]

    @api.multi
    def get_back(self):
        return self.env.ref('robo.open_robo_vadovas_client_action').read()[0]


RoboIssue()
