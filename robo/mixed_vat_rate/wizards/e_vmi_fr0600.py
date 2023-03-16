# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions, _


class FR0600(models.TransientModel):
    _inherit = 'e.vmi.fr0600'

    @api.multi
    def get_deductible_vat_rate(self):
        mixed_vat_id = self.env['res.company.mixed.vat'].search([('date_from', '<=', self.data_nuo),
                                                                 ('date_to', '>=', self.data_iki)])
        if not mixed_vat_id:
            if self.env['res.company.mixed.vat'].search([('date_from', '<=', self.data_iki),
                                                         ('date_to', '>=',self.data_nuo)], limit=1):
                raise exceptions.UserError(_('Nepavyko nustatyti mišraus PVM tarifo laikotarpiui: '
                                             'ataskaitiniam laikotarpiui taikomos kelios vertės'))
        rate = mixed_vat_id.rate if mixed_vat_id else 100
        return int(round(rate))
