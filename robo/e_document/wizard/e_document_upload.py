# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models


class EDocumentUpload(models.TransientModel):
    _name = 'e.document.upload'
    _inherit = 'ir.attachment.drop'

    @api.model
    def get_domain(self):
        user_ids = self.env['hr.employee'].search([]).mapped('user_id.id')
        return [('groups_id', 'not in', self.env.ref('base.group_system').id), ('id', 'in', user_ids)]

    @api.model
    def get_items(self):
        users = self.env['hr.employee'].search([]).mapped('user_id').filtered(
            lambda u: not u.has_group('base.group_system') and u.active)
        items = []
        for user in users:
            item = self.env['e.document.upload.item'].create(
                {'user_id': user.id, 'document_upload_id': self.id})
            items.append((4, item.id))
        return items

    user_items = fields.One2many('e.document.upload.item', 'document_upload_id', default=get_items)
    user_ids = fields.Many2many('res.users', compute='_get_users')
    topic = fields.Char(string='Tema')
    invite_to_sign_new_users = fields.Boolean(string='Kviesti pasirašyti naujus darbuotojus', default=False)

    @api.multi
    def delete_employees(self):
        self.ensure_one()
        self.user_items.unlink()
        self._get_users()

    @api.one
    @api.depends('user_items.user_id')
    def _get_users(self):
        admins = self.env['res.users'].search(
            [('groups_id', 'in', self.env.ref('robo_basic.group_robo_premium_accountant').id)])
        user_employee = self.env['hr.employee'].search([('user_id', '=', self.env.user.id)], limit=1)
        users = self.mapped('user_items.user_id') | admins
        if not user_employee:
            users |= self.env.user
        self.user_ids = users.ids

    @api.multi
    def confirm(self):
        self.ensure_one()
        if self.nbr_of_attachments == 0:
            raise exceptions.UserError(_('Prisekite bent vieną dokumentą!'))
        if not self.user_items:
            raise exceptions.UserError(_('Pasirinkite bent vieną darbuotoją'))
        ids = []
        view_id = self.env.ref('e_document.general_document_view').id
        for attach in self.user_attachment_ids:
            doc_name = attach.display_name[:-4]
            if 'pdf' not in attach.mimetype:
                raise exceptions.UserError(_('Galite pakviesti pasirašyti tik PDF formato dokumentus.'))
            e_doc_vals = {'name_force': doc_name,
                          'generated_document': attach.datas,
                          'force_view_id': view_id,
                          'file_name': attach.display_name,
                          'document_type': 'isakymas',
                          'no_mark': False,
                          'uploaded_document': True,
                          'topic': self.topic or attach.display_name,
                          'invite_to_sign_new_users': self.invite_to_sign_new_users}
            new_record = self.env['e.document'].create(e_doc_vals)
            if self.user_items:
                for rec in self.user_items:
                    self.sudo().env['signed.users'].create({
                        'document_id': new_record.id,
                        'user_id': rec.user_id.id,
                    })
            new_record.confirm()
            # inform users
            if self.user_items:
                users = self.user_items.mapped('user_id')
                new_record.inform_users(users)
            ids.append(new_record.id)
        domain = [('id', 'in', ids)]
        action = self.env.ref('e_document.e_document_action_badge2').read()[0]
        action['domain'] = domain
        return action

    @api.multi
    def name_get(self):
        return [(record.id, _('Dokumentų įkėlimas')) for record in self]

    @api.model
    def create(self, vals):
        doc_upl = super(EDocumentUpload, self).create(vals)
        wizard_id = vals.pop('unique_wizard_id', False)
        if wizard_id and doc_upl:
            wizards_records = self.env['ir.attachment.wizard'].search(
                [('res_model', '=', 'e.document.upload'), ('wizard_id', '=', wizard_id)])
            if wizards_records:
                for rec in wizards_records:
                    new_vals = {
                        'name': rec['name'],
                        'datas': rec['datas'],
                        'datas_fname': rec['datas_fname'],
                        'res_model': 'e.document.upload',
                        'res_id': doc_upl.id,
                        'type': rec['type'],
                    }
                    self.env['ir.attachment'].create(new_vals)
        return doc_upl


EDocumentUpload()
