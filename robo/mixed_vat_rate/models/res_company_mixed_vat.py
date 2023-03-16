# -*- encoding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields, _, api, exceptions, tools


class ResCompanyMixedVatRate(models.Model):
    _name = 'res.company.mixed.vat'

    date_from = fields.Date(string='Data nuo', required=True)
    date_to = fields.Date(string='Data iki', required=True)
    rate = fields.Float(string='Procentas', required=True, help='Procentas (tarp 0 ir 100)')

    @api.multi
    @api.constrains('date_to', 'date_from')
    def _check_dates(self):
        for rec in self:
            if rec.date_to and rec.date_from and rec.date_to < rec.date_from:
                raise exceptions.ValidationError(_('Data nuo negali būti vėliau, nei data iki'))
            date_from = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            if date_from.day != 1:
                raise exceptions.ValidationError(_('Pradžios data turi būti mėnesio pirma diena'))
            if date_to != date_to + relativedelta(day=31):
                raise exceptions.ValidationError(_('Pabaigos data turi būti mėnesio paskutinė diena'))
            domain = [('date_from', '<=', rec.date_to),
                      ('date_to', '>=', rec.date_from)]
            if isinstance(rec.id, (int, long)):
                domain += [('id', '!=', rec.id)]
            overlap = self.env['res.company.mixed.vat'].search_count(domain)
            if overlap:
                raise exceptions.ValidationError(_('Eilutės negali persidengti'))

    @api.multi
    @api.constrains('rate')
    def _check_rate_between_0_100(self):
        for rec in self:
            if tools.float_compare(rec.rate, 0, precision_digits=2) < 0 \
                    or tools.float_compare(rec.rate, 100, precision_digits=2) > 0:
                raise exceptions.ValidationError(_('Procentas turi būti tarp 0 ir 100'))
