# -*- coding: utf-8 -*-


from odoo import api, fields, models


class Months(models.Model):
    _name = 'months'

    code = fields.Integer(string='Month number', required=True, readonly=True)
    name = fields.Char(string='Month', required=True, readonly=True)

    @api.model
    def init(self):
        if self.env['months'].search_count([]) == 0:
            for j in range(2015, 2115):
                for i in range(1, 13):
                    month = {
                        'code': str(j) + str(i).zfill(2),
                        'name': str(j) + ' M' + str(i).zfill(2),
                    }
                    self.env['months'].create(month)
