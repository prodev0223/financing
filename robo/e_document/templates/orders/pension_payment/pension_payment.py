# -*- coding: utf-8 -*-
import logging

from odoo import models, api, fields, _, exceptions, tools

_logger = logging.getLogger(__name__)

PENSION_PAYMENT_ORDER_TEMPLATE = 'e_document.pension_payment_order_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    is_pension_payment_order = fields.Boolean(compute='_compute_is_pension_payment_order')

    @api.multi
    def _compute_is_pension_payment_order(self):
        pension_payment_order_template = self.env.ref(PENSION_PAYMENT_ORDER_TEMPLATE, False)
        for rec in self:
            rec.is_pension_payment_order = rec.template_id and rec.template_id == pension_payment_order_template

    @api.multi
    def execute_confirm_workflow_check_values(self):
        super(EDocument, self).execute_confirm_workflow_check_values()
        documents = self.filtered(lambda d: d.is_pension_payment_order and not d.sudo().skip_constraints_confirm)
        if documents:
            documents.perform_pension_payment_checks()

    @api.multi
    def perform_pension_payment_checks(self):
        self.ensure_one()

        company = self.env.user.company_id

        # Check if the payroll bank account journal is set
        payroll_bank_journal = company.payroll_bank_journal_id
        if not payroll_bank_journal:
            raise exceptions.ValidationError(
                _('Company payroll bank journal is not set. Please contact your accountant.')
            )

        # Check if the default accounts are in the system
        required_account_codes = ['4430', '63031']
        required_accounts = self.env['account.account'].sudo().search([('code', 'in', required_account_codes)])
        missing_account_codes = [c for c in required_account_codes if c not in required_accounts.mapped('code')]
        if missing_account_codes:
            raise exceptions.ValidationError(
                _('The following accounts are not configured properly: {}. Please contact your accountant.').format(
                    ', '.join(missing_account_codes)
                )
            )

        for rec in self:
            lines = rec.e_document_line_ids
            issues = ''
            if not lines:
                issues += _('No pension fund payment lines have been entered')
            for line in lines:
                if not line.pension_fund_id:
                    issues += _('The selected employee {} does not have an associated pension fund. Please set it in '
                                'the employee card').format(line.employee_id2.name)
                else:
                    pension_fund_issues = line.pension_fund_id.issues
                    if pension_fund_issues:
                        issues += _('The pension fund "{}" is not configured properly: {}').format(
                            line.pension_fund_id.name, pension_fund_issues
                        )
                if not line.employee_id2:
                    issues += _('Please specify the employee the payment is made for')
                elif tools.float_compare(line.float_1, 0.0, precision_digits=2) <= 0:
                    issues += _('Incorrect pension payment amount for employee {} entered').format(
                        line.employee_id2.name
                    )
            if issues:
                raise exceptions.ValidationError(issues)

    @api.multi
    def pension_payment_order_workflow(self):
        self.ensure_one()

        company = self.env.user.company_id
        journal = company.payroll_bank_journal_id

        record_model = 'pension.fund.transfer'

        self.write({'record_model': record_model})

        if not journal:
            _logger.info('Pension payment was not created for document {}'.format(self.id))
            return  # Don't create payments if journal is not set (constraints are skipped)

        PensionFundTransfer = self.env[record_model].sudo()
        pension_transfers = PensionFundTransfer

        for line in self.e_document_line_ids:
            employee = line.employee_id2
            amount = line.float_1
            pension_fund_id = line.pension_fund_id
            if not pension_fund_id or not pension_fund_id.partner_id:
                _logger.info('Pension fund transfer was not created for document {}'.format(self.id))
                continue  # Don't create payment if pension fund is not configured properly (constraints are skipped)

            pension_transfers |= PensionFundTransfer.create({
                'pension_fund_id': pension_fund_id.id,
                'amount': amount,
                'employee_id': employee.id,
                'payment_date': self.date_1,
                'transfer_purpose': _('{}, {}, pension payment for {}').format(
                    (company.name or str()).replace('&', '&amp;'), company.partner_id.kodas, employee.name
                ),
                'e_document_id': self.id,
            })
        pension_transfers.action_confirm()
        self.write({'record_ids': self.format_record_ids(pension_transfers.ids)})

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        document_to_be_cancelled = self.cancel_id
        if document_to_be_cancelled.is_pension_payment_order:
            transfer_ids = document_to_be_cancelled.parse_record_ids()
            transfers = self.env[document_to_be_cancelled.record_model].sudo().browse(transfer_ids).exists()
            transfers.action_cancel()
            transfers.unlink()
        else:
            return super(EDocument, self).execute_cancel_workflow()