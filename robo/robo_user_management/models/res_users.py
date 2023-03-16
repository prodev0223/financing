# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, tools, exceptions
from odoo.tools.translate import _
from dateutil.relativedelta import relativedelta
from datetime import datetime
from pytz import timezone
from six import iteritems

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    ir_model_access_override_ids = fields.One2many('ir.model.access.override', 'user_id', 'Prieigos teisės',
                                                   groups='base.group_system')

    main_user_rights_group = fields.Selection([('employee', 'Darbuotojas'),
                                   ('hr_manager', 'Personalo vadovas'),
                                   ('manager', 'Vadovas')], string='Pagrindinė teisių grupė', inverse='_set_main_user_rights',
                                  default='employee', compute='_compute_main_user_rights_group',
                                  groups='robo_basic.group_robo_premium_manager,robo_basic.group_robo_free_manager,robo_basic.group_robo_hr_manager')

    default_message_receiver = fields.Boolean(
        string='Įvairūs sisteminiai pranešimai (sąskaitos faktūros ir kt.)',
        compute='_compute_default_message_receiver',
        inverse='_update_default_message_receiver_list'
    )

    robo_front_mail_channel_ids = fields.Many2many('mail.channel', string='Pranešimų kanalai',
                                                   compute='_compute_robo_front_mail_channel_ids',
                                                   inverse='_update_mail_channel_subscriptions',
                                                   groups='robo_basic.group_robo_premium_manager')
    show_reset_2fa_button = fields.Boolean(compute='_compute_show_reset_2fa_button')
    login = fields.Char(inverse='_set_login')
    signup_valid = fields.Boolean(related='partner_id.signup_valid')

    @api.multi
    def _set_login(self):
        """On set updates related partner's email if it's empty or changed"""
        for rec in self.filtered(lambda x: x.login != x.partner_id.email):
            rec.partner_id.email = rec.login

    @api.one
    @api.depends('groups_id')
    def _compute_main_user_rights_group(self):
        if self.is_premium_manager():
            group = 'manager'
        elif self.has_group('robo_basic.group_robo_hr_manager'):
            group = 'hr_manager'
        else:
            group = 'employee'
        self.main_user_rights_group = group

    @api.multi
    def _set_main_user_rights(self):
        self.ensure_one()
        if self.is_accountant():
            raise exceptions.AccessError(_('You cannot change rights for this user'))
        if self.employee_ids:
            self.employee_ids.write({'robo_group': self.main_user_rights_group})
            msg = {
                'body': _('Pakeistos vartotojo teisės į {rights}').format(
                    rights=dict(
                        self._fields['main_user_rights_group']._description_selection(self.env)).
                        get(self.main_user_rights_group)
                ),
                'message_type': 'notification',
                'subtype': 'mail.mt_comment',
                'front_message': False,
            }
            self.partner_id.message_post(**msg)
        else:
            groups = []
            if self.main_user_rights_group == 'employee':
                groups.append(self.sudo().env.ref('robo_basic.group_robo_premium_user').id)
            elif self.main_user_rights_group == 'hr_manager':
                groups.extend([self.sudo().env.ref('robo_basic.group_robo_premium_user').id,
                               self.sudo().env.ref('robo_basic.group_robo_hr_manager').id])
            elif self.main_user_rights_group == 'manager':
                groups.append(self.sudo().env.ref('robo_basic.group_robo_premium_manager').id)
            if groups:
                self.write({'groups_id': [(6, 0, groups)]})

    @api.one
    @api.depends('partner_id')
    def _compute_default_message_receiver(self):
        company_receiver_ids = self.env.user.sudo().company_id.default_msg_receivers.ids
        self.default_message_receiver = self.partner_id and self.partner_id.id in company_receiver_ids

    @api.multi
    @api.depends('create_date')
    def _compute_robo_front_mail_channel_ids(self):
        channels = self.env['mail.channel'].search([('robo_front', '=', True)])
        for rec in self:
            rec_channels = channels.filtered(lambda c: rec.partner_id.id in c.channel_partner_ids.ids)
            rec.robo_front_mail_channel_ids = [(6, 0, rec_channels.ids)]

    @api.depends('has_accountant_rights')
    def _compute_show_reset_2fa_button(self):
        if self.env.user == self.env.user.company_id.sudo().vadovas.user_id\
                or self.env.user.has_group('robo_basic.group_robo_manage_2fa_credentials'):
            for rec in self:
                if not rec.has_accountant_rights and rec.enable_2fa:
                    rec.show_reset_2fa_button = True

    @api.one
    def _update_default_message_receiver_list(self):
        if self.partner_id:
            command = 3 if not self.default_message_receiver else 4
            self.env.user.company_id.sudo().write({'default_msg_receivers': [(command, self.partner_id.id, False)]})

    @api.multi
    def _update_mail_channel_subscriptions(self):
        self.ensure_one()
        channels_to_follow = self.robo_front_mail_channel_ids
        channels_to_unfollow = self.env['mail.channel'].search([
            ('robo_front', '=', True)
        ]).filtered(lambda c: c.id not in channels_to_follow.ids)
        if self.partner_id:
            channels_to_unfollow.sudo().write({'channel_partner_ids': [(3, self.partner_id.id)]})
            channels_to_follow.sudo().write({'channel_partner_ids': [(4, self.partner_id.id)]})
        # for channel in channels_to_unfollow:
            # channel.sudo(self.id).action_unfollow()
        # for channel in channels_to_follow:
        #     channel.sudo(self.id).action_follow()

    @api.model
    def create(self, vals):
        if self.has_group('robo_user_management.group_user_creator'):
            self = self.sudo()
        return super(ResUsers, self).create(vals=vals)

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        res = super(ResUsers, self).fields_get(allfields, attributes=attributes)

        front_groups = self.env['res.groups'].search([('robo_front', '=', True)])
        for group in front_groups:
            field_name = group.get_rum_field_name()  # Gets the shortened field name (based on ID)
            field_string = group.name
            selection_attrs = [('true', _('Įjungta')), ('false', _('Išjungta'))]

            # The (main) selection field
            res[field_name] = {
                'type': 'selection',
                'string': field_string,
                'selection': selection_attrs,
                'exportable': False,
                'selectable': False,
                'required': True
            }

            # Related help field
            res[group.get_rum_help_field_name()] = {
                'type': 'html',
                'exportable': False,
                'selectable': False,
                'readonly': True
            }

            # Related invisible field
            res[group.get_rum_invisible_field_name()] = {
                'type': 'boolean',
                'string': field_string + _(' laukelis yra nematomas'),
                'exportable': False,
                'selectable': False
            }

            # Related readonly field
            res[group.get_rum_readonly_field_name()] = {
                'type': 'boolean',
                'string': field_string + _(' laukelis yra tik skaitymui'),
                'exportable': False,
                'selectable': False
            }

        for group_category in self.env['front.res.groups.category'].search([]):
            res['rum_cat_' + str(group_category.id) + '_is_invisible'] = {
                'type': 'boolean',
                'string': group_category.name + _(' grupė yra matoma'),
                'exportable': False,
                'selectable': False
            }
            res['rum_cat_' + str(group_category.id) + '_is_readonly'] = {
                'type': 'boolean',
                'string': group_category.name + _(' grupė yra tik skaitymui'),
                'exportable': False,
                'selectable': False
            }

        return res

    @api.multi
    def read(self, fields=None, load='_classic_read'):
        is_rum_field = self.env['res.groups'].is_rum_field
        is_rum_group_field = self.env['front.res.groups.category'].is_rum_group_field
        rum_fields = [field for field in fields if is_rum_field(field)]
        rum_category_fields = [field for field in fields if is_rum_group_field(field)]
        non_rum_fields = [field for field in fields if field not in rum_fields + rum_category_fields]

        res = super(ResUsers, self).read(non_rum_fields, load)

        if len(res) != 1 or len(self) != 1:
            return res
        if not rum_fields and not rum_category_fields:
            return res

        all_groups_with_implied_ids = self.env['res.groups'].search([('implied_ids', '!=', False)])

        all_rum_groups_in_view = self.env['res.groups']

        # "Compute" the field values
        for rum_field in rum_fields:
            group = self.env['res.groups'].get_group_from_rum_field(rum_field)
            all_rum_groups_in_view |= group

            invisible_name = group.get_rum_invisible_field_name()
            readonly_name = group.get_rum_readonly_field_name()
            help_name = group.get_rum_help_field_name()

            if rum_field == invisible_name:
                field_value = group.is_disabled_in_rum()
            elif rum_field == readonly_name:
                if group.is_disabled_in_rum():
                    field_value = True
                else:
                    # Group is readonly when user has parent group that implies
                    parent_groups = all_groups_with_implied_ids.filtered(lambda g: group.id in g.implied_ids.ids)
                    field_value = any(x.id in self.groups_id.ids for x in parent_groups)
            elif rum_field == help_name:
                field_value = group.front_help_preview
            else:
                field_value = 'true' if group.id in self.groups_id.ids else 'false'

            res[0][rum_field] = field_value

        get_category_id_from_field_name = self.env['front.res.groups.category'].get_category_id_from_field_name
        for rum_cat_field in rum_category_fields:
            category_id = get_category_id_from_field_name(rum_cat_field)
            if not category_id:
                continue
            category_groups = all_rum_groups_in_view.filtered(lambda g: g.front_category_id.id == category_id and not g.is_disabled_in_rum())
            regular_cat_groups = category_groups.filtered(lambda g: not g.robo_front_only_shown_to_super)
            super_cat_groups = category_groups.filtered(lambda g: g.robo_front_only_shown_to_super)

            if regular_cat_groups or (super_cat_groups and self.env.user.is_accountant()):
                group_hidden = False
            else:
                group_hidden = True
            res[0][rum_cat_field] = group_hidden

        return res

    @api.multi
    def write(self, vals):
        # If any of these groups was changed CEO should be notified
        CEO_NOTIFICATION_GROUPS = [
            self.env.ref('robo_basic.group_robo_create_on_behalf').get_rum_field_name(),
            self.env.ref('e_document.group_robo_mark_requests_signed').get_rum_field_name(),
            self.env.ref('robo_user_management.group_user_manager').get_rum_field_name(),
            self.env.ref('robo.group_robo_need_action').get_rum_field_name(),
        ]

        # Map groups with a suitable notification
        GROUP_DISPLAY_NAMES = {
            CEO_NOTIFICATION_GROUPS[0]: _('Leisti kurti e-dokumentus už kitus'),
            CEO_NOTIFICATION_GROUPS[1]: _('Pažymėti prašymus pasirašytais'),
            CEO_NOTIFICATION_GROUPS[2]: _('Leisti koreguoti naudotojus'),
            CEO_NOTIFICATION_GROUPS[3]: _('Reprezentacinių sąskaitų faktūrų tvirtinimo įgaliotinis'),
        }

        is_rum_field = self.env['res.groups'].is_rum_field
        user_vals = {}
        rum_vals = {}
        for key, data in iteritems(vals):
            if is_rum_field(key):
                rum_vals[key] = data
            else:
                user_vals[key] = data
        vals = user_vals

        if rum_vals and not self.env.user.has_group('base.group_system'):
            if any(rec.is_accountant() for rec in self):
                raise exceptions.AccessError(_('You cannot change group for this user'))

        change_log_main = _('''
        <table>
            <tr>
                <th style="border: 1px solid black; padding: 2px;">Laikas</th>
                <th style="border: 1px solid black; padding: 2px;">Vartotojo vardas</th>
                <th style="border: 1px solid black; padding: 2px;">Teisės</th>
                <th style="border: 1px solid black; padding: 2px;">Sena būsena</th>
                <th style="border: 1px solid black; padding: 2px;">Nauja būsena</th>
            </tr>
        ''')

        change_line_table_row = '''  <tr>
            <td style="{style_string}">{0}</td>
            <td style="{style_string}">{1}</td>
            <td style="{style_string}">{2}</td>
            <td style="{style_string}">{3}</td>
            <td style="{style_string}">{4}</td>
        </tr>\n'''

        tzone = self._context.get('tz')
        datetime_value = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        if rum_vals:
            try:
                diff = round((datetime.now(timezone(tzone)).replace(tzinfo=None) - datetime.utcnow()).total_seconds(), 3)
                value_dt = datetime.utcnow() + relativedelta(seconds=diff)
                datetime_value = value_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            except:
                pass

        for key, data in iteritems(rum_vals):
            group = self.env['res.groups'].get_group_from_rum_field(key)
            if group.is_disabled_in_rum():
                continue
            operation = 4 if data == 'true' else 3
            vals['groups_id'] = vals.get('groups_id', []) + [(operation, group.id)]
            change_table_row = change_line_table_row.format(
                datetime_value,
                self.env.user.name or self.env.user.login or _('Nepavyko nustatyti'),
                group.name or '',
                _('Išjungta') if data == 'true' else _('Įjungta'),
                _('Įjungta') if data == 'true' else _('Išjungta'),
                style_string='border: 1px solid black; padding: 2px;'
            )
            change_log_main += change_table_row
        change_log_main += '''</table>'''

        if rum_vals:
            for rec in self:
                msg = {
                    'body': change_log_main,
                    'subject': _('Pakeistos vartotojo teisės'),
                    'message_type': 'notification',
                    'subtype': 'mail.mt_comment',
                    'front_message': False,
                }
                rec.partner_id.message_post(**msg)

        ceo = self.env.user.company_id.vadovas
        if set(CEO_NOTIFICATION_GROUPS) & set(rum_vals.keys()):
            if self.env.user != ceo.user_id:
                subject = _('Vartotojo teisės pasirašyti dokumentus buvo pakeistos')
                body = _("""
                Įmonėje {0} vartotojo {1} teisės buvo pakeistos.<br>
                Pakeitimai: {2}.<br>
                Jūs esate informuojamas el. laišku, nes esate įmonės vadovas. 
                """).format(
                    ceo.company_id.name,
                    ', '.join([user.name for user in self if user.name]),
                    ', '.join([GROUP_DISPLAY_NAMES.get(key) for key in rum_vals.keys() if GROUP_DISPLAY_NAMES.get(key)]))
                self.env['e.document'].message_post_to_mail_channel(
                    subject, body, 'e_document.user_rights_changes_mail_channel'
                )

        return super(ResUsers, self).write(vals)

    @api.multi
    def toggle_robo_active(self):
        for user in self:
            robo_access = not user.active
            if user.employee_ids:
                user.employee_ids.write({'robo_access': robo_access})
            else:
                if not self.env.user.is_manager() or user.is_accountant():
                    raise exceptions.AccessError(_('Negalite atlikti šio veiksmo.'))
                user.write({'active': robo_access})
            user.post_user_status_message()

    @api.multi
    def action_reset_2fa_credentials(self):
        """ Reinitialize 2FA for a user """
        self.ensure_one()
        credential_manager = self.env.user.has_group('robo_basic.group_robo_manage_2fa_credentials')
        if not credential_manager and self.env.user != self.env.user.company_id.sudo().vadovas.user_id:
            raise exceptions.AccessError(_('Šį veiksmą gali atlikti tik įmonės vadovas'))
        if self.is_accountant() or not self.enable_2fa:
            raise exceptions.AccessError(_('Šį veiksmą gali atlikti tik sistemos administratorius'))

        self.sudo().action_discard_2f_auth_credentials()
        msg = {
            'body': '2FA credentials were reset',
            'subject': 'Reset 2FA',
            'message_type': 'notification',
            'subtype': 'mail.mt_comment',
            'front_message': False,
        }
        self.partner_id.message_post(**msg)

    # @api.multi
    # def action_discard_2f_auth_credentials(self):
    #     super(ResUsers, self).action_discard_2f_auth_credentials()
    #     if self.env.context.get('changing_global_2fa_policy'):
    #         return
        for rec in self.filtered('email'):
            subject = '[{}]'.format(self.env.cr.dbname) + _('Dviejų veiksmu autentikacija atstatyta')
            message = _("""
                <div style="font-family:arial,helvetica neue,helvetica,sans-serif">
                Sveiki,<br>
                Jūsų dviejų veiksmų autentikacija (2FA) buvo atstatyta iš naujo.
                </div>
            """)

            self.env['script'].send_email(emails_to=[rec.email], subject=subject, body=message)

    @api.onchange('main_user_rights_group')
    def _onchange_user_rights(self):
        if self.main_user_rights_group:
            return {'warning': {
                'title': _('Įspėjimas'),
                'message': _('Pakeitus pagrindinę teisių grupę bus iš naujo pakeistos prieigos teisės.'),
            }}

    @api.multi
    def action_reset_password_front(self):
        for rec in self:
            rec.sudo().with_context(create_user=rec.state == 'new').action_reset_password()
