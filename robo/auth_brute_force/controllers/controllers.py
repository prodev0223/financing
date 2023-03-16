# -*- encoding: utf-8 -*-
import logging

from odoo import fields, http, registry, SUPERUSER_ID
from odoo.http import request
from odoo.addons.web.controllers.main import Home, ensure_db
from datetime import datetime

_logger = logging.getLogger(__name__)


class LoginController(Home):
    @http.route()
    def web_login(self, redirect=None, **kw):
        if request.httprequest.method == 'POST':
            ensure_db()
            try:
                remote_ips = request.httprequest.headers['X-Forwarded-For']
                if ',' in remote_ips:
                    remote = remote_ips.split(',')[-2].strip()  # -1 is Load Balancer
                else:
                    remote = remote_ips.strip()
            except:
                remote = False
            if not remote:
                try:
                    remote = request.httprequest.headers['X-Real-IP']
                except KeyError:
                    remote = None
            if not remote:
                remote = request.httprequest.remote_addr
            config_obj = request.env['ir.config_parameter'].sudo()
            attempt_obj = request.env['res.authentication.attempt'].sudo()
            banned_remote_obj = request.env['res.banned.remote'].sudo()

            # Get Settings
            max_attempts_qty = int(config_obj.search_read([('key', '=', 'auth_brute_force.max_attempt_qty')],
                ['value'])[0]['value'])

            # Test if remote user is banned
            banned = banned_remote_obj.search([('remote', '=', remote)])
            if banned:
                _logger.warning(
                    "Authentication tried from remote '%s'. The request has"
                    " been ignored because the remote has been banned after"
                    " %d attempts without success. Login tried : '%s'." % (
                        remote, max_attempts_qty, request.params['login']))
                request.params['password'] = ''

            else:
                # Try to authenticate
                result = request.session.authenticate(
                    request.session.db, request.params['login'],
                    request.params['password'])

            # Log attempt
            request._cr.commit()
            attempt_obj.sudo().create({
                'attempt_date': datetime.utcnow(),
                'login': request.params['login'],
                'remote': remote,
                'result': banned and 'banned' or (
                    result and 'successfull' or 'failed'),
            })
            request._cr.commit()
            if not banned and not result:
                # Check whitelist
                whitelisted_ips = config_obj.search_read([('key', '=', 'auth_brute_force.whitelist')],
                                                         ['value'])
                if whitelisted_ips and whitelisted_ips[0]:
                    whitelisted_ips = whitelisted_ips[0]['value']
                    whitelist = whitelisted_ips.split(',')
                    if remote in whitelist:
                        return super(LoginController, self).web_login(redirect=redirect, **kw)

                # Get last bad attempts quantity
                attempts_qty = len(attempt_obj.search_last_failed(remote))

                if max_attempts_qty <= attempts_qty:
                    # We ban the remote
                    _logger.warning(
                        "Authentication failed from remote '%s'. "
                        "The remote has been banned. Login tried : '%s'." % (
                            remote, request.params['login']))
                    new_rec = banned_remote_obj.sudo().create({
                        'remote': remote,
                        'ban_date': datetime.utcnow(),
                    })

                    new_rec.send_ban_message(request.params['login'])
                    request._cr.commit()

                else:
                    _logger.warning(
                        "Authentication failed from remote '%s'."
                        " Login tried : '%s'. Attempt %d / %d." % (
                            remote, request.params['login'], attempts_qty,
                            max_attempts_qty))

        return super(LoginController, self).web_login(redirect=redirect, **kw)
