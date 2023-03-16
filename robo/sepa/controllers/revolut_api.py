# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import tools
from odoo import http
from odoo import exceptions
from odoo.http import request
import logging
import werkzeug

_logger = logging.getLogger(__name__)

class ApiController(http.Controller):

    @http.route(['/web/revolut/<int:id>/'], type='http', auth='public')
    def revolut_set_oauth(self, id=None, **post):
        env = request.env
        revapi = env['revolut.api'].sudo().browse(id)
        if not revapi:
            _logger.info('Revolut API controller error: Revolut API (id: %s) not found', id)
            return werkzeug.utils.redirect('/')
        # if revapi.auth_code: # Maybe we don't need to prevent new changes, as the code is only used once with some internal data
        #     return werkzeug.utils.redirect('/')
        code = post.get('code')
        if not code:
            _logger.info('Revolut API controller error: Code could not be extracted')
            return werkzeug.utils.redirect('/')
        revapi.write({'auth_code': code})
        try:
            revapi.get_tokens()
        except Exception as e:
            _logger.info('Revolut API controller error: Failed to get tokens.\nException: %s', str(e))
            env.cr.rollback()
            env['robo.bug'].sudo().create({
                'user_id': 1,
                'error_message': 'Failed to get Revolut tokens. Error:\n %s' % str(e),
            })
        return werkzeug.utils.redirect('/')


ApiController()
