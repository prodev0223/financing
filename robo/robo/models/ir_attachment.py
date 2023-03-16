# -*- coding: utf-8 -*-


from odoo import SUPERUSER_ID, _, api, exceptions, models


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    @api.multi
    def unlink(self):
        if not self.env.user.is_accountant() and self._uid != SUPERUSER_ID:
            for rec in self:
                if rec.res_model == 'hr.employee' and rec.res_id:
                    if self.env['hr.employee'].browse(rec.res_id).exists().attachment_drop_lock:
                        raise exceptions.UserError(_('Negalite ištrinti dokumento, nes tam neturite teisių.'))
        is_system = self.env.user.has_group('base.group_system')
        is_accountant_or_superuser = self.env.user.is_accountant() or self._uid == SUPERUSER_ID
        for rec in self:
            if rec.res_model == 'account.invoice' and rec.res_id:
                if not is_system and self.env['mail.mail'].search([('attachment_ids', '=', rec.id), ], limit=1):
                    raise exceptions.UserError(_('Negalite ištrinti dokumento, nes dokumentas susijęs su el. laišku.'))
                if not is_accountant_or_superuser and self.env['account.invoice'].browse(
                        rec.res_id).exists().attachment_drop_lock:
                    raise exceptions.UserError(_('Negalite ištrinti dokumento, nes sąskaita jau patvirtinta.'))
            # should be impossible
            elif rec.res_model == 'hr.expense' and rec.res_id:
                if not is_accountant_or_superuser or self.env['hr.expense'].browse(rec.res_id).exists().state == 'paid':
                    raise exceptions.UserError(_('Negalite ištrinti dokumento, nes čekis jau patvirtintas.'))
        return super(IrAttachment, self).unlink()

    @api.model
    def create(self, vals):
        if vals.get('res_model') == 'robo.mail.mass.mailing.partners' and vals.get('res_field') == 'generated_report':
            vals.update({
                'name': _('Skolu_ataskaita'),
                'datas_fname': _('SkoluSuderinimoAktas')+'.pdf',
            })
        if not vals.get('res_field') and vals.get('res_model') == 'res.partner' and vals.get('res_id'):
            partner_name = self.env['res.partner'].browse(vals.get('res_id')).exists().name or 'a partner'
            subject = _('New debt reconciliation attached')
            body = _('A new debt reconciliation act was attached for {}.').format(partner_name)
            msg_vals = {
                'subject': subject,
                'body': body,
                'channel': 'robo.debt_reconciliation_act_attached_mail_channel',
                'rec_model': vals.get('res_model'),
                'rec_id': vals.get('res_id'),
            }
            self.message_post_to_mail_channel(**msg_vals)
        return super(IrAttachment, self).create(vals)

    @api.model
    def message_post_to_mail_channel(self, subject, body, channel, rec_model, rec_id):
        """
        Method to post a message to a certain mail channel on E documents module
        :param subject: Subject of the message
        :param body: Message
        :param channel: Channel to post the message to
        :param rec_model: Model for the message to point to
        :param rec_id: Particular record it for the message to point to
        """
        mail_channel = self.env.ref(channel, raise_if_not_found=False)
        if not mail_channel:
            return
        channel_partner_ids = mail_channel.sudo().mapped('channel_partner_ids')
        msg = {
            'body': body,
            'subject': subject,
            'message_type': 'comment',
            'subtype': 'robo.mt_robo_front_message',
            'priority': 'low',
            'front_message': True,
            'rec_model': rec_model,
            'rec_id': rec_id,
            'partner_ids': channel_partner_ids.ids,
        }
        mail_channel.sudo().robo_message_post(**msg)
