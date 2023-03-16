# -*- coding: utf-8 -*-

from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _, exceptions, tools
import calendar


class ResPartner(models.Model):
    _inherit = 'res.partner'

    area = fields.Float(string='Plotas/KVM')
    community_member = fields.Boolean(string='Bendrijos narys')
    date_start = fields.Date(string='Įstojimo data')
    date_end = fields.Date(string='Išstojimo data')
    email = fields.Char(required=True)

    @api.multi
    @api.constrains('email')
    def email_constrain(self):
        for rec in self:
            if self.env['res.partner'].search_count([('id', '!=', rec.id), ('email', '=', rec.email)]):
                raise exceptions.ValidationError(_('Toks kliento el paštas jau egzsituoja!'))


ResPartner()


class CommunityWizard(models.Model):
    _name = 'community.wizard'

    def default_from(self):
        return datetime.now() - relativedelta(months=1, day=1)

    def default_to(self):
        return datetime.now() - relativedelta(months=1, day=31)

    date_from = fields.Date(string='Data nuo', required=True, default=default_from)
    date_to = fields.Date(string='Data iki', required=True, default=default_to)
    action = fields.Selection([('no', 'Netvirtinti'),
                               ('open', 'Tvirtinti'),
                               ('send', 'Tvirtinti ir išsiųsti')], string='Automatinis veiksmas',
                              default='no', required=True)

    @api.onchange('date_from', 'date_to')
    def onchange_dates_constraint(self):
        d_from = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        if d_from != datetime(d_from.year, d_from.month, 1):
            raise exceptions.Warning(_('Periodo pradžia privalo būti mėnesio pirmoji diena'))
        d_to = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        if d_to != datetime(d_to.year, d_to.month, calendar.monthrange(d_to.year, d_to.month)[1]):
            raise exceptions.Warning(_('Periodo pabaiga privalo būti mėnesio paskutinė diena'))

    @api.multi
    def generate_report(self):
        members = self.env['res.partner'].search([('community_member', '=', True)])
        area_total = sum(member.area for member in members)
        expenses = self.get_expenses()
        ids = []
        for member in members:
            percentage = self.get_percentage(area_total, member)
            if percentage:
                inv_id = self.create_invoice(percentage, member, expenses)
                if inv_id:
                    ids.append(inv_id)
        if ids:
            domain = [('id', 'in', ids)]
            ctx = {
                'activeBoxDomain': "[('state','!=','cancel')]",
                'default_type': "out_invoice",
                'force_order': "recently_updated DESC NULLS LAST",
                'journal_type': "purchase",
                'lang': "lt_LT",
                'limitActive': 0,
                'params': {'action': self.env.ref('robo.open_client_invoice').id},
                'robo_create_new': self.env.ref('robo.new_client_invoice').id,
                'robo_menu_name': self.env.ref('robo.menu_pajamos').id,
                'robo_subtype': "pajamos",
                'robo_template': "RecentInvoices",
                'search_add_custom': False,
                'type': "in_invoice",
                'robo_header': {},
            }
            return {
                'context': ctx,
                'display_name': _('Pajamos'),
                'domain': domain,
                'name': _('Pajamos'),
                'res_model': 'account.invoice',
                'target': 'current',
                'type': 'ir.actions.act_window',
                'header': self.env.ref('robo.robo_button_pajamos').id,
                'view_id': self.env.ref('robo.pajamos_tree').id,
                'view_mode': 'tree_expenses_robo,form,kanban',
                'views': [[self.env.ref('robo.pajamos_tree').id, 'tree_expenses_robo'],
                          [self.env.ref('robo.pajamos_form').id, 'form'],
                          [self.env.ref('robo.pajamos_kanban').id, 'kanban']],
                'with_settings': True,
            }

    def get_percentage(self, area_total, member):
        date_from_p = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT).date()
        date_to_p = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT).date()

        date_from_mem = datetime.strptime(member.date_start, tools.DEFAULT_SERVER_DATE_FORMAT).date()
        if member.date_end:
            date_to_mem = datetime.strptime(member.date_end, tools.DEFAULT_SERVER_DATE_FORMAT).date()
        else:
            date_to_mem = False

        # todo ignore for now
        # delta_period = (date_to_p - date_from_p).days
        # day_fraction = 0.0
        #
        # if date_from_mem <= date_from_p and date_to_mem >= date_to_p:
        #     day_fraction = 1
        # elif date_from_mem >= date_from_p and date_to_mem <= date_to_p:
        #     member_delta = (date_to_mem - date_from_mem).days
        #     day_fraction = float(member_delta) / delta_period
        # elif date_to_mem > date_to_p > date_from_mem > date_from_p:
        #     member_delta = (date_to_p - date_from_mem).days
        #     day_fraction = float(member_delta) / delta_period
        # elif date_from_mem < date_from_p < date_to_mem < date_to_p:
        #     member_delta = (date_to_mem - date_from_p).days
        #     day_fraction = float(member_delta) / delta_period

        # return float(member.area) / area_total * day_fraction

        if not date_to_mem:
            if date_from_mem <= date_from_p:
                return float(member.area) / area_total
            else:
                return 0
        else:
            if (date_from_mem <= date_from_p and date_to_mem >= date_to_p) or \
                    (date_from_mem >= date_from_p and date_to_mem <= date_to_p) or \
                    (date_to_mem > date_to_p > date_from_mem > date_from_p) or \
                    (date_from_mem < date_from_p < date_to_mem < date_to_p):
                return float(member.area) / area_total
            else:
                return 0

    def get_expenses(self):
        expenses = []
        date_start = self.date_from
        date_end = self.date_to
        close_journal_id = self.env.user.sudo().company_id.period_close_journal_id.id or 0
        company_id = self.env.user.sudo().company_id
        expenses_acc = company_id.saskaita_debetas.id
        secondment = company_id.saskaita_komandiruotes.id
        sodra = company_id.darbdavio_sodra_debit.id
        accounts = []
        if expenses_acc:
            accounts.append(expenses_acc)
        if secondment:
            accounts.append(secondment)
        if sodra:
            accounts.append(sodra)
        accounts = tuple(accounts)
        self.env.cr.execute('''
         SELECT
           sum(exp) as exp,
           icon,
           color,
           name,
           cat_id
           FROM (
                 SELECT sum(debit) - sum(credit) as exp, product_category.ultimate_icon as icon, product_category.ultimate_color as color, product_category.ultimate_name as name, product_category.ultimate_id as cat_id
                 FROM account_move_line
                     INNER JOIN account_account on account_move_line.account_id = account_account.id
                     INNER JOIN account_move on account_move_line.move_id = account_move.id
                     LEFT JOIN product_product on account_move_line.product_id = product_product.id
                     LEFT JOIN product_template on product_product.product_tmpl_id = product_template.id
                     LEFT JOIN product_category on product_template.categ_id = product_category.id
                 WHERE account_account.code like %s and state = 'posted' and account_move_line.date >= %s and 
                 account_move_line.date <= %s and account_move.journal_id <> %s
                 and account_account.id not in %s
                 GROUP BY product_category.ultimate_icon, product_category.ultimate_color, product_category.ultimate_name, product_category.ultimate_id)
          as foo GROUP BY icon, color, name, cat_id;
         ''', ('6%', date_start, date_end, close_journal_id, accounts,))
        res = self.env.cr.dictfetchall()
        for line in res:
            if line['exp'] and not tools.float_is_zero(float(line['exp'] or 0.0), precision_digits=2):
                expenses.append({
                    'value': line['exp'] or 0.0,
                    'name': line['name'] or _('Kitos įvairios išlaidos'),
                    'id': line['cat_id'] or 'Kita',
                })
        self.env.cr.execute('''
                 SELECT sum(debit) - sum(credit) as exp
                 FROM account_move_line
                     INNER JOIN account_account on account_move_line.account_id = account_account.id
                     INNER JOIN account_move on account_move_line.move_id = account_move.id
                 WHERE account_account.code like %s and account_move.state = 'posted' and account_move_line.date >= %s 
                 and account_move_line.date <= %s and account_move.journal_id <> %s
                 and account_account.id in %s;
                 ''', ('6%', date_start, date_end, close_journal_id, accounts,))
        res = self.env.cr.dictfetchall()
        for line in res:
            if line['exp'] and not tools.float_is_zero(float(line['exp'] or 0.0), precision_digits=2):
                expenses.append({
                    'value': line['exp'] or 0.0,
                    'name': _('Darbo užmokesčio sąnaudos'),
                    'id': 'DU'
                })
        return expenses

    def create_invoice(self, percentage, member, expenses):
        invoice_obj = self.env['account.invoice'].sudo()
        account_obj = self.env['account.account'].sudo()
        invoice_values = {}
        journal_id = self.env['account.journal'].search([('code', '=', 'DNSB')], limit=1)
        invoice_values['journal_id'] = journal_id.id
        invoice_values['date_invoice'] = self.date_to
        invoice_values['date_due'] = self.date_to
        invoice_values['account_id'] = account_obj.search([('code', '=', '2410')]).id
        invoice_values['partner_id'] = member.id
        inv_lines = []
        invoice_values['invoice_line_ids'] = inv_lines
        invoice_values['type'] = 'out_invoice'
        invoice_values['intrastat_country_id'] = member.country_id.id
        invoice_values['community_invoice'] = True

        product = self.get_service()
        tax = self.env['account.tax'].search([('code', '=', 'Ne PVM')], limit=1)
        for line in expenses:
            if product:
                product_account = product.get_product_income_account(return_default=True)
                line_vals = {
                    'product_id': product.id,
                    'name': line['name'],
                    'quantity': percentage,
                    'price_unit': line['value'],
                    'uom_id': product.product_tmpl_id.uom_id.id,
                    'account_id': product_account.id,
                    'invoice_line_tax_ids': [(6, 0, tax.ids)],
                }
                inv_lines.append((0, 0, line_vals))
            else:
                return False
        try:
            invoice_id = invoice_obj.create(invoice_values)
            invoice_id.partner_data_force()
            if self.action in ['open', 'send']:
                invoice_id.action_invoice_open()
            if self.action == 'send':
                action = invoice_id.action_invoice_sent()
                if self.env.user.company_id.vadovas and self.env.user.company_id.vadovas.user_id:
                    user = self.env.user.company_id.vadovas.user_id
                else:
                    user = self.env.user
                ctx = action['context']
                mail = self.sudo(user=user).env['mail.compose.message'].with_context(ctx).create({})
                mail.onchange_template_id_wrapper()
                mail.send_mail_action()

            return invoice_id.id
        except Exception as e:
            raise exceptions.ValidationError(_('Nepavyko sukurti sąskaitos, sisteminė klaida atliekant '
                                               'veiksmus partneriui %s: %s') % (member.name, e.name))

    def get_service(self):
        return self.env['product.product'].search([('name', '=', 'Paslauga')])


CommunityWizard()


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    community_invoice = fields.Boolean(string='Bendrijos mokėjimo išrašas', groups='base.group_system', default=False)


AccountInvoice()
