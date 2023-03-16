# -*- coding: utf-8 -*-
import odoo
from odoo import http, _
from odoo.http import request
from odoo.addons.web.controllers.main import Home

class RoboHome(Home):

    @http.route()
    def web_client(self, s_action=None, **kw):
        if 'debug' in kw:
            users_obj = request.env['res.users']
            users_obj.env.uid = odoo.SUPERUSER_ID
            user_id = users_obj.search([('id', '=', request.session.uid)])
            # ADMIN: you can comment this to allow debuging for non-admin users
            if not user_id or not user_id.has_group('base.group_system'):
                kw.pop('debug')
                return http.redirect_with_hash('/web')
        return super(RoboHome, self).web_client(s_action=s_action, **kw)

RoboHome()
