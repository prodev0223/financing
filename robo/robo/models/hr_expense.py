# -*- coding: utf-8 -*-
import uuid

from odoo import api, fields, models


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    def random_unique_code(self):
        return uuid.uuid4()

    unique_wizard_id = fields.Text(default=random_unique_code, store=False)
    user_attachment_ids = fields.Many2many('ir.attachment', compute='_compute_all_attachments', string='Prisegtukai',
                                           readonly=False)
    nbr_of_attachments = fields.Integer(compute='_compute_nbr_of_attachments')
    attachment_drop_lock = fields.Boolean(compute='_compute_attachment_drop_lock')

    @api.one
    @api.depends('state')
    def _compute_attachment_drop_lock(self):
        self.attachment_drop_lock = False
        if self.state != 'draft':
            self.attachment_drop_lock = True

    @api.model
    def create(self, vals):
        wizard_id = vals.pop('unique_wizard_id', False)
        expense = super(HrExpense, self).create(vals)
        if wizard_id:
            wizards_records = self.env['ir.attachment.wizard'].search([('res_model', '=', 'hr.expense'),
                                                                       ('wizard_id', '=', wizard_id)])
            if expense and wizards_records:
                for rec in wizards_records:
                    new_vals = {
                        'name': rec['name'],
                        'datas': rec['datas'],
                        'datas_fname': rec['datas_fname'],
                        'res_model': 'hr.expense',
                        'res_id': expense.id,
                        'type': rec['type'],
                    }
                    self.env['ir.attachment'].create(new_vals)
        return expense

    @api.one
    def _compute_all_attachments(self):
        # ROBO: by default ref_field = False
        ids = self.env['ir.attachment'].search([('res_model', '=', 'hr.expense'),
                                                ('res_id', '=', self.id),
                                                ('res_field', '=', False)]).ids

        # old structure support: showing attachments with res_field not empty (added previously through model field)
        # maybe we should clean db by cleaning res_field for res_model l= account.invoice or hr.expense
        ids_field = self.env['ir.attachment'].search([('res_model', '=', 'hr.expense'),
                                                      ('res_id', '=', self.id),
                                                      ('res_field', '!=', False)]).ids
        ids = set(ids + ids_field)
        self.user_attachment_ids = [(4, doc_id) for doc_id in ids]

    @api.one
    def _compute_nbr_of_attachments(self):
        self.nbr_of_attachments = len(self.user_attachment_ids.ids)
