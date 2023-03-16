# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models, tools


class EDocFixAttendance(models.Model):
    _name = 'e.document.fix.attendance.line'

    _description = "Darbo grafikas"
    _order = 'dayofweek, hour_from'

    e_document = fields.Many2one('e.document', string='Dokumentas')
    dayofweek = fields.Selection([
        ('0', 'Pirmadienis'),
        ('1', 'Antradienis'),
        ('2', 'Trečiadienis'),
        ('3', 'Ketvirtadienis'),
        ('4', 'Penktadienis'),
        ('5', 'Šeštadienis'),
        ('6', 'Sekmadienis')
    ], string='Savaitės diena', required=True, index=True, default='0')
    hour_from = fields.Float(string='Dirbama nuo', required=True, index=True,
                             help='Darbo pradžios ir pabaigos laikai')
    hour_to = fields.Float(string='Dirbama iki', required=True)
    time_total = fields.Float(string='Trukmė', compute='_compute_time_total')

    @api.depends('hour_from', 'hour_to')
    def _compute_time_total(self):
        for rec in self:
            rec.time_total = rec.hour_to - rec.hour_from

    @api.constrains('hour_from', 'hour_to')
    def _check_hours_range(self):
        for rec in self:
            if tools.float_compare(rec.hour_from, rec.hour_to, precision_digits=2) >= 0:
                raise exceptions.ValidationError(_('Dirbama iki turi būti daugiau nei dirbama nuo'))
            if not 0 <= rec.hour_from <= 24 or not 0 <= rec.hour_to <= 24:
                raise exceptions.ValidationError(_('Grafiko laikas turi būti nuo 00:00 iki 24:00'))


EDocFixAttendance()
