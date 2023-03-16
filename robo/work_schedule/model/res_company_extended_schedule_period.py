# -*- coding: utf-8 -*-

from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, exceptions
from odoo.tools.translate import _


class ResCompanyExtendedSchedulePeriod(models.Model):
    _name = 'res.company.extended.schedule.period'

    date_from = fields.Date(string='Data nuo', inverse='_inverse_check_extended_schedule_groups')
    date_to = fields.Date(string='Data iki', inverse='_inverse_check_extended_schedule_groups')
    company_id = fields.Many2one('res.company', string='Company', readonly=True,
                                 default=lambda self: self.env.user.company_id.id)

    @api.one
    def _inverse_check_extended_schedule_groups(self):
        self.env['res.company'].cron_check_work_schedule_periods()

    @api.multi
    @api.constrains('date_to', 'date_from')
    def _check_dates(self):
        for rec in self:
            if not rec.date_to and not rec.date_from:
                raise exceptions.ValidationError(_('Turite pasirinkti bent vieną datą'))
            if rec.date_to and rec.date_from and rec.date_to < rec.date_from:
                raise exceptions.ValidationError(_('Data nuo negali būti vėliau, nei data iki'))

    @api.model_cr
    def init(self):
        if not self.search([], count=True):
            self.create({
                'date_from': datetime.utcnow() + relativedelta(day=1)
            })


ResCompanyExtendedSchedulePeriod()