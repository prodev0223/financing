# -*- coding: utf-8 -*-
from odoo import models, fields, _, api, exceptions


class ResCompanyVatStatus(models.Model):
    _name = 'res.company.vat.status'

    date_from = fields.Date(string='Data nuo')
    date_to = fields.Date(string='Data iki')
    company_id = fields.Many2one('res.company', string='Company', lt_string='Įmonė', readonly=True,
                                 default=lambda self: self.env.user.company_id.id)

    @api.multi
    @api.constrains('date_to', 'date_from')
    def _check_dates(self):
        for rec in self:
            if not rec.date_to and not rec.date_from:
                raise exceptions.ValidationError(_('Turite pasirinkti bent vieną datą'))
            if rec.date_to and rec.date_from and rec.date_to < rec.date_from:
                raise exceptions.ValidationError(_('Data nuo negali būti vėliau, nei data iki'))
            if self.env.user.company_id.check_date_overlap(line_to_check=rec):
                raise exceptions.ValidationError(_('Eilutės negali persidengti'))
