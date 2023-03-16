# -*- coding: utf-8 -*-

from odoo import api, models, _, exceptions


class MrpUnbuild(models.Model):

    _inherit = 'mrp.unbuild'

    @api.multi
    def unlink(self):
        for rec in self:
            if rec.state == 'done':
                raise exceptions.UserError(_('Negalima ištrinti patvirtinto išrinkimo.'))
            elif rec.state == 'reserved':
                raise exceptions.UserError(_('Negalima ištrinti rezervuoto išrinkimo. '
                                             'Pabandykite atšaukti rezervaciją.'))
        return super(MrpUnbuild, self).unlink()


MrpUnbuild()
