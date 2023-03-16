# -*- coding: utf-8 -*-


import uuid

from odoo import api, fields, models


class IrAttachmentDrop(models.Model):
    _name = 'ir.attachment.drop'

    def random_unique_code(self):
        return uuid.uuid4()

    unique_wizard_id = fields.Text(default=random_unique_code, store=False)
    user_attachment_ids = fields.Many2many('ir.attachment', compute='_compute_all_attachments', string='Prisegtukai',
                                           readonly=False)
    nbr_of_attachments = fields.Integer(compute='_compute_nbr_of_attachments')
    attachment_drop_lock = fields.Boolean(compute='_compute_attachment_drop_lock')

    @api.model
    def create(self, vals):
        wizard_id = vals.pop('unique_wizard_id', False)
        element = super(IrAttachmentDrop, self).create(vals)
        if wizard_id:
            wizards_records = self.env['ir.attachment.wizard'].search([('res_model', '=', self._name),
                                                                       ('wizard_id', '=', wizard_id)])
            if element and wizards_records:
                for rec in wizards_records:
                    new_vals = {
                        'name': rec['name'],
                        'datas': rec['datas'],
                        'datas_fname': rec['datas_fname'],
                        'res_model': self._name,
                        'res_id': element.id,
                        'type': rec['type'],
                    }
                    self.env['ir.attachment'].create(new_vals)
        return element

    @api.one
    def _compute_nbr_of_attachments(self):
        self.nbr_of_attachments = len(self.user_attachment_ids.ids)

    @api.one
    def _compute_all_attachments(self):
        if self.check_access_rights('read', raise_exception=False):
            ids = self.env['ir.attachment'].search([
                ('res_model', '=', self._name),
                ('res_id', '=', self.id),
                ('res_field', '=', False)
            ]).ids
            self.user_attachment_ids = [(4, doc_id) for doc_id in ids]
        else:
            self.user_attachment_ids = []

    @api.one
    def _compute_attachment_drop_lock(self):
        # condition for attachment_drop_lock
        self.attachment_drop_lock = True
        if self.check_access_rights('write', raise_exception=False):
            self.attachment_drop_lock = False
