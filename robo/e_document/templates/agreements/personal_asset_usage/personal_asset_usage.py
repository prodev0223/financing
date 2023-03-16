# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, api, exceptions, tools, _

TEMPLATE = 'e_document.personal_asset_usage_agreement_template'
CANCEL_TEMPLATE = 'e_document.isakymas_del_susitarimo_nutraukimo_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def create_periodic_employee_payment(self):
        self.ensure_one()
        date_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_from_dt = date_dt + relativedelta(day=1)
        date_from = date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_dt = date_dt + relativedelta(day=31)
        date_to = date_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_next_payment = (date_dt + relativedelta(months=1, day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        # Split payment amount in proportion of days in a month
        amount_base = self.float_1
        contract = self.employee_id2.contract_id
        number_of_days = contract.get_num_work_days(self.date_from, date_to) or (date_to_dt - date_dt).days + 1
        number_of_days_in_a_month = contract.get_num_work_days(date_from, date_to) or \
                                    (date_to_dt - date_from_dt).days + 1
        amount = amount_base * float(number_of_days) / float(number_of_days_in_a_month)  # P3:DivOK

        payment_values = {
            'state': 'ready',
            'description': _('Kompensacija už darbo priemonių naudojimą'),
            'employee_id': self.employee_id2.id,
            'partner_id': self.employee_id2.address_home_id.id,
            'date': date_to,
            'date_payment': date_to,
            'date_from': date_from,
            'date_to': date_to,
            'type': 'compensation',
            'amount_paid': amount,
            'amount_bruto': amount,
        }
        try:
            payment = self.env['hr.employee.payment'].create(payment_values)
            payment.onchange_type()
            payment.atlikti()

            periodic_payment = self.env['hr.employee.payment.periodic'].create({
                'payment_id': payment.id,
                'action': 'open',
                'date': date_next_payment,
                'amount_base': amount_base,
                'split_amount_in_proportion': True,
            })

            payment.write({
                'periodic_id': periodic_payment.id
            })

        except Exception:
            raise exceptions.UserError(_('Nepavyko sukurti periodinio kompensacijos mokėjimo įrašo. '
                                         'Kreipkitės į sistemos administratorių.'))
        return payment.periodic_id

    @api.multi
    def execute_last_sign_workflow(self):
        self.ensure_one()
        template = self.env.ref(TEMPLATE, False)
        not_signed_users = self.sudo().user_ids.filtered(lambda u: u.state != 'signed')
        if self.env.user.id in not_signed_users.mapped('user_id').ids and \
                len(not_signed_users) == 1 and not_signed_users.user_id.id == self.env.user.id and \
                self.template_id == template:
            periodic_payment = self.sudo().create_periodic_employee_payment()
            self.write({
                'record_model': 'hr.employee.payment.periodic',
                'record_id': periodic_payment.id
            })
        else:
            super(EDocument, self).execute_last_sign_workflow()

    @api.multi
    def execute_confirm_workflow(self):
        super(EDocument, self).execute_confirm_workflow()
        SignedUsers = self.env['signed.users'].sudo()
        template = self.env.ref(TEMPLATE, False)
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
            self.inform_users(users_to_sign)

    @api.one
    def execute_cancel_workflow(self):
        document_to_cancel = self.cancel_id
        if document_to_cancel and document_to_cancel.template_id == self.env.ref(TEMPLATE, False):
            record_model = document_to_cancel.record_model
            record_id = document_to_cancel.record_id
            periodic_payment = False
            if record_model == 'hr.employee.payment.periodic' and record_id:
                periodic_payment = self.env[record_model].browse(record_id).exists()
                if periodic_payment:
                    payment = periodic_payment.payment_id
                    date_dt = datetime.strptime(self.date_document, tools.DEFAULT_SERVER_DATE_FORMAT)
                    payment_template_date_dt = datetime.strptime(payment.date, tools.DEFAULT_SERVER_DATE_FORMAT)
                    # If document is cancelled on the same month, both payment and periodic payment should be deleted
                    same_month = date_dt.month == payment_template_date_dt.month
                    if same_month:
                        periodic_payment.unlink()
                        payment.atsaukti()
                        payment.unlink()
                    else:
                        date_next_payment = (date_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                        periodic_payment.write({
                            'date_stop': self.date_document,
                            'date': date_next_payment,
                        })

            if not periodic_payment:
                raise exceptions.Warning(_('Nerastas susijęs mokėjimas'))
        else:
            super(EDocument, self).execute_cancel_workflow()

    @api.multi
    def cancel_agreement(self):
        self.ensure_one()
        user = self.env.user
        if self.record_model != 'hr.employee.payment.periodic' or not self.record_id or not user.is_manager():
            raise exceptions.UserError(_('Negalima atšaukti susitarimo. Kreipkitės į sistemos administratorių.'))
        if self.document_type == 'agreement' and self.state == 'e_signed':
            template = self.env.ref(CANCEL_TEMPLATE, False)
            if template:
                user_employee = self.env['hr.employee'].search([('user_id', '=', user.id)], limit=1)
                date_to_sign = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                cancel_document = self.env['e.document'].create({
                    'template_id': template.id,
                    'document_type': 'isakymas',
                    'employee_id2': user_employee.id if user_employee else user.sudo().company_id.vadovas.id,
                    'cancel_id': self.id,
                    'date_4': date_to_sign,
                })

                ctx = dict(self._context)
                ctx['robo_header'] = {}
                return {
                    'name': _('eDokumentai'),
                    'type': 'ir.actions.act_window',
                    'view_type': 'form',
                    'view_mode': 'form',
                    'res_model': 'e.document',
                    'view_id': template.view_id.id,
                    'res_id': cancel_document.id,
                    'context': ctx,
                }


EDocument()
