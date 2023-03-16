# -*- coding: utf-8 -*-

from datetime import datetime

from odoo import _, api, exceptions, fields, models, tools


class DateWorkTimeLine(models.Model):
    _name = 'date.work.time.line'

    def _default_date(self):
        return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    e_document = fields.Many2one('e.document', string='Dokumentas')
    date = fields.Date(string='Data', required=True, default=_default_date)
    hour_from = fields.Float(string='Dirbama nuo', required=True, index=True)
    hour_to = fields.Float(string='Dirbama iki', required=True)
    time_total = fields.Float(string='Trukmė', compute='_compute_time_total')

    @api.depends('hour_from', 'hour_to')
    def _compute_time_total(self):
        for rec in self:
            rec.time_total = rec.hour_to - rec.hour_from if rec.hour_from and rec.hour_to else 0.0

    @api.constrains('hour_from', 'hour_to')
    def _check_hours_range(self):
        for rec in self:
            if rec.hour_to and rec.hour_from and rec.hour_to <= rec.hour_from:
                raise exceptions.ValidationError(_('Dirbama iki turi būti daugiau nei dirbama nuo'))
            if not 0 <= rec.hour_from <= 24 or not 0 <= rec.hour_to <= 24:
                raise exceptions.ValidationError(_('Grafiko laikas turi būti nuo 00:00 iki 24:00'))


DateWorkTimeLine()
