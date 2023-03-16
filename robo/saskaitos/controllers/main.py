# -*- coding: utf-8 -*-

import functools

from odoo.addons.web.controllers.main import Binary

from odoo import http
from odoo.modules import get_module_resource


class BinaryCustom(Binary):

    @http.route(['/web/binary/machine_readable'], type='http', auth="none")
    def machine_readable(self, **kw):
        imgname = 'machine_readable.png'
        default_logo_module = 'saskaitos'
        placeholder = functools.partial(get_module_resource, default_logo_module, 'static', 'src', 'img')
        response = http.send_file(placeholder(imgname))
        return response
