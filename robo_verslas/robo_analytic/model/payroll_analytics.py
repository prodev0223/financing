# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, fields, api, exceptions
from odoo.tools.translate import _
from datetime import datetime
from odoo import tools
from odoo.tools import float_is_zero
from dateutil.relativedelta import relativedelta
from six import iteritems, itervalues


class HrEmployee(models.Model):

    _inherit = 'hr.employee'

    analytic_type = fields.Selection([('fixed_ratio', 'Fiksuotas santykis')], string='Darbo užmokesčio analitika',
                                     groups='robo_basic.group_robo_premium_manager,hr.group_hr_manager', sequence=100)
    analytic_ratio_line_ids = fields.One2many('hr.employee.analytic.ratio', 'employee_id',
                                              string='Analitinės sąskaitos',
                                              groups='robo_basic.group_robo_premium_manager,hr.group_hr_manager',
                                              sequence=100,
                                              )

    @api.multi
    @api.constrains('analytic_ratio_line_ids', 'analytic_type')
    def _check_analytic_ratio_line_ids_qty_is_hundred(self):
        self._check_payroll_analytics_are_enabled_when_forced()
        for rec in self:
            if rec.analytic_type != 'fixed_ratio':
                continue
            err = _('Analitinių sąskaitų dalių suma turi būti lygi 100%')
            if not rec.analytic_ratio_line_ids.filtered(lambda l: l.period_start or l.period_end) \
                    and not tools.float_is_zero(sum(rec.analytic_ratio_line_ids.filtered(
                    lambda l: not l.period_start and not l.period_end).mapped('qty')) - 100.0, precision_digits=2):
                raise exceptions.ValidationError(err)
            for line in rec.analytic_ratio_line_ids.filtered(lambda l: l.period_start or l.period_end):
                domain = [('id', 'in', rec.analytic_ratio_line_ids.mapped('id'))]
                if line.period_start:
                    domain += ['|', ('period_end', '>=', line.period_start), ('period_end', '=', False)]
                if line.period_end:
                    domain += ['|', ('period_start', '<=', line.period_end), ('period_start', '=', False)]
                lines_for_period = self.env['hr.employee.analytic.ratio'].search(domain)
                if not tools.float_is_zero(sum(lines_for_period.mapped('qty')) - 100.0, precision_digits=2):
                    raise exceptions.ValidationError(err)

    @api.multi
    def _check_payroll_analytics_are_enabled_when_forced(self):
        req_du = self.sudo().env.user.company_id.required_du_analytic
        if req_du and any(not employee.analytic_ratio_line_ids for employee in self):
            raise exceptions.ValidationError('Privalote įvesti analitinę sąskaitą darbo užmokesčio analitikos skiltyje!')

    @api.multi
    @api.constrains('analytic_ratio_line_ids', 'analytic_type')
    def _check_analytic_ratio_line_ids_qty_is_positive(self):
        for rec in self:
            if rec.analytic_type == 'fixed_ratio':
                if any(tools.float_compare(qty, 0.0, precision_digits=2) < 0 or
                       tools.float_compare(qty, 100.0, precision_digits=2) > 0
                       for qty in rec.analytic_ratio_line_ids.mapped('qty')):
                    raise exceptions.ValidationError(_('Analitinės sąskaitos dalis turi būti tarp 0 ir 100'))

    @api.model
    def create_accumulated_holidays_reserve_entry(self, data):
        """
        Extend the method to create the related analytic entries
        :param data: dict with another dict under key 'data' with employee ids as keys, and dict as values.
                     'analytic_lines_vals' entry contain list of values to create analytic lines from
        :return: account.move record
        """
        res = super(HrEmployee, self).create_accumulated_holidays_reserve_entry(data)
        AccountAnalyticLine = self.env['account.analytic.line']
        for employee_data in itervalues(data['data']):
            for vals in employee_data.get('analytic_lines_vals'):
                AccountAnalyticLine.create(vals)
        return res

    @api.multi
    def open_analytic_recompute_wizard(self):
        self.ensure_one()
        wizard = self.env['recompute.analytics.employee.card.wizard'].create({'employee_id': self.id})
        action = self.env.ref('robo_analytic.recompute_analytics_employee_card_wizard_action').read()[0]
        action['res_id'] = wizard.id
        return action


