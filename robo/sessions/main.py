# -*- encoding: utf-8 -*-
import logging
from datetime import datetime

import odoo
import pytz
import werkzeug.contrib.sessions
from dateutil.relativedelta import *
from odoo import SUPERUSER_ID
from odoo import fields, _
from odoo import http
from odoo.http import request
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.addons.web.controllers.main import ensure_db
import random

# from odoo import pooler

_logger = logging.getLogger(__name__)


def random_pass():
    letters = 'qwertyuiopasdfghjklzxcvbnm'
    digits = '1234567890'
    caps = 'QWERTYUIOPASDFGHJKLZXCVBNM'
    token = ''.join(random.SystemRandom().choice(letters) for i in xrange(20))
    token += ''.join(random.SystemRandom().choice(digits) for i in xrange(20))
    token += ''.join(random.SystemRandom().choice(caps) for i in xrange(20))

    return token


class Home(odoo.addons.web.controllers.main.Home):
    # @http.route('/web/login', type='http', auth="none")
    # def web_login(self, redirect=None, **kw):
    #     if not request.registry.get('ir.sessions'):
    #         return super(Home, self).web_login(redirect=redirect, **kw)
    #     odoo.addons.web.controllers.main.ensure_db()
    #     request.params['login_success'] = False
    #     multi_ok = True
    #     calendar_set = 0
    #     calendar_ok = True
    #     calendar_group = ''
    #     unsuccessful_message = ''
    #     now = datetime.now()
    #
    #     session_obj = request.env['ir.sessions'].sudo()
    #     if request.httprequest.method == 'GET' and redirect and request.session.uid:
    #         return http.redirect_with_hash(redirect)
    #
    #     if not request.uid:
    #         request.uid = odoo.SUPERUSER_ID
    #
    #     values = request.params.copy()
    #     if not redirect:
    #         redirect = '/web?' + request.httprequest.query_string
    #     elif 'error' in redirect:
    #         redirect = '/web'
    #     values['redirect'] = redirect
    #
    #     try:
    #         values['databases'] = http.db_list()
    #     except odoo.exceptions.AccessDenied:
    #         values['databases'] = None
    #
    #     if request.httprequest.method == 'GET':
    #         if 'error' in kw and kw['error'] == 'session_expired':
    #             values['error'] = _('Sesija baigėsi. Prisijunkite iš naujo.')
    #
    #     if request.httprequest.method == 'POST':
    #         old_uid = request.uid
    #         uid = False
    #         if 'login' in request.params and 'password' in request.params:
    #             uid = request.session.authenticate(request.session.db, request.params[
    #                 'login'], request.params['password'])
    #         if uid is not False:
    #             user = request.env.user
    #             if not uid is SUPERUSER_ID:
    #                 # check for multiple sessions block
    #                 sessions = session_obj.search(
    #                     [('user_id', '=', uid), ('logged_in', '=', True)])
    #
    #                 if sessions and user.multiple_sessions_block:
    #                     multi_ok = False
    #
    #                 if multi_ok:
    #                     # check calendars
    #                     calendar_obj = request.env.get(
    #                         'resource.calendar')
    #                     attendance_obj = request.env.get(
    #                         'resource.calendar.attendance')
    #
    #                     # GET USER LOCAL TIME
    #                     if user.tz:
    #                         tz = pytz.timezone(user.tz)
    #                     else:
    #                         tz = pytz.timezone('GMT')
    #                     tzoffset = tz.utcoffset(now)
    #                     now = now + tzoffset
    #
    #                     if user.login_calendar_id:
    #                         calendar_set += 1
    #                         # check user calendar
    #                         attendances = attendance_obj.with_context(request.context).search(
    #                             [('calendar_id', '=', user.login_calendar_id.id),
    #                              ('dayofweek', '=', str(now.weekday())),
    #                              ('hour_from', '<=', now.hour + now.minute / 60.0),
    #                              ('hour_to', '>=', now.hour + now.minute / 60.0)])
    #                         if attendances:
    #                             calendar_ok = True
    #                         else:
    #                             unsuccessful_message = "unsuccessful login from '%s', user time out of allowed calendar defined in user" % \
    #                                                    request.params[
    #                                                        'login']
    #                             calendar_ok = False
    #                     else:
    #                         # check user groups calendar
    #                         for group in user.groups_id:
    #                             if group.login_calendar_id:
    #                                 calendar_set += 1
    #                                 attendances = attendance_obj.with_context(request.context).search(
    #                                     [('calendar_id', '=',
    #                                       group.login_calendar_id.id),
    #                                      ('dayofweek', '=',
    #                                       str(now.weekday())),
    #                                      ('hour_from', '<=',
    #                                       now.hour + now.minute / 60.0),
    #                                      ('hour_to', '>=',
    #                                       now.hour + now.minute / 60.0)],
    #                                     )
    #                                 if attendances:
    #                                     calendar_ok = True
    #                                 else:
    #                                     calendar_group = group.name
    #                             if sessions and group.multiple_sessions_block and multi_ok:
    #                                 multi_ok = False
    #                                 unsuccessful_message = _(
    #                                     "unsuccessful login from '%s', multisessions block defined in group '%s'") % (
    #                                                            request.params['login'], group.name)
    #                                 break
    #                         if calendar_set > 0 and calendar_ok == False:
    #                             unsuccessful_message = _(
    #                                 "unsuccessful login from '%s', user time out of allowed calendar defined in group '%s'") % (
    #                                                        request.params['login'], calendar_group)
    #                 else:
    #                     unsuccessful_message = _("unsuccessful login from '%s', multisessions block defined in user") % \
    #                                            request.params[
    #                                                'login']
    #         else:
    #             unsuccessful_message = _("unsuccessful login from '%s', wrong username or password") % request.params[
    #                 'login']
    #         if not unsuccessful_message or uid is SUPERUSER_ID:
    #             self.save_session(
    #                 user.tz,
    #                 request.httprequest.session.sid)
    #             request.params['login_success'] = True
    #             return http.redirect_with_hash(redirect)
    #         user = request.env.user
    #         self.save_session(
    #             user.tz,
    #             request.httprequest.session.sid,
    #             unsuccessful_message)
    #         _logger.error(unsuccessful_message)
    #         request.uid = old_uid
    #         if not calendar_ok:
    #             values['error'] = _("Šiuo metu draudžiamas prisijungimas. Bandykite vėliau")
    #         elif not multi_ok:
    #             values['error'] = _("Draudžiamas prisijungimas iš kelių skirtingų įrenginių")
    #         else:
    #             values['error'] = _("Neteisingas prisijungimo vardas/slaptažodis")
    #     sign_up_values = self.get_auth_signup_config()
    #     values.update(sign_up_values)
    #     return request.render('web.login', values)

    @http.route('/token', type='http', auth="public")
    def AccessByToken(self, token=None, uid=None, **kw):
        ensure_db()
        if token and uid:
            users_obj = request.env['res.users']
            users_obj.env.uid = odoo.SUPERUSER_ID
            user_id = users_obj.search([('id', '=', uid)])
            password = random_pass()
            if user_id and user_id.partner_id.signup_token == token and user_id.partner_id.signup_valid:
                values = {
                    'db': request.session.db,
                    'token': token,
                    'name': user_id.name,
                    'email': user_id.email,
                    'login': user_id.login,
                    'password': password,
                }
                db, login, password = request.env['res.users'].sudo().signup(values, token)
                request.env.cr.commit()
                uid = request.session.authenticate(db, login, password)
                if not uid:
                    values['error'] = _("Authentication failed.")
                    return request.render('web.login', values)
                user = request.env.user
                self.save_session(
                    user.tz,
                    request.httprequest.session.sid)
        return http.redirect_with_hash('/web')

    def save_session(
            self,
            tz,
            sid,
            unsuccessful_message='',
    ):
        now = fields.datetime.now()
        session_obj = request.env['ir.sessions'].sudo()
        cr = request.registry.cursor()

        # Get IP, check if it's behind a proxy
        ip = request.httprequest.headers.environ['REMOTE_ADDR']
        forwarded_for = ''
        if 'HTTP_X_FORWARDED_FOR' in request.httprequest.headers.environ and request.httprequest.headers.environ[
            'HTTP_X_FORWARDED_FOR']:
            forwarded_for = request.httprequest.headers.environ['HTTP_X_FORWARDED_FOR'].split(', ')
            if forwarded_for and forwarded_for[0]:
                ip = forwarded_for[0]

        # for GeoIP
        geo_ip_resolver = None
        ip_location = ''
        try:
            import GeoIP
            geo_ip_resolver = GeoIP.open(
                '/usr/share/GeoIP/GeoIP.dat',
                GeoIP.GEOIP_STANDARD)
        except ImportError:
            geo_ip_resolver = False
        if geo_ip_resolver:
            ip_location = (str(geo_ip_resolver.country_name_by_addr(ip)) or '')

        # autocommit: our single update request will be performed atomically.
        # (In this way, there is no opportunity to have two transactions
        # interleaving their cr.execute()..cr.commit() calls and have one
        # of them rolled back due to a concurrent access.)
        cr.autocommit(True)
        user = request.env.user
        logged_in = True
        uid = user.id
        if unsuccessful_message:
            uid = SUPERUSER_ID
            logged_in = False
            sessions = False
        else:
            sessions = session_obj.search([('session_id', '=', sid),
                                           ('ip', '=', ip),
                                           ('user_id', '=', uid),
                                           ('logged_in', '=', True)],
                                          )
        if not sessions:
            date_expiration = (now + relativedelta(seconds=user.session_default_seconds)).strftime(
                DEFAULT_SERVER_DATETIME_FORMAT)
            values = {
                'user_id': uid,
                'logged_in': logged_in,
                'session_id': sid,
                'session_seconds': user.session_default_seconds,
                'multiple_sessions_block': user.multiple_sessions_block,
                'date_login': now.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                'date_expiration': date_expiration,
                'ip': ip,
                'ip_location': ip_location,
                'remote_tz': tz or 'GMT',
                'unsuccessful_message': unsuccessful_message,
            }
            session_obj.sudo().create(values)
            cr.commit()
        cr.close()

    @http.route('/web/session/logout', type='http', auth="none")
    def logout(self, redirect='/web'):
        request.session.logout(keep_db=True, logout_type='ul')
        return werkzeug.utils.redirect(redirect, 303)
