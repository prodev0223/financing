# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import requests


class Frontend(http.Controller):
    """
    Load static frontend assets from CDN.
    """

    @http.route(['/home', '/revenue'], type='http', auth='user')
    def index(self, **kw):
        html = requests.get("https://frontend.robolabs.lt/")
        context = {
            'html': html.content
        }

        return request.render('frontend.index', qcontext=context)
