# -*- coding: utf-8 -*-
import requests
from requests.auth import HTTPDigestAuth
from odoo import models, fields, _, api, tools, exceptions
from datetime import datetime
from dateutil.relativedelta import relativedelta
import logging
import json

_logger = logging.getLogger(__name__)
host = 'http://stage.skolubiuras.lt'
token_ref = '.json?access_token='
api_import = '/api/import/'
api_update = '/api/update/'
api_upload = '/api/upload/'
api_investment = '/api/investment/'
get_handshake = '/api/handshake'
get_geo_list = '/api/geo/list'
get_court_list = '/api/court/list'
get_debtor_group = '/api/debtor/group/list'

token_expiration = None
access_token = None
token_type = None

debt = {
    'put_debt_history_record': '/api/create/debt/history/civilCaseNumber/',  # {civilCaseNumber}
    'get_tags_list': '/api/debt/tag/list',
    'get_creditor_tags_list': '/api/debt/creditor/tag/list',
    'get_status_list': '/api/debt/status/list',
    'post_debt': '/api/import/debt',
    'sync_det_credit_sch_payment': '/debt/sync/credit-scheduled-payments',  # with all syncs, puts, posts. put apt_upd
    'sync_debt_extend_payment': '/debt/sync/extend/payments',               # api_import + exd_id + actual statement
    'sync_debt_credit_hist': '/debt/sync/histories',
    'sync_debt_interests': '/debt/sync/interests',
    'sync_debt_payments': '/debt/sync/payments',
    'sync_debt_taxes': '/debt/sync/taxes',
    'post_debt_taxes': '/debt/taxes',
    'put_debt': '/debt',
    'put_debt_credit_sch_payment': '/debt/credit/scheduled/payment',
    'put_debt_ext_payment': '/debt/extend/payments',
    'put_debt_history': '/debt/history',
    'put_debt_interest': '/debt/interest',
    'put_debt_payment': '/debt/payment',
    'put_debt_tax': '/debt/tax',
    'post_register_debt_attach': '/api/upload/debt/attachment/',  # civilcasenumber
    'post_register_debt_attachment': '/extid/debt/attachment'  # ext_id,
}

debt_request = {
    'get_form_labels': '/api/debt/request/labels',
    'post_debt_request_with_user': '/api/debt/request/register'
}

bank = {
    'get_bank_list': '/api/bank/list'
}

bought_investment = {
    'post_bought_investment': '/register',
    'post_bought_investment_payment': '/register/payment',
    'post_bought_investment_bulk_payment': '/register/payment/bulk'
}

debtor = {
    'post_actions': '/debtor/import/actions',
    'post_remarks': '/debtor/import/remarks',
    'sync_actions': '',
    'sync_banned_debt_register_data': '',
    'sync_debts': '',
    'sync_incomes': '',
    'sync_remarks': '',
    'sync_solvency_checks': '',
    'sync_workplaces': '',
    'put_action': '',
}

user = 'worker'
password = 'madingasDebesis'
token_link = 'http://stage.skolubiuras.lt/oauth/v2/token?client_id=913_4bs2hf' \
             'xh5jac4w40cww00c8owswsogkc4ok884s44sogowww48&client_secret=5jdg03' \
             'p7svwg8s4sos04so8ws4g4cw408wog88kckk4w804gsw&username=worker&password=madingasDebesis&grant_type=client_credentials'


# def get_access():
#     auth = HTTPDigestAuth(user, password)
#     try:
#         resp = requests.get(token_link, auth=auth).json()
#         if resp:
#             access_token = resp['access_token']
#             token_type = resp['token_type']
#             expires_in = resp['expires_in']
#             link = host + debt['debt_tags'] + '.json?access_token=' + access_token
#             response = requests.get(link, auth=auth)
#             print(response.json())
#     except Exception as e:
#         _logger.error("Couldn't connect to eSkolos API, error msg: \n %s...") % e

def get_access():
    authorize = HTTPDigestAuth(user, password)
    global access_token
    global token_type
    global expires_in
    try:
        resp = requests.get(token_link, auth=authorize).json()
        access_token = resp['access_token']
        token_type = resp['token_type']
        expires_in = resp['expires_in']
    except Exception as e:
        raise exceptions.ValidationError(_("Couldn't connect to API, error msg: \n %s") % e)


class EDebtImportWizard(models.Model):
    _name = 'e.debt.import.wizard'

    def import_debt(self):
        pass

    def debt_imp_api_call(self):
        pass


EDebtImportWizard()


