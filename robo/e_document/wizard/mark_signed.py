# coding=utf-8
from odoo import _, exceptions, fields, models, tools
import base64


class MarkSigned(models.TransientModel):
    _name = 'e_document.mark_signed'

    e_document_id = fields.Many2one('e.document', 'Dokumentas', required=True, ondelete='cascade')
    document = fields.Binary('Pasirašytas dokumentas')
    document_filename = fields.Char('Document filename')

    def mark_signed(self):
        if not self.document:
            raise exceptions.UserError(_('Neprisegtas pasirašytas dokumentas'))
        self.e_document_id.mark_signed()
        self.sudo().e_document_id.attached_signed_document = self.document
        self.sudo().e_document_id.attached_signed_document_filename = self.document_filename
        mimetype = tools.mimetypes.guess_mimetype(base64.b64decode(self.document))
        if mimetype == 'application/pdf':
            self.sudo().e_document_id.generated_document = self.document
        return True


MarkSigned()
