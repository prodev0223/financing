# -*- coding: utf-8 -*-
from odoo import models, api, exceptions, _, fields


class AlignmentCommittee(models.Model):
    _inherit = 'alignment.committee'

    inventory_ids = fields.One2many('stock.inventory', 'komisija')

    @api.multi
    def unlink(self):
        for rec in self.sudo():
            if rec.inventory_ids:
                raise exceptions.UserError(_('Negalima ištrinti komisijų, kurios turi susietų inventorių.'))
        return super(AlignmentCommittee, self).unlink()
