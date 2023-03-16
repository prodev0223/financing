# from odoo import http
# from odoo.http import request
# from odoo.addons.web.controllers.main import Home
#
# class Home(Home):
#
#     @http.route('/web/login', type='http', auth="none")
#     def web_login(self, redirect=None, **kw):
#
#         request.params['background_src'] = request.env['ir.config_parameter'].get_param('login_robo_form_background_default') or ''
#
#         return super(Home, self).web_login(redirect, **kw)
