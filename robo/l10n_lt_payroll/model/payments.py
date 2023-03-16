# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, fields, api, tools, exceptions, _
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo.tools import float_round, float_compare, float_is_zero

# def suma(self, employee_id, code, from_date, to_date=None):
#     if to_date is None:
#         to_date = datetime.now().strftime('%Y-%m-%d')
#     self._cr.execute("SELECT sum(case when hp.credit_note = False then (pl.total) else (-pl.total) end)\
#                 FROM hr_payslip as hp, hr_payslip_line as pl \
#                 WHERE hp.employee_id = %s AND hp.state = 'done' \
#                 AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pl.slip_id AND pl.code = %s",
#                      (employee_id, from_date, to_date, code))
#     res = self._cr.fetchone()
#     return res and res[0] or 0.0
#
#
# def suma_dd(self, employee_id, codes, from_date, to_date=None):
#     if to_date is None:
#         to_date = datetime.now().strftime('%Y-%m-%d')
#     self._cr.execute("SELECT sum(case when hp.credit_note = False then (pl.number_of_days) else (-pl.number_of_days) end)\
#                 FROM hr_payslip AS hp, hr_payslip_worked_days AS pl \
#                 WHERE hp.employee_id = %s AND hp.state = 'done' \
#                 AND hp.date_from >= '%s' AND hp.date_to <= '%s' AND hp.id = pl.payslip_id AND pl.code IN ('%s') " %
#                      (employee_id, from_date, to_date, "','".join(codes)))
#     res = self._cr.fetchone()
#     return res and res[0] or 0.0
#
#
# def suma_dv(self, employee_id, codes, from_date, to_date=None):
#     if to_date is None:
#         to_date = datetime.now().strftime('%Y-%m-%d')
#     self._cr.execute("SELECT sum(case when hp.credit_note = False then (pl.number_of_hours) else (-pl.number_of_hours) end)\
#                 FROM hr_payslip AS hp, hr_payslip_worked_days AS pl \
#                 WHERE hp.employee_id = %s AND hp.state = 'done' \
#                 AND hp.date_from >= '%s' AND hp.date_to <= '%s' AND hp.id = pl.payslip_id AND pl.code IN ('%s')" %
#                      (employee_id, from_date, to_date, "','".join(codes)))
#     res = self._cr.fetchone()
#     return res and res[0] or 0.0


def f_round(value, precision=2):
    """Float round -- precision digits=2"""
    return tools.float_round(value, precision_digits=precision)


