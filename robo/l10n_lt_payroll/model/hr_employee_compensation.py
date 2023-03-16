# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import api, exceptions, fields, models, tools
from odoo.tools.translate import _


class HrEmployeeCompensation(models.Model):
    _name = 'hr.employee.compensation'

    def _default_payslip_year_id(self):
        return self.env['years'].search([('code', '=', datetime.utcnow().year)], limit=1)

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True,
                                  states={'confirm': [('readonly', True)]})
    date_from = fields.Date(string='For period from', required=True, states={'confirm': [('readonly', True)]})
    date_to = fields.Date(string='For period to', required=True, states={'confirm': [('readonly', True)]})
    compensation_type = fields.Selection([('dynamic_workplace', 'Dynamic workplace compensation'),
                                          ('approved_leave', 'Approved leave compensation')],
                                         string='Compensation type', required=True,
                                         states={'confirm': [('readonly', True)]})
    amount = fields.Float(string='Amount', required=True, default=0.0, states={'confirm': [('readonly', True)]})
    comment = fields.Text(string='Comments', states={'confirm': [('readonly', True)]})
    state = fields.Selection([('draft', 'Draft'), ('confirm', 'Confirm')], string='State', readonly=True,
                             default='draft', required=True, copy=False)
    payslip_month = fields.Selection([('01', 'January'), ('02', 'February'), ('03', 'March'), ('04', 'April'),
                                      ('05', 'May'), ('06', 'June'), ('07', 'July'), ('08', 'August'),
                                      ('09', 'September'), ('10', 'October'), ('11', 'November'), ('12', 'December')],
                                     string='Month of payslip to payout with',
                                     default=str(datetime.utcnow().month).zfill(2), required=True,
                                     states={'confirm': [('readonly', True)]})
    payslip_year_id = fields.Many2one('years', string='Year of payslip to payout with',
                                      default=_default_payslip_year_id, required=True,
                                      states={'confirm': [('readonly', True)]})
    compensation_time_ids = fields.One2many('hr.employee.compensation.time.line', 'compensation_id',
                                            string='Compensation times', states={'confirm': [('readonly', True)]})

    @api.multi
    def name_get(self):
        res = []
        for rec in self:
            rec_type = _(dict(self._fields['compensation_type'].selection).get(rec.compensation_type)) or \
                       _('Compensation')
            res.append((
                rec.id,
                _('{} {} for the period from {} to {}').format(
                    rec.employee_id.name,
                    rec_type.lower(),
                    rec.date_from,
                    rec.date_to
                )
            ))
        return res

    @api.multi
    @api.constrains('employee_id', 'date_from', 'date_to', 'compensation_type', 'state')
    def _check_overlapping_compensations(self):
        """
        Prevents overlapping confirmed compensations of the same type
        """
        for rec in self.filtered(lambda r: r.state == 'confirm'):
            other_compensations_exist_for_period = self.search_count([
                ('employee_id', '=', rec.employee_id.id),
                ('date_from', '<=', rec.date_to),
                ('date_to', '>=', rec.date_from),
                ('compensation_type', '=', rec.compensation_type),
                ('state', '=', 'confirm'),
                ('id', '!=', rec.id),
            ])
            if other_compensations_exist_for_period:
                raise exceptions.ValidationError(_('Another compensation of the same type for this employee and this '
                                                   'period already exists'))

    @api.multi
    @api.constrains('state')
    def _check_state(self):
        """
        Checks if a payslip for the compensation period is confirmed when trying to change state.
        """
        for rec in self:
            payroll_month_start_dt = rec.payroll_month_start_dt()
            date_from = payroll_month_start_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to = (payroll_month_start_dt+relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            payslip_is_confirmed = self.env['hr.payslip'].sudo().search_count([
                ('date_from', '<=', date_to),
                ('date_to', '>=', date_from),
                ('employee_id', '=', rec.employee_id.id),
                ('state', 'not in', ['draft', 'cancel'])
            ])
            if payslip_is_confirmed:
                raise exceptions.ValidationError(_('Payroll has already been calculated for some employees in the '
                                                   'compensation period. You can not make changes to this '
                                                   'compensation.'))

    @api.multi
    @api.constrains('date_from', 'date_to', 'compensation_type')
    def _check_dates(self):
        """
        Enforces some specific types of compensations to be for a whole month.
        """
        enforce_same_month_types = ['dynamic_workplace']
        for rec in self.filtered(lambda r: r.compensation_type in enforce_same_month_types):
            date_from_dt = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            if date_from_dt.year != date_to_dt.year or date_from_dt.month != date_to_dt.month:
                raise exceptions.ValidationError(_('A compensation of type "{}" must be for a single '
                                                   'month').format(rec.compensation_type))

    @api.multi
    @api.constrains('amount')
    def _check_amount(self):
        """
        Ensures that the compensation amounts are positive
        """
        for rec in self:
            if tools.float_compare(rec.amount, 0.0, precision_digits=2) <= 0:
                raise exceptions.ValidationError(_('Compensation amount must be greater than 0.0'))

    @api.multi
    @api.constrains('date_from', 'date_to')
    def _check_date_from_is_before_date_to(self):
        """
        Ensure that that the date_from is before date_to
        """
        for rec in self:
            if rec.date_from > rec.date_to:
                raise exceptions.ValidationError(_('Compensation date from must be before the date to'))

    @api.multi
    @api.constrains('date_to', 'payslip_year_id', 'payslip_month')
    def _check_compensation_is_for_the_period_before_payout(self):
        """
        Ensures that the compensation payout month is after the period the compensation is for
        """
        for rec in self:
            payout_month_end_dt = rec.payroll_month_start_dt() + relativedelta(day=31)
            payout_month_end = payout_month_end_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if rec.date_to > payout_month_end:
                raise exceptions.ValidationError(_('Compensation must be payed out after the period the compensation '
                                                   'is for'))

    @api.multi
    def action_confirm(self):
        """
        Action to confirm the compensation
        """
        self.write({'state': 'confirm'})

    @api.multi
    def action_draft(self):
        """
        Action to make the compensation draft again
        """
        self.write({'state': 'draft'})

    @api.multi
    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise exceptions.ValidationError(_('You can not unlink confirmed compensation records'))
        super(HrEmployeeCompensation, self).unlink()

    @api.multi
    def payroll_month_start_dt(self):
        self.ensure_one()
        year = self.payslip_year_id.code
        month = int(self.payslip_month)
        return datetime(year, month, 1)

    @api.model
    def get_payslip_inputs(self, contract_ids, date_from, date_to):
        """
        Parses compensations for specified contracts for given dates. Returns data in a format used to create payslip
        inputs.
        Args:
            contract_ids (): Contracts to look up the compensation for
            date_from (): The date to look the compensations up from
            date_to (): The date to look the compensations up to

        Returns: a list of dictionaries - parsed compensation data for period
        """

        def is_first_contract_of_the_month(contract, period):
            period_year = self.env['years'].browse(period[0]).code
            period_month = int(period[1])
            period_from_dt = datetime(period_year, period_month, 1)
            period_from = period_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            period_to = (period_from_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            employee_contracts_in_period = contract.employee_id.contract_ids.filtered(lambda c:
                                                                                      c.date_start <= period_to and
                                                                                      (not c.date_end or
                                                                                       c.date_end >= period_from))
            employee_contracts_in_period = employee_contracts_in_period.sorted(key=lambda c: c.date_start)
            if len(employee_contracts_in_period) > 1:
                first_period_contract = employee_contracts_in_period[0]
            else:
                first_period_contract = employee_contracts_in_period
            return first_period_contract.id == contract.id

        res = []
        if not contract_ids or not date_from or not date_to:
            return res

        compensation_type_code_mapping = {
            'dynamic_workplace': 'KKPD',
            'approved_leave': 'KNDDL'
        }

        date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_check = date_from_dt
        date_pairs = []
        while date_check <= date_to_dt:
            date_year_id = self.env['years'].search([('code', '=', date_check.year)], limit=1).id
            date_month = str(date_check.month).zfill(2)
            date_pairs.append((date_year_id, date_month))
            date_check += relativedelta(months=1)
        date_pairs = list(set(date_pairs))

        contracts = self.env['hr.contract'].browse(contract_ids)
        for date_pair in date_pairs:
            contracts_to_create_for = contracts.filtered(lambda c: is_first_contract_of_the_month(c, date_pair))
            employees = contracts_to_create_for.mapped('employee_id')
            compensations = self.search([
                ('employee_id', 'in', employees.ids),
                ('payslip_year_id', '=', date_pair[0]),
                ('payslip_month', '=', date_pair[1]),
                ('state', '=', 'confirm')
            ])
            for contract in contracts_to_create_for:
                contract_compensations = compensations.filtered(lambda c: c.employee_id == contract.employee_id)
                for compensation_type in set(contract_compensations.mapped('compensation_type')):
                    type_compensations = contract_compensations.filtered(lambda c:
                                                                         c.compensation_type == compensation_type)

                    res.append({
                        'name': _(dict(self._fields['compensation_type'].selection).get(compensation_type)) or
                                _('Compensation'),
                        'code': compensation_type_code_mapping.get(compensation_type, 'KOMP'),
                        'contract_id': contract.id,
                        'amount': sum(type_compensations.mapped('amount'))
                    })
        return res


HrEmployeeCompensation()