HrEmployee()


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    analytic_line_ids = fields.One2many('account.analytic.line', 'payslip_run_id', string='Analitinės eilutės')

    @api.multi
    def draft_payslip_run(self):
        for rec in self:
            rec.sudo().analytic_line_ids.unlink()
        super(HrPayslipRun, self).draft_payslip_run()

    @api.multi
    def cancel_holiday_reserve(self):
        for rec in self:
            rec.sudo().analytic_line_ids.unlink()
        super(HrPayslipRun, self).cancel_holiday_reserve()

    @api.multi
    def get_holidays_reserve_accounting_data(self, date):
        """
        Returns data for accumulated holiday reserves analytic entry creation
        :param date: date at which to get the amounts
        :return: a dict with keys hr_employee.id, and containing a dict with keys:
        'amount', 'sodra' and 'holiday_expense_account_id'
        """
        self.ensure_one()
        MoveLine = self.env['account.move.line']
        labels = self.env['hr.employee'].get_holiday_reserve_entry_labels(date)
        res = {}
        move = self.account_move_id
        for payslip in self.slip_ids:
            employee = payslip.employee_id
            partner = employee.address_home_id
            holiday_expense_account_id = employee.department_id.kaupiniai_expense_account_id.id \
                                         or employee.company_id.kaupiniai_expense_account_id.id
            corresponding_reserve_line = MoveLine.search([('move_id', '=', move.id),
                                                          ('partner_id', '=', partner.id),
                                                          ('name', '=', labels['amount'])], limit=1)
            corresponding_reserve_sodra_line = MoveLine.search([('move_id', '=', move.id),
                                                                ('partner_id', '=', partner.id),
                                                                ('name', '=', labels['sodra'])], limit=1)
            if not corresponding_reserve_line or not corresponding_reserve_sodra_line:
                raise exceptions.UserError(_('Corresponding holiday reserve journal entry not found for employee %s.')
                                           % employee.name)
            res[employee.id] = {
                'amount': -corresponding_reserve_line.balance,
                'sodra': -corresponding_reserve_sodra_line.balance,
                'holiday_expense_account_id': holiday_expense_account_id,
            }
        return res

    @api.multi
    def create_holiday_reserve_analytic_entries(self):
        """
        A method for creating holiday reserve analytic entries corresponding to employee accounting settings and
        already posted holiday reserve accounting entries
        :return: None
        """
        AccountAnalyticLine = self.env['account.analytic.line']
        for rec in self:
            date = rec.date_end
            if not rec.account_move_id:
                continue
            rec.sudo().analytic_line_ids.unlink()
            data = rec.get_holidays_reserve_accounting_data(date)
            for payslip in rec.slip_ids:
                employee = payslip.employee_id
                if not data.get(employee.id):
                    continue
                analytic_lines_values = payslip.get_accumulated_holidays_data_values(data[employee.id], date)
                for val in analytic_lines_values:
                    AccountAnalyticLine.create(val)


HrPayslipRun()


