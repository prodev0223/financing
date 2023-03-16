from odoo.addons.robo_api.controllers.api_controller import ApiController
from odoo import http
from odoo.http import request
import logging
_logger = logging.getLogger(__name__)


class ApiControllerDasp(ApiController):

    @http.route(['/api/create_invoice'], type='json', auth='public', methods=['POST'], csrf=False)
    def create_invoice(self, **post):
        post = request.jsonrequest
        if post and post.get('proforma'):
            post.pop('proforma')
        if post and not post.get('draft'):
            post['draft'] = True
        request.jsonrequest = post
        return super(ApiControllerDasp, self).create_invoice(**post)
