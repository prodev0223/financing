# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models, tools


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _get_messages_domain(self):
        domain = [('model', '=', self._name)]
        try:
            if not self.env.user.is_accountant():
                domain.append(('front_message', '=', True))
        except:
            pass
        return domain

    message_ids = fields.One2many('mail.message', 'res_id', string='Messages', domain=_get_messages_domain,
                                  auto_join=True, sequence=100,
                                  )

    def _get_ticket_rpc_object(self):
        internal = self.env['res.company']._get_odoorpc_object()
        return internal.env['support.ticket']

    @api.multi
    @api.returns('self', lambda value: value.id)
    def robo_message_post(self, body='', subject=None, message_type='notification',
                          subtype='robo.mt_robo_front_message', parent_id=False, attachments=None,
                          content_subtype='html', front_message=False, priority='low', rec_model=False, rec_id=False,
                          view_id=False, action_id=False, robo_chat=False, client_message=False, **kwargs):
        # new parameters: front_message, priority, rec_model, rec_id, view_id
        # if rec_model and rec_id are set, link to the record is posted
        self.ensure_one()
        if subtype == 'mail.mt_note':
            robo_chat = False
            client_message = False
            # crm.lead simple user can write internal comment
            if self.env.user.is_accountant():
                front_message = False

        # Allow posting messages with sudo and forcing them as front messages
        force_front_message = kwargs.get('force_front_message')
        if force_front_message:
            front_message = True

        if 'partner_ids' in kwargs:
            partners = kwargs['partner_ids'] or []
        else:
            partners = []

        notify_settings_by_partner = {}
        post_partner_ids = []
        accountant_partner_ids = False
        ticket_create = False
        ticket_update = False
        ticket_close = False

        creator = self.create_uid
        current_user_partner = self.env.user.sudo().partner_id
        employee_msg_authors = self.sudo().message_ids.mapped('author_id').filtered(lambda r: r.is_employee)
        # manager_partner_ids = False

        # client_message == True is Buhalteris
        if robo_chat and not client_message and self._name == 'client.support.ticket':
            if not self._context.get('internal_ticketing'):
                # create ticket in internal system to match the client system ticket. Internal will send back ticket number
                self.env.cr.commit()  # ROBO: must commit before connecting to internal
                try:
                    ticket_obj = self._get_ticket_rpc_object()
                    ticket_close = kwargs.get('ticket_close', False)
                    ticket_reopen = kwargs.get('ticket_reopen', False)
                    client_ticket_type = kwargs.get('client_ticket_type', False)
                    vals = {
                        'ticket_dbname': self.env.cr.dbname,
                        'ticket_model_name': self.sudo().rec_model or self._name,
                        'ticket_record_id': self.sudo().rec_id or False,
                        'name': self.display_name,
                        'ticket_user_login': self.env.user.login,
                        'ticket_user_name': self.env.user.name,
                        'description': body,
                        'ticket_type': 'accounting' if client_ticket_type != 'it' else 'bug',
                        'user_posted': self.env.user.name,
                        'client_support_ticket_id': self.id,
                        'ticket_close': ticket_close,
                        'ticket_reopen': ticket_reopen,
                        'client_ticket_type': client_ticket_type,
                    }

                    if 'attachment_ids' in kwargs:
                        attach_list = []
                        attachment_ids = self.env['ir.attachment'].browse(kwargs['attachment_ids'])
                        for attachment_id in attachment_ids:
                            fname = attachment_id.datas_fname or attachment_id.description
                            attach_list.append((fname, attachment_id.datas))
                        vals['attachments'] = attach_list
                    res = ticket_obj.create_ticket(**vals)
                    if not res:
                        raise exceptions.UserError(_('The distant method did not create the ticket.'))
                except Exception as exc:
                    ticket_create = True
                    message = 'Failed to create ticket. Exception: %s' % str(exc.args)
                    self.env['robo.bug'].sudo().create({
                        'user_id': self.env.user.id,
                        'error_message': message,
                    })

            # ROBO: from now on, we disable SPAM
            # accountant_group_id = self.sudo().env.ref('robo_basic.group_robo_premium_accountant').id
            # system_admin_group_id = self.sudo().env.ref('base.group_system').id
            # accountant_partner_ids = self.sudo().env['res.users'].search([('groups_id', 'in', accountant_group_id), ('groups_id', 'not in', system_admin_group_id)]).mapped('partner_id.id')
            accountant_partner_ids = []

            # support_partner_ids = self.sudo().env['res.partner'].search([('email', '=', 'support@robolabs.lt')]).ids
            # accountant_partner_ids.extend(support_partner_ids)
            # we send message to all followers if accountant_partner_id coerces to True
            if accountant_partner_ids:
                for accountant_partner_id in accountant_partner_ids:
                    if accountant_partner_id not in partners:
                        partners.append(accountant_partner_id)
                # other followers without accountant and current_user
                # other_followers = employee_followers.filtered(lambda r:  r.id != accountant_partner_id.id and r.id != current_user_partner.id)
                # ROBO: other users should be triggered or only accountant+default followers?
                # other_followers += employee_msg_authors.filtered(lambda r:  r.id != accountant_partner_id.id and r.id != current_user_partner.id)
                # other_followers = list(set(other_followers))
                # for follower in other_followers:
                #     if follower.id not in partners:
                #         partners.append(follower.id)
            partners = list(set(partners))
        elif robo_chat and client_message and self._name == 'client.support.ticket':
            # update ticket in internal system
            self.env.cr.commit()  # ROBO: must commit before connecting to internal
            if not self._context.get('internal_ticketing'):
                try:
                    ticket_close = kwargs.get('ticket_close', False)
                    ticket_reopen = kwargs.get('ticket_reopen', False)
                    ticket_obj = self._get_ticket_rpc_object()
                    client_ticket_type = kwargs.get('client_ticket_type', False)
                    vals = {
                        'ticket_dbname': self.env.cr.dbname,
                        'ticket_model_name': self.sudo().rec_model or self._name,
                        'ticket_record_id': self.sudo().rec_id or False,
                        'body': body,
                        'ticket_type': 'accounting' if client_ticket_type != 'it' else 'bug',
                        'user_posted': self.env.user.name,
                        'ticket_close': ticket_close,
                        'ticket_reopen': ticket_reopen,
                        'client_support_ticket_id': self.id,
                        'client_ticket_type': client_ticket_type,
                    }
                    if 'attachment_ids' in kwargs:
                        attach_list = []
                        attachment_ids = self.env['ir.attachment'].browse(kwargs['attachment_ids'])
                        for attachment_id in attachment_ids:
                            fname = attachment_id.datas_fname or attachment_id.description
                            attach_list.append((fname, attachment_id.datas))
                        vals['attachments'] = attach_list
                    res = ticket_obj.update_ticket(**vals)
                    if not res:
                        raise exceptions.UserError(_('The distant method did not update the ticket.'))
                except Exception as exc:
                    ticket_update = True
                    message = 'Failed to update ticket. Exception: %s' % str(exc.args)
                    self.env['robo.bug'].sudo().create({
                        'user_id': self.env.user.id,
                        'error_message': message,
                    })

            employee_followers = self.sudo().message_partner_ids.filtered(lambda r: r.is_employee)
            post_partner_ids = employee_followers.filtered(lambda r: r.id != current_user_partner.id).ids
            # ROBO: if accountant writes chat message reply, every previous "writer" does get it.
            post_partner_ids += employee_msg_authors.filtered(lambda r: r.id != current_user_partner.id).ids

            if not creator.is_accountant() and self._uid != creator.id:
                post_partner_ids.extend([creator.partner_id.id])  # ar kurejas visa laika bus tarp follower'iu?
                partners.extend(post_partner_ids)
            else:
                default_msg_receivers = self.sudo().env.user.company_id.default_msg_receivers.filtered(
                    lambda r: r.id != current_user_partner.id).ids
                post_partner_ids.extend(default_msg_receivers)
                partners.extend(post_partner_ids)

            partners = list(set(partners))
            post_partner_ids = list(set(post_partner_ids))
        elif robo_chat and not self.env.context.get('update_record_from_ticket'):
            # If we write on any other document, we want to create a client support ticket, which will create the internal ticket.
            domain = [('rec_id', '=', self.id),
                      ('rec_model', '=', self._name),
                      ('state', '=', 'open')]
            if not self.env.user.is_accountant():
                domain.append(('user_id', '=', self.env.user.id))
            existing_tickets = self.env['client.support.ticket'].sudo().search(domain)
            if existing_tickets:
                client_tickets = self.env['client.support.ticket'].browse(existing_tickets.ids)
            elif not client_message:
                if self._name == 'account.invoice':
                    reason = 'invoice'
                elif self._name == 'e.document':
                    reason = 'edoc'
                else:
                    reason = 'other'

                client_tickets = self.env['client.support.ticket'].create({
                    'reason': reason,
                    'subject': self.display_name or _('Komentaras'),
                    'rec_model': self._name,
                    'rec_id': self.id,
                })
            else:
                client_tickets = []
            if subject and 'Komentaras' in subject and self.display_name:
                subject += ': ' + self.display_name
            for client_ticket in client_tickets:
                client_ticket.with_context(ignore_rec_model=True).robo_message_post(
                    body=body, subject=subject or client_ticket.subject or _('Komentaras') + ': ' + self.display_name,
                    message_type=message_type, subtype=subtype,
                    parent_id=parent_id, attachments=attachments, content_subtype=content_subtype,
                    front_message=front_message, priority=priority, rec_model=rec_model, rec_id=rec_id,
                    view_id=view_id, action_id=action_id, robo_chat=True, client_message=client_message,
                    **kwargs)

            if client_message and not client_tickets:
                # When accountant writes on a record and there are no open tickets, we dont go through any of the previous
                # if cases, and no email is sent to partners. In this case, we do it here
                employee_followers = self.sudo().message_partner_ids.filtered(lambda r: r.is_employee)
                post_partner_ids = employee_followers.filtered(lambda r: r.id != current_user_partner.id).ids
                # ROBO: if accountant writes chat message reply, every previous "writer" does get it.
                post_partner_ids += employee_msg_authors.filtered(lambda r: r.id != current_user_partner.id).ids

                if not creator.is_accountant() and self._uid != creator.id:
                    post_partner_ids.extend([creator.partner_id.id])  # ar kurejas visa laika bus tarp follower'iu?
                    partners.extend(post_partner_ids)
                else:
                    default_msg_receivers = self.sudo().env.user.company_id.default_msg_receivers.filtered(
                        lambda r: r.id != current_user_partner.id).ids
                    post_partner_ids.extend(default_msg_receivers)
                    partners.extend(post_partner_ids)

                partners = list(set(partners))
                post_partner_ids = list(set(post_partner_ids))

        partner_ids = self.env['res.partner'].browse(partners)
        if robo_chat and not client_message and accountant_partner_ids:
            priority = 'high'
        if priority == 'high' and partners:
            notify_settings_by_partner = dict(partner_ids.sudo().mapped(lambda r: (r.id, r.notify_email)))
            partner_ids = partner_ids.sudo().filtered(lambda r: not r.opt_out_robo_mails)
            for partner_id in partner_ids:
                partner_id.write({'notify_email': 'always'})

        kwargs['partner_ids'] = partners
        followers = self.sudo().message_partner_ids.mapped('id')
        unfollow_partners = list(set(partners).difference(followers))
        if unfollow_partners:
            self.sudo().message_unsubscribe(unfollow_partners)

        # if kwargs.get('robo_message_type', False) == 'new_order':
        #     kwargs.pop('robo_message_type')
        #     inform_partner_ids = partner_ids.filtered(lambda r: not r.opt_out_robo_mails and r.user_ids and r.user_ids[0].inform_orders)
        #     for inform_partner_id in inform_partner_ids:
        #         if inform_partner_id.id not in notify_settings_by_partner:
        #             notify_settings_by_partner[inform_partner_id.id] = inform_partner_id.notify_email
        #     inform_partner_ids.write({'notify_email': 'always'})

        if robo_chat and client_message:
            inform_partner_ids = partner_ids.filtered(
                lambda r: not r.opt_out_robo_mails and r.user_ids and r.user_ids[0].inform_comments)
            for inform_partner_id in inform_partner_ids:
                if inform_partner_id.id not in notify_settings_by_partner:
                    notify_settings_by_partner[inform_partner_id.id] = inform_partner_id.notify_email
            inform_partner_ids.sudo().write({'notify_email': 'always'})

        res = self.with_context(robo_chat=robo_chat, front_message=front_message,
                                message_priority=priority).message_post(body=body,
                                                                        subject=subject,
                                                                        message_type=message_type,
                                                                        subtype=subtype,
                                                                        parent_id=parent_id,
                                                                        attachments=attachments,
                                                                        content_subtype=content_subtype,
                                                                        **kwargs)
        if res:
            if not action_id:
                action_id = self.sudo()._guess_action_id(rec_model=rec_model, rec_id=rec_id)
            vals = {
                'rec_model': rec_model,
                'rec_id': rec_id,
                'view_id': view_id,
                'action_id': action_id,
                'ticket_to_update': ticket_update,
                'ticket_to_create': ticket_create,
                'ticket_close': ticket_close,
                'ticket_name': self.display_name,
            }
            if self._name == 'client.support.ticket':
                vals['client_support_ticket_id'] = self.id
            res.write(vals)
        if notify_settings_by_partner:
            for partner_id in partner_ids:
                if partner_id.id in notify_settings_by_partner:
                    partner_id.sudo().write({'notify_email': notify_settings_by_partner[partner_id.id]})

        if robo_chat and accountant_partner_ids and not client_message:
            res.mark_roboFrontMessage_as_unread(accountant_partner_ids)
        elif robo_chat and client_message and post_partner_ids:
            res.mark_roboFrontMessage_as_unread(post_partner_ids)
        if partners:
            partners = list(set(partners))
            if front_message and res and not robo_chat:
                res.mark_roboFrontMessage_as_unread(partners)

        return res

    def _guess_action_id(self, rec_model=False, rec_id=False):
        res = False
        if not rec_model:
            rec_model = self._name
        if rec_model and rec_model == 'robo.upload':
            res = self.env.ref('robo.show_all_files').id
        elif rec_model and rec_model != 'account.invoice':
            actions = self.env['ir.actions.act_window'].search(
                [('res_model', '=', rec_model), '|', '|', ('robo_front', '=', True),
                 ('view_id.robo_front', '=', True), ('view_ids.view_id.robo_front', '=', True)])
            if actions:
                res = actions[0].id
        elif rec_model == 'account.invoice' and rec_id:
            invoice = self.env['account.invoice'].browse(rec_id)
            if invoice.type in ['in_invoice', 'in_refund']:
                res = self.env.ref('robo.robo_expenses_action').id
            elif invoice.type in ['out_invoice', 'out_refund']:
                res = self.env.ref('robo.open_client_invoice').id
        elif rec_model == 'product.template' and rec_id:
            res = self.env.ref('robo_stock.open_robo_stock_product', raise_if_not_found=False)
            if res:
                res = res.id
        return res

    @api.multi
    def message_get_email_values(self, notif_mail=None):
        self.ensure_one()
        res = super(MailThread, self).message_get_email_values(notif_mail=notif_mail)

        if not notif_mail or not notif_mail.additional_recipients:
            return res

        additional_recipients_emails = notif_mail.additional_recipients
        res.update({
            'email_to': str(additional_recipients_emails),
        })

        return res
