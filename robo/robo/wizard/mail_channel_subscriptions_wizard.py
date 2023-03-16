# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _


_logger = logging.getLogger(__name__)


class MailChannelSubscriptionsWizard(models.TransientModel):
    _name = 'mail.channel.subscriptions.wizard'

    def _get_default_mail_channel_ids(self):
        channels = self.env['mail.channel'].search([('robo_front', '=', True)])
        return [(6, 0, channels.filtered(lambda c: self.env.user.partner_id.id in c.channel_partner_ids.ids).ids)]

    mail_channel_ids = fields.Many2many('mail.channel', string='Mail channels', default=_get_default_mail_channel_ids, )
    show_mail_channels = fields.Boolean(compute='_compute_show_mail_channels')

    @api.multi
    def _compute_show_mail_channels(self):
        """
        Compute method to check if a user is authorized to see at least one mail channel;
        """
        self.ensure_one()
        if self.env.user.has_group('robo.group_allow_user_manage_own_channel_subscriptions'):
            front_channel_group_ids = self.env['mail.channel'].search([
                ('robo_front', '=', True)
            ]).mapped('group_public_ids').ids
            user_group_ids = self.env.user.groups_id.ids
            self.show_mail_channels = any(set(user_group_ids).intersection(front_channel_group_ids))
        else:
            self.show_mail_channels = False

    @api.multi
    def save(self):
        """
        Method to save user subscription choices;
        """
        self.ensure_one()

        user_followed_channels = self.env['mail.channel.partner'].search([
            ('partner_id', '=', self.env.user.partner_id.id),
        ]).mapped('channel_id')
        channels_to_follow = self.mail_channel_ids
        channels_to_unfollow = user_followed_channels - channels_to_follow
        if self.env.user.partner_id.id:
            if channels_to_unfollow:
                _logger.info('User %s is unfollowing the following channels: %s',
                             self.env.user.login, ', '.join(channels_to_unfollow.sudo().mapped('name')))
            channels_to_unfollow.sudo().write({'channel_partner_ids': [(3, self.env.user.partner_id.id)]})
            channels_to_follow.sudo().write({'channel_partner_ids': [(4, self.env.user.partner_id.id)]})

    @api.model
    def action_create_wizard(self):
        """
        Action to create self record before opening the wizard;
        :return: wizard action
        """
        res = self.env[self._name].create({})
        return {
            'name': _('Mail channel subscription wizard'),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': self.env.ref('robo.view_mail_channel_subscriptions').id,
            'res_id': res.id,
            'res_model': self._name,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }


