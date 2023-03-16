# -*- coding: utf-8 -*-
from odoo import models, fields, tools, _
from datetime import datetime


class Statistics(models.Model):

    _name = 'robo.company.statistics'

    def _get_user_id(self):
        return self._uid

    model = fields.Char(string='Modelis')
    tag = fields.Char(string='Žymė')
    # date = fields.Date(string='Diena', default=datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
    duration = fields.Integer(string='Intervalas, s', default=0)
    user = fields.Integer(string='Vartotojas', default=_get_user_id)

Statistics()