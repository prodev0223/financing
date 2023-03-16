# -*- coding: utf-8 -*-

from odoo import models, api, fields, _, exceptions, tools


class EDocument(models.Model):
    _inherit = 'e.document'

    additional_remote_work_compensation = fields.Selection([
            ('based_on_documents', 'Compensate based on submitted documents'),
            ('specific_amount', 'Compensate specific amount'),
            ('not_compensated', 'Remote work is not compensated'),
        ],
        default='based_on_documents',
        string='Remote work compensation',
        readonly=True,
        states={'draft': [('readonly', False)]},
        inverse='set_final_document'
    )

    @api.multi
    def execute_confirm_workflow_check_values(self):
        super(EDocument, self).execute_confirm_workflow_check_values()
        template = self.get_remote_work_agreement_template()
        for rec in self.filtered(lambda d: d.template_id == template):
            if rec.date_to and rec.date_to < rec.date_from:
                raise exceptions.UserError(_('Date to has to be a later or the same date as date from'))
            compensation_is_set = tools.float_compare(rec.float_1, 0.0, precision_digits=2) > 0
            if rec.additional_remote_work_compensation == 'specific_amount' and not compensation_is_set:
                raise exceptions.UserError(_('Incorrect compensation amount'))

    @api.multi
    def execute_confirm_workflow(self):
        super(EDocument, self).execute_confirm_workflow()
        SignedUsers = self.env['signed.users'].sudo()
        template = self.get_remote_work_agreement_template()
        for rec in self.filtered(lambda d: d.template_id.id == template.id):
            users_to_sign = rec.employee_id2.sudo().user_id
            manager = self.env.user.sudo().company_id.vadovas.user_id
            if manager:
                users_to_sign |= manager
            users_to_sign = users_to_sign.filtered(lambda x: x.active)

            for user in users_to_sign:
                SignedUsers.create({
                    'document_id': rec.id,
                    'user_id': user.id,
                })

            users_ids_not_to_inform = self._context.get('users_ids_not_to_inform', [])
            self.inform_users(users_to_sign.filtered(lambda u: u.id not in users_ids_not_to_inform))

    @api.multi
    def check_workflow_constraints(self):
        body = super(EDocument, self).check_workflow_constraints()
        template = self.get_remote_work_agreement_template()
        for rec in self.filtered(lambda d: d.template_id == template):
            contract = self.env['hr.contract'].search([
                ('employee_id', '=', rec.employee_id2.id),
                ('date_start', '<=', rec.date_from),
                '|',
                ('date_end', '>=', rec.date_to),
                ('date_end', '=', False)
            ])
            if not contract:
                body += _('Can not set that the employee {} will be working remotely from {} to {} because the '
                          'employee does not have an active contract for that date').format(rec.employee_id2.name,
                                                                                            rec.date_from, rec.date_to)
        return body

    @api.multi
    def set_draft(self):
        super(EDocument, self).set_draft()
        template = self.get_remote_work_agreement_template()
        for rec in self.filtered(lambda d: d.template_id == template):
            rec.user_ids.sudo().unlink()

    @api.model
    def get_remote_work_agreement_template(self):
        return self.env.ref('e_document.remote_work_agreement_template', raise_if_not_found=False)

    @api.multi
    def execute_last_sign_workflow(self):
        self.ensure_one()
        not_signed_users = self.sudo().user_ids.filtered(lambda u: u.state != 'signed')
        if self.env.user.id in not_signed_users.mapped('user_id').ids and \
                len(not_signed_users) == 1 and not_signed_users.user_id.id == self.env.user.id and \
                self.template_id == self.get_remote_work_agreement_template():
            self.sudo().create_remote_work_appointments()
        else:
            super(EDocument, self).execute_last_sign_workflow()

    @api.multi
    def create_remote_work_appointments(self, working_remotely=True):
        self.ensure_one()
        if self.template_id == self.get_remote_work_agreement_template():
            contract = self.employee_id2.with_context(date=self.date_from).contract_id
            if not contract:
                raise exceptions.UserError(_('Employee contract could not be found for {} for '
                                             'date {}').format(self.employee_id2.name, self.date_from))
            contract.toggle_remote_work(date_from=self.date_from, date_to=self.date_to,
                                        working_remotely=working_remotely)

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        if self.cancel_id and self.cancel_id.template_id == self.get_remote_work_agreement_template():
            try:
                self.cancel_id.create_remote_work_appointments(working_remotely=False)
            except Exception as e:
                try:
                    body = "Buvo atšauktas įsakymas dėl nuotolinio darbo. Peržiūrėkite sutarties pakeitimus ir " \
                           "atlikite atitinkamas korekcijas"
                    self.cancel_id.create_internal_ticket("Atšauktas įsakymas dėl nuotolinio darbo", body)
                except Exception as exc:
                    self._create_cancel_workflow_failed_ticket_creation_bug(self.id, exc)
        else:
            super(EDocument, self).execute_cancel_workflow()


EDocument()
