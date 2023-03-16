# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _
from .. import rr_tools as rt


class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner', 'mail.thread', 'importable.to.raso']

    imported_ids = fields.Many2many('sync.data.import', copy=False)

    revision_number = fields.Integer(string='Įrašo versija', copy=False)
    revision_number_display = fields.Char(compute='get_display_revision', string='Įrašo versija')
    raso_revision = fields.Char(string='Įrašo statusas RASO serveryje', compute='get_raso_revision')
    last_update_state = fields.Selection([('waiting', 'info'),
                                          ('rejected', 'danger'),
                                          ('out_dated', 'warning'),
                                          ('newest', 'success'),
                                          ('not_tried', 'muted')
                                          ], string='Importavimo būsena', compute='get_raso_revision')
    need_to_update = fields.Boolean(string='Reikia atnaujinti', compute='_need_to_update', store=True)

    @api.one
    @api.depends('last_update_state', 'revision_number')
    def _need_to_update(self):
        if self.last_update_state in rt.UPDATE_IMPORT_STATES:
            self.with_context(prevent_loop=True).need_to_update = True
        else:
            self.with_context(prevent_loop=True).need_to_update = False

    @api.model
    def import_raso_partners_action(self):
        action = self.env.ref('raso_retail.import_raso_partners_rec')
        if action:
            action.create_action()

    @api.model
    def create(self, vals):
        return super(ResPartner, self.with_context(skip_revision_increments=True)).create(vals)

    @api.multi
    def write(self, vals):
        res = super(ResPartner, self).write(vals)
        for rec in self:
            if self._context.get('prevent_loop', False):
                self.with_context(prevent_loop=False)
                continue
            else:
                if not self._context.get('skip_revision_increments', False):
                    rec.with_context(prevent_loop=True).revision_number += 1
        return res

    @api.multi
    def import_partners(self):
        for rec in self:
            if not rec.kodas:
                raise exceptions.ValidationError(_('Partneris %s neturi sukonfigūruoto kodo.' % rec.name))
        import_obj = self.env['sync.data.import'].sudo().create({
            'data_type': '1',
            'partner_ids': [(4, partner) for partner in self.ids],
            'full_sync': self._context.get('full_sync', False)
        })
        import_obj.format_xml()
        self._need_to_update()


ResPartner()
