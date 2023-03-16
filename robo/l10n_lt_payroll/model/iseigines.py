# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, tools
from odoo.tools.translate import _
import time
from datetime import datetime, timedelta


class SistemaIseigines(models.Model):

    _name = 'sistema.iseigines'
    _order = 'date desc'
    _sql_constraints = [
        ('date_uniq', 'unique (date)', 'Negali būti daugiau nei viena išeiginė tai pačiai datai !')
    ]

    name = fields.Text(string='Išeiginės', required=True)
    date = fields.Date('Data', default=lambda *a: time.strftime('%Y-%m-%d'), required=True)

    @api.model
    def get_dates_with_shorter_work_date(self, date_from, date_to):
        date_to = (datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)+relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        national_holidays = self.env['sistema.iseigines'].search(
            [('date', '>', date_from), ('date', '<=', date_to)]).mapped('date')
        dates_with_shorter_work_date = [
            (datetime.strptime(d, tools.DEFAULT_SERVER_DATE_FORMAT) - timedelta(days=1)).strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT)
            for d in national_holidays]
        return dates_with_shorter_work_date


SistemaIseigines()