class HrEmployeePayment(models.Model):

    _name = 'hr.employee.payment'
    _inherit = 'mail.thread'
    _description = _('Employee Payments')
    _order = 'name desc'

    def _serija(self):
        return self.env['ir.sequence'].next_by_code('MOK')

    def default_journal_id(self):
        return self.env.user.company_id.salary_journal_id

    def _saskaita_kreditas(self):
        return self.env.user.company_id.saskaita_kreditas or False

    def _saskaita_debetas(self):
        return self.env.user.company_id.saskaita_debetas or False

    def _saskaita_gpm(self):
        return self.env.user.company_id.saskaita_gpm or False

    def _saskaita_sodra(self):
        return self.env.user.company_id.saskaita_sodra or False

    def default_date(self):
        return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    # def default_date_from(self):
    #     return datetime(datetime.now().year, datetime.now().month, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    # def default_date_to(self):
    #     metai = datetime.now().year
    #     menuo = datetime.now().month
    #     return datetime(metai, menuo, calendar.monthrange(metai, menuo)[1]).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def default_currency(self):
        return self.env.user.company_id.currency_id

    def default_company(self):
        return self.env.user.company_id

    name = fields.Char(string='Numeris', default=_serija, copy=False, required=True)
    description = fields.Char(string='Apibūdinimas', states={'done': [('readonly', True)],
                                                         'cancel': [('readonly', True)]})
    state = fields.Selection([('cancel', 'Cancel'), ('draft', 'Preliminarus'), ('ready', 'Paruošta tvirtinimui'),
                              ('done', 'Patvirtinta')],
                             string='Būsena', default='ready', readonly=True, copy=False, required=True)
    type = fields.Selection([('holidays', 'Atostoginiai'),
                             ('allowance', 'Dienpinigiai'),
                             ('rent', 'NT nuoma'),
                             ('auto_rent', 'Auto nuoma'),
                             ('compensation', 'Kompensacija'),
                             ('other', 'Kiti')], required=True, default='other',
                            states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    company_id = fields.Many2one('res.company', string='Kompanija', default=default_company, required=True)
    contract_id = fields.Many2one('hr.contract', string='Kontraktas', states={'done': [('readonly', True)],
                                                                                 'cancel': [('readonly', True)]})
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', states={'done': [('readonly', True)],
                                                                                  'cancel': [('readonly', True)]})
    partner_id = fields.Many2one('res.partner', string='Partneris', states={'done': [('readonly', True)],
                                                                               'cancel': [('readonly', True)]}
                                 , required=True)
    date = fields.Date(string='Operacijos data', default=default_date, required=True, states={'done': [('readonly', True)],
                                                                                          'cancel': [('readonly', True)]})
    date_payment = fields.Date(string='Išmokėjimo data', default=default_date, required=True,
                               states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    date_from = fields.Date(string='Už periodą nuo', default=default_date, required=True,
                            states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    date_to = fields.Date(string='Už periodą iki', default=default_date, required=True,
                          states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    payment_line_ids = fields.One2many('hr.employee.payment.line', 'payment_id', states={'done': [('readonly', True)],
                                                                                         'cancel': [('readonly', True)]}, copy=True)
    currency_id = fields.Many2one('res.currency', string='Valiuta', default=default_currency,
                                  groups='base.group_multi_currency')
    amount_bruto = fields.Float(string='Bruto', digits=(2, 2), compute='_amount_bruto', store=True,
                                inverse='_inverse_amount',
                                states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    amount_paid = fields.Float(string='Neto', compute='_amount_paid', store=True, inverse='_inverse_amount',
                               states={'done': [('readonly', True)],
                                       'cancel': [('readonly', True)]})
    amount_gpm = fields.Float(string='GPM suma', states={'done': [('readonly', True)],
                                                            'cancel': [('readonly', True)]})
    amount_sdb = fields.Float(string='Darbuotojo sodra', states={'done': [('readonly', True)],
                                                                    'cancel': [('readonly', True)]})
    amount_sdd = fields.Float(string='Darbdavio sodra', states={'done': [('readonly', True)],
                                                                   'cancel': [('readonly', True)]})
    advanced_settings = fields.Boolean(string='Išplėstiniai nustatymai', store=False)
    journal_id = fields.Many2one('account.journal', string='Avansų žurnalas', default=default_journal_id,
                                 states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    saskaita_debetas = fields.Many2one('account.account', string='Sąnaudų sąskaita',
                                       domain="[('code','=like','6%')]", default=_saskaita_debetas,
                                       states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    saskaita_kreditas = fields.Many2one('account.account', string='Įsipareigojimų sąskaita',
                                       domain="[('code','=like','4%')]", default=_saskaita_kreditas,
                                        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    saskaita_gpm = fields.Many2one('account.account', string='GPM įsipareigojimų sąskaita',
                                   domain="[('code','=like','4%')]", default=_saskaita_gpm,
                                   states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    saskaita_sodra = fields.Many2one('account.account', string='Sodros sąskaita',
                                    domain="[('code','=like','4%')]", default=_saskaita_sodra,
                                    states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    code = fields.Char(string='Kodas', states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    include_in_payslip = fields.Boolean(string='Įtraukti į algalapį', states={'done': [('readonly', True)],
                                                                                 'cancel': [('readonly', True)]})
    account_move_id = fields.Many2one('account.move', string='Žurnalo įrašas', copy=False, readonly=True)
    account_move_ids = fields.Many2many('account.move', string='Žurnalo įrašai', copy=False, readonly=True)
    holidays_ids = fields.One2many('hr.holidays', 'payment_id', string='Holiday', readonly=True)
    a_klase_kodas_id = fields.Many2one('a.klase.kodas', string='A klasės kodas', states={'done': [('readonly', True)],
                                       'cancel': [('readonly', True)]})
    b_klase_kodas_id = fields.Many2one('b.klase.kodas', string='B klasės kodas', states={'done': [('readonly', True)],
                                       'cancel': [('readonly', True)]})
    periodic_id = fields.Many2one('hr.employee.payment.periodic', string='Pasikartojantis')
    periodic_ids = fields.One2many('hr.employee.payment.periodic', 'payment_id')

    theoretical_bruto = fields.Float(string='Teorinis bruto', compute='_compute_theoretical_gpm')
    theoretical_gpm = fields.Float(string='Teorinis GPM', compute='_compute_theoretical_gpm')
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analitinė sąskaita', states={'done': [('readonly', True)]})

    has_contract = fields.Boolean('Periode egzistuoja darbo sutartis', compute='_compute_has_contract')
    has_periodic_ids = fields.Boolean(compute='_has_periodic_ids')
    structured_payment_ref = fields.Char(string='Struktūruota mokėjimo paskirtis')

    @api.one
    def _has_periodic_ids(self):
        self.has_periodic_ids = True if self.periodic_ids else False

    @api.one
    @api.depends('partner_id', 'date_from', 'date_to')
    def _compute_has_contract(self):
        has_contract = True
        if self.partner_id and len(self.partner_id.with_context(active_test=False).employee_ids) != 0 and self.date_from and self.date_to:
            employee_id = self.partner_id.employee_ids
            if len(employee_id) > 1:
                employee_id = employee_id[0]
            has_contract = bool(self.env['hr.contract'].search_count([
                ('employee_id', '=', employee_id.id),
                ('date_start', '<=', self.date_to),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', self.date_from)
            ]) != 0)
        self.has_contract = has_contract

    @api.onchange('partner_id', 'date_from', 'date_to')
    def _onchange_set_has_contract(self):
        self._compute_has_contract()

    @api.multi
    def _get_theoretical_gpm(self):
        self.ensure_one()
        if self.type == 'holidays':
            contract = self.contract_id
            if not contract:
                return
            bruto = gpm = 0.0
            payment_slips = self.env['hr.payslip'].search([
                ('contract_id', '=', self.contract_id.id), ('payment_line_ids.payment_id', '=', self.id)
            ])
            payment_line_ids = self._context.get('force_payment_lines', self.payment_line_ids)
            for payment_line in payment_line_ids:
                # line_bruto = payment_line.amount_bruto
                # the_slip = payment_slips.filtered(lambda s:
                #                                   any(f_round(l.amount_bruto) == f_round(payment_line.amount_bruto) and
                #                                       f_round(l.amount_paid) == f_round(payment_line.amount_paid)
                #                                       for l in s.payment_line_ids
                #                                       )
                #                                   and s.date_from == payment_line.date_from
                #                                   and s.date_to == payment_line.date_to)
                # if len(the_slip) > 1:
                #     the_slip = the_slip.filtered(lambda s: self.id in s.mapped('payment_line_ids.payment_id').ids)
                # if the_slip and len(the_slip) == 1:
                #     total_npd = sum(the_slip.line_ids.filtered(lambda l: l.code == 'NPD').mapped('total'))
                #     total_bruto = sum(the_slip.line_ids.filtered(lambda l: l.code in ['MEN', 'VAL']).mapped('total'))
                #     holiday_npd = line_bruto / total_bruto * total_npd
                # else:
                #     holiday_npd = 0.0
                bruto += payment_line.amount_bruto
                # gpm_percentage = contract.with_context(date=payment_line.date_to).get_payroll_tax_rates(fields_to_get=['gpm_proc'])['gpm_proc']
                # line_gpm = max(0.0, line_bruto - holiday_npd) * gpm_percentage / 100.0
                gpm += payment_line.amount_gpm
            # for payment_line in self.payment_line_ids:
            #     paym_bruto, paym_gpm = contract.get_theoretical_bruto_gpm(payment_line.amount_paid, payment_line.date_to)
            #     bruto += paym_bruto
            #     gpm += paym_gpm
        else:
            bruto = self.amount_bruto
            gpm = self.amount_gpm
        return bruto, gpm

    @api.one
    def _compute_theoretical_gpm(self):
        self.theoretical_bruto, self.theoretical_gpm = self._get_theoretical_gpm()

    @api.onchange('type')
    def onchange_type(self):
        a_code = False
        gpm_account = False
        debit_account = False
        credit_account = False
        if self.type in ['rent', 'auto_rent']:
            a_code = '23' if self.type == 'rent' else '24'
            debit_account = self.env.ref('l10n_lt.1_account_455', raise_if_not_found=False)
            credit_account = self.env.ref('l10n_lt.account_account_6', raise_if_not_found=False)
            gpm_account = self.env.ref('l10n_lt.account_account_7', raise_if_not_found=False)
        elif self.type == 'other':
            credit_account = self.env.ref('l10n_lt.account_account_6', raise_if_not_found=False)
            gpm_account = self.env.ref('l10n_lt.account_account_7', raise_if_not_found=False)
        elif self.type == 'compensation':
            a_code = '08'
            debit_account = self.env.ref('l10n_lt.account_account_61', raise_if_not_found=False)
            credit_account = self.env.ref('l10n_lt.1_account_392', raise_if_not_found=False)
        else:
            self.saskaita_gpm = self._saskaita_gpm()
            self.saskaita_kreditas = self._saskaita_kreditas()
        if a_code:
            a_class_code = self.env['a.klase.kodas'].search([('code', '=', a_code)], limit=1)
            self.a_klase_kodas_id = a_class_code.id if a_class_code else False
        if gpm_account:
            self.saskaita_gpm = gpm_account.id
        if debit_account:
            self.saskaita_debetas = debit_account.id
        if credit_account:
            self.saskaita_kreditas = credit_account.id

    @api.onchange('partner_id')
    def onchange_partner_id(self):
        if len(self.partner_id.employee_ids) == 0:
            saskaita_kreditas = self.env.ref('l10n_lt.account_account_6', raise_if_not_found=False)
            if saskaita_kreditas:
                self.saskaita_kreditas = saskaita_kreditas
            saskaita_gpm = self.env.ref('l10n_lt.account_account_7', raise_if_not_found=False)
            if saskaita_gpm:
                self.saskaita_gpm = saskaita_gpm
        else:
            self.onchange_type()

    @api.onchange('amount_paid', 'type', 'date_from', 'employee_id', 'partner_id', 'a_klase_kodas_id')
    def onchange_amount_paid(self):
        neto = self.amount_paid
        calculation_date = self.date_from

        kwargs = {}

        # Find the contract
        contract = self.contract_id
        if not contract:
            employee = self.employee_id or (self.partner_id.employee_ids and self.partner_id.employee_ids[0])
            if employee:
                contracts = self.env['hr.contract'].search([
                    ('employee_id', '=', employee.id),
                    ('date_start', '<=', self.date_to),
                    '|',
                    ('date_end', '=', False),
                    ('date_end', '>=', self.date_from),
                ], order='date_start')
                contract = contracts[0] if contracts else None

        kwargs['contract'] = contract

        # Find appointment and the properties that the tax rates depend upon
        appointment = contract and contract.with_context(date=calculation_date).appointment_id
        if appointment:
            force_npd = None if appointment.use_npd else 0.0
            additional_sodra_type = appointment.sodra_papildomai and appointment.sodra_papildomai_type
            disability = appointment.invalidumas and appointment.darbingumas.name
            is_terminated_contract = contract.is_fixed_term
            is_foreign_resident = appointment.employee_id.is_non_resident
        else:
            force_npd = None
            additional_sodra_type = disability = is_terminated_contract = is_foreign_resident = False

        if not contract:
            contract = self.env['hr.contract']
        # Set GPM rate to rate unrelated to salary if the payment is not related to salary
        if self.type in ['rent', 'other', 'auto_rent']:
            du_unrelated_income_tax_percentage = contract.with_context(date=calculation_date).get_payroll_tax_rates(
                ['gpm_du_unrelated']
            )['gpm_du_unrelated']
            kwargs['gpm_proc'] = du_unrelated_income_tax_percentage
            kwargs['force_npd'] = 0.0

        # Only calculate SoDra amounts for a particular case
        if self.a_klase_kodas_id != self.env.ref('l10n_lt_payroll.a_klase_kodas_44', raise_if_not_found=False):
            # Force tax rates
            kwargs.update({
                'sodra_papild_proc': 0.0,
                'sodra_papild_exponential_proc': 0.0,
                'darbuotojo_sveikatos_proc': 0.0,
                'darbdavio_sodra_proc': 0.0,
                'darbuotojo_pensijos_proc': 0.0,
            })

        # Check forced zero taxes
        if self._context.get('force_zero_employee_sodra'):
            kwargs.update({
                'darbuotojo_pensijos_proc': 0.0,
                'darbuotojo_sveikatos_proc': 0.0,
                'sodra_papild_proc': 0.0,
                'sodra_papild_exponential_proc': 0.0,
            })
        if self._context.get('force_zero_employer_sodra'):
            kwargs['darbuotojo_sveikatos_proc'] = 0.0
        if self._context.get('force_zero_income_tax'):
            force_npd = 0.0
            kwargs.update({
                'gpm_proc': 0.0,
                'force_npd': 0.0
            })

        kwargs.update({
            'date': calculation_date,
            'npd_date': self.date_payment or calculation_date,
            'forced_tax_free_income': force_npd,
            'voluntary_pension': additional_sodra_type,
            'disability': disability,
            'is_fixed_term': is_terminated_contract,
            'is_foreign_resident': is_foreign_resident,
        })

        # First compute GROSS amount from NET amount
        gross_amount = self.env['hr.payroll'].convert_net_income_to_gross(neto, **kwargs)
        gross_amount = tools.float_round(gross_amount, precision_digits=2)

        # Get payroll values based on GROSS amount
        kwargs['bruto'] = gross_amount
        payroll_data = self.env['hr.payroll'].sudo().get_payroll_values(**kwargs)

        self.amount_bruto = gross_amount
        self.amount_gpm = payroll_data.get('gpm', 0.0)
        self.amount_sdb = payroll_data.get('employee_health_tax', 0.0) + \
                          payroll_data.get('employee_pension_tax', 0.0) + \
                          payroll_data.get('voluntary_sodra', 0.0)
        self.amount_sdd = payroll_data.get('darbdavio_sodra', 0.0)

    @api.onchange('a_klase_kodas_id')
    def onchange_a_klase_kodas_id(self):
        if self.a_klase_kodas_id == self.env.ref('l10n_lt_payroll.a_klase_kodas_44', raise_if_not_found=False):
            self.onchange_amount_paid()
        if self.a_klase_kodas_id == self.env.ref('l10n_lt_payroll.a_klase_kodas_70', raise_if_not_found=False):
            self.onchange_amount_paid()
            saskaita_kreditas = self.env.ref('l10n_lt.account_account_6', raise_if_not_found=False)
            if saskaita_kreditas:
                self.saskaita_kreditas = saskaita_kreditas
            saskaita_gpm = self.env.ref('l10n_lt.account_account_7', raise_if_not_found=False)
            if saskaita_gpm:
                self.saskaita_gpm = saskaita_gpm

    @api.multi
    def set_to_draft(self):
        for rec in self:
            if rec.state == 'cancel':
                if rec.type == 'holidays':
                    rec.state = 'draft'
                    rec.check_if_holiday_payment_ready()
                else:
                    rec.state = 'preliminary'
            else:
                raise exceptions.UserError(_('Negalima grąžinti į juodraštį neatšaukto įrašo. Pirmiau jį atšaukite'))

    @api.multi
    @api.constrains('contract_id', 'employee_id')
    def constrain_employee_contract(self):
        for rec in self.filtered('contract_id'):
            if rec.contract_id.employee_id != rec.employee_id:
                raise exceptions.ValidationError(_('Nustatytas netinkamas darbuotojas'))

    @api.multi
    @api.constrains('partner_id', 'employee_id')
    def constrain_employee_partner(self):
        for rec in self.filtered('employee_id'):
            if rec.employee_id.address_home_id != rec.partner_id and \
                    rec.employee_id.advance_accountancy_partner_id != rec.partner_id:
                raise exceptions.ValidationError(_('Nustatytas netinkamas partneris'))

    @api.multi
    def action_ready(self):
        for rec in self:
            if rec.state == 'draft':
                rec.state = 'ready'

    @api.multi
    @api.depends('payment_line_ids.amount_bruto')
    def _amount_bruto(self):
        for rec in self:
            rec.amount_bruto = sum(rec.payment_line_ids.mapped('amount_bruto'))

    @api.multi
    @api.depends('payment_line_ids.amount_paid')
    def _amount_paid(self):
        for rec in self:
            rec.amount_paid = sum(rec.payment_line_ids.mapped('amount_paid'))

    @api.multi
    def open_holiday_ids(self):
        action = self.env.ref('hr_holidays.open_department_holidays_approve')
        if len(self.holidays_ids) == 1:
            return {
                'id': action.id,
                'name': _('Atostogos'),
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'hr.holidays',
                'view_id': False,
                'type': 'ir.actions.act_window',
                'res_id': self.holidays_ids.id,
                'target': 'current',
                # 'domain': [('id', '=', self.account_move_id.id)],
            }
        else:
            return {
                'id': action.id,
                'name': action.name,
                # 'name': _('Atostogos'),
                'view_type': 'form',
                'view_mode': 'tree,form',
                'res_model': 'hr.holidays',
                'view_id': False,
                'type': 'ir.actions.act_window',
                'domain': [('id', 'in', self.holidays_ids.ids)],
            }

    # @api.onchange('employee_id')
    # def _change_accouts(self):
    #     self.saskaita_kreditas = self.company_id.saskaita_kreditas.id
    #     self.saskaita_debetas = self.company_id.saskaita_debetas.id
    #     self.saskaita_gpm = self.company_id.saskaita_gpm.id
    #     self.saskaita_sodra = self.company_id.saskaita_sodra.id
    #     self.currency_id = self.company_id.currency_id.id
    #     self.journal_id = self.company_id.salary_journal_id.id

    @api.multi
    def dk_irasai(self):
        if self.account_move_ids:
            return {
                'name': _('DK įrašai'),
                'view_type': 'form',
                'view_mode': 'tree,form',
                'res_model': 'account.move',
                'view_id': False,
                'type': 'ir.actions.act_window',
                'domain': [('id', 'in', self.account_move_ids.ids)],
            }
        else:
            return {
                'name': _('DK įrašai'),
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'account.move',
                'view_id': False,
                'type': 'ir.actions.act_window',
                'res_id': self.account_move_id.id,
            }

    @api.multi
    def dk_irasai_tree(self):
        if self.account_move_ids.mapped('line_ids'):
            return {
                'name': _('DK įrašų pasirinkimai'),
                'view_type': 'tree',
                'view_mode': 'list',
                'res_model': 'account.move.line',
                'view_id': False,
                'type': 'ir.actions.act_window',
                'domain': [('id', 'in', self.account_move_ids.mapped('line_ids.id'))],
            }
        elif self.account_move_id.line_ids:
            return {
                'name': _('DK įrašų pasirinkimai'),
                'view_type': 'tree',
                'view_mode': 'list',
                'res_model': 'account.move.line',
                'view_id': False,
                'type': 'ir.actions.act_window',
                'domain': [('id', 'in', self.account_move_id.line_ids.mapped('id'))],
            }
        else:
            return {
                'name': _('DK įrašai'),
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'account.move',
                'view_id': False,
                'type': 'ir.actions.act_window',
                'res_id': self.account_move_id.id,
            }

    def _inverse_amount(self):
        if self.type in ['holiday']:
            raise exceptions.UserError(_('Negalima keisti visos atostoginių sumos. Keiskite eilutės lygmenyje.'))
        else:
            vals = {'date_from': self.date,
                    'date_to': self.date,
                    'amount_paid': self.amount_paid,
                    'amount_bruto': self.amount_bruto}
            self.payment_line_ids = [(5,), (0, 0, vals)]

    def get_reference(self):
        ref = self.description or ''
        date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        if date_from_dt.day == 1 and date_from_dt + relativedelta(day=31) == date_to_dt:
            year = str(date_from_dt.year)
            month = str(date_from_dt.month) if date_from_dt.month >= 10 else '0' + str(date_from_dt.month)
            ref += ' (%s m. %s mėn.)' % (year, month)
        elif date_from_dt < date_to_dt:
            ref += ' (%s - %s)' % (self.date_from, self.date_to)
        else:
            ref += ' (%s)' % self.date_from
        return ref

    def get_move_vals(self):
        moves = []
        if self.type == 'holidays':
            for line in self.payment_line_ids:
                lines = []
                rounding = self.company_id.currency_id.rounding
                amount = float_round(line.amount_paid, precision_rounding=rounding)
                if float_is_zero(amount, precision_rounding=rounding):
                    raise exceptions.UserError(_('Negalima patvirtinti tuščio mokėjimo'))
                saskaita_kreditas = self.saskaita_kreditas.id
                saskaita_debetas = self.saskaita_debetas.id
                if not saskaita_kreditas:
                    raise exceptions.Warning(_('Nenurodyta DU įsipareigojimų sąskaita'))
                if not saskaita_debetas:
                    raise exceptions.Warning(_('Nenurodyta DU sąnaudų sąskaita'))
                journal_id = self.journal_id.id
                if not journal_id:
                    raise exceptions.Warning(_('Nenurodytas žurnalas'))
                saugomas = self.account_move_id
                date = datetime.strptime(line.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
                name = 'Atostoginiai %s m. %s mėn.' % (line.date_to[:4], line.date_to[5:7])
                company = self.journal_id.company_id
                date_maturity = (date + timedelta(days=company.salary_payment_day)).strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT)
                partneris = self.partner_id.id
                if len(saugomas) == 0:
                    base_line = {
                        'name': name,
                        'debit': 0.0,
                        'credit': 0.0,
                        'partner_id': partneris,
                        'analytic_account_id': self.account_analytic_id.id,
                    }
                    l_salary_c = base_line.copy()
                    l_salary_d = base_line.copy()
                    l_salary_c.update({
                        'credit': amount,
                        'account_id': saskaita_kreditas,
                        'date_maturity': date_maturity,
                        'a_klase_kodas_id': self.a_klase_kodas_id.id,
                        'b_klase_kodas_id': self.b_klase_kodas_id.id,
                    })
                    l_salary_d.update({
                        'debit': amount,
                        'account_id': saskaita_debetas,
                    })
                    lines += [(0, 0, l_salary_c), (0, 0, l_salary_d)]
                move_rec = {'line_ids': lines, 'journal_id': journal_id, 'date': line.date_to, 'ref': self.name}
                moves.append(move_rec)
        else:
            self.check_constrain_amount_paid()
            rounding = self.company_id.currency_id.rounding
            amount = float_round(self.amount_paid, precision_rounding=rounding)
            amount_gpm = float_round(self.amount_gpm, precision_rounding=rounding)
            amount_sodra_darbuotojo = float_round(self.amount_sdb, precision_rounding=rounding)
            amount_sodra_darbdavio = float_round(self.amount_sdd, precision_rounding=rounding)
            if float_is_zero(amount, precision_rounding=rounding):
                raise exceptions.UserError(_('Negalima patvirtinti tuščio mokėjimo'))
            saskaita_kreditas = self.saskaita_kreditas.id
            saskaita_debetas = self.saskaita_debetas.id
            if not saskaita_kreditas:
                raise exceptions.Warning(_('Nenurodyta DU įsipareigojimų sąskaita'))
            if not saskaita_debetas:
                raise exceptions.Warning(_('Nenurodyta DU sąnaudų sąskaita'))
            journal_id = self.journal_id.id
            if not journal_id:
                raise exceptions.Warning(_('Nenurodytas žurnalas'))
            data = self.date
            date_maturity = self.date_payment
            saugomas = self.account_move_id
            date = datetime.strptime(data, tools.DEFAULT_SERVER_DATE_FORMAT)
            year = str(date.year)
            month = str(date.month)
            if len(month) == 1:
                month = '0' + month
            name = (self.description or 'Išmokėjimas') + ' ' + year + ' m.' + month + u' mėn.'
            partneris = self.partner_id.id
            if len(saugomas) == 0:
                base_line = {
                    'name': name,
                    'debit': 0.0,
                    'credit': 0.0,
                    'partner_id': partneris,
                    'analytic_account_id': self.account_analytic_id.id,
                }
                l_salary_c = base_line.copy()
                l_salary_d = base_line.copy()
                l_salary_c.update({
                    'credit': amount,
                    'account_id': saskaita_kreditas,
                    'date_maturity': date_maturity,
                    'a_klase_kodas_id': self.a_klase_kodas_id.id,
                    'b_klase_kodas_id': self.b_klase_kodas_id.id,
                })
                l_salary_d.update({
                    'debit': amount,
                    'account_id': saskaita_debetas,
                })
                lines = []
                if float_compare(amount_gpm, 0, precision_rounding=rounding):
                    saskaita_gpm = self.saskaita_gpm.id or False
                    vmi_partner_id = self.env['hr.salary.rule'].search([('code', '=', 'GPM')],
                                                                       limit=1).register_id.partner_id.id
                    if not saskaita_gpm:
                        raise exceptions.UserError(_('Nenurodyta GPM sąskaita'))
                    l_salary_d['debit'] += amount_gpm
                    l_gpm = base_line.copy()
                    l_gpm.update({
                        'credit': amount_gpm,
                        'account_id': saskaita_gpm,
                        'partner_id': vmi_partner_id,
                        'a_klase_kodas_id': self.a_klase_kodas_id.id,
                        'b_klase_kodas_id': self.b_klase_kodas_id.id,
                    })
                    lines += [(0, 0, l_gpm)]
                if float_compare(amount_sodra_darbuotojo, 0, precision_rounding=rounding):
                    saskaita_sodra = self.saskaita_sodra.id
                    sodra_partner_id = self.env['hr.salary.rule'].search([('code', '=', 'SDD')],  # todo! Deeper too
                                                                         limit=1).register_id.partner_id.id
                    if not saskaita_sodra:
                        raise exceptions.UserError(_('Nenurodyta Sodros sąskaita'))
                    l_sodra_darbuotojo = base_line.copy()
                    l_sodra_darbuotojo.update({
                        'credit': amount_sodra_darbuotojo,
                        'account_id': saskaita_sodra,
                        'partner_id': sodra_partner_id,
                        'a_klase_kodas_id': self.a_klase_kodas_id.id,
                        'b_klase_kodas_id': self.b_klase_kodas_id.id,
                    })
                    l_sodra_darbuotojo_debetas = base_line.copy()
                    l_sodra_darbuotojo_debetas.update({
                        'debit': amount_sodra_darbuotojo,
                        'account_id': saskaita_debetas,
                        'partner_id': sodra_partner_id,
                        'a_klase_kodas_id': self.a_klase_kodas_id.id,
                        'b_klase_kodas_id': self.b_klase_kodas_id.id,
                    })
                    lines += [(0, 0, l_sodra_darbuotojo), (0, 0, l_sodra_darbuotojo_debetas)]
                if float_compare(amount_sodra_darbdavio, 0, precision_rounding=rounding):
                    saskaita_sodra = self.saskaita_sodra.id
                    sodra_partner_id = self.env['hr.salary.rule'].search([('code', '=', 'SDD')],
                                                                         limit=1).register_id.partner_id.id
                    if not saskaita_sodra:
                        raise exceptions.UserError(_('Nenurodyta Sodros sąskaita'))
                    l_sodra_darbdavio = base_line.copy()
                    l_sodra_darbdavio.update({
                        'credit': amount_sodra_darbdavio,
                        'account_id': saskaita_sodra,
                        'partner_id': sodra_partner_id,
                        'a_klase_kodas_id': self.a_klase_kodas_id.id,
                        'b_klase_kodas_id': self.b_klase_kodas_id.id,
                    })
                    l_sodra_darbdavio_debetas = base_line.copy()
                    l_sodra_darbdavio_debetas.update({
                        'debit': amount_sodra_darbdavio,
                        'account_id': saskaita_debetas,
                        'partner_id': sodra_partner_id,
                        'a_klase_kodas_id': self.a_klase_kodas_id.id,
                        'b_klase_kodas_id': self.b_klase_kodas_id.id,
                    })
                    lines += [(0, 0, l_sodra_darbdavio), (0, 0, l_sodra_darbdavio_debetas)]
                lines += [(0, 0, l_salary_c), (0, 0, l_salary_d)]
                ref = self.get_reference()
                move_rec = {'line_ids': lines, 'journal_id': journal_id, 'date': date, 'ref': ref}
                moves.append(move_rec)
                # mid = self.env['account.move'].create(move_rec)
                # mid.post()
                # if mid:
                #     rec.account_move_id = mid.id
        # rec.state = 'done'
        return moves

    @api.multi
    def atlikti(self):
        for rec in self:
            if rec.state == 'done':
                raise exceptions.Warning(_('Įrašas jau patvirtintas'))
            if rec.type == 'holidays':
                move_vals = rec.get_move_vals()
                for val in move_vals:
                    mid = self.env['account.move'].create(val)
                    mid.post()
                    rec.account_move_ids = [(4, mid.id,)]
            else:
                move_vals = rec.get_move_vals()
                for val in move_vals:  #should always be one
                    mid = self.env['account.move'].create(val)
                    mid.post()
                    rec.account_move_id = mid.id
            rec.state = 'done'

    @api.multi
    def create_bank_statement(self, show_front=False):
        """
        Method that creates corresponding 'mokejimu.eksportas'
        records and account.bank.statement records
        based on hr.employee.payment data.
        Show front indicates whether front.bank.statement
        record should be created or not
        :param show_front: True/False
        :return: None
        """
        self.ensure_one()
        payment = self.filtered(lambda r: r.state == 'done')
        partner_ids = payment.mapped('employee_id.address_home_id')
        potential_account_move_lines = payment.mapped('account_move_id.line_ids').filtered(
            lambda r: r.account_id.reconcile and not r.reconciled)
        company = self.env.user.company_id
        wage_accounts = payment.saskaita_kreditas | company.saskaita_kreditas
        gpm_accounts = payment.saskaita_gpm | company.saskaita_gpm
        sodra_accounts = payment.saskaita_sodra | company.saskaita_sodra
        payment_export_obj = self.env['mokejimu.eksportas']
        bank_journal = company.payroll_bank_journal_id
        bank_journal_id = company.payroll_bank_journal_id.id

        # Make dict with base data
        base_data = {
            'partner_ids': partner_ids.ids,
            'show_front': show_front,
            'structured_payment_ref': self.structured_payment_ref,
        }
        if not bank_journal_id:
            raise exceptions.UserError(_('Nenurodytas su DU susijęs banko žurnalas'))
        for wage_account in wage_accounts:
            account_move_line_ids = potential_account_move_lines.filtered(
                lambda r: r.account_id == wage_account and r.amount_residual != 0.0).ids
            if account_move_line_ids:
                name = _('Mokėjimas %s') % payment.name
                date_end_dt = datetime.strptime(payment.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
                search_date_from = (date_end_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                search_date_end = (date_end_dt + relativedelta(days=company.salary_payment_day)).strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT)
                # Prepare line data
                line_data = {
                    'name': name,
                    'account_ids': wage_account.ids,
                    'account_move_line_ids': account_move_line_ids,
                    'include_holidays': True,
                }
                # Copy base data dict, and extend it
                data = base_data.copy()
                data.update(line_data)
                # Create statement
                payment_export_obj.with_context(search_in_range=(search_date_from, search_date_end)).create_statement(
                    payment.date_from, payment.date_to, bank_journal_id, data)
        for gpm_account in gpm_accounts:
            gpm_move_lines = potential_account_move_lines.filtered(
                lambda r: r.account_id == gpm_account and r.amount_residual != 0.0)
            account_move_line_ids = potential_account_move_lines.filtered(
                lambda r: r.account_id == gpm_account and r.amount_residual != 0.0).ids
            if account_move_line_ids and float_compare(-sum(gpm_move_lines.mapped('amount_residual')), 10.0,
                                                       precision_rounding=bank_journal.currency_id.rounding or self.env.user.company_id.currency_id.rounding) >= 0:
                name = _('GPM mokėjimas %s') % payment.name
                line_data = {
                    'name': name,
                    'account_ids': gpm_account.ids,
                    'account_move_line_ids': account_move_line_ids,
                }
                # Copy base data dict, and extend it
                data = base_data.copy()
                data.update(line_data)
                # Create statement
                payment_export_obj.create_statement(payment.date_from, payment.date_to, bank_journal_id, data)
        for sodra_account in sodra_accounts:
            account_move_line_ids = potential_account_move_lines.filtered(lambda r: (r.account_id == sodra_account)
                                                                                    and r.amount_residual != 0.0).ids
            if account_move_line_ids:
                name = _('Sodros mokėjimas %s') % payment.name
                line_data = {
                    'name': name,
                    'account_ids': sodra_account.ids,
                    'account_move_line_ids': account_move_line_ids,
                }
                # Copy base data dict, and extend it
                data = base_data.copy()
                data.update(line_data)
                # Create statement
                payment_export_obj.create_statement(payment.date_from, payment.date_to, bank_journal_id, data)

    @api.multi
    def atsaukti(self):
        for rec in self:
            if rec.account_move_id:
                rec.account_move_id.button_cancel()
                rec.account_move_id.unlink()
            rec.account_move_ids.button_cancel()
            rec.account_move_ids.unlink()
            rec.state = 'ready'  # todo?

    @api.multi
    def unlink(self):
        for rec in self:
            if rec.state == 'done':
                raise exceptions.Warning(_('Negalima ištrinti patvirtinto įrašo.'))
            # if rec.holidays_ids:
            #     if len(rec.holidays_ids) == 1:
            #         if rec.holidays_ids.state == 'validate':
            #             raise exceptions.UserError(_('Negalima ištrinti atostogų mokėjimo.'))
        super(HrEmployeePayment, self).unlink()

    @api.one
    def check_if_holiday_payment_ready(self):
        if not self.holidays_ids:
            return
        date_payment = self.date
        ready_to_confirm = False
        code = self.code
        if code not in ['A']:
            return
        if code == 'A':
            date_payment_dt = datetime.strptime(date_payment, tools.DEFAULT_SERVER_DATE_FORMAT)
            relevant_vdu_date_froms = [date_payment_dt + relativedelta(months=-i, day=1) for i in range(1, 4)]
            relevant_vdu_date_froms = map(lambda r: r.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                                          relevant_vdu_date_froms)
            contract_date_start = self.contract_id.date_start
            relevant_vdu_date_froms = filter(lambda r: r >= contract_date_start, relevant_vdu_date_froms)
            domain = [
                ('employee_id', '=', self.employee_id.id),
                ('date_from', 'in', relevant_vdu_date_froms)
            ]
            if self.contract_id:
                related_contracts = self.contract_id.get_contracts_related_to_work_relation()
                domain += [
                    '|',
                    ('contract_id', '=', False),
                    ('contract_id', 'in', related_contracts.ids)
                ]
            num_vdu_records = self.env['employee.vdu'].search_count(domain)

            if num_vdu_records != len(relevant_vdu_date_froms):
                return
            ready_to_confirm = True
        if ready_to_confirm:
            self.action_ready()

    @api.multi
    def force_unlink(self):
        for rec in self:
            acc_move = rec.account_move_id
            acc_move.line_ids.remove_move_reconcile()
            acc_move.button_cancel()
            acc_move.unlink()
            rec.atsaukti()
            rec.unlink()

    @api.one
    def check_constrain_amount_paid(self):
        if self.type != 'holidays' and float_compare(self.amount_bruto,
                                                     self.amount_paid + self.amount_gpm + self.amount_sdb,
                                                     precision_rounding=self.currency_id.rounding) != 0:
            raise exceptions.Warning(_('Bruto dydis turi būti lygus sumokėtai neto, gpm ir darbuotojo sodros sumai'))

    @api.onchange('contract_id')
    def onchange_contract_id(self):
        if self.contract_id:
            self.employee_id = self.contract_id.employee_id.id

    @api.onchange('employee_id')
    def onchange_employee_id(self):
        if self.employee_id:
            self.partner_id = self.employee_id.address_home_id.id

    @api.multi
    def make_periodic(self):
        self.ensure_one()
        if self.state == 'done' and not self.periodic_ids and self.type not in ['holidays', 'allowance']:
            date = self.date
            date_dt = datetime.strptime(self.date, tools.DEFAULT_SERVER_DATE_FORMAT)
            cdate = datetime(datetime.utcnow().year, datetime.utcnow().month, datetime.utcnow().day)
            if (date_dt + relativedelta(months=1)) <= cdate:
                day = min([date_dt.day, (cdate+relativedelta(day=31)).day])
                date = datetime(cdate.year, cdate.month, day).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            periodic_id = self.env['hr.employee.payment.periodic'].create({
                'payment_id': self.id,
                'date': date,
            })
            periodic_id.set_next_date()
            self.periodic_id = periodic_id.id

    @api.multi
    def stop_periodic(self):
        self.ensure_one()
        if self.periodic_ids:
            self.periodic_ids.unlink()


HrEmployeePayment()


class HrEmployeePaymentLine(models.Model):

    _name = 'hr.employee.payment.line'

    payment_id = fields.Many2one('hr.employee.payment', readonly=True, required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', related='payment_id.company_id', compute_sudo=True, readonly=True)
    state = fields.Selection([('draft', 'Juodraštis'), ('done', 'Patvirtinta')], string='Būsena',
                             related='payment_id.state')
    date_from = fields.Date(string='Data nuo', required=True, states={'done': [('readonly', True)]})
    date_to = fields.Date(string='Data iki', required=True, states={'done': [('readonly', True)]})
    amount_bruto = fields.Float(string='Bruto', required=True, states={'done': [('readonly', True)]})
    amount_paid = fields.Float(string='Mokėtina suma', required=True, states={'done': [('readonly', True)]})
    amount_npd = fields.Float(string='NPD', required=True, states={'done': [('readonly', True)]}, default=0.0)
    amount_gpm = fields.Float(string='GPM', required=True, states={'done': [('readonly', True)]}, default=0.0)
    amount_sodra = fields.Float(string='SODRA', required=True, states={'done': [('readonly', True)]}, default=0.0)
    vdu = fields.Float(string='VDU')

    @api.multi
    @api.constrains('amount_bruto', 'amount_paid')
    def constrain_amount_nonnegative(self):
        rounding = self.env.user.company_id.currency_id.rounding
        for rec in self:
            if float_compare(rec.amount_bruto, 0, precision_rounding=rounding) < 0:
                raise exceptions.ValidationError(_('Bruto negali būti neigiama'))
            if float_compare(rec.amount_paid, 0, precision_rounding=rounding) < 0:
                raise exceptions.ValidationError(_('Mokėtina suma negali būti neigiama'))

    @api.multi
    @api.constrains
    def constrain_dates(self):
        for rec in self:
            if not rec.date_from <= rec.date_to:
                raise exceptions.ValidationError(_('Laikotarpio pradžia turi būti prieš paskutinę dieną'))


HrEmployeePaymentLine()


class HrEmployeePaymentPeriodic(models.Model):
    _name = 'hr.employee.payment.periodic'

    payment_id = fields.Many2one('hr.employee.payment', string='Mokėjimo šablonas', required=True)
    payment_ids = fields.One2many('hr.employee.payment', 'periodic_id', string='Sukurti mokėjimai')
    date = fields.Date(string='Kito mokėjimo data')
    date_stop = fields.Date(string='Sustabdyti nuo')
    action = fields.Selection(
        [('no', 'Netvirtinti'),
         ('open', 'Tvirtinti'),
         ('open_form', 'Tvirtinti ir formuoti pavedimą'),
         ('open_form_front', 'Tvirtinti, formuoti pavedimą ir siųsti ruošinį į banką'),
         ], help='Jei darbo užmokesčio banko žurnalas nepriklauso integruotiems bankams, '
                 'paskutinės opcijos atveju, ruošinys vis tiek bus suformuojamas.',
        string='Automatinis veiksmas', default='no', required=True
    )
    skip_payment_reconciliation = fields.Boolean(string='Išlaikyti originalias sumas')
    split_amount_in_proportion = fields.Boolean(string='Mokėjimo sumą skaidyti proporcingai')
    amount_base = fields.Float(string='Bazinė mokėjimo suma')
    partner_id = fields.Many2one(
        'res.partner', string='Partneris', related='payment_id.partner_id', store=True, readonly=True)

    @api.multi
    @api.constrains('action')
    def _check_action(self):
        """
        Constraints //
        If action is open_form or open_form_front, check
        whether company payroll bank account is set.
        :return: None
        """
        journal = self.env.user.company_id.payroll_bank_journal_id
        correct_bank = journal.bank_id and journal.bank_acc_number

        for rec in self:
            if rec.action in ['open_form', 'open_form_front'] and not correct_bank:
                raise exceptions.ValidationError(
                    _('Negalima formuoti pavedimo/ruošinio, nenustatytas kompanijos darbo '
                      'užmokesčio banko žurnalas arba neteisinga jo IBAN sąskaita.'))

    @api.multi
    def set_next_date(self):
        self.ensure_one()
        payment_date = datetime.strptime(self.payment_id.date, tools.DEFAULT_SERVER_DATE_FORMAT)
        payment_day = payment_date.day
        last_day_date = payment_date + relativedelta(day=31)
        if payment_date.day == last_day_date.day:
            last_day = True
        else:
            last_day = False
        date = datetime.strptime(self.date, tools.DEFAULT_SERVER_DATE_FORMAT)
        new_day = 31 if last_day else payment_day
        date += relativedelta(months=1, day=new_day)
        if self.date_stop and date > datetime.strptime(self.date_stop, tools.DEFAULT_SERVER_DATE_FORMAT):
            self.date = False
        else:
            self.date = date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    def run(self):
        payments_to_inform_about = self.env['hr.employee.payment.periodic']
        company = self.env.user.company_id
        lock_date = company.get_user_accounting_lock_date()
        for rec in self:
            if rec.date <= lock_date:
                payments_to_inform_about |= rec
                continue
            try:
                cdate = datetime.utcnow()
                stop_date = datetime.strptime(rec.date_stop, tools.DEFAULT_SERVER_DATE_FORMAT) if rec.date_stop \
                    else False
                if datetime.strptime(rec.date, tools.DEFAULT_SERVER_DATE_FORMAT) > cdate:
                    continue
                if stop_date and stop_date < cdate:
                    continue
                start_date = datetime.strptime(rec.date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(day=1)
                end_date = start_date + relativedelta(day=31)
                payment_values = {
                    'date': rec.date,
                    'date_payment': rec.date,
                    'date_from': start_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                    'date_to': end_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                }
                # If amount is split in proportion, the template payment is split as well
                # so base amount should be used instead
                if rec.split_amount_in_proportion and not tools.float_is_zero(rec.amount_base, precision_digits=2):
                    amount = rec.amount_base
                    last_monthly_payment = stop_date and stop_date.month == start_date.month
                    maternity_leaves = self.env['hr.holidays'].search([
                        ('employee_id', '=', rec.mapped('partner_id.employee_ids').ids),
                        ('holiday_status_id.kodas', '=', 'G'),
                        ('state', '=', 'validate'),
                        ('type', '=', 'remove'),
                    ])
                    # Split payment amount in proportion of days in a month
                    if last_monthly_payment or maternity_leaves:
                        calendar_number_of_days = (stop_date - start_date).days + 1
                        calendar_number_of_days_in_a_month = (end_date - start_date).days + 1
                        contract = rec.payment_id.employee_id.contract_id if rec.payment_id.employee_id else False
                        if contract:
                            number_of_days = contract.get_num_work_days(
                                start_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                                stop_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)) \
                                             or calendar_number_of_days
                            number_of_days_in_a_month = contract.get_num_work_days(
                                start_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                                end_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)) \
                                                        or calendar_number_of_days_in_a_month
                        else:
                            number_of_days = calendar_number_of_days
                            number_of_days_in_a_month = calendar_number_of_days_in_a_month

                        # Use work days if contract is found
                        number_of_days_on_leave = 0.0
                        for leave in maternity_leaves:
                            period_date_from = start_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                            period_date_to = end_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                            leave_date_from = max(leave.date_from_date_format, period_date_from)
                            leave_date_to = min(leave.date_to_date_format, period_date_to)
                            if contract:
                                number_of_days_on_leave += contract.get_num_work_days(leave_date_from, leave_date_to)
                            else:
                                leave_date_to_dt = datetime.strptime(leave_date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
                                leave_date_from_dt = datetime.strptime(leave_date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                                number_of_days_on_leave += (leave_date_to_dt - leave_date_from_dt).days + 1
                        number_of_days -= number_of_days_on_leave
                        number_of_days = max(number_of_days, 0.0)
                        amount = rec.amount_base * float(number_of_days) / float(number_of_days_in_a_month)  # P3:DivOK
                    payment_values.update({
                        'amount_paid': amount,
                    })
                payment_template = rec.payment_id
                payment_id = payment_template.copy(payment_values)
                context = self._context.copy()

                # Determine if some of the taxes should be zero
                context.update({
                    'force_zero_income_tax': tools.float_is_zero(payment_template.amount_gpm, precision_digits=2),
                    'force_zero_employer_sodra': tools.float_is_zero(payment_template.amount_sdd, precision_digits=2),
                    'force_zero_employee_sodra': tools.float_is_zero(payment_template.amount_sdb, precision_digits=2)
                })

                payment_id.with_context(context).onchange_amount_paid()
                if rec.action in ['open', 'open_form', 'open_form_front']:
                    payment_id.atlikti()
                if rec.action in ['open_form', 'open_form_front']:
                    # Determine whether front bank statement should be created
                    show_front = rec.action == 'open_form_front'
                    payment_id.with_context(
                        skip_payment_reconciliation=rec.skip_payment_reconciliation
                    ).create_bank_statement(show_front=show_front)
                rec.set_next_date()
                self._cr.commit()
            except:
                import traceback
                message = traceback.format_exc()
                self._cr.rollback()
                if message:
                    self.env['robo.bug'].sudo().create({
                        'user_id': self.env.user.id,
                        'error_message': message,
                        'subject': 'Failed to create periodic payment [%s]' % self._cr.dbname,
                    })
                    self._cr.commit()

        if payments_to_inform_about:
            try:
                ticket_obj = self.env['mail.thread'].sudo()._get_ticket_rpc_object()
                subject = 'Nepavyko sukurti periodinio mokėjimo dėl užrakinimo datos [%s]' % self._cr.dbname
                body = """
                Nepavyko sukurti periodinių mokėjimų, nes data patenka į užrakintą apskaitos laikotarpį.\n
                Darbuotojai:\n\n
                """

                body += ', '.join(payments_to_inform_about.mapped('partner_id.name'))

                vals = {
                    'ticket_dbname': self.env.cr.dbname,
                    'ticket_model_name': self._name,
                    'ticket_record_id': False,
                    'name': subject,
                    'ticket_user_login': self.env.user.login,
                    'ticket_user_name': self.env.user.name,
                    'description': body,
                    'ticket_type': 'accounting',
                    'user_posted': self.env.user.name
                }

                res = ticket_obj.create_ticket(**vals)
                if not res:
                    raise exceptions.UserError('The distant method did not create the ticket.')
            except Exception as e:
                message = 'Failed to create ticket for periodic payment check.\nException: %s' % (str(e.args))
                self.env['robo.bug'].sudo().create({
                    'user_id': self.env.user.id,
                    'error_message': message,
                })

    @api.model
    def cron_create_periodic_payments(self):
        cdate = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        periodic_ids = self.search([('date', '<=', cdate),
                                    '|',
                                        ('date_stop', '=', False),
                                        ('date_stop', '>', cdate)])
        periodic_ids.run()

    @api.multi
    def delete(self):
        self.ensure_one()
        self.unlink()

    @api.multi
    def open_payments(self):
        self.ensure_one()
        if self.payment_ids:
            action = self.env.ref('l10n_lt_payroll.action_holiday_pay').read()[0]
            action['domain'] = [('periodic_id', '=', self.id)]
            return action
        else:
            raise exceptions.Warning(_('Dar nėra sukurtų periodinių mokėjimų.'))


HrEmployeePaymentPeriodic()