class HrPayslip(models.Model):

    _inherit = 'hr.payslip'

    analytic_type = fields.Selection([('fixed_ratio', 'Fixed ratio')], string='Darbo užmokesčio analitika',
                                     groups='hr.group_hr_manager,hr.group_hr_manager', readonly=True,
                                     states={'draft': [('readonly', False)]})
    analytic_line_ids = fields.One2many('account.analytic.line', 'payslip_id', string='Analitinės eilutės')

    analytic_ratio_line_ids = fields.One2many('hr.payslip.analytic.ratio', 'payslip_id', string='Analitinės sąskaitos',
                                              groups='hr.group_hr_manager,hr.group_hr_manager', readonly=True,
                                              states={'draft': [('readonly', False)]})

    @api.onchange('analytic_type')
    def onchange_analytic_type(self):
        if self.employee_id and self.analytic_type == 'fixed_ratio':
            self.analytic_ratio_line_ids = [(5,)] + [
                (0, 0, {'account_analytic_id': l.account_analytic_id.id, 'period_start': l.period_start, 'period_end': l.period_end, 'qty': l.qty}) for l in
                self.employee_id.analytic_ratio_line_ids.filtered(lambda line: (line.period_end >= self.date_from or not line.period_end) and (line.period_start <= self.date_to or not line.period_start))]

    @api.multi
    def get_amounts_by_analytic_acc_id(self):
        self.ensure_one()
        amounts_by_analytic_account_id = {}
        if self.analytic_type == 'fixed_ratio':
            for l in self.analytic_ratio_line_ids.filtered(lambda line: (line.period_end >= self.date_from or not line.period_end) and (line.period_start <= self.date_to or not line.period_start)):
                if l.account_analytic_id.id not in amounts_by_analytic_account_id:
                    amounts_by_analytic_account_id[l.account_analytic_id.id] = l.qty
                else:
                    amounts_by_analytic_account_id[l.account_analytic_id.id] += l.qty
        return amounts_by_analytic_account_id

    @api.multi
    def get_accumulated_holidays_data(self, date):
        """
        Add extra data for holiday reserve accounting entry: analytics details
        :param date:
        :return:
        """
        res = super(HrPayslip, self).get_accumulated_holidays_data(date)
        data = res['data']
        for rec in self:
            employee = rec.employee_id
            if data[employee.id].get('analytic_lines_vals'):
                # Employee can have several payslips for same month, on different contract.
                # get_amounts_by_analytic_acc_id should return same values for all payslips.
                # One payslip is thus enough, otherwise analytic amounts are duplicated
                continue
            data[employee.id]['analytic_lines_vals'] = rec.get_accumulated_holidays_data_values(data[employee.id], date)
        return res

    @api.multi
    def get_accumulated_holidays_data_values(self, data, date):
        """
        Get analytic line values for accumulated holidays
        :param data: Employee data
        :param date: Date to set analytic default for
        :return: Dictionary of analytic line values
        """
        self.ensure_one()
        label_map = self.env['hr.employee'].get_holiday_reserve_entry_labels(date)
        analytic_lines_vals = []
        holiday_expense_account_id = data['holiday_expense_account_id']
        amounts_by_analytic_account_id = self.get_amounts_by_analytic_acc_id()
        if not amounts_by_analytic_account_id:
            analytic_account = self.env['account.analytic.default'].account_get(
                account_id=holiday_expense_account_id, date=date).analytic_id.id
            if analytic_account:
                amounts_by_analytic_account_id[analytic_account] = 1.0
        total_amount = sum(amounts_by_analytic_account_id.values())
        if float_is_zero(total_amount, precision_digits=2):
            return analytic_lines_vals
        for account_analytic_id, amount in iteritems(amounts_by_analytic_account_id):
            for key in ['amount', 'sodra']:
                amount_expenses = - data[key]
                value = amount * amount_expenses / total_amount  # P3:DivOK
                analytic_lines_vals.append({
                    'account_id': account_analytic_id,
                    'general_account_id': holiday_expense_account_id,
                    'date': self.date_to,
                    'name': label_map[key],
                    'payslip_run_id': self.payslip_run_id.id,
                    'amount': value,
                })
        return analytic_lines_vals

    @api.one
    def _create_analytic_entries(self):
        AccountAnalyticLine = self.env['account.analytic.line']
        amounts_by_analytic_account_id = self.get_amounts_by_analytic_acc_id()
        total_amount = sum(amounts_by_analytic_account_id.values())
        if float_is_zero(total_amount, precision_digits=2):
            return

        general_account_id = self.env['hr.salary.rule'].search([('code', '=', 'BRUTON')]).get_account_debit_id(
            self.employee_id, self.contract_id)
        payslip_amount_codes = ['BM', 'BV', 'V', 'A', 'L', 'P', 'NTR', 'INV', 'IST', 'VD', 'VDN', 'VSS', 'DN', 'SNV',
                                'NDL', 'DP', 'PR', 'PRI', 'T', 'AK', 'PR', 'PD', 'PDN', 'PNVDU', 'KR', 'MA', 'BUD',
                                'VDL', 'KV', 'PN', 'PDNM', 'KOMP', 'KKPD', 'KNDDL']
        payslip_amount = sum(self.env['hr.payslip.line'].search([('slip_id', '=', self.id),
                                                                 ('code', 'in', payslip_amount_codes)]).mapped(
            'amount'))
        payslip_amount += sum(self.other_line_ids.filtered(lambda r: r.type == 'priskaitymai' and
                                                                     r.a_klase_kodas_id.code == '01').mapped('amount'))
        if payslip_amount and not general_account_id:
            raise exceptions.UserError(_('Nenurodyta darbo užmokesčio sąnaudų sąskaita.'))

        employer_sodra_amount = sum(self.line_ids.filtered(lambda r: r.code in ['SDD']).mapped('amount'))
        employer_sodra_amount += sum(self.other_line_ids.filtered(lambda r: r.type == 'sdd').mapped('amount'))
        employee_sodra_amount = sum(self.line_ids.filtered(lambda r: r.code in ['SDB']).mapped('amount'))
        employee_sodra_extra_amount = sum(self.line_ids.filtered(lambda r: r.code in ['SDP']).mapped('amount'))
        gpm_amount = sum(self.line_ids.filtered(lambda r: r.code in ['GPM']).mapped('amount'))
        benefit_in_kind_employer_pays_taxes_amount = sum(self.line_ids.filtered(lambda r:
                                                                                r.code in ['NTRD']).mapped('amount'))
        payslip_amount -= employee_sodra_amount + employee_sodra_extra_amount + gpm_amount + \
                          benefit_in_kind_employer_pays_taxes_amount

        business_trip_amount = sum(self.line_ids.filtered(lambda r: r.code in ['NAKM']).mapped('amount'))

        business_trip_account_id = self.employee_id.department_id.saskaita_komandiruotes.id \
                                   or self.env.user.company_id.saskaita_komandiruotes.id
        if business_trip_amount and not business_trip_account_id:
            raise exceptions.UserError(_('Nenurodyta komandiruočių sąnaudų sąskaita.'))

        # Split total DU amounts into DU/GPM/SoDra analytic lines and create additional analytic line for business trip
        for account_analytic_id in amounts_by_analytic_account_id:
            base_values = {
                'account_id': account_analytic_id,
                'date': self.date_to,
                'payslip_id': self.id,
            }
            # DU amount analytic line
            # P3:DivOK
            payslip_value = -amounts_by_analytic_account_id[account_analytic_id] * payslip_amount / total_amount
            if payslip_value:
                line = base_values.copy()
                line.update({
                    'general_account_id': general_account_id,
                    'name': _('Darbo užmokestis'),
                    'amount': payslip_value,
                })
                AccountAnalyticLine.create(line)
            # Employer SoDra amount analytic line
            employer_sodra_value = -amounts_by_analytic_account_id[account_analytic_id] * employer_sodra_amount \
                                   / total_amount  # P3:DivOK
            if employer_sodra_value:
                line = base_values.copy()
                line.update({
                    'general_account_id': general_account_id,
                    'name': _('Darbdavio SoDra'),
                    'amount': employer_sodra_value,
                })
                AccountAnalyticLine.create(line)
            # Employee SoDra analytic line
            employee_sodra_value = -amounts_by_analytic_account_id[account_analytic_id] * employee_sodra_amount \
                                   / total_amount  # P3:DivOK
            if employee_sodra_value:
                line = base_values.copy()
                line.update({
                    'general_account_id': general_account_id,
                    'name': _('Darbuotojo SoDra'),
                    'amount': employee_sodra_value,
                })
                AccountAnalyticLine.create(line)
            # Employee extra SoDra analytic line
            employee_sodra_extra_value = -amounts_by_analytic_account_id[account_analytic_id] * \
                                         employee_sodra_extra_amount / total_amount  # P3:DivOK
            if employee_sodra_extra_value:
                line = base_values.copy()
                line.update({
                    'general_account_id': general_account_id,
                    'name': _('SoDra papildomai'),
                    'amount': employee_sodra_extra_value,
                })
                AccountAnalyticLine.create(line)
            # GPM analytic line
            gpm_value = -amounts_by_analytic_account_id[account_analytic_id] * gpm_amount / total_amount  # P3:DivOK
            if gpm_value:
                line = base_values.copy()
                line.update({
                    'general_account_id': general_account_id,
                    'name': _('GPM'),
                    'amount': gpm_value,
                })
                AccountAnalyticLine.create(line)
            # Business trip analytic line
            business_trip_value = -amounts_by_analytic_account_id[account_analytic_id] * business_trip_amount \
                                  / total_amount  # P3:DivOK
            if business_trip_value:
                line = base_values.copy()
                line.update({
                    'general_account_id': business_trip_account_id,
                    'name': _('Neapmokestinami dienpinigiai'),
                    'amount': business_trip_value,
                })
                AccountAnalyticLine.create(line)

    @api.model
    def create(self, vals):
        res = super(HrPayslip, self).create(vals)
        if self._context.get('set_default_analytics'):
            res.set_default_analytics()
        return res

    @api.one
    def set_default_analytics(self):
        self.analytic_type = self.employee_id.analytic_type
        self.onchange_analytic_type()

    @api.onchange('employee_id')
    def set_analytic_from_contract(self):
        if self.employee_id:
            self.analytic_type = self.employee_id.analytic_type

    @api.multi
    def action_payslip_done(self):
        res = super(HrPayslip, self).action_payslip_done()
        self.create_analytic_entries()
        return res

    @api.multi
    def reset_and_create_analytic_entries(self):
        self.set_default_analytics()
        self.create_analytic_entries()

    @api.multi
    def atsaukti(self):
        for rec in self:
            rec.sudo().analytic_line_ids.unlink()
        res = super(HrPayslip, self).atsaukti()
        return res

    @api.multi
    def create_analytic_entries(self):
        for rec in self:
            rec.sudo().analytic_line_ids.unlink()
        self._create_analytic_entries()

    @api.multi
    def show_analytic_entries(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.analytic.line',
            'view_mode': 'tree,form,pivot',
            'view_type': 'form',
            'domain': [('payslip_id', '=', self.id)],
        }

    @api.multi
    def _constrain_analytic_account(self):
        '''
        method to be overriden to check that analytic accounts are set correctly
        '''
        return True

    @api.multi
    def atlikti(self):
        self._constrain_analytic_account()
        return super(HrPayslip, self).atlikti()


