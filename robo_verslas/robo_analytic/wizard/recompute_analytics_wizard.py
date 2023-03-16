# -*- coding: utf-8 -*-
import logging
from odoo import _, api, exceptions, fields, models, tools


_logger = logging.getLogger(__name__)


class RecomputeAnalyticsWizard(models.TransientModel):
    _name = 'recompute.analytics.wizard'

    employee_id = fields.Many2one('hr.employee', string='Employee')
    date_from = fields.Date(string='Date from')
    date_to = fields.Date(string='Date to')
    records_to_recompute = fields.Selection([
        ('account_move', 'Analytics of income and expenses'),
        ('invoice', 'Analytics of all invoices'),
        ('payslip', 'Analytics of payslips and payslip batches'),
        ('holiday_reserve', 'Analytics of holiday reserve'),
    ], string='Records to recompute',)
    is_analytics_recompute_for_single_employee = fields.Boolean(string="Single employee")
    description = fields.Html(translate=True, compute='_compute_record_description_html')

    @api.multi
    def recompute_analytics_account_move_line(self):
        self.ensure_one()
        self.check_constraints(is_account_move_line=True)
        company = self.env.user.sudo().company_id
        analytic_id = company.analytic_account_id.id
        AnalyticDefault = self.env['account.analytic.default']

        accounts_to_exclude_ids = AnalyticDefault.get_account_ids_to_exclude()
        move_lines = self.env['account.move.line'].search([
            ('account_id', 'not in', accounts_to_exclude_ids),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('invoice_id', '=', False),
            '|',
            ('account_id.code', '=like', '5%'),
            ('account_id.code', '=like', '6%'),
        ])
        for line in move_lines:
            analytic_default = AnalyticDefault.account_get(
                partner_id=line.partner_id.id,
                company_id=line.move_id.company_id.id,
                journal_id=line.journal_id.id,
                account_id=line.account_id.id,
                product_id=line.product_id.id,
                date=line.date)

            # Always apply analytic default set in company settings if analytic rule is not found
            # This behavior is replicated when posting account move
            analytic_account_to_set = analytic_default.analytic_id.id or analytic_id
            if analytic_account_to_set:
                line.write({'analytic_account_id': analytic_default.analytic_id.id or analytic_id})
                line.create_analytic_lines()

    @api.multi
    def recompute_analytics_invoices(self):
        self.ensure_one()
        self.check_constraints()

        invoice_lines = self.env['account.invoice.line'].search([
            ('invoice_id.date_invoice', '>=', self.date_from),
            ('invoice_id.date_invoice', '<=', self.date_to),
        ])
        for invoice_line in invoice_lines:
            analytic_default = invoice_line.get_default_analytic_account()
            if analytic_default:
                vals = {
                    'invoice_line_id': invoice_line.id,
                    'old_analytic_id': invoice_line.account_analytic_id.id,
                    'analytic_id': analytic_default.analytic_id.id,
                    'name': invoice_line.name,
                    'qty': invoice_line.quantity,
                    'amount': invoice_line.price_subtotal,
                    'currency_id': invoice_line.currency_id.id,
                    'sequence': invoice_line.sequence,
                }
                wizard = self.env['invoice.analytic.wizard.line'].create(vals)
                try:
                    wizard.change_analytics()
                except Exception as e:
                    _logger.info('Error while changing analytics on invoice line %s. Exception: %s', invoice_line.id, tools.ustr(e))
                    raise exceptions.UserError(_('Kreipkitės į sistemos administratorių'))

    @api.multi
    def recompute_analytics_payslips(self):
        self.ensure_one()
        self.check_constraints()

        domain = [
            ('date_from', '<=', self.date_to),
            ('date_to', '>=', self.date_from),
            ('state', '=', 'done'),
        ]
        if self.is_analytics_recompute_for_single_employee:
            domain.append(('employee_id', '=', self.employee_id.id))
        payslips = self.env['hr.payslip'].search(domain)
        if not payslips:
            return
        set_default_analytics = self._context.get('set_default_analytics') and self.env.user.is_accountant()
        for payslip in payslips:
            if not payslip.analytic_type or set_default_analytics:
                payslip.set_default_analytics()
            payslip.sudo().create_analytic_entries()

    @api.multi
    def recompute_analytics_holiday_reserve(self):
        self.ensure_one()
        self.check_constraints()

        domain = [
            ('date_start', '<=', self.date_to),
            ('date_end', '>=', self.date_from),
            ('state', '=', 'close'),
        ]
        payslip_runs = self.env['hr.payslip.run'].search(domain)
        if not payslip_runs:
            return
        set_default_analytics = self._context.get('set_default_analytics') and self.env.user.is_accountant()
        for payslip_run in payslip_runs:
            for payslip in payslip_run.slip_ids:
                if not payslip.analytic_type or set_default_analytics:
                    payslip.set_default_analytics()
            payslip_run.sudo().create_holiday_reserve_analytic_entries()

    @api.multi
    def check_constraints(self, is_account_move_line=False):
        self.ensure_one()
        if not self.env.user.is_hr_manager() and not self.env.user.is_manager():
            raise exceptions.UserError(_('You do not have sufficient rights'))
        if self.date_to < self.date_from:
            raise exceptions.UserError(_('"Date from" needs to be earlier than "Date to"'))
        # Dates earlier than accounting lock date;
        if is_account_move_line:
            lock_date = self.env.user.company_id.get_user_accounting_lock_date()
            if self.date_from <= lock_date:
                raise exceptions.UserError(self.env.user.company_id.accounting_lock_error_message(lock_date))

    @api.multi
    @api.depends('records_to_recompute')
    def _compute_record_description_html(self):
        """
        Set description based on chosen records
        :return: None
        """
        for rec in self:
            if rec.records_to_recompute == 'account_move':
                rec.description = _("""
                    Analitika bus perskaičiuojama <b>pajamų</b> ir <b>sąnaudų</b> įrašams nurodytu laikotarpiu.
                    <p><i>Įrašai, negali būti ankstesni, nei metų užrakinimo data.</i></p> 
                """)
            elif rec.records_to_recompute == 'invoice':
                rec.description = _("""
                    Analitika bus perskaičiuojama <b>visoms sąskaitoms</b> nurodytu laikotarpiu.
                """)
            elif rec.records_to_recompute == 'payslip':
                rec.description = _("""
                    Analitika bus perskaičiuojama <b>algalapiams</b> nurodytu laikotarpiu.
                    <p><i>Jeigu žymimasis langelis:<ul>
                        <li>Pažymėtas - perskaičiuojama analitika pasirinktam darbuotojui</li>
                        <li>Nepažymėtas - analitika perskaičiuojama visiems darbuotojams</li>
                    </ul></i></p> 
                """)
            elif rec.records_to_recompute == 'holiday_reserve':
                rec.description = _("""
                    Analitika bus perskaičiuojama <b>atostogų kaupiniams</b> nurodytu laikotarpiu.
                """)
