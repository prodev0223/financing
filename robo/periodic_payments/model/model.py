# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions
from odoo.tools.translate import _
from datetime import datetime
from dateutil.relativedelta import relativedelta


class SutarciuRusis(models.Model):

    _name = 'sutarciu.rusis'
    _order = 'code'

    name = fields.Char(string='Pavadinimas', required=True, groups='account.group_account_user')
    code = fields.Char(sting=_('Kodas'), required=True, groups='account.group_account_user')
    description = fields.Text(string='Aprašymas', required=False, groups='account.group_account_user')
    active = fields.Boolean(string='Aktyvus', required=True, groups='account.group_account_user')
    account_id = fields.Many2one('account.account', string='Sąskaita', domain="[('code', '=like', '6%')]",
                                 required=False, groups='account.group_account_user')


SutarciuRusis()


class PeriodicPayment(models.Model):

    _name = 'periodic.payment'
    _order = 'name desc'

    @api.model_cr
    def init(self):
        if len(self.env['subscription.document'].sudo().search([('name','=','Accounting move')])) == 0:
            acc_model = self.env['ir.model'].sudo().search([('model', '=', 'account.move')], limit=1)
            if acc_model:
                subscription_field = {
                    'field': acc_model.id,
                    'value': 'date',
                }
                lines = [(0, 0, subscription_field)]
                self.env['subscription.document'].create({
                    'name': 'DK įrašas',
                    'model': acc_model.id,
                    'field_ids': lines,
                })

    def _serija(self):
        return self.env['ir.sequence'].next_by_code('ASUT')

    def _debetas(self):
        company = self.company_id or self._default_company()
        if company:
            return self.company_id.saskaita_debetas
        else:
            return False

    def _kreditas(self):
        company_id = self.company_id or self._default_company()
        if company_id:
            return self.company_id.saskaita_kreditas
        else:
            return False

    def _gpm(self):
        company_id = self.company_id or self._default_company()
        if company_id:
            return self.company_id.saskaita_gpm
        else:
            return False

    def _op_data(self):
        return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _valiuta(self):
        user = self.env.user
        if user.company_id:
            return user.company_id.currency_id
        else:
            valiuta = self.env['res.currency'].search([('rate', '=', 1.0)], limit=1)
            if valiuta:
                return valiuta

    def _default_company(self):
        return self.env.user.company_id

    state = fields.Selection([('draft', 'Juodraštis'),
                              ('done', 'Patvirtinta')
                              ], string='Būsena', default='draft')
    name = fields.Char(string='Numeris', default=_serija, states={'done': [('readonly', True)]})
    journal_id = fields.Many2one('account.journal', string='Žurnalas', required=True,
                                 states={'done': [('readonly', True)]})
    data = fields.Date(string='Periodinės operacijos data', default=_op_data, required=True,
                       states={'done': [('readonly', True)]})
    type = fields.Selection([('a_klase', 'A klasė'),
                             ('b_klase', 'B klasė')
                             ], default='a_klase', required=True, states={'done': [('readonly', True)]})
    mokejimo_terminas = fields.Selection([('1', 'Iki 15 dienos'),
                                          ('2', 'Po 15 dienos')
                                          ], readonly=True, compute='_mokejimo_terminas')
    contract_id = fields.Many2one('hr.contract', string='Kontraktas', states={'done': [('readonly', True)],
                                                                                 'cancel': [('readonly', True)]})
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', states={'done': [('readonly', True)],
                                                                                  'cancel': [('readonly', True)]})
    partner_id = fields.Many2one('res.partner', string='Partneris', required=True,
                                 states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    rusis = fields.Many2one('sutarciu.rusis', string='Pajamų rūšis', required=True,
                            states={'done': [('readonly', True)]})
    suma = fields.Float(string='Mėnesinė įmoka', required=True, default=0.00, states={'done': [('readonly', True)]})
    saskaita_debetas = fields.Many2one('account.account', string='Debeto sąskaita', default=_debetas,
                                       domain="['|',('code', '=like', '5%'), ('code', '=like', '6%')]", required=True,
                                       states={'done': [('readonly', True)]})
    saskaita_kreditas = fields.Many2one('account.account', string='Kredito sąskaita', default=_kreditas,
                                        domain="['!', ('code', '=like', '5%'), '!', ('code', '=like', '6%')]",
                                        required=True, states={'done': [('readonly', True)]})
    saskaita_gpm = fields.Many2one('account.account', string='GPM sąskaita', default=_gpm,
                                   domain="['!', ('code', '=like', '5%'), '!', ('code', '=like', '6%')]",
                                   required=True, states={'done': [('readonly', True)]})
    subscription = fields.Many2one('subscription.subscription', string='Pasikartojančios operacijos', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Valiuta', default=_valiuta,
                                  groups='base.group_multi_currency')
    advanced_settings = fields.Boolean(string='Išplėstiniai nustatymai', store=False)
    company_id = fields.Many2one('res.company', string='Kompanija', required=True, default=_default_company)

    @api.onchange('company_id')
    def onchange_company_id(self):
        self.saskaita_debetas = self._debetas()
        self.saskaita_kreditas = self._kreditas()
        self.saskaita_gpm = self._gpm()
        self.journal_id = self.company_id.salary_journal_id

    @api.onchange('contract_id')
    def onchange_contract_id(self):
        if self.contract_id:
            self.employee_id = self.contract_id.employee_id.id

    @api.onchange('employee_id')
    def onchange_employee_id(self):
        if self.employee_id:
            self.partner_id = self.employee_id.address_home_id.id

    @api.multi
    def copy(self, default=None):
        if default is None:
            default = {}
        default['subscription'] = False
        default['name'] = self.env['ir.sequence'].next_by_code('ASUT')
        return super(PeriodicPayment, self).copy(default=default)

    @api.multi
    @api.depends('data')
    def _mokejimo_terminas(self):
        for rec in self:
            if rec.data:
                if datetime.strptime(rec.data, tools.DEFAULT_SERVER_DATE_FORMAT).day <= 15:
                    rec.mokejimo_terminas = '1'
                else:
                    rec.mokejimo_terminas = '2'

    @api.onchange('partner_id')
    def onchange_partner_id(self):
        if self.partner_id:
            if not self.partner_id.kodas and not self.partner_id.vat:
                return {
                    'warning': {'title': _('Įspėjimas'),
                                'message': _('Partneris neturi nei asmens/įmonės kodo, nei PVM mokėtojo kodo')}
                }

    @api.onchange('rusis')
    def onchange_rusis(self):
        if self.rusis:
            if self.rusis.account_id:
                self.saskaita_debetas = self.rusis.account_id.id

    @api.multi
    def atsaukti(self):
        for rec in self:
            if rec.subscription:
                rec.subscription.set_done()
                rec.subscription.set_draft()
            rec.state = 'draft'

    @api.multi
    def patvirtinti(self):
        for rec in self:
            if rec.subscription:
                rec.subscription.unlink()
            payment_vals = {'contract_id': self.contract_id.id,
                            'employee_id': self.employee_id.id,
                            'partner_id': self.partner_id.id,
                            }
            payment = self.env['hr.employee.payment'].create(payment_vals)
            payment.amount_bruto = self.suma
            if self.type == 'a_klase':
                gpm_dydis = self.company_id.gpm_proc / 100.0
                payment.amount_paid = self.suma * (1 - gpm_dydis)
            else:
                payment.amount_paid = self.suma
            payment.atlikti()
            sub = {
                'name': rec.name,
                'display_name': rec.name,  # todo
                'interval_number': 1,  # (tikrai?)
                'doc_source': 'hr.employee.payment,' + str(payment.id),
                'interval_type': 'months',
                'date_init': (datetime.strptime(rec.data, tools.DEFAULT_SERVER_DATE_FORMAT).date()
                              + relativedelta(months=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),  # todo
            }
            rec.subscription = self.env['subscription.subscription'].create(sub)  # todo
            rec.subscription.set_process()
            rec.state = 'done'

    @api.multi
    def unlink(self):
        for rec in self:
            if rec.state == 'done':
                raise exceptions.Warning(_('Negalima ištrinti patvirtintų įrašų.'))
        super(PeriodicPayment, self).unlink()


PeriodicPayment()


class SubscriptionSubscription(models.Model):

    _inherit = 'subscription.subscription'

    @api.multi
    def model_copy(self):
        return super(SubscriptionSubscription, self.with_context(auto_confirm_employee_payments=True)).model_copy()


SubscriptionSubscription()


class HrEmployeePayment(models.Model):

    _inherit = 'hr.employee.payment'

    @api.multi
    @api.returns('self', lambda value: value.id)
    def copy(self, default=None):
        res = super(HrEmployeePayment, self).copy(default=default)
        if self._context.get('auto_confirm_employee_payments', False):
            res.atlikti()
        return res


HrEmployeePayment()