HrPayslip()


class AccountAnalyticLine(models.Model):

    _inherit = 'account.analytic.line'

    payslip_id = fields.Many2one('hr.payslip', string='Algalapis', readonly=True, ondelete='restrict',
                                 groups='robo_basic.group_robo_premium_manager,hr.group_hr_manager', copy=False)

    payslip_run_id = fields.Many2one('hr.payslip.run', string='Algalapių suvestinė',
                                     readonly=True, ondelete='restrict', copy=False,
                                     groups='robo_basic.group_robo_premium_manager,hr.group_hr_manager')
    general_account_id = fields.Many2one('account.account', string='Financial Account', ondelete='restrict',
                                         readonly=True, compute='_general_account_id', related=False,
                                         store=True, domain=[('deprecated', '=', False)])
    imported_general_account_id = fields.Many2one('account.account', string='Imported Financial Account', ondelete='restrict',
                                         domain=[('deprecated', '=', False)])

    @api.multi
    @api.depends('move_id', 'imported_general_account_id')
    def _general_account_id(self):
        for rec in self:
            if rec.move_id:
                rec.general_account_id = rec.move_id.account_id.id
            elif rec.imported_general_account_id:
                rec.general_account_id = rec.imported_general_account_id.id


AccountAnalyticLine()


class ZiniarastisPeriodLine(models.Model):

    _inherit = 'ziniarastis.period.line'

    @api.multi
    def button_single_done(self):
        return super(ZiniarastisPeriodLine, self.with_context(set_default_analytics=True)).button_single_done()


