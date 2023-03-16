# -*- coding: utf-8 -*-
from odoo import http, _, exceptions
from odoo.http import request
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.web.controllers.main import ensure_db, Session
from odoo import SUPERUSER_ID
import operator


class PasswordSecuritySession(Session):

    @http.route('/web/session/change_password', type='json', auth="user")
    def change_password(self, fields):
        new_password = operator.itemgetter('new_password')(
            dict(map(operator.itemgetter('name', 'value'), fields))
        )
        user = request.env.user
        user.check_password(new_password)
        return super(PasswordSecuritySession, self).change_password(fields)

    @http.route('/web/session/change_password_internal', type='json', auth="user")
    def change_password_internal(self, fields):
        new_password = operator.itemgetter('new_password')(
            dict(map(operator.itemgetter('name', 'value'), fields))
        )
        user = request.env.user
        user.with_context(internal=True).check_password(new_password)
        return super(PasswordSecuritySession, self).change_password(fields)

PasswordSecuritySession()


class PasswordSecurityHome(AuthSignupHome):

    def do_signup(self, qcontext):
        password = qcontext.get('password')
        user_id = request.env['res.users'].browse(request.uid)
        user_id.check_password(password)
        return super(PasswordSecurityHome, self).do_signup(qcontext)

    @http.route()
    def web_login(self, *args, **kw):
        ensure_db()
        response = super(PasswordSecurityHome, self).web_login(*args, **kw)
        if not request.httprequest.method == 'POST':
            return response
        try:
            uid = request.uid
        except:
            uid = None
        if not uid:
            request.uid = SUPERUSER_ID
            return response
        users_obj = request.env['res.users'].sudo()
        user_id = users_obj.browse(request.uid)
        if not user_id._password_has_expired():
            return response
        user_id.action_expire_password()
        redirect = user_id.partner_id.signup_url
        return http.redirect_with_hash(redirect)

    @http.route('/web/signup', type='http', auth='public', website=True)
    def web_auth_signup(self, *args, **kw):
        try:
            return super(PasswordSecurityHome, self).web_auth_signup(
                *args, **kw
            )
        except exceptions.UserError as e:
            qcontext = self.get_auth_signup_qcontext()
            qcontext['error'] = _(e.message)
            return request.render('auth_signup.signup', qcontext)

    @http.route(
        '/web/reset_password',
        type='http',
        auth='public',
        website=True
    )
    def web_auth_reset_password(self, *args, **kw):
        super_user_email = request.env['res.users'].sudo().browse(SUPERUSER_ID).email
        resetting_super_user = kw.get('login') == super_user_email
        if resetting_super_user:
            return http.redirect_with_hash('/web/login?db=%s' % request.env.cr.dbname, 303)

        response = super(PasswordSecurityHome, self).web_auth_reset_password(
            *args,
            **kw
        )
        qcontext = response.qcontext

        resetting_super_user = qcontext.get('login') == super_user_email
        if resetting_super_user:
            return http.redirect_with_hash('/web/login?db=%s' % request.env.cr.dbname, 303)
        if 'error' not in qcontext and qcontext.get('token'):
            qcontext['error'] = _("Jūsų slaptažodis turi būti atnaujintas")
            return request.render('auth_signup.reset_password', qcontext)
        return response


PasswordSecurityHome()
