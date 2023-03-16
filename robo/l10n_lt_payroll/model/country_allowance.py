# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions
from odoo.tools.translate import _
from odoo.tools import float_compare
from datetime import datetime, timedelta


class CountryAllowance(models.Model):

    _name = 'country.allowance'
    _description = 'Allowance by country'
    _order = 'name'
    _rec_name = 'name'

    name = fields.Char(string='Name', translate=True)
    amount_allowance = fields.Float(string='Suma', help='Kiek pinigų išmokama per dieną')
    amount_max_renting = fields.Float(string='Suma nuomai', help='Kiek leidžiama išleisti nuomai per dieną')
    line_ids = fields.One2many('country.allowance.line', 'country_allowance_id', string='Norma pagal datą')
    active = fields.Boolean(string='Aktyvus', default=True, lt_string='Aktyvus')

    # @api.constrains('amount_allowance', 'amount_max_renting')
    # def constrain_positive_amount(self):
    #     for rec in self:
    #         if float_compare(rec.amount_allowance, 0, precision_digits=2) < 0:
    #             raise exceptions.ValidationError(_('Dienos užmokestis negali būti neigiamas'))
    #         if float_compare(rec.amount_max_renting, 0, precision_digits=2) < 0:
    #             raise exceptions.ValidationError(_('Dienos nuomos limitas negali būti neigiamas'))

    @api.multi
    def get_amount(self, date_from, date_to):
        if not self or not date_from or not date_to:
            return 0.0
        self.ensure_one()
        if date_from > date_to:
            return 0.0
        lines = self.line_ids.filtered(lambda r: (not r.date_from or r.date_from <= date_to) and (not r.date_to or r.date_to >= date_from))
        date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        if not lines:
            raise exceptions.UserError(_('Nerastos normos %s laikotarpiui %s - %s') % (self.name, date_from, date_to))
        elif len(lines) == 1:
            lines = lines.filtered(lambda r: (not r.date_from or r.date_from <= date_from) and (not r.date_to or r.date_to >= date_to))  # the only line could end in period
            if not lines:
                raise exceptions.UserError(_('Nerastos normos %s laikotarpiui %s - %s') % (self.name, date_from, date_to))
            num_days = (date_to_dt - date_from_dt).days + 1
            return lines.amount_allowance * num_days
        else:
            # happens very rarely, so slow algorithm is not a problem
            amount = 0.0
            date_dt = date_from_dt
            while date_dt <= date_to_dt:
                date = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                lines_d = lines.filtered(lambda r: (not r.date_from or r.date_from <= date) and (not r.date_to or r.date_to >= date))
                if len(lines_d) != 1:
                    raise exceptions.UserError(_('Nenustatytos dienpinigių normos %s datai %s') % (self.name, date))
                amount += lines_d.amount_allowance
                date_dt += timedelta(days=1)
            return amount


CountryAllowance()


class CountryAllowanceLine(models.Model):

    _name = 'country.allowance.line'
    _description = 'Allowance by country line'
    _order = 'country_allowance_id'
    _rec_name = 'country_allowance_id'

    country_allowance_id = fields.Many2one('country.allowance', string='Valstybė', required=True, ondelete="cascade")
    amount_allowance = fields.Float(string='Suma', help='Kiek pinigų išmokama per dieną')
    amount_max_renting = fields.Float(string='Suma nuomai', help='Kiek leidžiama išleisti nuomai per dieną')
    date_from = fields.Date(string='Data nuo')
    date_to = fields.Date(string='Data iki')

    @api.constrains('amount_allowance', 'amount_max_renting')
    def constrain_positive_amount(self):
        for rec in self:
            if float_compare(rec.amount_allowance, 0, precision_digits=2) < 0:
                raise exceptions.ValidationError(_('Dienos užmokestis negali būti neigiamas'))
            if float_compare(rec.amount_max_renting, 0, precision_digits=2) < 0:
                raise exceptions.ValidationError(_('Dienos nuomos limitas negali būti neigiamas'))


CountryAllowance()
