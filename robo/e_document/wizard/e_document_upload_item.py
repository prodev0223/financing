# -*- coding: utf-8 -*-
from odoo import api, fields, models


class EDocumentUploadList(models.TransientModel):
    _name = 'e.document.upload.item'

    @api.model
    def get_domain(self):
        user_ids = self.env['hr.employee'].search([]).mapped('user_id.id')
        return [('groups_id', 'not in', self.env.ref('base.group_system').id), ('id', 'in', user_ids)]

    user_id = fields.Many2one('res.users', string='Pakviesti pasirašyti', domain=get_domain, required=True)
    document_upload_id = fields.Many2one('e.document.upload')


EDocumentUploadList()
