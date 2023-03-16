# -*- coding: utf-8 -*-

from odoo import models, api, exceptions, _

TEMPLATE = 'e_document.kuro_nurasymo_aktas_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def kuro_nurasymo_aktas_workflow(self):
        self.ensure_one()

        existing_doc = self.env['e.document'].search_count([
            ('date_1', '=', self.date_1),
            ('state', '=', 'e_signed'),
            ('template_id', '=', self.template_id.id)
        ])

        if existing_doc:
            raise exceptions.UserError(_('Nurodytai datai jau egzistuoja aktas'))
        pass

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        if self.template_id == self.env.ref(TEMPLATE):
            raise exceptions.UserError(_('Kuro nurašymo akto panaikinti negalima'))
        else:
            return super(EDocument, self).execute_cancel_workflow()


EDocument()
