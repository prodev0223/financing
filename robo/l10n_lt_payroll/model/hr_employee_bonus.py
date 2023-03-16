# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, tools, exceptions
from odoo.tools.translate import _
from .payroll_codes import PAYROLL_CODES


class HrEmployeeBonus(models.Model):
    _name = 'hr.employee.bonus'
    _order = 'for_date_from DESC, employee_id'
    _inherit = ['mail.thread']

    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', required=True,
                                  states={'confirm': [('readonly', True)]})
    for_date_from = fields.Date(string='Laikotarpio už data nuo', required=True,
                                states={'confirm': [('readonly', True)]})
    for_date_to = fields.Date(string='Laikotarpio už data iki', required=True, states={'confirm': [('readonly', True)]})
    payment_date_from = fields.Date(string='Išmokėjimo laikotarpio data už', required=True,
                                    states={'confirm': [('readonly', True)]})
    payment_date_to = fields.Date(string='Išmokėjimo laikotarpio data iki', required=True,
                                  states={'confirm': [('readonly', True)]})
    bonus_type = fields.Selection([('1men', 'Mėnesinė'),
                                   ('3men', 'Ketvirtinė'),
                                   ('ilgesne', 'Ilgesnė nei 3 mėn., bet ne ilgesnė nei 12 mėn.'),
                                   ('ne_vdu', 'Nepatenkanti į vdu')], string='Premijos rūšis', required=True,
                                  states={'confirm': [('readonly', True)]})
    amount = fields.Float(string='Suma', states={'confirm': [('readonly', True)]})
    comment = fields.Text(string='Pastabos', states={'confirm': [('readonly', True)]})
    state = fields.Selection([('draft', 'Draft'), ('confirm', 'Confirm')], string='State', readonly=True,
                             default='draft', required=True, copy=False)
    periodic_id = fields.Many2one('hr.employee.bonus.periodic', string='Pasikartojantis')
    periodic_ids = fields.One2many('hr.employee.bonus.periodic', 'bonus_id')
    amount_type = fields.Selection([('bruto', _('Bruto')), ('neto', _('Neto'))], string='Sumos tipas', required=True,
                                   default='bruto', states={'confirm': [('readonly', True)]})
    has_periodic_ids = fields.Boolean(compute='_has_periodic_ids')
    taxation_type = fields.Selection([
        ('fully_taxable', 'Visa priedo suma'),
        ('taxable_over_half_of_salary', 'Priedo suma viršijanti 50% darbuotojo bazinio DU')
    ], string='Apmokestinama suma', required=True, default='fully_taxable', states={'confirm': [('readonly', True)]})

    @api.one
    def _has_periodic_ids(self):
        self.has_periodic_ids = True if self.periodic_ids else False

    @api.onchange('bonus_type', 'amount_type')
    def _check_bonus_amount_type(self):
        if self.bonus_type not in ['1men', 'ne_vdu']:
            self.amount_type = 'bruto'
            self.taxation_type = 'fully_taxable'

    @api.multi
    @api.constrains('taxation_type', 'amount_type')
    def _check_bruto_is_payed_when_not_fully_taxable(self):
        if any(rec.taxation_type != 'fully_taxable' and rec.amount_type != 'bruto' for rec in self):
            raise exceptions.ValidationError(_('Priedo suma turi būti BRUTO, kai priedas nėra pilnai apmokestinamas'))

    @api.constrains('bonus_type', 'amount_type')
    def _check_bonus_input_type_for_specific_bonus_types(self):
        if any(rec.amount_type == 'neto' and rec.bonus_type not in ['1men', 'ne_vdu'] for rec in self):
            raise exceptions.ValidationError(_('Negalima skirti priedo pagal NETO sumą už ilgesnį nei vieno mėnesio '
                                               'laikotarpį, dėl galimų netikslingų paskaičiavimų'))
        if any(rec.taxation_type != 'fully_taxable' and rec.bonus_type != '1men' for rec in self):
            raise exceptions.ValidationError(_('Kai priedas nėra pilnai apmokestinamas - priedas negali būti už '
                                               'periodą ilgesnį nei vieno mėnesio laikotarpis'))

    @api.multi
    def name_get(self):
        return [(rec.id, '%s %s' % (rec.employee_id.name, rec.for_date_to)) for rec in self]

    @api.onchange('payment_date_from')
    def onchange_payment_date_from(self):
        if self.payment_date_from:
            payment_date_from_dt = datetime.strptime(self.payment_date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            if payment_date_from_dt.day != 1:
                raise exceptions.Warning(_('Išmokėjimo laikotarpio data nuo turi sutapti su pirma mėnesio diena'))
            else:
                self.payment_date_to = (payment_date_from_dt + relativedelta(day=31)).strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    @api.constrains('payment_date_from', 'payment_date_to')
    def constrain_payment_date_from(self):
        for rec in self:
            payment_date_from_dt = datetime.strptime(rec.payment_date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            if payment_date_from_dt.day != 1:
                raise exceptions.ValidationError(
                    _('Išmokėjimo laikotarpio data nuo turi sutapti su pirma mėnesio diena'))
            else:
                payment_date_to = (payment_date_from_dt + relativedelta(day=31)).strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT)
                if payment_date_to != rec.payment_date_to:
                    raise exceptions.ValidationError(
                        _('Išmokėjimo laikotarpis turi sutapti su mėnesio pirma ir paskutine dienomis'))

    @api.model
    def default_get(self, field_list):
        res = super(HrEmployeeBonus, self).default_get(field_list)
        if 'payment_date_from' in field_list:
            res['payment_date_from'] = (datetime.now() + relativedelta(day=1)).strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT)
        if 'payment_date_to' in field_list:
            res['payment_date_to'] = (datetime.now() + relativedelta(day=31)).strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT)

        if 'for_date_from' in field_list:
            res['for_date_from'] = (datetime.now() + relativedelta(day=1)).strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT)
        if 'for_date_to' in field_list:
            res['for_date_to'] = (datetime.now() + relativedelta(day=31)).strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT)
        return res

    @api.multi
    def confirm(self):
        for rec in self:
            if rec.state == 'confirm':
                raise exceptions.Warning(_('Įrašas jau patvirtintas'))
            rec.state = 'confirm'
            self.env['hr.payslip'].refresh_info(rec.employee_id.id, rec.payment_date_to)

    @api.multi
    def action_cancel(self):
        slip_run_ids = self.env['hr.payslip.run'].search([
            ('date_start', '<=', max(self.mapped('payment_date_to'))),
            ('date_end', '>=', min(self.mapped('payment_date_from')))
        ])
        for rec in self:
            rec_slip_run = slip_run_ids.filtered(lambda r:
                                                 r.date_start <= rec.payment_date_to and
                                                 r.date_end >= rec.payment_date_from and
                                                 r.state != 'draft')
            if len(rec_slip_run) > 1:
                rec_slip_run = rec_slip_run[0]
            if rec_slip_run:
                raise exceptions.ValidationError(_('Periodo %s - %s suvestinė uždaryta, priedo atšaukti nebegalima') % (
                rec_slip_run.date_start, rec_slip_run.date_end))
            rec.state = 'draft'
            self.env['hr.payslip'].refresh_info(rec.employee_id.id, rec.payment_date_to)

    @api.multi
    def make_periodic(self):
        self.ensure_one()
        if self.state == 'confirm' and not self.periodic_ids:
            date = self.for_date_to
            date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
            cdate = datetime(datetime.utcnow().year, datetime.utcnow().month, datetime.utcnow().day)
            if (date_dt + relativedelta(months=1)) <= cdate and not self._context.get('skip_past_date_check'):
                date = datetime(cdate.year, cdate.month, date_dt.day).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            periodic_id = self.env['hr.employee.bonus.periodic'].create({
                'bonus_id': self.id,
                'employee_id': self.employee_id.id,
                'date': date,
            })
            periodic_id.set_next_date()
            self.periodic_id = periodic_id.id

    @api.multi
    def stop_periodic(self):
        self.ensure_one()
        if self.periodic_ids:
            self.periodic_ids.unlink()

    @api.multi
    def unlink(self):
        for rec in self:
            if rec.state == 'confirm':
                raise exceptions.UserError(_('Negalima ištrinti patvirtintų premijų. Pirmiau atšaukite.'))
        return super(HrEmployeeBonus, self).unlink()

    @api.model
    def create_bonus_inputs(self, payslips):
        """
        Creates payslip bonus inputs. compute_sheet must be called before and after this method
        :param payslips: payslips to recompute bonuses for
        """
        vals = []
        HrPayslip = self.env['hr.payslip'].sudo()
        payslips.mapped('input_line_ids').filtered(lambda l: l.code in ['PD', 'PRI', 'PDN', 'PR', 'PDNM']).unlink()
        for payslip in payslips:
            contract = payslip.contract_id
            same_period_payslip = HrPayslip.search_count([('id', '!=', payslip.id),
                                                          ('employee_id', '=', payslip.employee_id.id),
                                                          ('date_from', '=', payslip.date_from),
                                                          ('date_to', '=', payslip.date_to)])
            if contract.date_end and contract.date_end < payslip.date_to and same_period_payslip:
                # Skip payslip when its contract ends before payslip end date and there is another payslip in the period
                # to prevent duplicate bonuses in payslips
                continue
            bonuses = self.env['hr.employee.bonus'].search([('employee_id', '=', contract.employee_id.id),
                                                            ('payment_date_from', '=', payslip.date_from),
                                                            ('payment_date_to', '=', payslip.date_to),
                                                            ('state', '=', 'confirm')])
            regular_bonuses = bonuses.filtered(lambda b: b.taxation_type == 'fully_taxable')
            amount_pr = sum(regular_bonuses.filtered(lambda r: r.bonus_type == '3men').mapped('amount'))
            amount_pri = sum(regular_bonuses.filtered(lambda r: r.bonus_type == 'ilgesne').mapped('amount'))

            # Get non VDU bonuses
            non_vdu_bonuses = regular_bonuses.filtered(lambda r: r.bonus_type == 'ne_vdu')
            non_vdu_bruto_bonuses = non_vdu_bonuses.filtered(lambda r: r.amount_type == 'bruto')
            non_vdu_neto_bonuses = non_vdu_bonuses.filtered(lambda r: r.amount_type == 'neto')

            # Get other regular bonuses
            regular_bonuses = regular_bonuses.filtered(lambda r: r.bonus_type == '1men')
            regular_bruto_bonuses = regular_bonuses.filtered(lambda b: b.amount_type == 'bruto')
            regular_neto_bonuses = regular_bonuses.filtered(lambda b: b.amount_type == 'neto')

            amount_pd = 0.0
            amount_pdn = sum(non_vdu_bruto_bonuses.mapped('amount'))
            for bonus in regular_bruto_bonuses:
                # Finds payslips that has worked time set for the bonus for period
                has_worked = self.env['hr.payslip'].search_count([
                    ('date_from', '<=', bonus.for_date_to),
                    ('date_to', '>=', bonus.for_date_from),
                    ('employee_id', '=', bonus.employee_id.id),
                    ('worked_days_line_ids.code', 'in', PAYROLL_CODES['WORKED']),
                    '|',
                    ('worked_days_line_ids.number_of_days', '!=', 0.0),
                    ('worked_days_line_ids.number_of_hours', '!=', 0.0),
                ])
                # If an employee has not worked in a bonus period that bonus should not be accounted for in VDU
                if has_worked:
                    amount_pd += bonus.amount
                else:
                    amount_pdn += bonus.amount

            pr_vals = {
                    'name': _('Ketvirtinės Premijos'),
                    'code': 'PR',
                    'contract_id': contract.id,
                    'amount': amount_pr,
                    'payslip_id': payslip.id
            }
            pd_vals = {
                'name': _('Priedai'),
                'code': 'PD',
                'contract_id': contract.id,
                'amount': amount_pd,
                'payslip_id': payslip.id
            }
            pri_vals = {
                'name': _('Ilgesnio laikotarpio premijos'),
                'code': 'PRI',
                'contract_id': contract.id,
                'amount': amount_pri,
                'payslip_id': payslip.id
            }
            pdn_vals = {
                'name': _('Į VDU nepatenkantys priedai'),
                'code': 'PDN',
                'contract_id': contract.id,
                'amount': amount_pdn,
                'payslip_id': payslip.id
            }

            appointments = contract.appointment_ids
            appointments = appointments.filtered(lambda a: a.date_start <= payslip.date_to and
                                                           (not a.date_end or a.date_end >= payslip.date_from))
            appointments = appointments.sorted(lambda a: a.date_start)
            appointment = appointments[0] if appointments else False
            if not appointment:
                continue

            regular_amount = sum(regular_neto_bonuses.mapped('amount'))
            non_vdu_amount = sum(non_vdu_neto_bonuses.mapped('amount'))
            if tools.float_is_zero(regular_amount + non_vdu_amount, precision_digits=2):
                vals += [pd_vals, pr_vals, pri_vals, pdn_vals]
                continue

            force_npd = None
            in_zero_npd_period = self.env['zero.npd.period'].search_count([
                ('date_start', '<=', payslip.date_to),
                ('date_end', '>=', payslip.date_from)
            ])
            if not appointment.use_npd or payslip.npd_nulis or in_zero_npd_period:
                force_npd = 0.0

            voluntary_pension = appointment.sodra_papildomai and appointment.sodra_papildomai_type
            disability = appointment.employee_id.invalidumas and appointment.employee_id.darbingumas.name
            is_foreign_resident = payslip.employee_id.is_non_resident
            npd_date = payslip.get_npd_values().get('npd_date') or payslip.date_from
            tax_rates = contract.with_context(date=payslip.date_from).get_payroll_tax_rates()

            slip_payable = sum(payslip.line_ids.filtered(lambda l: l.code in ['BENDM', 'AVN']).mapped('total'))
            benefit_in_kind_amount = sum(payslip.line_ids.filtered(lambda l: l.code in ['NTR']).mapped('total'))
            other_neto_amounts = sum(payslip.line_ids.filtered(lambda l: l.code in ['KOMP', 'KKPD']).mapped('total'))
            illness_amount = sum(payslip.line_ids.filtered(lambda l: l.code in ['L']).mapped('total'))
            deduction_amount = sum(payslip.line_ids.filtered(lambda l: l.code in ['IŠSK']).mapped('total'))
            benefit_in_kind_employer_pays_taxes_amount = sum(
                payslip.line_ids.filtered(lambda l: l.code in ['NTRD']).mapped('total')
            )
            slip_payable += deduction_amount
            HrPayroll = self.env['hr.payroll']
            bruto_pd = 0.0
            if not tools.float_is_zero(regular_amount, precision_digits=2):
                net_amount = slip_payable + regular_amount - other_neto_amounts + benefit_in_kind_amount - \
                             benefit_in_kind_employer_pays_taxes_amount
                payslip_bruto_needed = HrPayroll.with_context(
                    force_override_taxes_by_npd_date=True
                ).convert_net_income_to_gross(
                    net_amount, date=payslip.date_from, forced_tax_free_income=force_npd,
                    illness_bruto_amount=illness_amount, npd_date=npd_date, disability=disability,
                    is_foreign_resident=is_foreign_resident, voluntary_pension=voluntary_pension,
                    contract=contract, **tax_rates
                )
                bruto_pd = payslip_bruto_needed - payslip.bruto + benefit_in_kind_employer_pays_taxes_amount
                if tools.float_compare(bruto_pd, 0.0, precision_digits=2) > 0:
                    pd_vals['amount'] = pd_vals['amount'] + bruto_pd
            if not tools.float_is_zero(non_vdu_amount, precision_digits=2):
                net_amount = slip_payable + non_vdu_amount + regular_amount - other_neto_amounts + \
                             benefit_in_kind_amount - benefit_in_kind_employer_pays_taxes_amount
                payslip_bruto_needed = HrPayroll.with_context(
                    force_override_taxes_by_npd_date=True
                ).convert_net_income_to_gross(
                    net_amount, date=payslip.date_from, forced_tax_free_income=force_npd,
                    illness_bruto_amount=illness_amount, npd_date=npd_date, disability=disability,
                    is_foreign_resident=is_foreign_resident, voluntary_pension=voluntary_pension, contract=contract,
                    **tax_rates
                )
                bruto_pdn = payslip_bruto_needed - payslip.bruto - bruto_pd + benefit_in_kind_employer_pays_taxes_amount
                if tools.float_compare(bruto_pdn, 0.0, precision_digits=2) > 0:
                    pdn_vals['amount'] = pdn_vals['amount'] + bruto_pdn

            vals += [pd_vals, pr_vals, pri_vals, pdn_vals]
        bonus_inputs = [b for b in vals if not tools.float_is_zero(b.get('amount', 0.0), precision_digits=2)]
        for bonus_input_vals in bonus_inputs:
            self.env['hr.payslip.input'].create(bonus_input_vals)


HrEmployeeBonus()