class EDebt(models.Model):
    _name = 'e.debt'

    state = fields.Selection([
        ('requested', 'Skola laukia'),
        ('imported', 'Skola priimta'),
        ('declined', 'Skola nepriimta')], string='Būsena')

    debtor_type = fields.Selection([
        ('natural', 'Naturalus'),
        ('legal', 'Legalus'),
    ], string='Skolininko tipas')

    open_date = fields.Date(string='Skolos atsiradimo data')
    extra_info_request = fields.Text(string='Papildoma informacija')
    request_amount = fields.Float(string='Skolos suma')
    user_id = fields.Many2one('res.users', help='Concact user')
    do_patch = fields.Boolean(help='This field indicates whether debt was ever imported or not')
    debt_amount = fields.Float(string='Piniginė skola')
    remark_ids = fields.One2many('e.debt.remark', 'debt_id')
    invoice_ids = fields.One2many('account.invoice', 'debt_id')

    def import_debt(self):
        pass

    def call_debt_register(self):
        debt_dict = {
            'form': {
                'user': {
                    'username': self.user_id.email,
                    'phoneNumber': self.user_id.phone,
                },
                'debtRequests': [
                    {
                        'debtorType': self.debtor_type,
                        'amount': str(self.request_amount),
                        'debtOpenedAt': self.open_date,
                        'extraInformation': self.extra_info_request,
                    },
                ],
                'acceptSystemRules': True,
                'acceptTerms': True,
                'subscribeToNewsLetter': True
            }
        }


        link = host + '/api/debt/request/register' + '.json?access_token=' + access_token
        response = requests.get(link, auth=auth, json=debt_dict)
        print(response.json())


EDebt()


class EDebtor(models.Model):
    _name = 'e.debtor'

    # state = fields
    do_patch = fields.Boolean(help='This field indicates whether record was ever imported or not')
    partner_id = fields.Many2one('res.partner', string='Skolininkas')
    remarks = fields.Text(string='Pastabos')

    def import_debt(self):
        pass

    def debtor_api_call(self, api_extension):
        get_access()
        global access_token
        global token_expiration
        global auth

        if api_extension == 'post_actions':
            data = [{
                'content': self.remarks,
                'author': self.env.user,
                'created': datetime.utcnow()
            }]
            json_data = json.dumps(data)
            call = host + api_import + self.partner_id.id + debtor['post_actions'] + token_ref + access_token
            response = requests.get(call, auth=auth, data=json_data)

        if api_extension == 'post_remarks':
            data = [{
                'content': self.remarks,
                'author': self.env.user,
                'created': datetime.utcnow()
            }]
            json_data = json.dumps(data)
            call = host + api_import + self.partner_id.id + debtor['post_remarks'] + token_ref + access_token
            response = requests.get(call, auth=auth, data=json_data)


EDebtor()


class EDebtRemark(models.Model):
    _name = 'e.debt.remark'

    debt_id = fields.Many2one('e.debt')
    remark = fields.Text(string='Pastaba')
    date_remark = fields.Datetime(string='Pastabos data')
    invoice_id = fields.Many2one(string='Sąskaita faktūra')


EDebtRemark()

class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    debt_remark_ids = fields.One2many('e.debt.remark', 'invoice_id')
    show_debt_tab = fields.Boolean(compute='compute_debt_tab')
    debt_id = fields.Many2one('e.debt')

    @api.one
    @api.depends('date_due', 'residual_company_signed')
    def compute_debt_tab(self):
        if self.date_due and self.residual_company_signed != 0:
            date_due_dt = datetime.strptime(self.date_due, tools.DEFAULT_SERVER_DATE_FORMAT)
            current_date = datetime.utcnow().date()
            delta = relativedelta(current_date, date_due_dt)
            if delta.months >= 2:
                self.show_debt_tab = True
            else:
                self.show_debt_tab = False
        else:
            self.show_debt_tab = False

    @api.model
    def post_debt(self):
        debt_vals = {
            'debtor_type': 'natural',
            'amount': self.residual_company_signed,
            'debt_opened_at': datetime.utcnow(),
            'extra_info': self.extra_information,
            'user_id': ''
        }
        debt_id = self.env['e.debt'].create(debt_vals)
        debt_id.call_debt_register()


AccountInvoice()


class DebtRegisterWizard(models.TransientModel):

    _name = 'debt.register.wizard'

    debtor_type = fields.Selection([
        ('natural', 'Naturalus'),
        ('legal', 'Legalus'),
    ], string='Skolininko tipas', default='natural')
    user_id = fields.Many2one('res.users', help='Skolininkas', readonly=True)
    request_amount = fields.Float(string='Skolos suma', readonly=True)
    extra_info_request = fields.Text(string='Papildoma informacija')
    open_date = fields.Date(string='Skolos atsiradimo data')

    @api.multi
    def post_debt(self):
        self.ensure_one()
        debt_dict = {
            'form': {
                'user': {
                    'username': self.user_id.email,
                    'phoneNumber': self.user_id.phone,
                },
                'debtRequests': [
                    {
                        'debtorType': self.debtor_type,
                        'amount': str(self.request_amount),
                        'debtOpenedAt': self.open_date,
                        'extraInformation': self.extra_info_request,
                    },
                ],
                'acceptSystemRules': True,
                'acceptTerms': True,
                'subscribeToNewsLetter': True
            }
        }
        link = host + '/api/debt/request/register' + '.json?access_token=' + access_token
        response = requests.get(link, auth=auth, json=debt_dict)
        print(response.json())

        vals = {
            'user_id': self.user_id.id,
            'debtor_type': self.debtor_type,
            'request_amount': self.request_amount,
            'extra_info_request': self.extra_info_request,
            'open_date': self.open_date,
        }
        self.env['e.debt'].create(vals)






DebtRegisterWizard()