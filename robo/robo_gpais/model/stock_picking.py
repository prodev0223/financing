# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    force_gpais_entry_id = fields.Char(string='Priverstinis GPAIS žurnalo kodas',
                                       help='Turi būti tik skaičiai. Naudojami tik paskutiniai 4 skaitmenys.',
                                       )

    @api.constrains('force_gpais_entry_id')
    def _constrain_force_gpais_entry_id(self):
        if any(rec.force_gpais_entry_id and not rec.force_gpais_entry_id.isdigit() for rec in self):
            raise exceptions.ValidationError(_('Priverstinis GPAIS žurnalo kodas turi būti sudarytas tik iš skaitmenų.'))
