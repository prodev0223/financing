# -*- coding: utf-8 -*-
import odoo
from odoo import http, _
from odoo.http import request
from odoo.addons.web.controllers.main import ensure_db, serialize_exception, Database, Home, CSVExport, ExcelExport, \
    Export
import random


def random_pass():
    letters = 'qwertyuiopasdfghjklzxcvbnm'
    digits = '1234567890'
    caps = 'QWERTYUIOPASDFGHJKLZXCVBNM'
    token = ''.join(random.SystemRandom().choice(letters) for i in xrange(20))
    token += ''.join(random.SystemRandom().choice(digits) for i in xrange(20))
    token += ''.join(random.SystemRandom().choice(caps) for i in xrange(20))

    return token


class MultiDatabaseAccess(http.Controller):

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
        return http.redirect_with_hash('/web')


MultiDatabaseAccess()


# class DatabaseController(Database):
#
#     @http.route('/web/database/selector', type='http', auth="none")
#     def selector(self, **kw):
#         return request.not_found()
#
#     @http.route('/web/database/manager', type='http', auth="none")
#     def manager(self, **kw):
#         return request.not_found()
#
#     @http.route('/web/database/create', type='http', auth="none", methods=['POST'], csrf=False)
#     def create(self):
#         return request.not_found()
#
#     @http.route('/web/database/duplicate', type='http', auth="none", methods=['POST'], csrf=False)
#     def dublicate(self):
#         return request.not_found()
#
#     @http.route('/web/database/drop', type='http', auth="none", methods=['POST'], csrf=False)
#     def drop(self):
#         return request.not_found()
#
#     @http.route('/web/database/backup', type='http', auth="none", methods=['POST'], csrf=False)
#     def backup(self):
#         return request.not_found()
#
#     @http.route('/web/database/restore', type='http', auth="none", methods=['POST'], csrf=False)
#     def restore(self):
#         return request.not_found()
#
#     @http.route('/web/database/change_password', type='http', auth="none", methods=['POST'], csrf=False)
#     def change_password(self):
#         return request.not_found()
#
#     @http.route('/web/database/list', type='json', auth='none')
#     def list(self):
#         return request.not_found()
#
# DatabaseController()


class RoboHome(Home):

    @http.route('/', type='http', auth="none")
    def index(self, s_action=None, db=None, **kw):
        ensure_db()
        return http.local_redirect('/web', query=request.params, keep_hash=True)


RoboHome()


class RoboCSVExport(CSVExport):

    @http.route('/web/export/csv', type='http', auth="user")
    @serialize_exception
    def index(self, data, token):
        if request.env.user.has_group('robo_basic.group_robo_import_export'):
            return self.base(data, token)
        else:
            return request.not_found()


RoboCSVExport()


class RoboExcelExport(ExcelExport):

    @http.route('/web/export/xls', type='http', auth="user")
    @serialize_exception
    def index(self, data, token):
        if request.env.user.has_group('robo_basic.group_robo_import_export'):
            return self.base(data, token)
        else:
            return request.not_found()


RoboExcelExport()


class RoboExport(Export):

    @http.route('/web/export/formats', type='json', auth="user")
    def formats(self):
        if request.env.user.has_group('robo_basic.group_robo_import_export'):
            return super(RoboExport, self).formats()
        else:
            return []

    @http.route('/web/export/get_fields', type='json', auth="user")
    def get_fields(self, model, prefix='', parent_name='',
                   import_compat=True, parent_field_type=None,
                   exclude=None):
        if request.env.user.has_group('robo_basic.group_robo_import_export'):
            return super(RoboExport, self).get_fields(model, prefix=prefix, parent_name=parent_name,
                                                      import_compat=import_compat, parent_field_type=parent_field_type,
                                                      exclude=exclude)
        else:
            return []


RoboExport()
