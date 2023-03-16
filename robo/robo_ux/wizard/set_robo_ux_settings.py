# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _


class SetRoboUxSettings(models.TransientModel):
    _name = 'set.robo.ux.settings'

    @api.model
    def default_get(self, field_list):
        res = super(SetRoboUxSettings, self).default_get(field_list)
        company_settings_id = self._context.get('company_settings_id')
        if company_settings_id:
            settings = self.env['robo.company.settings'].browse(company_settings_id)
            company = settings.company_id
            res['company_id'] = company.id
            if company:
                settings = company.robo_ux_settings_id

                if settings:
                    res['enabled'] = settings.enabled
                    res['invoice_mail_template_lt_id'] = settings.invoice_mail_template_lt_id.id
                    res['invoice_mail_template_en_id'] = settings.invoice_mail_template_en_id.id
        return res

    def _default_company_id(self):
        return self._context.get('company_id')

    company_id = fields.Many2one('res.company', string='Company', required=True)
    enabled = fields.Boolean('Enabled')

    # Invoice mail template settings
    invoice_mail_template_lt_id = fields.Many2one('mail.template', string='Invoice email lithuanian template',
                                                  domain=[('model', '=', 'account.invoice')])
    invoice_mail_template_en_id = fields.Many2one('mail.template', string='Invoice email english template',
                                                  domain=[('model', '=', 'account.invoice')])

    @api.onchange('company_id')
    def _onchange_company_id(self):
        company = self.company_id
        if not company:
            raise exceptions.UserError(_('Nenumatyta klaida, prašome perkrauti puslapį'))

        settings = company.robo_ux_settings_id

        if not settings:
            return

        self.enabled = settings.enabled
        self.invoice_mail_template_lt_id = settings.invoice_mail_template_lt_id
        self.invoice_mail_template_en_id = settings.invoice_mail_template_en_id

    @api.multi
    def confirm(self):
        self.ensure_one()
        if not self.env.user.is_manager():
            return self.env.ref('robo.open_robo_vadovas_client_action').read()[0]
        company = self.sudo().company_id
        if company:
            settings = company.robo_ux_settings_id

            vals = {
                'company_id': company.id,
                'enabled': self.enabled,
                'invoice_mail_template_lt_id': self.invoice_mail_template_lt_id.id,
                'invoice_mail_template_en_id': self.invoice_mail_template_en_id.id
            }

            if not settings:
                settings = self.env['robo.ux.settings'].create(vals)
                company.write({'robo_ux_settings_id': settings.id})
            else:
                settings.write(vals)
        return self.env.ref('robo.action_robo_company_settings').read()[0]

    @api.multi
    def cancel(self):
        self.ensure_one()
        return self.env.ref('robo.action_robo_company_settings').read()[0]


SetRoboUxSettings()
