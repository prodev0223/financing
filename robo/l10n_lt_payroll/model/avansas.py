# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions
from odoo.tools.translate import _
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
import calendar
from odoo.tools import float_round


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


class Avansas(models.Model):
    _name = 'darbo.avansas'
    _order = 'name desc'

    def _serija(self):
        return self.env['ir.sequence'].next_by_code('AVANSAS')

    def _zurnalas(self):
        advance_payment_journal = self.env['account.journal'].search([('code', '=', 'AVN')], limit=1) or False
        if not advance_payment_journal:
            advance_payment_journal = self.env['account.journal'].search([('code', '=', 'ATLY')]) or False
        return advance_payment_journal

    def _saskaita_kreditas(self):
        return self.env.user.company_id.saskaita_kreditas.id or False

    def _saskaita_debetas(self):
        return self.env.user.company_id.employee_advance_account.id or False

    def _op_data(self):
        return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _pradzia(self):
        return datetime(datetime.utcnow().year, datetime.utcnow().month, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _pabaiga(self):
        metai = datetime.utcnow().year
        menuo = datetime.utcnow().month
        return datetime(metai, menuo, calendar.monthrange(metai, menuo)[1]).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _valiuta(self):
        user = self.env.user
        if user.company_id:
            return user.company_id.currency_id
        else:
            valiuta = self.env['res.currency'].search([('rate', '=', 1.0)])
            if valiuta:
                return valiuta

    def _get_original_selection(self):
        return self.env['res.company']._fields['avansu_politika'].selection

    def default_kompanija(self):
        return self.env.user.company_id

    name = fields.Char(string='Numeris', default=_serija)
    company_id = fields.Many2one('res.company', string='Kompanija', required=True, default=default_kompanija)
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', required=True,
                                  states={'done': [('readonly', True)]})
    contract_id = fields.Many2one('hr.contract', string='Kontraktas', required=True,
                                  states={'done': [('readonly', True)]}, domain="[('employee_id','=',employee_id)]")
    operation_date = fields.Date(string='Operacijos data', default=_op_data, required=True,
                                 states={'done': [('readonly', True)]})
    date_from = fields.Date(string='Už periodą nuo', default=_pradzia, required=True,
                            states={'done': [('readonly', True)]})
    date_to = fields.Date(string='Už periodą iki', default=_pabaiga, required=True,
                          states={'done': [('readonly', True)]})
    currency_id = fields.Many2one('res.currency', string='Valiuta', default=_valiuta,
                                  groups='base.group_multi_currency')
    suma = fields.Float(string='Suma', digits=(2, 2), compute='_suma', store=True)
    advanced_settings = fields.Boolean(string='Išplėstiniai nustatymai', store=True,
                                       states={'done': [('readonly', True)]})
    journal_id = fields.Many2one('account.journal', string='Avansų žurnalas', default=_zurnalas, required=True,
                                 states={'done': [('readonly', True)]})
    saskaita_kreditas = fields.Many2one('account.account', string='DU įsipareigojimų sąskaita',
                                        default=_saskaita_kreditas,
                                        required=True, states={'done': [('readonly', True)]})
    saskaita_debetas = fields.Many2one('account.account', string='Avansinių išmokų sąskaita',
                                       default=_saskaita_debetas,
                                       required=True, states={'done': [('readonly', True)]})
    state = fields.Selection([('draft', 'Juodraštis'), ('done', 'Patvirtinta')], string='Būsena',
                             default='draft')
    account_move_id = fields.Many2one('account.move', string='Žurnalo įrašas', copy=False, required=False)
    avansu_suvestine = fields.Many2one('avansai.run', string='Avansų suvestinė', copy=False, required=False,
                                       states={'done': [('readonly', True)]})
    avansu_politika_suma = fields.Float(string='Avanso dydis (neto)', digits=(2, 2), default=0.0,
                                        states={'done': [('readonly', True)]})
    procentas = fields.Float(string='Atlyginimo proc.',
                             default=lambda self: self.env.user.company_id.avansu_politika_proc,
                             required=False, states={'done': [('readonly', True)]})
    avansu_politika = fields.Selection(selection=_get_original_selection, string='Avansų politika', default='fixed_sum',
                                       states={'done': [('readonly', True)]})
    algalapio_suma = fields.Float(string='Suma eksportui į algalapį', compute='_algalapio_suma', store=True,
                                  readonly=True)
    type = fields.Selection([('advance', 'Advance'), ('allowance', 'Allowance')], string='Type',
                            default='advance', required=True, states={'done': [('readonly', True)]},
                            help='If selected "advance", amount will be deducted from salary')
    included_in_payslip = fields.Boolean(string='Included in payslip', compute='_included_in_payslip', store=True)

    theoretical_bruto = fields.Float(string='Teorinis bruto', compute='_compute_theoretical_gpm')
    theoretical_gpm = fields.Float(string='Teorinis GPM', compute='_compute_theoretical_gpm')
    statement_id = fields.Many2one('account.bank.statement', string='Banko ruošinys', readonly=True)

    @api.one
    def _compute_theoretical_gpm(self):
        if not self.contract_id:
            return
        bruto, gpm = self.contract_id.get_theoretical_bruto_gpm(self.suma, self.date_to)
        self.theoretical_bruto = bruto
        self.theoretical_gpm = gpm

    @api.one
    @api.depends('included_in_payslip', 'suma')
    def _algalapio_suma(self):
        self.algalapio_suma = self.included_in_payslip and self.suma or 0

    @api.multi
    def get_sum(self):
        self.ensure_one()
        if self.avansu_politika == 'fixed_sum':
            res = self.avansu_politika_suma
        else:
            # for future cases
            res = 0
        return res

    @api.onchange('contract_id', 'avansu_politika')
    def change_avansu_politika(self):
        if self.contract_id and self.avansu_politika == 'fixed_sum':
            appointment = self.env['hr.contract.appointment'].search([('contract_id', '=', self.contract_id.id),
                                                                      ('date_start', '<=', self.date_from),
                                                                      '|',
                                                                      ('date_end', '=', False),
                                                                      ('date_end', '>=', self.date_to),
                                                                      ], limit=1)
            if appointment:
                self.suma = appointment.avansu_politika_suma

    @api.multi
    @api.depends('avansu_politika', 'avansu_politika_suma')
    def _suma(self):
        for rec in self:
            if rec.avansu_politika == 'fixed_sum':
                rec.suma = rec.get_sum()

    @api.multi
    @api.depends('type')
    def _included_in_payslip(self):
        for rec in self:
            if rec.type == 'advance':
                rec.included_in_payslip = True
            else:
                rec.included_in_payslip = False

    @api.onchange('employee_id')
    def onchange_employee(self):
        self.contract_id = self.employee_id.contract_id.id

    @api.multi
    @api.constrains('employee_id', 'contract_id')
    def costrain_contract(self):
        if self.filtered(lambda r: r.contract_id.employee_id != r.employee_id):
            raise exceptions.ValidationError(_('Darbuotojas neatitinka kontrakto darbuotojo'))

    @api.multi
    @api.constrains('employee_id')
    def _check_if_contains_contract(self):
        for rec in self:
            if not rec.employee_id.contract_id:
                raise exceptions.ValidationError(_('Darbuotojas neturi kontrakto.'))

    @api.multi
    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from:
                date_from = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                if date_from != datetime(date_from.year, date_from.month, 1):
                    raise exceptions.ValidationError(
                        _('Periodo pradžia ir pabaiga privalo būti pirma ir paskutinė mėnesio dienos!'))
            if rec.date_to and rec.date_from:
                date_to = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_from = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                if date_to != datetime(date_from.year, date_from.month,
                                       calendar.monthrange(date_from.year, date_from.month)[1]):
                    raise exceptions.ValidationError(
                        _('Periodo pradžia ir pabaiga privalo būti pirma ir paskutinė mėnesio dienos!'))

    @api.multi
    def copy(self, default=None):
        if default is None:
            default = {}
        default['name'] = self.env['ir.sequence'].next_by_code('AVANSAS')
        return super(Avansas, self).copy(default=default)

    @api.multi
    def dk_irasai(self):
        return {
            'name': _('DK įrašai'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.move',
            'view_id': False,
            'type': 'ir.actions.act_window',
            # 'domain': [('id', '=', self.account_move_id.id)],
            'res_id': self.account_move_id.id,
        }

    @api.multi
    def atlikti(self):
        for rec in self:
            rec._check_contract_end_date()
            suma_nevirsija = rec.check_if_advance_not_too_big()
            if not suma_nevirsija:
                raise exceptions.Warning(_('Avanso negalima mokėti, nes viršytų mėnesinį atlyginimą'))
            # employee = rec.employee_id.name
            amount = rec.suma
            if tools.float_is_zero(amount, precision_digits=2):
                return False
            saskaita_kreditas = rec.saskaita_kreditas.id or False
            saskaita_debetas = rec.saskaita_debetas.id or False
            zurnalas = rec.journal_id.id
            if not zurnalas:
                raise exceptions.Warning(_('Nenurodytas žurnalas'))

            data = rec.operation_date
            saugomas = rec.account_move_id
            name = u'Avansas %s m. %s mėn.' % (data[:4], data[5:7])
            ref = u'Darbo užmokesčio ' + name.lower()
            if rec.employee_id.address_home_id:
                partneris = rec.employee_id.address_home_id.id
            elif rec.employee_id.user_id and rec.employee_id.user_id.partner_id:
                partneris = rec.employee_id.user_id.partner_id.id
            else:
                partneris = False
            # company_id = rec.journal_id.company_id.id
            if len(saugomas) == 0:
                base_line = {
                    'name': name,
                    'debit': 0.0,
                    'credit': 0.0,
                    # 'date': date,
                    'partner_id': partneris,
                    # 'company_id': company_id,
                }
                l_salary_c = base_line.copy()
                l_salary_d = base_line.copy()
                l_salary_c.update({
                    'credit': amount,
                    'account_id': saskaita_kreditas,
                    'a_klase_kodas_id': self.env.ref('l10n_lt_payroll.a_klase_kodas_1').id
                })
                l_salary_d.update({
                    'debit': amount,
                    'account_id': saskaita_debetas,
                })

                lines = [(0, 0, l_salary_c), (0, 0, l_salary_d)]

                # date_dt = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                # year = str(date_dt.year)
                # month = str(date_dt.month) if date_dt.month >= 10 else '0' + str(date_dt.month)
                move_rec = {'line_ids': lines,
                            'journal_id': zurnalas,
                            'date': data,
                            'ref': ref,
                            'name': ref}
                mid = self.env['account.move'].create(move_rec)
                mid.post()
                if mid:
                    rec.account_move_id = mid.id
            rec.state = 'done'
        account_move_lines = self.mapped('account_move_id.line_ids')
        export_wizard_data = account_move_lines.call_multiple_invoice_export_wizard()
        wizard_id = export_wizard_data.get('res_id', False)
        if wizard_id:
            wizard = self.env['account.invoice.export.wizard'].browse(wizard_id)
            wizard.write({'journal_id': self.env.ref('base.main_company').payroll_bank_journal_id.id})
            bank_statement_data = wizard.create_bank_statement()
            bank_statement_id = bank_statement_data.get('res_id', False)
            if bank_statement_id:
                bank_statement = self.env['account.bank.statement'].browse(bank_statement_id)
                bank_statement.write({'name': _('Darbo užmokesčio avansai')})
                self.write({'statement_id': bank_statement.id})
                if self._context.get('show_front'):
                    bank_statement.show_front()

    @api.multi
    def atsaukti(self):
        for rec in self:
            if rec.account_move_id:
                rec.account_move_id.button_cancel()
                rec.account_move_id.unlink()
            rec.state = 'draft'
            statement = rec.statement_id
            if statement:
                front_statements = statement.front_statements
                viewed_front_statements = front_statements.filtered(lambda s: s.state == 'viewed')
                other_front_statements = front_statements.filtered(lambda s: s.state != 'viewed')
                other_front_statements.unlink()
                if not viewed_front_statements:
                    statement.unlink()

    @api.model
    def create_atsaukti_action(self):
        action = self.env.ref('l10n_lt_payroll.advance_payment_cancel_all')
        if action:
            action.create_action()

    @api.multi
    def unlink(self):
        for rec in self:
            if rec.state == 'done':
                raise exceptions.Warning(_('Negalima ištrinti patvirtinto įrašo.'))
        super(Avansas, self).unlink()

    @api.one
    def _check_contract_end_date(self):
        if self.contract_id.date_start > self.date_to or self.contract_id.date_end and self.contract_id.date_end < self.date_from:
            raise exceptions.UserError(_('Negalima patvirtinti avanso kitam laikotarpiui, nei darbo sutartis.'))

    @api.multi  # todo
    def check_if_advance_not_too_big(self):
        return True
    #     self.ensure_one()
    #     advance_size = self.suma
    #     amount_period_total = self.contract_id.with_context(date_from=self.date_from).neto_monthly
    #     amount_paid_in_advances = sum(self.env['darbo.avansas'].search([('contract_id', '=', self.contract_id.id),
    #                                                                     ('date_from', '=', self.date_from),
    #                                                                     ('date_to', '=', self.date_to),
    #                                                                     ('state', '=', 'done')]).mapped('suma'))
    #     amount_paid_holidays = sum(self.env['hr.employee.payment.line'].
    #                                search([('payment_id.contract_id', '=', self.contract_id.id),
    #                                        ('payment_id.state', '=', 'done'),
    #                                        ('date_from', '=', self.date_from),
    #                                        ('date_to', '=', self.date_to)]).mapped('amount'))
    #     amount_left_to_pay = amount_period_total - amount_paid_in_advances - amount_paid_holidays
    #     if advance_size <= amount_left_to_pay:
    #         return True
    #     else:
    #         return False


Avansas()


class AvansaiRun(models.Model):
    _name = 'avansai.run'
    _order = 'name desc'

    def _serija(self):
        return self.env['ir.sequence'].next_by_code('AVANSAI')

    def _zurnalas(self):
        return self.env['account.journal'].search([('code', '=', 'ATLY')]) or False

    def _saskaita_kreditas(self):
        return self.env.user.company_id.employee_advance_account.id or False

    def _saskaita_debetas(self):
        return self.env.user.company_id.saskaita_kreditas.id or False

    def _saskaita_sodra(self):
        return self.env.user.company_id.saskaita_sodra.id or False

    def _op_data(self):
        return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _pradzia(self):
        return datetime(datetime.utcnow().year, datetime.utcnow().month, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _pabaiga(self):
        metai = datetime.utcnow().year
        menuo = datetime.utcnow().month
        return datetime(metai, menuo, calendar.monthrange(metai, menuo)[1]).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def default_kompanija(self):
        return self.env.user.company_id

    name = fields.Char(string='Numeris', default=_serija)
    company_id = fields.Many2one('res.company', string='Kompanija', required=True, default=default_kompanija)
    employee_ids = fields.Many2many('hr.employee', string='Darbuotojai', required=True,
                                    states={'done': [('readonly', True)]})
    operation_date = fields.Date(string='Operacijos data', default=_op_data, required=True,
                                 states={'done': [('readonly', True)]})
    date_from = fields.Date(string='Už periodą nuo', default=_pradzia, required=True,
                            states={'done': [('readonly', True)]})
    date_to = fields.Date(string='Už periodą iki', default=_pabaiga, required=True,
                          states={'done': [('readonly', True)]})
    journal_id = fields.Many2one('account.journal', string='Avansų žurnalas', default=_zurnalas, required=True,
                                 states={'done': [('readonly', True)]})
    advanced_settings = fields.Boolean(string='Advanced settings', store=False)
    saskaita_kreditas = fields.Many2one('account.account', string='Avanso sąskaita',
                                        default=_saskaita_kreditas, required=True,
                                        states={'done': [('readonly', True)]})
    saskaita_debetas = fields.Many2one('account.account', string='Avansinių išmokų sąskaita',
                                       default=_saskaita_debetas, required=True, states={'done': [('readonly', True)]})
    saskaita_gpm = fields.Many2one('account.account', string='GPM sąskaita',
                                   domain="[('code','=like','4%'),('reconcile','=',False)]",
                                   states={'done': [('readonly', True)]})  # todo remove
    saskaita_sodra = fields.Many2one('account.account', string='Iš DU mokėtina sodros sąskaita',
                                     states={'done': [('readonly', True)]})  # todo remove
    state = fields.Selection([('draft', 'Juodraštis'), ('done', 'Patvirtinta')], string='Būsena',
                             default='draft')
    avansai = fields.One2many('darbo.avansas', 'avansu_suvestine', string='Avansai', required=False,
                              states={'done': [('readonly', True)]})

    @api.multi
    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from:
                date_from = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                if date_from != datetime(date_from.year, date_from.month, 1):
                    raise exceptions.ValidationError(
                        _('Periodo pradžia ir pabaiga privalo būti pirma ir paskutinė mėnesio dienos!'))
            if rec.date_from and rec.date_to:
                date_to = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_from = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                if date_to != datetime(date_from.year, date_from.month,
                                       calendar.monthrange(date_from.year, date_from.month)[1]):
                    raise exceptions.ValidationError(
                        _('Periodo pradžia ir pabaiga privalo būti pirma ir paskutinė mėnesio dienos!'))

    @api.multi
    def copy(self, default=None):
        if default is None:
            default = {}
        default['avansai'] = False
        default['name'] = self.env['ir.sequence'].next_by_code('AVANSAI')
        return super(AvansaiRun, self).copy(default=default)

    @api.multi
    def atlikti(self):
        for rec in self:
            if rec.employee_ids:
                data = rec.operation_date
                date_from = rec.date_from
                date_to = rec.date_to
                zurnalo_id = rec.journal_id.id or False
                saskaita_kreditas = rec.saskaita_kreditas.id or False
                saskaita_debetas = rec.saskaita_debetas.id or False
                # saskaita_gpm = rec.saskaita_gpm.id or False

                avansai = []

                sugeneruoti_avansai = rec.avansai.mapped('contract_id.id') or []
                nr = 1
                contract_ids = self.env['hr.contract'].search([('employee_id', 'in', self.employee_ids.mapped('id')),
                                                               ('date_start', '<=', self.date_to),
                                                               '|',
                                                               ('date_end', '=', False),
                                                               ('date_end', '>=', self.date_from)])
                for contract in contract_ids:
                    if contract.id in sugeneruoti_avansai:
                        continue

                    if contract.date_end and \
                            datetime.strptime(contract.date_end, tools.DEFAULT_SERVER_DATE_FORMAT) < \
                            datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT):
                        continue

                    # resursas = self.env['hr.payslip'].get_worked_day_lines([contract.id], date_from, date_to)
                    # stopas = False
                    # if not resursas:
                    #     stopas = True
                    # for res in resursas:
                    #     if res['code'] == 'FD' and (res['number_of_days'] <= 0.0 or not res['number_of_days']):
                    #         stopas = True

                    # if stopas:
                    #     continue
                    str_nr = str(nr).zfill(8)
                    avanso_irasas = {
                        'name': 'TEMP-' + str_nr,
                        'operation_date': data,
                        'date_from': date_from,
                        'date_to': date_to,
                        'journal_id': zurnalo_id,
                        'saskaita_kreditas': saskaita_kreditas,
                        'saskaita_debetas': saskaita_debetas,
                        # 'saskaita_gpm': saskaita_gpm,
                        'employee_id': contract.employee_id.id,
                        'contract_id': contract.id,
                    }

                    aid = self.env['darbo.avansas'].create(avanso_irasas)
                    aid.suma = aid.get_sum()
                    nr += 1
                    if aid:
                        if aid.suma == 0.0:
                            aid.unlink()
                        else:
                            aid.name = self.env['ir.sequence'].next_by_code('AVANSAS')
                            avansai.append(aid.id)
                avansai = self.env['darbo.avansas'].browse(avansai)
                avansai.write({'avansu_suvestine': rec.id})
                # rec.avansai = [(6, 0, avansai)]
                rec.state = 'done'

    @api.multi
    def patvirtinti(self):
        for rec in self:
            rec.avansai.filtered(lambda a: a.state == 'draft').atlikti()

    @api.multi
    def atsaukti(self):
        for rec in self:
            rec.state = 'draft'

    @api.multi
    def unlink(self):
        for rec in self:
            if rec.state == 'done':
                raise exceptions.Warning(_('Negalima atšaukti patvirtinto įrašo.'))
        super(AvansaiRun, self).unlink()

    @api.model
    def cron_avansu_generavimas(self):
        current_date = datetime.utcnow()
        company_ids = self.env['res.company'].search([])
        for company in company_ids:
            company_id = company.id
            journal_id = company.advance_journal_id.id
            generated_advances = self.env['darbo.avansas']
            year, month = current_date.year, current_date.month
            day_generate = company.advance_payment_day
            day_generate_date = datetime(year, month, 1) + relativedelta(day=day_generate)
            closest_work_days = self.env['hr.contract'].closest_work_dates(day_generate_date, True)
            previous_work_day = closest_work_days.get('previous', day_generate_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
            day_generate = datetime.strptime(previous_work_day, tools.DEFAULT_SERVER_DATE_FORMAT).day
            date_from = datetime(year, month, 1)
            last_day_of_month = (date_from + relativedelta(day=31)).day
            if current_date.day == day_generate or (current_date.day == last_day_of_month and day_generate > current_date.day):
                pass
            else:
                return
            date_from_str = date_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            try:
                date_to_str = datetime(year, month, day_generate).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            except ValueError:
                date_to_str = datetime(year, month, 15).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            contracts = self.env['hr.contract'].search(
                [('date_start', '<=', date_from_str), '|', ('date_end', '=', False),
                 ('date_end', '>=', date_to_str), ('company_id', '=', company_id)])
            advance_date_from = date_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            advance_date_to = (date_from + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            existing_advances = self.env['darbo.avansas'].search([('contract_id', 'in', contracts.mapped('id')),
                                                                  ('date_from', '=', advance_date_from),
                                                                  ('date_to', '=', advance_date_to),
                                                                  ('company_id', '=', company_id)])
            holidays = self.env['hr.holidays'].search([
                ('contract_id', 'in', contracts.mapped('id')),
                ('state', '=', 'validate'),
                ('holiday_status_id.kodas', 'in', ['A', 'L', 'N', 'NS', 'MA', 'KA', 'G', 'TA', 'VP', 'KR']),
                ('date_from', '<=', date_to_str),
                ('date_to', '>=', date_from_str)
            ])
            contracts_on_leaves = self.env['hr.contract']
            for contract in contracts:
                contract_appointment = self.env['hr.contract.appointment'].search([
                    ('contract_id', '=', contract.id),
                    ('date_start', '<=', date_to_str),
                    '|',
                    ('date_end', '=', False),
                    ('date_end', '>=', date_from_str)
                ], order='date_start asc',  # get an earlier appointment in case of two appointments as a result
                    limit=1)
                advance_amount = contract_appointment.avansu_politika_suma
                rounding = company.currency_id.rounding
                amount = float_round(advance_amount, precision_rounding=rounding)
                if amount == 0:
                    continue
                contract_holidays = holidays.filtered(lambda h: h.contract_id.id == contract.id)
                if contract_holidays:
                    contracts_on_leaves |= contract
                    continue
                existing_advance = existing_advances.filtered(lambda a: a.contract_id.id == contract.id)
                if existing_advance:
                    continue
                if not contract_appointment:
                    continue
                if not journal_id:
                    continue

                advance_vals = {'date_from': advance_date_from,
                                'date_to': advance_date_to,
                                'operation_date': date_to_str,
                                'contract_id': contract.id,
                                'employee_id': contract.employee_id.id,
                                'avansu_politika': contract_appointment.avansu_politika,
                                'avansu_politika_suma': contract_appointment.avansu_politika_suma,
                                'journal_id': journal_id,
                                'company_id': company_id,
                                }
                new_advance = self.env['darbo.avansas'].create(advance_vals)
                generated_advances |= new_advance
            if generated_advances:
                avansai_run_values = {'date_from': advance_date_from,
                                      'date_to': advance_date_to,
                                      'journal_id': journal_id,
                                      'company_id': company_id,
                                      }
                avansai_run = self.env['avansai.run'].create(avansai_run_values)
                generated_advances.write({'avansu_suvestine': avansai_run.id})
                avansai_run.with_context(show_front=not bool(contracts_on_leaves)).patvirtinti()
                # generated_move_lines = avansai_run.mapped('avansai.account_move_id.line_ids').\
                #     filtered(lambda r: r.account_id.reconcile)
                # partner_ids = generated_move_lines.mapped('partner_id.id')
                # account_ids = generated_move_lines.mapped('account_id.id')
                # self.env['mokejimu.eksportas'].with_context(default_name='Avansai %s' % date_from.strftime('%Y-%m')).create_statement(advance_date_from, advance_date_to, journal_id,
                #                                                 name=None,
                #                                                 partner_ids=partner_ids,
                #                                                 account_ids=account_ids,
                #                                                 account_move_line_ids=generated_move_lines.ids)
            if contracts_on_leaves:
                base = \
                '''<table style="border: 1px solid black">
                    <tr>
                        <th style="border: 1px solid black">Darbuotojas</th>
                        <th style="border: 1px solid black">Sutartys</th>
                    </tr>
                    {0}
                </table>'''
                row_template = '''<tr>
                <td style="border: 1px solid black">{0}</td>
                <td style="border: 1px solid black">{1}</td>
                </tr>'''
                data = ''
                employees = contracts_on_leaves.mapped('employee_id')
                for employee in employees:
                    contract_numbers = ', '.join(contracts_on_leaves.filtered(lambda c: c.employee_id.id == employee.id).mapped('name'))
                    data += row_template.format(employee.name, contract_numbers) + '\n'
                table = _('Sveiki, generuojant DU avansus, nebuvo sukurti avansai kai kuriems darbuotojams. Avansai '
                          'nekuriami darbuotojams, kurie sirgo, atostogavo ar dėl kitų priežasčių dalį mėnesio neatvyko '
                          'į darbą (dažnai nuo neatvykimų laikotarpio priklauso avanso dydis). Darbuotojai, kuriems '
                          'avansų įrašai nebuvo sukurti:\n') + base.format(data)
                findir_email = company.findir.partner_id.email
                if findir_email:
                    database = self._cr.dbname
                    subject = _('Nepavyko sukurti DU avansų [%s]') % database
                    self.env['script'].send_email(emails_to=[findir_email], subject=subject, body=table)


AvansaiRun()
