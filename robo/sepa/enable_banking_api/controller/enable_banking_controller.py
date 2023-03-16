# -*- coding: utf-8 -*-
from odoo.http import request
from odoo import http
import logging
import werkzeug

_logger = logging.getLogger(__name__)
REDIRECT_MODEL = 'enable.banking.connector'


class EnableBankingController(http.Controller):

    @http.route(['/web/e_banking_auth'], type='http', auth='public')
    def enable_banking_auth_redirect(self, **post):
        """
        Route //
        User is redirected to this route after confirming access
        for specific Enable banking connector.
        Access tokens are fetched based on passed enable banking code
        :param post: post data containing unique enable banking state vector (dict)
        :return: redirect (object)
        """

        # TODO: Route is left here for testing purposes, meant to be removed
        env = request.env
        # Get post values
        session_code = post.get('code')
        state_vector = post.get('state')

        banking_connector = None
        if state_vector:
            # Search for the connector based on latest state vector
            banking_connector = env[REDIRECT_MODEL].sudo().search([
                ('latest_state_vector', '=', state_vector),
            ])
        # if not found, redirect to main page
        if not banking_connector:
            return werkzeug.utils.redirect('/')
        # Initiate the new user session
        banking_connector.initiate_user_session(session_code)
        # Return user to corresponding bank connector form
        return werkzeug.utils.redirect('/web?#model=%s&id=%s&view_type=form' % (
            REDIRECT_MODEL, banking_connector.id
        ))
