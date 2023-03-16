# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions
from odoo.tools.translate import _
from odoo.tools import float_round, float_compare
from datetime import datetime
from six import iteritems
import calendar


class MokejimuEksportas(models.Model):

    _name = 'mokejimu.eksportas'
    _order = 'data desc'

    def _serija(self):
        return self.env['ir.sequence'].next_by_code('SEPA')

    def _saskaita(self):
        company = self.company_id or self.env.user.company_id
        if company:
            return company.saskaita_kreditas
        else:
            return False

    def _op_data(self):
        return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _pradzia(self):
        return datetime(datetime.utcnow().year, datetime.utcnow().month, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _pabaiga(self):
        metai = datetime.utcnow().year
        menuo = datetime.utcnow().month
        return datetime(metai, menuo, calendar.monthrange(metai, menuo)[1]).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _company_id(self):
        return self.env.user.company_id

    name = fields.Char(string='Numeris', default=_serija, states={'done':[('readonly', True)]})
    journal_id = fields.Many2one('account.journal', string='Mokėjimo būdas', required=True, domain="[('type', '=', 'bank')]",
                                 states={'done': [('readonly', True)]})
    data = fields.Date(string='Operacijos data', default=_op_data, required=True, states={'done': [('readonly', True)]})
    partneriai = fields.Many2many('res.partner', string='Partneriai', states={'done': [('readonly', True)]})
    data_nuo = fields.Date(string='Už periodą nuo', default=_pradzia, required=True, states={'done': [('readonly', True)]})
    data_iki = fields.Date(string='Už periodą iki', default=_pabaiga, required=True, states={'done': [('readonly', True)]})
    saskaitos = fields.Many2many('account.account', string='Įsipareigojimų sąskaita', default=_saskaita, required=True,
                                 states={'done': [('readonly', True)]},
                                 domain="[('reconcile','=',True)]")
    sudengta = fields.Boolean(string='Sudengta', states={'done': [('readonly', True)]}, default=False)
    state = fields.Selection([('draft', 'Juodraštis'), ('done', 'Patvirtinta')], string='Būsena', default='draft')
    eilutes = fields.Many2many('account.move.line', string='DK įrašai', states={'done': [('readonly', True)]})
    payment_order = fields.Many2one('account.payment', string='Mokėjimo nurodymas')
    bank_statement = fields.Many2one('account.bank.statement', string='Banko išrašas')
    company_id = fields.Many2one('res.company', string='Kompanija', default=_company_id, required=True)
    all_partners = fields.Boolean(string='Visi partneriai', states={'done': [('readonly', True)]})
    eilutes_domain = fields.Many2many('account.move.line', compute='_eilutes_domain')
    include_exported = fields.Boolean(string='Rodyti eksportuotus įrašus', default=False)
    structured_payment_ref = fields.Char(string='Struktūruota mokėjimo paskirtis')

    @api.one
    @api.depends('data_nuo', 'data_iki', 'saskaitos', 'company_id', 'partneriai', 'all_partners', 'include_exported')
    def _eilutes_domain(self):
        if self.data_nuo and self.data_iki and self.company_id:
            domain = [('date', '>=', self.data_nuo),
                      ('date', '<=', self.data_iki),
                      ('account_id', 'in', self.saskaitos.mapped('id')),
                      ('company_id', '=', self.company_id.id),
                      ('amount_residual', '!=', 0),
                      ('reconciled', '=', False)]
            if not self.include_exported:
                domain.append(('eksportuota', '=', False))
            if self.all_partners:
                domain.append(('partner_id', '!=', False))
            else:
                domain.append(('partner_id', 'in', self.partneriai.mapped('id')))
            eilutes_ids = self.env['account.move.line'].search(domain).mapped('id')
            self.eilutes_domain = [(6, 0, eilutes_ids)]

    @api.multi
    def atsaukti(self):
        self.ensure_one()
        self.eilutes.with_context(check_move_validity=False).write({'eksportuota': False})
        if self.payment_order:
            self.payment_order.state = 'draft'
        if self.bank_statement:
            # Remove statement reconciliations and unlink it instead of just canceling it
            self.bank_statement.line_ids.button_cancel_reconciliation()
            self.bank_statement.button_cancel()
            self.bank_statement.unlink()
        self.state = 'draft'

    @api.multi
    def patvirtinti(self):
        self.ensure_one()
        company_id = self.journal_id.company_id
        if self.payment_order or self.bank_statement:
            self.state = 'done'
            return False
        for line in self.eilutes:
            if not line.partner_id:
                self.eilutes = [(3, line.id,)]
        if len(self.eilutes) == 0:
            return False
        partneriu_sumos = {}
        bankai = {}
        peilutes = {}
        names = {}
        forced_ref = self.structured_payment_ref
        for line in self.eilutes:
            account_id = line.account_id.id
            partner_id = line.partner_id.id
            employee_id = self.env['hr.employee'].search([('address_home_id', '=', partner_id)], limit=1)
            if employee_id and employee_id.bank_account_id:
                bank = employee_id.bank_account_id.id
            else:
                banks = line.partner_id.bank_ids
                preferred_bank = self.journal_id.bank_id
                bank = banks.filtered(lambda r: r.bank_id.id == preferred_bank.id)
                if not bank:
                    bank = banks[0].id if len(banks) > 0 else False
                else:
                    bank = bank[0].id
            if partner_id and partner_id not in bankai.keys():
                bankai[partner_id] = bank
            if account_id not in partneriu_sumos:
                partneriu_sumos[account_id] = {}
            amount = line.amount_residual
            if partner_id and partner_id in partneriu_sumos[account_id].keys() and not self._context.get('force_split'):
                partneriu_sumos[account_id][partner_id][-1] += amount
            else:
                if partner_id not in partneriu_sumos[account_id]:
                    partneriu_sumos[account_id][partner_id] = [amount]
                else:
                    partneriu_sumos[account_id][partner_id].append(amount)
            if amount < 0:
                names.setdefault(account_id, {}).setdefault(partner_id, {})[line.id] = line.ref or ''
            if account_id not in peilutes.keys():
                peilutes[account_id] = {}
            if partner_id:
                if partner_id not in peilutes[account_id].keys():
                    peilutes[account_id][partner_id] = line
                else:
                    peilutes[account_id][partner_id] |= line
        bank_pool = self.env['account.bank.statement']
        statement_lines = []
        eiluciu_suma = 0
        for acc_id, l in iteritems(partneriu_sumos):
            for partner_id, s in iteritems(l):
                if acc_id not in names:
                    continue  # it means that all partner lines are nonnegative.
                lines = peilutes[acc_id][partner_id]
                if partner_id not in names[acc_id]:
                    continue
                name_line_ids = names[acc_id][partner_id].keys()
                p_names = []
                if self.env.user.has_group('hr.group_hr_manager'):
                    algalapiai = self.env['hr.payslip'].search([('employee_id.address_home_id.id', '=', partner_id),
                                                                ('move_id.line_ids', 'in', lines.ids)])
                    algalapiai_line_ids = algalapiai.mapped('move_id.line_ids.id')
                    name_line_ids = filter(lambda l_id: l_id not in algalapiai_line_ids, name_line_ids)
                    if algalapiai:
                        for algalapis in algalapiai.sorted(lambda r: r.date_to):
                            p_names.append(
                                'Darbo užmokestis %s m. %s mėn.' % (algalapis.date_to[:4], algalapis.date_to[5:7]))
                            atostogos = algalapis.mapped('payment_line_ids').filtered(lambda r: r.code == 'A').mapped(
                                'payment_id.holidays_ids').filtered(
                                lambda r: r.state == 'validate' and r.ismokejimas == 'du')
                            if atostogos:
                                p_names.append('atostoginiai')
                                atostogos_line_ids = atostogos.mapped('payment_id.account_move_ids.line_ids.id')
                                name_line_ids = filter(lambda l_id: l_id not in atostogos_line_ids, name_line_ids)
                            if algalapis.ismoketi_kompensacija:
                                p_names.append('ir kompensacija už nepanaudotas atostogas')
                for index, item in enumerate(s):
                    account_code = self.env['account.account'].browse(acc_id).code
                    if account_code == '4481':
                        date_from = lines and min(lines.mapped('date')) or ''
                        if date_from and len(date_from) == 10:
                            date_dt = fields.Date.from_string(date_from)
                            y = str(date_dt.year)
                            m = str(date_dt.month)
                            if len(m) == 1:
                                m = '0' + m
                            p_name = 'GPM įmokos už %s m. %s mėn.' % (y, m)
                        else:
                            p_name = 'GPM įmokos'
                        ref = p_name
                    elif account_code == '4482':
                        date_from = lines and min(lines.mapped('date')) or ''
                        if date_from and len(date_from) == 10:
                            date_dt = fields.Date.from_string(date_from)
                            y = str(date_dt.year)
                            m = str(date_dt.month)
                            if len(m) == 1:
                                m = '0' + m
                            p_name = 'Sodros įmokos už %s m. %s mėn.' % (y, m)
                        else:
                            p_name = 'Sodros įmokos'
                        ref = p_name
                    else:
                        if not self._context.get('force_split'):
                            ref = ', '.join(set([aml.move_id.ref or '' for aml in peilutes[acc_id][partner_id]])) or '/'
                        else:
                            ref = peilutes[acc_id][partner_id][index].move_id.ref
                    p_names.extend(names[acc_id][partner_id][l_id] for l_id in name_line_ids)
                    if not self._context.get('force_split'):
                        p_names_unique = []
                        for p_name in p_names:
                            p_name = p_name.strip()
                            if p_name not in p_names_unique:
                                p_names_unique.append(p_name)
                        memo = ', '.join(p_names_unique) or ref
                    else:
                        memo = names[acc_id][partner_id][peilutes[acc_id][partner_id][index].id]
                    journal_currency = self.journal_id.currency_id or self.company_id.currency_id
                    if journal_currency.id == self.company_id.currency_id.id:
                        amount = item
                    elif (lines and lines[0]).currency_id.id == journal_currency.id:
                        amount = sum(lines.mapped('amount_residual_currency'))
                    else:
                        amount = 0.0
                        for line in lines:
                            currency = line.currency_id or self.company_id.currency_id
                            if line.currency_id and line.currency_id != self.company_id.currency_id:
                                line_residual = line.amount_residual_currency
                            else:
                                line_residual = line.amount_residual
                            amount += currency.with_context(date=self.data).compute(line_residual, journal_currency)
                    account = self.env['account.account'].browse(acc_id)
                    if account.use_rounding:
                        amount = float_round(amount, precision_rounding=1)
                    if float_compare(amount, 0, precision_rounding=journal_currency.rounding) == 0:
                        continue
                    eilute = {
                        'company_id': company_id.id,
                        'date': self.data,
                        'name': memo or '/',
                        'ref': ref,
                        'amount': amount,
                        'partner_id': partner_id,
                    }
                    if forced_ref:
                        eilute['name'] = eilute['ref'] = forced_ref
                        eilute['info_type'] = 'structured'
                    elif account.structured_code:
                        eilute['info_type'] = 'structured'
                        eilute['name'] = account.structured_code
                    elif eilute['name'] == '/':
                        eilute['name'] = eilute['ref'] or '/'
                    if line.currency_id:
                        eilute['amount_currency'] = line.amount_residual_currency
                        eilute['currency_id'] = line.currency_id.id
                    if partner_id in bankai:
                        eilute['bank_account_id'] = bankai[partner_id]
                    statement_lines.append((0, 0, eilute))
                    eiluciu_suma += amount
                    line.with_context(check_move_validity=False).eksportuota = True
        if self.journal_id.default_credit_account_id:
            credit_account_id = self.journal_id.default_credit_account_id.id
        else:
            raise exceptions.Warning(_('Nenurodyta žurnalo kredito sąskaita'))
        # todo: einamuju metu pradzia nebutinai sutampa su kalendoriniu metu pradzia
        starto_data = datetime(datetime.utcnow().year, 1, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        pabaigos_data = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        self._cr.execute('''select sum(debit) as debit, sum(credit) as credit from account_move_line AS line,
                                account_move as move
                                WHERE line.move_id = move.id AND line.date >= %s AND line.date <= %s
                                AND account_id = %s AND move.state = 'posted' AND move.company_id = %s ''', (
            starto_data,
            pabaigos_data,
            credit_account_id,
            company_id.id))
        result = self._cr.dictfetchall()
        if len(result) > 0:
            result = result[0]
            if 'debit' in result.keys():
                d = result['debit'] or 0
            else:
                d = 0
            if 'credit' in result.keys():
                k = result['credit'] or 0
            else:
                k = 0
            balance_start = d - k
            balance_end_real = balance_start + eiluciu_suma
        else:
            balance_start = 0
            balance_end_real = eiluciu_suma
        vals_bank = {
            'date': self.data,
            'company_id': company_id.id,
            'journal_id': self.journal_id.id,
            'line_ids': statement_lines,
            'balance_start': balance_start,
            'balance_end_real': balance_end_real,
            'state': 'open',
            'name': self.name,
        }
        bids = bank_pool.create(vals_bank)
        if self._context.get('front_statements', False):
            for bid in bids:
                bid.show_front()
        self.bank_statement = bids.id
        self.state = 'done'

    @api.multi
    def unlink(self):
        for rec in self:
            if rec.state == 'done':
                raise exceptions.Warning(_('Negalima ištrinti apmokėtų įrašų.'))
        super(MokejimuEksportas, self).unlink()

    @api.multi
    def copy(self, default=None):
        if default is None:
            default = {}
        default['payment_order'] = False
        default['bank_statement'] = False
        default['name'] = self.env['ir.sequence'].next_by_code('SEPA')
        return super(MokejimuEksportas, self).copy(default=default)

    @api.multi
    def istraukti_darbuotojus(self):
        self.ensure_one()
        if self.state == 'draft':
            darbuotojai = self.env['hr.employee'].search([('active', '=', True),
                                                          ('company_id', '=', self.journal_id.company_id.id)])
            partneriai = []
            eilutes = []
            for emp in darbuotojai:
                if emp.address_home_id:
                    if emp.address_home_id.id not in partneriai:
                        partneriai.append(emp.address_home_id.id)
                        eilutes.append((0, 0, emp.address_home_id.id))
            self.partneriai = partneriai

    @api.multi
    def mokejimai(self):
        return {
            'name': _('Mokėjimų nurodymai'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.payment',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id', '=', self.payment_order.id)],
        }

    @api.multi
    def israsai(self):
        bank_statements = self.env['account.bank.statement'].search([('id', '=', self.bank_statement.id)])

        if len(bank_statements) > 1:
            view_mode = 'tree,form'
        else:
            view_mode = 'form,tree'

        return {
            'name': _('Banko išrašai'),
            'view_type': 'form',
            'view_mode': view_mode,
            'res_model': 'account.bank.statement',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': bank_statements[0].id if len(bank_statements) > 0 else 'new',
            'res_id': bank_statements[0].id if len(bank_statements) > 0 else False,
            'domain': [('id', '=', self.bank_statement.id)],
        }
