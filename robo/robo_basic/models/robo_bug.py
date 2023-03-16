# -*- coding: utf-8 -*-
from odoo import fields, models, _, api, tools
from odoo.addons.web.controllers.main import Home
from odoo import http, _, SUPERUSER_ID
from odoo.http import request
from datetime import datetime


class Robobug(models.Model):
    _name = 'robo.bug'
    _inherit = 'mail.thread'

    _order = 'date desc'

    @api.model
    def default_get(self, fields_list):
        res = super(Robobug, self).default_get(fields_list)
        if 'date' in fields_list:
            res['date'] = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        if 'user_id' in fields_list:
            res['user_id'] = self.env.user.id
        return res

    date = fields.Datetime(string='Date', required=True)
    user_id = fields.Many2one('res.users', string='User')
    error_message = fields.Text(string='Error', required=True)
    skip_ticket_creation = fields.Boolean(string='Do not create ticket', default=False)


Robobug()


class BugHome(Home):

    @http.route('/web/send_front_error_message', type='json', auth="user")
    def send_front_error_message(self, **kwargs):
        # FIXME: HERE FOR FRONT END BUGS: summary="o_mail_notification" should not be in the html
        data = kwargs.get('data', False)
        if data:
            debug = data.get('debug', '')
        else:
            debug = ''

        message = kwargs.get('message', '') + '<br/> DEBUG: <br/>' + debug

        request.env['robo.bug'].sudo().create({
            'user_id': request.uid,
            'subject': 'Front-end bug in robo [%s]' % request.cr.dbname,
            'error_message': message,
            'skip_ticket_creation': True,
        })

        request.cr.commit()
        return True


BugHome()
