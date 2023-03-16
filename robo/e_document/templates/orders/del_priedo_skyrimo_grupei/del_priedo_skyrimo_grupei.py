# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, api, tools, exceptions, _, fields


TEMPLATE = 'e_document.isakymas_del_priedo_skyrimo_grupei_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    show_accumulative_work_time_accounting_net_bonus_constraint_warning = fields.Boolean(
        compute='_compute_show_accumulative_work_time_accounting_net_bonus_constraint_warning'
    )

    @api.multi
    @api.depends(lambda self: self._get_accumulative_work_time_accounting_net_bonus_warning_dependencies())
    def _compute_show_accumulative_work_time_accounting_net_bonus_constraint_warning(self):
        prevent_signing = not self.env.user.sudo().company_id.allow_accumulative_work_time_accounting_net_bonus_orders
        if not prevent_signing:
            return
        templates = [
            self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template'),
            self.env.ref('e_document.isakymas_del_periodinio_priedo_skyrimo_template'),
            self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_pagal_darbo_laika_template'),
        ]
        applicable_documents = self.filtered(
                lambda x: x.template_id in templates and x.bonus_input_type == 'neto' and not x.sudo().skip_constraints
        )
        for rec in applicable_documents:
            rec.show_accumulative_work_time_accounting_net_bonus_constraint_warning = \
                bool(rec._find_employees_working_by_accumulative_work_time_accounting())

    @api.model
    def _get_accumulative_work_time_accounting_net_bonus_warning_dependencies(self):
        return ['template_id', 'e_document_line_ids.employee_id2', 'bonus_input_type', 'date_3', 'skip_constraints']

    @api.multi
    def _get_employees_for_bonuses(self):
        return self.mapped('e_document_line_ids.employee_id2')

    @api.multi
    def _find_employees_working_by_accumulative_work_time_accounting(self):
        """
        Finds employees working by accumulative work time accounting based on the payment dates of the document.
        """
        self.ensure_one()
        dates = self._get_bonus_payment_dates()
        employee_obj = self.env['hr.employee']
        if not dates or any(not date for date in dates):
            return employee_obj
        employees = self._get_employees_for_bonuses()
        if not employees:
            return employee_obj
        date_from, date_to = dates
        return self.env['hr.contract.appointment'].sudo().search([
            ('employee_id', 'in', employees.ids),
            ('use_npd', '=', True),
            ('schedule_template_id.template_type', '=', 'sumine'),
            ('date_start', '<=', date_to),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', date_from),
        ]).mapped('employee_id')

    @api.multi
    def _get_bonus_payment_dates(self):
        self.ensure_one()
        if not self.date_3:
            return False, False
        date_from_dt = datetime.strptime(self.date_3, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_from = (date_from_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = (date_from_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        return date_from, date_to

    @api.multi
    def isakymas_del_priedo_skyrimo_grupei_workflow(self):
        self.ensure_one()
        lines = self.e_document_line_ids
        payment_date_from, payment_date_to = self._get_bonus_payment_dates()
        bonuses = self.env['hr.employee.bonus']
        employees_ids = lines.mapped('employee_id2').ids
        for line in lines:
            bonus_rec = self.env['hr.employee.bonus'].create({
                'employee_id': line.employee_id2.id,
                'for_date_from': self.date_1,
                'for_date_to': self.date_2,
                'payment_date_from': payment_date_from,
                'payment_date_to': payment_date_to,
                'bonus_type': self.bonus_type_selection,
                'amount': line.float_1,
                'amount_type': self.bonus_input_type,
                'related_document': self.id,
            })
            bonus_rec.confirm()
            bonuses += bonus_rec
        self.write({
            'record_model': 'hr.employee.bonus',
            'record_ids': self.format_record_ids(bonuses.ids),
        })

        self.inform_about_payslips_that_need_to_be_recomputed(employees_ids, payment_date_from, payment_date_to)

    @api.multi
    def execute_confirm_workflow_check_values(self):
        super(EDocument, self).execute_confirm_workflow_check_values()
        template = self.env.ref(TEMPLATE)
        for rec in self.filtered(lambda d: d.template_id == template):
            exception = rec._check_bonus_document_lines()
            if exception:
                raise exceptions.ValidationError(exception)

    @api.multi
    def check_workflow_constraints(self):
        res = super(EDocument, self).check_workflow_constraints()
        for rec in self.filtered(lambda d: d.template_id == self.env.ref(TEMPLATE)):
            res += rec._check_bonus_document_lines()
            res += rec.check_bonus_type_accumulative_accounting_constraints()
        return res

    @api.multi
    def check_bonus_type_accumulative_accounting_constraints(self):
        """
        Checks if company parameter prevents from signing orders with NET bonus input type for accumulative work time
        accounting.
        """
        self.ensure_one()
        msg = ''
        if self.bonus_input_type != 'neto' or \
                self.env.user.sudo().company_id.allow_accumulative_work_time_accounting_net_bonus_orders:
            return msg
        employees = self._find_employees_working_by_accumulative_work_time_accounting()
        if not employees:
            return msg
        return _('Signing bonus orders with NET bonus amount type for people working in accordance to accumulative '
                 'work time accounting structure is currently disabled. Please specify the GROSS amount or contact '
                 'your accountant to enable this option. This constraint applies to the following employees: {}'
                 ).format(', '.join(employees.mapped('name')))

    @api.multi
    def _check_bonus_document_lines(self):
        self.ensure_one()
        for line in self.get_document_lines():
            if tools.float_is_zero(line.float_1, precision_digits=2):  # todo: or currency precision ?
                return _('Priedo dydis (bruto) negali būti nulinis!')
            if not line.employee_id2.contract_id:
                return _('Employee {} has no contract, therefore can not get a bonus').format(
                    line.employee_id2.name_related)
        return ''

    @api.multi
    def confirm(self):
        template = self.env.ref(TEMPLATE, raise_if_not_found=False)
        for rec in self.filtered(lambda document: document.template_id == template):
            document_lines = rec.get_document_lines()
            if len(document_lines) == 1:
                rec.write({'name': 'Įsakymas dėl priedo skyrimo'})
            else:
                rec.write({'name': 'Įsakymas dėl priedo skyrimo grupei'})
        return super(EDocument, self).confirm()

    @api.multi
    def get_document_lines(self):
        """
        Method meant to be overridden
        :return: e.document.line records
        """
        self.ensure_one()
        return self.e_document_line_ids

    @api.model
    def inform_about_payslips_that_need_to_be_recomputed(self, employees_ids, payment_date_from, payment_date_to):
        return  # Disable for now. Payslips should be recomputed automatically when bonus record is confirmed.
        payslips = self.env['hr.payslip'].sudo().search([
            ('employee_id', 'in', employees_ids),
            ('date_from', '<=', payment_date_to),
            ('date_to', '>=', payment_date_from),
        ])
        if not payslips:
            return
        subject = _('A new bonus order has been signed, but a payslip already exists')
        body = _("""
        A new bonus document has been signed but the system found payslips for the following employees: {}. 
        Please ensure that the payslips include the newly formed bonus amounts
        """).format(', '.join(payslips.mapped('employee_id.name')))

        self.create_internal_ticket(subject, body)


EDocument()
