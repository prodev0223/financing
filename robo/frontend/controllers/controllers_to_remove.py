# -*- coding: utf-8 -*-
from odoo.addons.web.controllers.main import DataSet
from odoo.addons.web.controllers.main import Action
from odoo.addons.robo.controllers.charts import Charts
from odoo.addons.robo.controllers.controllers import roboControler
from odoo import http, api, SUPERUSER_ID
from odoo.http import route, request
from odoo.models import check_method_name


# todo: REMOVE THIS FILE, DO NOT INSTALL IN PRODUCTION!
class DataSetExt(DataSet):
    """
    Enable CORS and open up database read to everyone. This is done to enable easier backend testing.
    """

    @http.route(['/web/dataset/call_kw_testing/<int:uid>/', '/web/dataset/call_kw_testing/<int:uid>/<path:path>'], type='json', auth="none", cors="*")
    def call_kw_testing(self, model, method, args, kwargs, uid=SUPERUSER_ID, path=None):
        return self._call_kw_testing(model, method, args, kwargs, uid)

    def _call_kw_testing(self, model, method, args, kwargs, uid):
        check_method_name(method)
        env = api.Environment(http.request.cr, uid, {'lang': 'lt_LT'})[model]
        return api.call_kw(env, method, args, kwargs)

    @http.route('/web/dataset/search_read', type='json', auth="none", cors="*")
    def search_read(self, model, fields=False, offset=0, limit=False, domain=None, sort=None):
        request.env.uid = 1
        return super(DataSetExt, self).search_read(model, fields, offset, limit, domain, sort)


class ActionExt(Action):

    @http.route('/web/action/load', type='json', auth="none", cors="*")
    def load(self, action_id, additional_context=None):
        request.env.uid = 1
        return super(ActionExt, self).load(action_id, additional_context)


class ChartsExt(Charts):
    """
    Enable CORS and open up read to everyone
    """

    @route('/pagalbininkas/get_graph_data', type='json', auth="none", cors="*")
    def get_graph_data(self, chart_type, chart_filter, is_screen_big):
        request.env.uid = 1
        return super(ChartsExt, self).get_graph_data(chart_type, chart_filter, is_screen_big)

    @route("/graph/cashflow/last_statement_closed_date", type='json', auth='none', cors="*")
    def get_bank_statement_last_date(self):
        request.env.uid = 1
        return super(ChartsExt, self).get_bank_statement_last_date()

    @route('/graph/get_default_dates', type='json', auth='none', cors='*')
    def get_graph_default_dates(self):
        request.env.uid = 1
        return super(ChartsExt, self).get_graph_default_dates()

    @route('/graph/get_default_comparison_dates', type='json', auth='none', cors='*')
    def get_grapt_comparison_default_dates(self):
        request.env.uid = 1
        return super(ChartsExt, self).get_grapt_comparison_default_dates()


class roboControlerExt(roboControler):
    """
        Enable CORS and open up read to everyone
        """

    @route('/e_document/needaction', type='json', auth='none', cors='*')
    def needaction(self):
        return request.env['e.document'].sudo().get_needaction_count()

    @route('/robomessage/needaction', type='json', auth='none', cors='*')
    def countRoboFrontMessages(self):
        return request.env['res.partner'].sudo().get_roboNeedaction_count()

    @route('/robomessage/lastmessages', type='json', auth='none', cors='*')
    def lastRoboFrontMessages(self):
        return request.env['res.partner'].sudo().get_lastRoboNeedaction_messages()

    @route('/roboupload/statistics', type='json', auth='none', cors='*')
    def countRoboUploadFiles(self, **dates):
        return request.env['robo.upload'].sudo().get_roboUpload_count(**dates)

    @route('/robo/upload', type='http', auth='none', cors='*', csrf=False)
    def upload(self, callback, ufile):
        request.env.uid = 1
        return super(roboControlerExt, self).upload(callback, ufile)

    @route('/web/binary/upload_attachment_invoice', type='http', auth='none', cors='*')
    def upload_attachment(self, model, id, wizard_id, ufile):
        request.env.uid = 1
        return super(roboControlerExt, self).upload_attachment(model, id, wizard_id, ufile)
