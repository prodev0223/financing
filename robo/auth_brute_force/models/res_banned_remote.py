# -*- encoding: utf-8 -*-
import urllib
import json

from odoo import models, fields, api, tools
from six import iteritems
from datetime import datetime


class ResBannedRemote(models.Model):
    _name = 'res.banned.remote'
    _rec_name = 'remote'

    _GEOLOCALISATION_URL = "http://ip-api.com/json/{}"

    # Default Section
    def _default_ban_date(self):
        return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

    # Column Section
    description = fields.Text(
        string='Description', compute='_compute_description', store=True)

    ban_date = fields.Datetime(
        string='Ban Date', required=True, default=_default_ban_date)

    remote = fields.Char(string='Remote ID', required=True)

    active = fields.Boolean(
        string='Active', help="Uncheck this box to unban the remote",
        default=True)

    attempt_ids = fields.Many2many(
        comodel_name='res.authentication.attempt', string='Attempts',
        compute='_compute_attempt_ids')

    # Compute Section
    @api.multi
    @api.depends('remote')
    def _compute_description(self):
        for item in self:
            url = self._GEOLOCALISATION_URL.format(item.remote)
            res = json.loads(urllib.urlopen(url).read())
            item.description = ''
            for k, v in iteritems(res):
                item.description += '%s : %s\n' % (k, v)

    @api.multi
    def _compute_attempt_ids(self):
        for item in self:
            attempt_obj = self.env['res.authentication.attempt']
            item.attempt_ids = attempt_obj.search_last_failed(item.remote).ids

    @api.multi
    def send_ban_message(self, login):
        """ Create a robo.bug record to inform about IP banning """
        self.ensure_one()
        database = self.env.cr.dbname
        message = "Authentication failed from remote '%s'. ""The remote has been banned. " \
                  "Login tried : '%s'. Database : '%s'." % (self.remote, login, database)

        self.env['robo.bug'].sudo().create({
            'error_message': message,
            'date': self.ban_date,
            'subject': '[%s] Banned user (IP - %s, Login Tried - %s)' % (database, self.remote, login)
        })
