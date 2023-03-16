# -*- coding: utf-8 -*-


from odoo import api, fields, models


class IrAttachmentWizard(models.TransientModel):
    _name = 'ir.attachment.wizard'
    _inherit = 'ir.attachment'

    wizard_id = fields.Text()

    @api.model
    def get_query(self):
        """When ir.attachment model is inherited, the model for access check is changed to ir.attachment.wizard
        :return: Query for access check
        """
        return 'SELECT res_model, res_id, create_uid, public FROM ir_attachment_wizard WHERE id IN %s'
