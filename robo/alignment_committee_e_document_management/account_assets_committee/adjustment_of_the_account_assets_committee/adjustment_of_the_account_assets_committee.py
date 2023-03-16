# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import _, models, api, fields, exceptions, tools

TEMPLATE = 'e_document.adjustment_of_the_account_assets_committee_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.onchange('alignment_committee_id')
    def _onchange_account_assets_committee_values(self):
        for rec in self.filtered(lambda t: t.template_id == self.env.ref(TEMPLATE, raise_if_not_found=False)):
            if not rec.alignment_committee_id:
                continue
            rec.date_from = rec.alignment_committee_id.date
            rec.date_to = rec.alignment_committee_id.date_to
            rec.int_2 = rec.alignment_committee_id.no_of_approve
            rec.department_id2 = rec.alignment_committee_id.department_id
            chairman = rec.alignment_committee_id.chairman_id
            rec.e_document_line_ids = [(5,)] + [
                (0, 0, {
                    'employee_id2': employee.id,
                    'committee_structure': 'chairman' if chairman.id == employee.id else 'member'
                }) for employee in rec.alignment_committee_id.mapped('employee_ids')
            ]
            rec.chairman_id = rec.alignment_committee_id.chairman_id

    @api.multi
    def execute_confirm_workflow(self):
        super(EDocument, self).execute_confirm_workflow()
        template = self.env.ref(TEMPLATE, raise_if_not_found=False)
        for rec in self.filtered(lambda t: t.template_id == template):
            document_lines = rec.get_document_lines()
            committee_users = rec.alignment_committee_id.mapped('employee_ids.user_id')
            document_lines_users = document_lines.mapped('employee_id2.user_id')
            chairman = document_lines.filtered(lambda l: l.committee_structure == 'chairman').mapped('employee_id2.user_id')

            signed_users_values = []
            for user in document_lines_users:
                if user == chairman or user not in committee_users:
                    signed_users_values.append((0, 0, {
                        'document_id': rec.id,
                        'user_id': user.id,
                    }))
            rec.write({'user_ids': [(5,)] + signed_users_values})

    @api.multi
    def execute_last_sign_workflow(self):
        self.ensure_one()
        template = self.env.ref(TEMPLATE, raise_if_not_found=False)
        not_signed_users = self.sudo().user_ids.filtered(lambda u: u.state != 'signed')
        if self.env.user.id in not_signed_users.mapped('user_id').ids and \
                len(not_signed_users) == 1 and not_signed_users.user_id.id == self.env.user.id and \
                self.template_id == template:
            document_lines = self.get_document_lines()
            chairman = document_lines.filtered(lambda e: e.committee_structure == 'chairman').employee_id2
            employee_ids = document_lines.mapped('employee_id2').ids
            name = _('Account assets committee')
            if self.department_id2:
                name += ' ({})'.format(self.department_id2.name)
            self.sudo().alignment_committee_id.write({
                'name': name,
                'no_of_approve': self.int_2,
                'chairman_id': chairman.id,
                'employee_ids': [(6, 0, employee_ids)],
                'department_id': self.department_id2.id or '',
            })
            self.write({
                'document_number': self.env['ir.sequence'].next_by_code('ISAKYMAS'),
            })
        else:
            super(EDocument, self).execute_last_sign_workflow()
