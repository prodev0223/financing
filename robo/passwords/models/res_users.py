# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, exceptions, tools
from datetime import datetime, timedelta
import re


def delta_now(**kwargs):
    dt = datetime.utcnow() + timedelta(**kwargs)
    return fields.Datetime.to_string(dt)


class PasswordException(Exception):
    def __init__(self, message):
        super(PasswordException, self).__init__()
        self.message = message


class ResUsers(models.Model):
    _inherit = 'res.users'
    password_write_date = fields.Datetime(
        'Latest password update', readonly=True, default=fields.Datetime.now
    )

    @api.model
    def create(self, vals, ):
        vals['password_write_date'] = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        return super(ResUsers, self).create(vals)

    @api.multi
    def write(self, vals, ):
        if vals.get('password'):
            self.check_password(vals['password'])
            vals['password_write_date'] = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        return super(ResUsers, self).write(vals)

    @api.multi
    def password_match_message(self):
        company_id = self.company_id
        message = [_(u'Slaptažodis privalo būti sudarytas iš mažiausiai %d simbolių.') % company_id.password_length,
                   _(u'Slaptažodį privalo sudaryti:')]
        if company_id.password_lower:
            message.append(_(u'* Mažosios raidės'))
        if company_id.password_upper:
            message.append(_(u'* Didžiosios raidės'))
        if company_id.password_numeric:
            message.append(_(u'* Skaičiai'))
        if company_id.password_special:
            message.append(_(u'* Specialūs simboliai'))
        return u'\r'.join(message)

    @api.multi
    def check_password(self, password):
        # company_id = self.company_id
        # password_regex = ['^']
        # if company_id.password_lower:
        #     password_regex.append('(?=.*?[a-z])')
        # if company_id.password_upper:
        #     password_regex.append('(?=.*?[A-Z])')
        # if company_id.password_numeric:
        #     password_regex.append(r'(?=.*?\d)')
        # if company_id.password_special:
        #     password_regex.append(r'(?=.*?\W)')
        # password_regex.append('.{%d,}$' % company_id.password_length)
        # if not re.search(''.join(password_regex), password):
        #     if self._context.get('internal', False):
        #         raise exceptions.UserError(self.password_match_message())
        #     else:
        #         raise PasswordException(self.password_match_message())
        return True

    @api.multi
    def _password_has_expired(self, ):
        if not self.password_write_date:
            return True
        write_date = fields.Datetime.from_string(self.password_write_date)
        today = fields.Datetime.from_string(datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT))
        days = (today - write_date).days
        if self.id == 1:
            return False
        else:
            return days > self.company_id.password_expiration

    @api.multi
    def action_expire_password(self):
        expiration = delta_now(days=+1)
        for rec_id in self:
            rec_id.mapped('partner_id').signup_prepare(
                signup_type="reset", expiration=expiration
            )


ResUsers()


class ChangePasswordUser(models.TransientModel):

    _inherit = 'change.password.user'

    @api.multi
    def change_password_button(self):
        super(ChangePasswordUser, self.with_context(internal=True)).change_password_button()


ChangePasswordUser()
