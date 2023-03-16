# -*- coding: utf-8 -*-


from odoo import api, fields, models


class IrActionsServer(models.Model):
    _inherit = 'ir.actions.server'

    robo_front = fields.Boolean(string='Ar rodyti veiksmą vartotojui?', default=False)
    robo_front_view_ids = fields.Many2many('ir.ui.view', string='Rodyti tik šiuose vartotojo rodiniuose')
    group_ids = fields.Many2many('res.groups', string='Grupės')

    @api.multi
    def read(self, fields=None, load='_classic_read'):
        results = super(IrActionsServer, self).read(fields, load=load)
        if not self.env.user.is_back_user():
            results = [x for x in results if x.get('robo_front')]
        return results
