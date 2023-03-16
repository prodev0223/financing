# -*- coding: utf-8 -*-


from odoo import api, fields, models


class RoboMailMassMailingPartners(models.TransientModel):
    _name = 'robo.mail.mass.mailing.partners'

    mail_compose_message_id = fields.Many2one('robo.mail.compose.message')
    partner_id = fields.Many2one('res.partner', string='Partneris', required=True, readonly=True)
    email = fields.Char(string='El. paštas')
    amount = fields.Float(string='Viso',
                          readonly=True)  # ROBO: shows currency only in edit mode? why? widget=monetary;currency_field=currency_id
    currency_id = fields.Many2one('res.currency')
    generated_report = fields.Binary(string='Generated document', attachment=True, readonly=True)
    file_name = fields.Char()
    forced_amount = fields.Float(string='Priverstinė skola')
    accountant_work_phone = fields.Char(compute='_compute_accountant_work_phone')

    # history
    # last_attachment_id = fields.Many2one('ir.attachment', string='Paskutinis prisegtukas', related='partner_id.balance_reconciliation_attachment_id', readonly=True)
    last_attachment = fields.Binary(string='Paskutinis prisegtukas', readonly=True)
    comment = fields.Text(string='Komentaras', readonly=True)
    last_email_date = fields.Datetime(string='Paskutinio laiško data', readonly=True)
    last_balance_reconciliation_date = fields.Datetime(string='Paskutinio skolų suderinimo data', readonly=True)
    last_attachment_file_name = fields.Char()

    @api.multi
    def name_get(self):
        return [(rec.id, 'Laiškai partneriams') for rec in self]

    @api.onchange('partner_id')
    def onchage_partner_id(self):
        self.email = self.partner_id.email

    @api.multi
    def _compute_accountant_work_phone(self):
        phone = self.env['res.users'].sudo().search([('main_accountant', '=', True)], limit=1).work_phone
        for rec in self:
            rec.accountant_work_phone = phone if not self.env.user.is_accountant() else False

    # @api.model
    # def check_mail_message_access(self, res_ids, operation, model_name=None):
    #     if operation == 'create':
    #         return True
    #     else:
    #         return super(MailMassMaillingParners, self).check_mail_message_access(res_ids, operation, model_name=model_name)
