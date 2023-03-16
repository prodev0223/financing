# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import _, models, api, fields, exceptions, tools

TEMPLATE = 'e_document.formation_of_the_account_assets_committee_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    compute_chairman = fields.Text(compute='_compute_chairman')

    @api.multi
    @api.depends('e_document_line_ids')
    def _compute_chairman(self):
        template_ids = self.get_account_assets_committee_formation_and_adjustment_template_ids()
        for rec in self.filtered(lambda t: t.template_id.id in template_ids):
            chairman = rec.e_document_line_ids.filtered(
                lambda x: x.committee_structure == 'chairman').mapped('employee_id2')
            if len(chairman) != 1:
                continue
            text = str(chairman.job_id.name) + ' ' + str(chairman.name)
            rec.compute_chairman = text

    @api.model
    def default_get(self, fields):
        res = super(EDocument, self).default_get(fields)
        template = self.env.ref(TEMPLATE, raise_if_not_found=False)
        if template and res.get('template_id') == template.id:
            res['int_2'] = 1
        return res

    @api.multi
    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        """
        Checks whether date_from is not greater than date_to
        """
        super(EDocument, self)._check_dates()
        template = self.env.ref(TEMPLATE, raise_if_not_found=False)
        for rec in self.filtered(lambda t: t.template_id == template):
            if not rec.date_to:
                continue
            date_from_dt = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            if date_to_dt <= date_from_dt:
                raise exceptions.ValidationError(
                    _('Date of entry into force of the Committee cannot be greater than Date of expiry of Committee')
                )

    @api.multi
    @api.constrains('int_2')
    def _check_number_of_votes_at_least_one(self):
        """
        Check that the number of votes in favor is at least 1
        """
        template_ids = self.get_account_assets_committee_formation_and_adjustment_template_ids()
        for rec in self.filtered(lambda t: t.template_id.id in template_ids):
            if rec.int_2 <= 0:
                raise exceptions.ValidationError(_('The number of votes in favor must be at least 1'))

    @api.multi
    @api.constrains('int_2')
    def _check_number_of_votes_in_favor_is_not_greater_than_number_of_members(self):
        """
        Checks whether the number of votes in favor is not greater than number of Members of the Committee
        """
        template_ids = self.get_account_assets_committee_formation_and_adjustment_template_ids()
        for rec in self.filtered(lambda t: t.template_id.id in template_ids):
            if rec.int_2 > len(rec.get_document_lines()):
                raise exceptions.ValidationError(
                    _('The number of votes in favor can\'t be greater than number of Members of the Committee'))

    @api.multi
    @api.constrains('e_document_line_ids')
    def _check_chairman_of_the_committee(self):
        """
        Checks whether Chairman of the Committee is in list and Chairman is only one
        """
        template_ids = self.get_account_assets_committee_formation_and_adjustment_template_ids()
        for rec in self.filtered(lambda t: t.template_id.id in template_ids):
            document_lines = rec.get_document_lines()
            number_of_chairmen = len(document_lines.filtered(lambda l: l.committee_structure == 'chairman'))

            if number_of_chairmen > 1:
                raise exceptions.ValidationError(
                    _('There must be only one Chairman of the Committee'))
            elif number_of_chairmen == 0:
                raise exceptions.ValidationError(
                    _('There must be one Chairman of the Committee'))

    @api.model
    def get_account_assets_committee_formation_and_adjustment_template_ids(self):
        templates = [
            'e_document.formation_of_the_account_assets_committee_template',
            'e_document.adjustment_of_the_account_assets_committee_template',
        ]
        template_ids = [self.env.ref(template, raise_if_not_found=False).id for template in templates]
        return template_ids

    @api.multi
    def execute_confirm_workflow_check_values(self):
        super(EDocument, self).execute_confirm_workflow_check_values()
        template_ids = self.get_account_assets_committee_formation_and_adjustment_template_ids()
        for rec in self.filtered(lambda t: t.template_id.id in template_ids):
            document_lines = rec.get_document_lines()
            employees_not_users = []
            employees_list = []
            duplicate_users_list = []
            for line in document_lines:
                user_id = line.employee_id2.user_id
                if line.employee_id2.name in employees_list:
                    user_id = line.employee_id2.user_id
                    duplicate_users_list.append(str(line.employee_id2.name))

                employees_list.append(line.employee_id2.name)
                if not user_id:
                    employees_not_users.append(str(line.employee_id2.name))

            if employees_not_users:
                raise exceptions.ValidationError(
                    _('These employees are not users:\n{}').format('\n'.join(employees_not_users)))

            if duplicate_users_list:
                raise exceptions.ValidationError(
                    _('These users are duplicated in the list:\n{}').format('\n'.join(duplicate_users_list)))

    @api.multi
    def execute_confirm_workflow(self):
        super(EDocument, self).execute_confirm_workflow()
        template = self.env.ref(TEMPLATE, raise_if_not_found=False)
        for rec in self.filtered(lambda t: t.template_id == template):
            document_lines = rec.get_document_lines()
            for line in document_lines:
                user_id = line.employee_id2.user_id
                vals = {
                    'document_id': rec.id,
                    'user_id': user_id.id,
                }
                self.env['signed.users'].sudo().create(vals)

    @api.multi
    def set_draft(self):
        super(EDocument, self).set_draft()
        template_ids = self.get_account_assets_committee_formation_and_adjustment_template_ids()
        for rec in self.filtered(lambda t: t.template_id.id in template_ids):
            if not rec.env.user.is_premium_manager():
                raise exceptions.AccessError(_('Only managers can perform this action'))
            elif rec.env.user.is_premium_manager and rec.sudo().user_ids.filtered(lambda u: u.state == 'signed'):
                raise exceptions.AccessError(
                    _('The document has already been signed by at least one member of the committee')
                )
            rec.user_ids.sudo().unlink()

    @api.multi
    def execute_first_sign_workflow(self):
        super(EDocument, self).execute_first_sign_workflow()
        template_ids = self.get_account_assets_committee_formation_and_adjustment_template_ids()
        for rec in self.filtered(lambda t: t.template_id.id in template_ids):
            users = rec.get_document_lines().mapped('employee_id2.user_id')
            rec.inform_users(users)

    @api.multi
    def execute_last_sign_workflow(self):
        self.ensure_one()
        template = self.env.ref(TEMPLATE, raise_if_not_found=False)
        not_signed_users = self.sudo().user_ids.filtered(lambda u: u.state != 'signed')
        if self.env.user.id in not_signed_users.mapped('user_id').ids and \
                len(not_signed_users) == 1 and not_signed_users.user_id.id == self.env.user.id and \
                self.template_id == template:
            self.sudo().create_account_assets_committee()
            self.write({
                'document_number': self.env['ir.sequence'].next_by_code('ISAKYMAS'),
            })
        else:
            super(EDocument, self).execute_last_sign_workflow()

    @api.multi
    def create_account_assets_committee(self):
        self.ensure_one()
        name = _('Account assets committee {}').format(
            '(' + self.department_id2.name + ')' if self.department_id2 else ''
        )
        employee_ids = self.e_document_line_ids.mapped('employee_id2').ids
        chairman = self.e_document_line_ids.filtered(lambda e: e.committee_structure == 'chairman').employee_id2
        values = {
            'name': name,
            'company_id': self.company_id.id,
            'date': self.date_from,
            'type': 'asset',
            'no_of_approve': self.int_2,
            'employee_ids': [(6, 0, employee_ids)],
            'chairman_id': chairman.id,
        }
        if self.date_to:
            values.update({
                'date_to': self.date_to,
            })
        if self.department_id2:
            values.update({
                'department_id': self.department_id2.id,
            })
        committee = self.env['alignment.committee'].create(values)
        committee.validate()

    @api.multi
    def cancel_order(self):
        super(EDocument, self).cancel_order()
        template_ids = self.get_account_assets_committee_formation_and_adjustment_template_ids()
        for rec in self.filtered(lambda t: t.template_id.id in template_ids):
            is_manager = rec.env.user.is_manager() or rec.env.user.has_group('robo_basic.group_robo_edocument_manager')
            if not is_manager:
                raise exceptions.ValidationError(
                    _('Only a manager can cancel this document.'))
            if rec.state == 'e_signed':
                raise exceptions.ValidationError(
                    _('The document has already been signed by all members, to cancel a document, you must sign the '
                      '"Įsakymas dėl ilgalaikio turto įvedimo į eksploataciją komisijos likvidavimo" document'))
            elif rec.state == 'confirm':
                rec.user_ids.sudo().unlink()
                rec.write({
                    'cancel_uid': rec.env.uid,
                    'state': 'cancel',
                })


EDocument()


class EDocumentLine(models.Model):
    _inherit = 'e.document.line'

    committee_structure = fields.Selection(selection=[('chairman', 'Chairman of the Committee'),
                                                      ('member', 'Member of the Committee'),
                                                      ], string='Committee structure', default='member')


EDocumentLine()
