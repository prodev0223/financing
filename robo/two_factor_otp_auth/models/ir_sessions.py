# -*- encoding: utf-8 -*-
import logging
from odoo import api, fields, models, SUPERUSER_ID

_logger = logging.getLogger(__name__)


class IrSessions(models.Model):
    _inherit = 'ir.sessions'

    with_2fa = fields.Boolean(string='Logged in with 2FA', readonly=True)

    @api.model
    def validate_sessions(self):
        """ Close sessions that are not 2FA when the user is set to use it """
        res = super(IrSessions, self).validate_sessions()
        sessions = self.sudo().search([
            ('user_id.enable_2fa', '=', True),
            ('logged_in', '=', True),
            ('with_2fa', '=', False),
            ('user_id', '!=', SUPERUSER_ID),
        ])
        if sessions:
            _logger.info('Logging out users requiring 2FA: %s', ', '.join(sessions.mapped('user_id.login')))
            sessions._close_session(logout_type='sk')
        return res

    @api.model
    def create(self, vals):
        user_id = vals.get('user_id')
        user = self.env['res.users'].sudo().browse(user_id)
        if user:
            vals['with_2fa'] = user.enable_2fa
        return super(IrSessions, self).create(vals)
