# -*- coding: utf-8 -*-

from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    @api.depends('template_id', 'date_from', 'date_time_from', 'date_1', 'date_2', 'date_3', 'date_4', 'date_5',
                 'document_type', 'state')
    def _compute_reikia_pasirasyti_iki(self):
        for rec in self:
            if rec.document_type == 'agreement':
                if rec.reikia_pasirasyti_iki:
                    rec.env['e.document.delegate'].sudo().search([
                        ('date_start', '<=', rec.reikia_pasirasyti_iki),
                        ('date_stop', '>=', rec.reikia_pasirasyti_iki)
                    ]).mapped('employee_id.user_id')._compute_delegated_document_ids()
                if rec.state == 'cancel':
                    rec.reikia_pasirasyti_iki = False
                    continue
                rec.reikia_pasirasyti_iki = rec.date_from
        return super(EDocument, self)._compute_reikia_pasirasyti_iki()


EDocument()
