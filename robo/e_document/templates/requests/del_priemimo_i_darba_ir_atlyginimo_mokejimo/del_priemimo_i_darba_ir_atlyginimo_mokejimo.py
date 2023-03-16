# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, models, fields
from odoo.addons.base_iban.models.res_partner_bank import validate_iban


TEMPLATE = 'e_document.prasymas_del_priemimo_i_darba_ir_atlyginimo_mokejimo_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    contract_priority = fields.Selection([('foremost', 'Foremost'), ('secondary', 'Secondary')],
                                         string='Contract Priority', default='foremost', inverse='set_final_document',
                                         readonly=True, states={'draft': [('readonly', False)]})

    @api.multi
    def prasymas_del_priemimo_i_darba_ir_atlyginimo_mokejimo_workflow(self):
        self.ensure_one()
        if self.text_4:
            partner_id = self.employee_id1.address_home_id
            bank_account_id = self.env['res.partner.bank'].create({
                'acc_number': self.text_4,
                'partner_id': partner_id.id or False,
            })
            bank_account_id.onchange_acc_number()
            self.employee_id1.write({'bank_account_id': bank_account_id.id})

        employee_vals = {
            'sodra_papildomai': self.selection_bool_1 == 'true',
            'sodra_papildomai_type': self.sodra_papildomai_type,
        }
        is_disabled = self.selection_bool_2 == 'true'
        employee_vals.update(invalidumas=is_disabled)
        if is_disabled and self.selection_nedarbingumas in ['0_25', '30_55']:
            darbingumas_id = self.env.ref('l10n_lt_payroll.' + self.selection_nedarbingumas).id
            employee_vals.update(darbingumas=darbingumas_id)
        self.employee_id1.write(employee_vals)

        appointment = self.env['hr.contract.appointment'].search([
            ('employee_id', '=', self.employee_id1.id),
            ('date_start', '=', self.date_1)
        ])
        if len(appointment) == 1:
            appointment.write({
                # 'sodra_papildomai': self.selection_bool_1 == 'true',
                # 'sodra_papildomai_type': self.sodra_papildomai_type,
                'use_npd': self.selection_bool_3 == 'true',
                'contract_priority': self.contract_priority or 'foremost',
            })

        if is_disabled:
            subject = _('Limited capacity for work has been marked on employment request')
            body = _('''Employee {0} marked having limited capacity for work on employment request. Do not forget 
            to examine, attach supporting documents to the employee card.''').format(self.employee_id1.name,
                                                                                     self.document_number)
            self.env['e.document'].message_post_to_mail_channel(
                subject, body, 'e_document.inform_about_limited_capacity_of_work_documents'
            )

    @api.multi
    def check_workflow_constraints(self):
        res = super(EDocument, self).check_workflow_constraints()
        request_template = self.env.ref(TEMPLATE)
        for rec in self.filtered(lambda t: t.template_id == request_template):
            # Check if at least a single request has been signed for the contract already
            contract = rec.employee_id1.with_context(date=rec.date_1, strict_date_check=True).contract_id
            if not contract:
                res += _('Nurodytam laikotarpiui neegzistuoja aktyvus darbuotojo kontraktas')
            domain = [
                ('template_id', '=', request_template.id),
                ('employee_id1', '=', rec.employee_id1.id),
                ('state', '=', 'e_signed'),
                ('date_1', '>=', contract.date_start),
            ]
            if contract.date_end:
                domain.append(('date_1', '<=', contract.date_end))
            existing_request_document = self.search(domain)
            if existing_request_document:
                res += _('There is already a signed request for the work relation. Please leave a note for Your '
                         'accountant if You wish to provide different information than already provided')
        return res

    @api.onchange('employee_id1')
    def _onchange_employee_id1(self):
        template = self.env.ref(TEMPLATE)
        if self.template_id == template and self.env.user == self.employee_id1.user_id:
            self.text_4 = self.employee_id1.sudo().bank_account_id.acc_number or False

    @api.multi
    @api.constrains('text_4')
    def check_iban(self):
        for rec in self.filtered(lambda x: x.text_4):
            if rec.template_id == self.env.ref(TEMPLATE):
                validate_iban(rec.text_4)

    @api.model
    def default_get(self, fields):
        """
        Default get override to fetch bank account number from current employee object.
        Used for this template only.
        """
        res = super(EDocument, self).default_get(fields)
        template_id = self.sudo().env.ref(
            'e_document.' + self._context.get('rec_template_id', str()), raise_if_not_found=False)
        if template_id and template_id == self.env.ref(TEMPLATE) and self.env.user.employee_ids:
            res['text_4'] = self.env.user.employee_ids[0].bank_account_id.acc_number
        return res

    @api.multi
    def get_required_form_fields(self):
        """Overridden method, returns required fields for this template form view"""
        self.ensure_one()
        res = super(EDocument, self).get_required_form_fields()

        # If current template matches this eDoc, update the list
        if self.template_id == self.env.ref(TEMPLATE):
            res.update({
                'text_4': _('Banko sąskaitos Nr.')
            })
        return res

    @api.model
    def cron_inform_about_unsigned_documents(self):
        documents = self.env['e.document'].search([('state', 'in', ['draft', 'confirm']),
                                                   ('template_id', '=', self.env.ref(TEMPLATE).id)])
        if documents:
            body = _('''
                Turite nepasirašytų prašymų dėl priėmimo į darbą. Jie nepasirašyti šiems asmenims:
            ''')
            body += ', '.join(documents.mapped('employee_id1.name')) + '.'
            subject = _('Nepasirašyti priėmimo į darbą prašymai')
            msg = {
                'body': body,
                'subject': subject,
                'message_type': 'comment',
                'subtype': 'mail.mt_comment'
            }
            channel = self.env.ref('e_document.unsigned_prasymas_del_priemimo_i_darba_ir_atlyginimo_mokejimo_mail_channel', False)
            if channel:
                channel.sudo().message_post(**msg)
            else:
                raise exceptions.UserError('Mail channel is missing')


EDocument()
