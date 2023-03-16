# -*- coding: utf-8 -*-


import logging

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)


class MailMessage(models.Model):
    _inherit = 'mail.message'

    def default_priority(self):
        return self._context.get('message_priority', False)

    def default_front_message(self):
        return self._context.get('front_message', False)

    front_message = fields.Boolean(string='Žinutė rodoma vartotojui', default=default_front_message)
    priority = fields.Selection([('low', 'Mažas'), ('medium', 'Vidutinis'), ('high', 'Didelis')], string='Prioritetas',
                                default=default_priority)
    rec_model = fields.Char(string='Nuoroda (modelis)', readonly=True)
    rec_id = fields.Integer(string='Nuoroda (ID)', readonly=True)
    view_id = fields.Integer(string='Nuoroda (rodinys)', readonly=True)
    action_id = fields.Integer(string='Nuoroda (veiksmas)', readonly=True)
    ticket_to_create = fields.Boolean(default=False)
    ticket_to_update = fields.Boolean(default=False)
    ticket_close = fields.Boolean(default=False)
    ticket_name = fields.Char(string='Pavadinimas')
    client_support_ticket_id = fields.Integer(string='Client-side ticket ID')
    additional_recipients = fields.Char(string='Additional recipients')

    @api.model
    def cron_recreate_tickets(self):
        try:
            ticket_obj = self.env['mail.thread']._get_ticket_rpc_object()
        except Exception as e:
            _logger.info('Ticket Re-Create, failed to reach server, exception %s' % e)
            return

        client_tickets = self.env['client.support.ticket'].search([('number', '=', False)])
        subtype = self.env.ref('robo.mt_robo_front_message').id
        for ticket in client_tickets:
            ticket.message_ids.filtered(lambda m: m.subtype_id.id == subtype and m.front_message).write(
                {'ticket_to_create': True})

        messages = self.search([('ticket_to_create', '=', True)])
        for message in messages:
            # ticket_record_id and ticket_model_name should not be used anymore as we use client_support_ticket_id only
            vals = {
                'ticket_dbname': self.env.cr.dbname,
                'ticket_model_name': message.rec_model,
                'client_support_ticket_id': message.client_support_ticket_id,
                'ticket_record_id': message.rec_id,
                'name': message.ticket_name,
                'ticket_user_login': message.create_uid.login,
                'ticket_user_name': message.create_uid.name,
                'description': message.body,
                'ticket_type': 'accounting',
                'user_posted': message.env.user.name,
            }
            attach_list = []
            if message.attachment_ids:
                for attachment_id in message.attachment_ids:
                    fname = attachment_id.datas_fname or attachment_id.description
                    attach_list.append((fname, attachment_id.datas))
                vals['attachments'] = attach_list
            try:
                res = ticket_obj.create_ticket(**vals)
                if not res:
                    raise exceptions.UserError(_('The distant method did not create the ticket.'))
                message.write({'ticket_to_create': False})
            except Exception as e:
                _logger.info('Ticket Re-Create, failed to reach server, exception %s' % e)
                continue

        messages = self.search([('ticket_to_update', '=', True)])
        for message in messages:
            vals = {
                'ticket_dbname': self.env.cr.dbname,
                'ticket_model_name': message.rec_model,
                'ticket_record_id': message.rec_id,
                'body': message.body,
                'ticket_type': 'accounting',
                'user_posted': message.create_uid.name,
                'ticket_close': message.ticket_close,
            }
            attach_list = []
            if message.attachment_ids:
                for attachment_id in message.attachment_ids:
                    fname = attachment_id.datas_fname or attachment_id.description
                    attach_list.append((fname, attachment_id.datas))
                vals['attachments'] = attach_list
            try:
                res = ticket_obj.update_ticket(**vals)
                if not res:
                    raise exceptions.UserError(_('The distant method did not update the ticket.'))
                message.write({'ticket_to_update': False})
            except Exception as e:
                _logger.info('Ticket Update: failed to reach server, exception %s' % e)
                continue

    @api.multi
    def unlink(self):
        res = super(MailMessage, self).unlink()
        if res:
            self._update_roboMessage_bell()
        return res

    @api.model
    def _update_roboMessage_bell(self, **notification):
        if 'partner_ids' in notification:
            partner_ids = notification['partner_ids']
        else:
            partner_ids = [self.env.user.partner_id.id]
        for partner_id in partner_ids:
            self.env['bus.bus'].sendone((self._cr.dbname, 'robo.message', partner_id), notification)

    @api.multi
    def mark_roboFrontMessage_as_unread(self, partners=False):
        """ Add needactions to messages for the current partner. """
        if not partners:
            partners = [self.env.user.partner_id.id]
        for message in self:
            message.write({'needaction_partner_ids': [(6, 0, partners)]})

        # ids = [m.id for m in self]
        message = {'type': 'robo_message', 'partner_ids': partners}
        self._update_roboMessage_bell(**message)

    @api.model
    def set_AllRoboFrontMessage_done(self):
        partner_id = self.env.user.partner_id

        notifications = self.env['mail.notification'].sudo().search([
            ('res_partner_id', '=', partner_id.id),
            ('is_read', '=', False)])

        if notifications:
            notifications.write({'is_read': True})

        message = {'type': 'robo_message'}
        self._update_roboMessage_bell(**message)

    @api.multi
    def set_roboFrontMessage_done(self):
        partner_id = self.env.user.partner_id

        notifications = self.env['mail.notification'].sudo().search([
            ('mail_message_id', 'in', self.ids),
            ('res_partner_id', '=', partner_id.id),
            ('is_read', '=', False)])

        if notifications:
            notifications.write({'is_read': True})

        message = {'type': 'robo_message'}
        self._update_roboMessage_bell(**message)

    @api.multi
    def set_message_done(self):
        super(MailMessage, self).set_message_done()
        self.filtered(lambda r: r.front_message == True).set_roboFrontMessage_done()

    @api.model
    def _message_read_dict_postprocess(self, messages, message_tree):
        res = super(MailMessage, self)._message_read_dict_postprocess(messages, message_tree)
        for message_dict in messages:
            message_id = message_dict.get('id')
            message = message_tree[message_id]
            statistics_ids = self.sudo().env['mail.mail'].search(
                [('mail_message_id', '=', message.id)]).mapped('statistics_ids')
            if statistics_ids and any(statistics_ids.mapped('opened')):
                customer_email_data = message_dict.get('customer_email_data')
                for i, d in enumerate(customer_email_data):
                    d = list(d)
                    customer_email_data[i] = d
                    if len(d) > 2 and d[2] == 'sent':
                        d[2] = 'read'
                message_dict.update({
                    'customer_email_status': 'read',
                    'customer_email_data': customer_email_data,
                })
        return res

    @api.multi
    def _notify(self, force_send=False, send_after_commit=True, user_signature=True):
        followers = False
        partner_ids = False
        if self._context.get('custom_layout',
                             False) == u'account.mail_template_data_notification_email_account_invoice':
            if self.sudo().subtype_id and self.model and self.res_id:
                record_id = self.env[self.model].browse(self.res_id)
                followers = self.env['mail.followers'].sudo().search([
                    ('res_model', '=', self.model),
                    ('res_id', '=', self.res_id)
                ]).filtered(lambda fol: self.subtype_id in fol.subtype_ids)
                if followers:
                    partner_ids = followers.mapped('partner_id.id')
                    record_id.message_unsubscribe(partner_ids)
        res = super(MailMessage, self)._notify(force_send=False, send_after_commit=True, user_signature=True)
        if followers and partner_ids:
            record_id.message_subscribe(partner_ids)
        return res
