# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import tools
from odoo import http
from odoo import exceptions
from odoo.http import request
import logging
import werkzeug
import requests

_logger = logging.getLogger(__name__)


class ApiController(http.Controller):

    @http.route(['/web/paysera_configuration/<int:rec_id>/'], type='http', auth='public')
    def paysera_oauth_redirect(self, rec_id=None, **post):
        """
        Route //
        User is redirected to this route after confirming access in their Paysera account.
        Access tokens are fetched based on passed paysera code
        :param rec_id: paysera.configuration record
        :param post: post data containing paysera_code
        :return: redirect object
        """
        env = request.env
        paysera_wizard = env['paysera.configuration'].sudo().browse(rec_id)
        if not paysera_wizard:
            return werkzeug.utils.redirect('/')
        paysera_code = post.get('code')
        # Fetch access tokens based on redirect code
        paysera_wizard.get_access_tokens(paysera_code)
        # Return user to the paysera configuration form
        return werkzeug.utils.redirect('/web?#model=%s&id=%s&view_type=form' % (
            'paysera.configuration',
            paysera_wizard.id
        ))


ApiController()
