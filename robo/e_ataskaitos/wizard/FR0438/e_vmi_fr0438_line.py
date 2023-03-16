# -*- coding: utf-8 -*-

from odoo import models, fields, api


class FR0438Line(models.TransientModel):
    _name = 'e.vmi.fr0438.line'

    shareholder_id = fields.Many2one('res.company.shareholder', string='Akcininkas')
    shareholder_address = fields.Text(string='Akciniko adresas')  # required in form and validate
    share_percentage = fields.Float(compute='_share_percentage', string='Akcijos (Procentais)')
    wizard_id = fields.Many2one('e.vmi.fr0438')

    @api.one
    @api.depends('shareholder_id')
    def _share_percentage(self):
        shareholder_ids = self.env['res.company.shareholder'].search([])
        total_shares = sum(x.shareholder_shares for x in shareholder_ids)
        percent_per_share = 100 / total_shares if total_shares else 0
        self.share_percentage = round(percent_per_share * self.shareholder_id.shareholder_shares, 2)


FR0438Line()
