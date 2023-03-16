# -*- coding: utf-8 -*-
import calendar
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import _, api, exceptions, fields, models, tools


class HrEmployeeNatura(models.Model):

    _name = 'hr.employee.natura'

    def default_currency_id(self):
        return self.env.user.company_id.currency_id.id

    def default_date_from(self):
        return (datetime.now() + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def default_date_to(self):
        return (datetime.now() + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True,
                                  states={'confirm': [('readonly', True)]})
    state = fields.Selection([('draft', 'Draft'), ('confirm', 'Confirm')], string='State', readonly=True,
                             default='draft', required=True, copy=False)
    date_from = fields.Date(string='Data nuo', required=True, states={'confirm': [('readonly', True)]}, default=default_date_from)
    date_to = fields.Date(string='Data iki', required=True, states={'confirm': [('readonly', True)]}, default=default_date_to)

    amount = fields.Monetary(string='Suma', states={'confirm': [('readonly', True)]})
    currency_id = fields.Many2one('res.currency', string='Valiuta', required=True, default=default_currency_id)
    name = fields.Char(readonly=True, string='Name')
    comment = fields.Text(string='Komentaras', states={'confirm': [('readonly', True)]})
    taxes_paid_by = fields.Selection([
        ('employee', 'Employee'),
        ('employer', 'Employer')
    ], string='Taxes paid by', help='Who pays the taxes', default='employee', required='True')
    theoretical_bruto = fields.Float(string='Teorinis bruto', compute='_compute_theoretical_gpm')
    theoretical_gpm = fields.Float(string='Teorinis GPM', compute='_compute_theoretical_gpm')
    move_ids = fields.Many2many('account.move', string='Žurnalo įrašas', readonly=True)
    periodic_id = fields.Many2one('hr.employee.kind.periodic', string='Pasikartojantis')
    periodic_ids = fields.One2many('hr.employee.kind.periodic', 'kind_id')
    has_periodic_ids = fields.Boolean(compute='_compute_has_periodic_ids')

    @api.multi
    def _compute_has_periodic_ids(self):
        for rec in self:
            rec.has_periodic_ids = True if rec.periodic_ids else False

    @api.one
    def _compute_theoretical_gpm(self):
        contract_id = self.env['hr.contract'].search([('employee_id', '=', self.employee_id.id),
                                                      ('date_start', '<=', self.date_to),
                                                      '|',
                                                        ('date_end', '=', False),
                                                      ('date_end', '>=', self.date_from)], limit=1)

        bruto, gpm = contract_id.get_theoretical_bruto_gpm(self.amount, self.date_to)
        self.theoretical_bruto = bruto
        self.theoretical_gpm = gpm

    @api.onchange('date_from', 'date_to')
    def onchange_dates_constraint(self):
        if self.date_from:
            data_nuo = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            if data_nuo != datetime(data_nuo.year, data_nuo.month, 1):
                raise exceptions.Warning(_('Periodo pradžia privalo būti mėnesio pirmoji diena'))
            if self.date_to:
                data_iki = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
                if data_iki != datetime(data_nuo.year, data_nuo.month,
                                        calendar.monthrange(data_nuo.year, data_nuo.month)[1]):
                    raise exceptions.Warning(_('Periodo pabaiga privalo būti to paties mėnesio paskutinė diena'))

    @api.constrains('date_from', 'date_to')
    def _tikrinti_datas(self):
        for rec in self:
            data_nuo = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            if data_nuo.day != 1:
                raise exceptions.ValidationError(
                    _('Periodo pradžia ir pabaiga privalo būti pirma ir paskutinė mėnesio dienos!'))
            if rec.date_to != (data_nuo + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT):
                raise exceptions.ValidationError(
                    _('Periodo pradžia ir pabaiga privalo būti pirma ir paskutinė mėnesio dienos!'))
        return True

    @api.model
    def _create_employer_pays_tax_account_move(self, partner, sodra_amount, income_tax_amount, date_to):
        """
        Creates tax transfer for when employer pays taxes for benefit in kind
        Args:
            partner (res.partner): The partner to create the move for
            sodra_amount (float): SoDra payment amount
            income_tax_amount (float): Income tax amount
            date_to (date): End date for the benefit in kind period.
        Returns: The created account move (account.move)
        """

        # Check accounts
        income_tax_account = self.env['account.account'].search([('code', '=', '4481')], limit=1)
        if not income_tax_account:
            raise exceptions.UserError(_('Income tax account (4481) not found!'))
        sodra_account = self.env['account.account'].search([('code', '=', '4482')], limit=1)
        if not sodra_account:
            raise exceptions.UserError(_('SoDra account (4482) not found!'))
        debit_account = self.env['account.account'].search([('code', '=', '652')], limit=1)
        if not debit_account:
            debit_account = self.env['account.account'].search([('name', '=', 'Neleidžiami atskaitymai')], limit=1)
        if not debit_account:
            raise exceptions.UserError(_('Non-deductible account (652) not found!'))

        # Basic company info
        company = self.env.user.company_id
        currency = company.currency_id

        # Find journal
        salary_journal = company.salary_journal_id
        if not salary_journal:
            raise exceptions.UserError(_('Salary journal is not set for company'))

        # Compute date maturity
        # date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        # salary_payment_date = company.salary_payment_day or 15
        # date_maturity_dt = date_to_dt + relativedelta(months=1, day=salary_payment_date)
        # date_maturity = date_maturity_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        # Create line values
        line_vals = {
            # 'currency_id': currency.id,
            'partner_id': partner.id,
            'date_maturity': date_to,
            'ref': _('{} benefit in kind {}').format(partner.name, date_to),
            'name': _('Benefit in kind (employer pays taxes)'),
            'credit': 0.0,
            'debit': 0.0,
        }
        income_tax_line_vals = line_vals.copy()
        sodra_line_vals = line_vals.copy()
        debit_line_vals = line_vals.copy()

        vmi_partner = self.env.ref('l10n_lt_payroll.vmi_partner', raise_if_not_found=False)
        if not vmi_partner:
            vmi_partner = self.env['res.partner'].search([('kodas', '=', '188659752')], limit=1)
        income_tax_line_vals.update({
            'account_id': income_tax_account.id,
            'credit': income_tax_amount,
            'partner_id': vmi_partner.id,
        })
        sodra_partner = self.env.ref('l10n_lt_payroll.sodra_partner', raise_if_not_found=False)
        if not sodra_partner:
            sodra_partner = self.env['res.partner'].search([('kodas', '=', '191630223')], limit=1)
        sodra_line_vals.update({
            'account_id': sodra_account.id,
            'credit': sodra_amount,
            'partner_id': sodra_partner.id,
        })
        debit_line_vals.update({
            'account_id': debit_account.id,
            'debit': income_tax_amount + sodra_amount,
        })

        # Create and post move
        account_move = self.env['account.move'].create({
            'name': _('{} benefit in kind').format(partner.name),
            'journal_id': salary_journal.id,
            'date': date_to,
            # 'currency_id': currency.id,
            'line_ids': [(0, 0, income_tax_line_vals), (0, 0, sodra_line_vals), (0, 0, debit_line_vals)],
        })
        account_move.post()
        return account_move

    @api.multi
    def make_periodic(self):
        self.ensure_one()
        if self.state == 'confirm' and not self.periodic_ids:
            date = self.date_to
            date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
            current_date = datetime.utcnow()
            if (date_dt + relativedelta(months=1)) <= current_date:
                date = (current_date + relativedelta(day=date_dt.day)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            periodic_payment = self.env['hr.employee.kind.periodic'].create({
                'kind_id': self.id,
                'date': date,
            })
            periodic_payment.set_next_date()
            self.periodic_id = periodic_payment.id

    @api.multi
    def stop_periodic(self):
        self.ensure_one()
        if self.periodic_ids:
            self.periodic_ids.unlink()

    @api.multi
    def open_related_move_ids(self):
        move_ids = self.mapped('move_ids').ids
        return {
            'name': _('Journal Entries'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', move_ids)],
        }

    @api.model
    def create(self, vals):
        res = super(HrEmployeeNatura, self).create(vals)
        res.name = self.env['ir.sequence'].next_by_code('NATUR')
        return res

    @api.multi
    def unlink(self):
        if any(rec.state == 'confirm' for rec in self):
            raise exceptions.UserError(_('Negalima trinti patvirtinto įrašo. Pirmiau atšaukite.'))
        return super(HrEmployeeNatura, self).unlink()

    @api.multi
    def confirm(self):
        for rec in self:
            if rec.state == 'confirm':
                raise exceptions.Warning(_('Įrašas jau patvirtintas'))
            rec.state = 'confirm'
            self.env['hr.payslip'].refresh_info(rec.employee_id.id, rec.date_to)

    @api.multi
    def action_cancel(self):
        for rec in self:
            if rec.state == 'draft':
                raise exceptions.Warning(_('Įrašas nėra patvirtintas'))
            rec.state = 'draft'
            self.env['hr.payslip'].refresh_info(rec.employee_id.id, rec.date_to)

    @api.model
    def fix_names(self):
        for rec in self.search([('name', '=', False)], order='create_date asc'):
            rec.name = self.env['ir.sequence'].next_by_code('NATUR')


HrEmployeeNatura()
