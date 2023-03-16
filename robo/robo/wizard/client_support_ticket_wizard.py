# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models


class ClientSupportTicketWizard(models.TransientModel):
    _name = 'client.support.ticket.wizard'

    _inherit = 'ir.attachment.drop'

    def get_context_reason(self):
        return self._context.get('reason', False)

    reason = fields.Selection([('invoice', 'Sąskaitos faktūros'),
                               ('payment', 'Mokėjimai'),
                               ('payroll', 'Darbo užmokestis'),
                               ('edoc', 'El. dokumentai'),
                               ('it', 'Sistemos sutrikimai'),
                               ('other', 'Kita')], string='Kategorija', required=True, default=get_context_reason)
    subject = fields.Char(string='Tema')

    message = fields.Text(string='Klausimas')

    # ready_to_submit = fields.Boolean(compute='_compute_ready_to_submit')
    #
    # @api.one
    # @api.depends('reason', 'subject', 'message')
    # def _compute_ready_to_submit(self):
    #     if self.message and self.reason and not (self.reason == 'other' and not self.subject):
    #         self.ready_to_submit = True

    @api.multi
    @api.constrains('reason', 'subject')
    def _check_reason(self):
        for rec in self:
            if rec.reason == 'other' and not rec.subject:
                raise exceptions.ValidationError(_('Privalote nurodyti temą.'))

    @api.onchange('reason')
    def onchange_reason(self):
        if self.reason and not self.subject:  # TODO: when you select one category, then another, it keeps subject as first category
            self.subject = dict(self._fields['reason'].selection).get(self.reason)

    @api.multi
    def create_ticket(self):
        self.ensure_one()
        if not self.message or len(self.message) < 20:
            raise exceptions.UserError(_('Prašome įveskite detalesnį aprašymą.'))
        ticket_vals = {'reason': self.reason,
                       'subject': self.subject or dict(self._fields['reason'].selection).get(self.reason)}
        ticket = self.env['client.support.ticket'].create(ticket_vals)

        ticket.robo_message_post(
            body=self.message,
            subject=self.reason == 'kita' and self.subject or self.reason,
            subtype='robo.mt_robo_front_message',
            robo_chat=True,
            content_subtype='html',
            front_message=True, message_type='notification',
            attachment_ids=self.user_attachment_ids.ids
        )

        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'client.support.ticket',
            'res_id': ticket.id,
            'type': 'ir.actions.act_window',
            'target': 'current',
            'header': self.env.ref('robo.robo_header_help_ticket').id,
            'robo_front': True,
        }
