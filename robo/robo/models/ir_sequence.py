# -*- coding: utf-8 -*-
from odoo import api, models


class IrSequence(models.Model):
    _inherit = 'ir.sequence'

    @api.constrains('use_date_range', 'prefix')
    def check_use_date_range_prefix(self):
        for seq in self:
            if seq.use_date_range and seq.prefix and not '%(' in seq.prefix:
                message = 'Sequence %s (id: %s) with prefix %s use date ranges but prefix is static' % (seq.name, seq.id, seq.prefix)
                self.env['robo.bug'].sudo().create({
                    'user_id': self.env.user.id,
                    'error_message': message,
                })

    @api.multi
    def get_prefix_size_number(self):
        self.ensure_one()
        return self.prefix, self.padding, self.number_next_actual