ZiniarastisPeriodLine()


class HrEmployeeAnalyticRatio(models.Model):

    _name = 'hr.employee.analytic.ratio'

    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', required=True, ondelete="cascade")
    account_analytic_id = fields.Many2one('account.analytic.account', required=True, string='Analitinė sąskaita')
    period_start = fields.Date(string='Periodo pradžia')
    period_end = fields.Date(string='Periodo pabaiga')
    qty = fields.Float(string='Dalis (%)')

    @api.onchange('period_start', 'period_end')
    def _onchange_period(self):
        if self.period_start:
            self.period_start = (datetime.strptime(self.period_start, tools.DEFAULT_SERVER_DATE_FORMAT)+relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        if self.period_end:
            self.period_end = (datetime.strptime(self.period_end, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    @api.constrains('period_start', 'period_end')
    def _check_periods_logical(self):
        for rec in self:
            if rec.period_start and rec.period_end and rec.period_start >= rec.period_end:
                raise exceptions.ValidationError(
                    _('Analitikos periodo pradžia turi būti vėliau, nei periodo pabaiga')
                )


HrEmployeeAnalyticRatio()


class HrPayslipAnalyticRatio(models.Model):

    _name = 'hr.payslip.analytic.ratio'

    payslip_id = fields.Many2one('hr.payslip', string='Algalapis', required=True, ondelete="cascade")
    period_start = fields.Date(string='Periodo pradžia')
    period_end = fields.Date(string='Periodo pabaiga')
    account_analytic_id = fields.Many2one('account.analytic.account', required=True, string='Analitinė sąskaita')
    qty = fields.Float(string='Dalis (%)')

    @api.multi
    @api.constrains('period_start', 'period_end')
    def _check_period_matches_payslip(self):
        for rec in self:
            if (rec.period_start and rec.period_start >= rec.payslip_id.date_to) or \
                    (rec.period_end and rec.period_end <= rec.payslip_id.date_from):
                raise exceptions.ValidationError(_('Analitikos periodas turi patekti į algalapio periodą'))

    @api.multi
    @api.constrains('period_start', 'period_end')
    def _check_periods_logical(self):
        for rec in self:
            if rec.period_start and rec.period_end and rec.period_start >= rec.period_end:
                raise exceptions.ValidationError(
                    _('Analitikos periodo pradžia turi būti vėliau, nei periodo pabaiga')
                )


HrPayslipAnalyticRatio()
