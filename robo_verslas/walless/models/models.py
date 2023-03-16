# -*- coding: utf-8 -*-
import uuid

from odoo import models, fields, api, exceptions, tools, _
import requests
from datetime import datetime
import json
import logging
import threading
from odoo.api import Environment
import odoo

_logger = logging.getLogger(__name__)

codes = {
    'timeout': 504,
    'success': 200,
    'error': 0,
    'inv_not_found': 205,
}

bank_codes_limitations = ['72900']


def validate_response(resp, shareholder):
    try:
        response_dict = json.loads(resp.text)
        msg = response_dict.get('message', False)
        body = str()
        if msg and msg == '404: Not found':
            body += _('Walless sąskaitų eksportavimo klaidos | '
                      'Problema su robo API, metodas nerastas | Partneris %s ') % shareholder.shareholder_name
        if response_dict.get('result', False):
            code = response_dict['result'].get('status_code', 0)
            error = response_dict['result'].get('error', '')
            if not msg and error:
                msg = error
        else:
            code = codes['error']
            error = str()
        if error:
            body += _('Walless sąskaitų eksportavimo klaidos |'
                      ' Pranešimas %s | Partneris %s \n') % (error, shareholder.shareholder_name)
            _logger.info(body)
            if code == codes['success']:  # code cant be 200 if error occurs
                code = codes['error']
    except ValueError:
        try:
            json_bug = str(resp._content) + '\n Status Code:' + str(resp.status_code)
        except ValueError:
            try:
                json_bug = str(resp.text) + '\n Status Code:' + str(resp.status_code)
            except ValueError:
                json_bug = str(resp.status_code)

        code = resp.status_code
        if code != codes['timeout']:
            msg = 'ROBO API BUG:\n' + json_bug
        else:
            msg = str()
    return code, msg


def check_existence_manual(shareholder, rec):
    api_route = '/api/check_invoice'
    url = shareholder.api_extension + api_route
    vals = {
        'walless_main_ext_id': rec.id,
        'secret': shareholder.api_key
    }
    resp = requests.post(url, json=vals)
    return resp


class EDocument(models.Model):
    _inherit = 'e.document'

    def random_unique_code(self):
        return uuid.uuid4()

    unique_wizard_id = fields.Text(default=random_unique_code, store=False)
    user_attachment_ids = fields.Many2many('ir.attachment', compute='_compute_all_attachments', string='Prisegtukai',
                                           readonly=False)
    nbr_of_attachments = fields.Integer(compute='_compute_nbr_of_attachments')
    attachment_drop_lock = fields.Boolean(
        compute='_compute_attachment_drop_lock')  # TODO does not work for some reason, user can upload docs in any stage of e doc, it only prevents from removing docs in state e_signed, would be nice to have both
    walless_e_doc_template_id = fields.Integer(compute='_walless_e_doc_template_id')

    info_about_expense = fields.Text(string='Informacija apie kompensaciją', inverse='set_final_document',
                                     readonly=True,
                                     states={'draft': [('readonly', False)]})
    expense_state_approval = fields.Selection(
        [('waiting', 'Laukiama patvirtinimo'), ('approved', 'Patvirtinta'), ('declined', 'Atmesta')],
        string='Išlaidų patvirtinimo būsena', default='waiting', inverse='check_allow_change_compensation_state')
    show_attach_doc = fields.Boolean(compute='_show_attach_doc')
    employee_is_validator = fields.Boolean(compute='_employee_is_validator')

    @api.multi
    def sign(self):
        for rec in self:
            if rec.template_id.id == rec.walless_e_doc_template_id:
                if rec.nbr_of_attachments == 0:
                    raise exceptions.UserError(_('Negalite pasirašyti dokumento, kol neprisegėte nors vieno dokumento'))
        return super(EDocument, self).sign()

    @api.multi
    def cancel_request(self):
        res = super(EDocument, self).cancel_request()
        for rec in self:
            if rec.expense_state_approval != 'waiting':
                raise exceptions.UserError(
                    _('Nebegalite atšaukti dokumento, kuris jau buvo patvirtintas arba atmestas.'))
        return res

    @api.one
    def _walless_e_doc_template_id(self):
        self.walless_e_doc_template_id = self.env.ref('walless.prasymas_del_islaidu_kompensavimo_template').id

    @api.one
    @api.depends('expense_state_approval')
    def _compute_attachment_drop_lock(self):
        self.attachment_drop_lock = False
        if self.template_id.id == self.walless_e_doc_template_id and not self.employee_is_validator and self.state == 'e_signed':
            self.attachment_drop_lock = True

    @api.model
    def create(self, vals):
        wizard_id = vals.pop('unique_wizard_id', False)
        document = super(EDocument, self).create(vals)
        if wizard_id and self.template_id.id == self.walless_e_doc_template_id:
            wizards_records = self.env['ir.attachment.wizard'].search([('res_model', '=', 'e.document'),
                                                                       ('wizard_id', '=', wizard_id)])
            if document and wizards_records:
                for rec in wizards_records:
                    new_vals = {
                        'name': rec['name'],
                        'datas': rec['datas'],
                        'datas_fname': rec['datas_fname'],
                        'res_model': 'e.document',
                        'res_id': document.id,
                        'type': rec['type'],
                    }
                    self.env['ir.attachment'].create(new_vals)
        return document

    @api.one
    def _compute_nbr_of_attachments(self):
        self.nbr_of_attachments = len(self.user_attachment_ids.ids)

    @api.one
    def _compute_all_attachments(self):
        ids = self.env['ir.attachment'].search([('res_model', '=', 'e.document'),
                                                ('res_id', '=', self.id),
                                                ('res_field', '=', False)]).ids

        # ids_field = self.env['ir.attachment'].search([('res_model', '=', 'e.document'),
        #                                               ('res_id', '=', self.id),
        #                                               ('res_field', '!=', False)]).ids
        ids = set(ids)  # set(ids + ids_field)
        self.user_attachment_ids = [(4, doc_id) for doc_id in ids]

    @api.one
    def _employee_is_validator(self):
        validating_employee_ids = self.env.user.company_id.mapped('employees_approving_compensation.user_id.id')
        ceo = self.env.user.company_id.vadovas.user_id.id
        is_admin = self.env.user._is_admin()
        validating_employee_ids.append(ceo)
        if (self.env.user.id in validating_employee_ids or is_admin):
            self.employee_is_validator = True
        else:
            self.employee_is_validator = False

    @api.one
    @api.depends('expense_state_approval')
    def _show_attach_doc(self):
        if self.employee_is_validator or self.expense_state_approval == 'approved':
            self.show_attach_doc = True
        else:
            self.show_attach_doc = False

    @api.one
    def check_allow_change_compensation_state(self):
        if not self.employee_is_validator:
            raise exceptions.UserError(_('Jums neleidžiama keisti kompensacijos patvirtinimo būsenos.'))
        else:
            if self.state != 'e_signed' and self.expense_state_approval != 'waiting':
                raise exceptions.UserError(_('Kompensacijos būsena gali būti keičiama tik pasirašytuose dokumentuose.'))

    @api.one
    def approve_expense_compensation(self):
        self.check_allow_change_compensation_state()
        files = self.env['ir.attachment'].search([('res_model', '=', 'e.document'),
                                                  ('res_id', '=', self.id),
                                                  ('res_field', '=', False)])
        if len(files) == 0:
            raise exceptions.UserError(_('Nėra prisegtų dokumentų'))
        for file in files:
            self.env['robo.upload'].upload_file_app(file.datas, file.name)
        self.write({'expense_state_approval': 'approved'})

    @api.one
    def decline_expense_compensation(self):
        self.check_allow_change_compensation_state()
        self.write({'expense_state_approval': 'declined'})


EDocument()


class ResCompany(models.Model):
    _inherit = 'res.company'

    employees_approving_compensation = fields.Many2many('hr.employee',
                                                        string='Darbuotojai tvirtinantys kompensacijas',
                                                        inverse='_set_walless_rights')

    @api.one
    def _set_walless_rights(self):
        employees = self.env['hr.employee'].search([])
        for employee in employees:
            if employee.sudo().user_id.has_group('walless.group_walless_expense_validator'):
                employee.sudo().user_id.groups_id = [
                    (3, self.sudo().env.ref('walless.group_walless_expense_validator').id,)]
        for employee in self.employees_approving_compensation:
            employee.sudo().user_id.groups_id = [
                (4, self.sudo().env.ref('walless.group_walless_expense_validator').id,)]


ResCompany()


class CompanySettings(models.TransientModel):
    _inherit = 'robo.company.settings'

    employees_approving_compensation = fields.Many2many('hr.employee',
                                                        string='Darbuotojai tvirtinantys kompensacijas')

    @api.model
    def default_get(self, field_list):
        res = super(CompanySettings, self).default_get(field_list)
        company_id = self.sudo().env.user.company_id
        res['employees_approving_compensation'] = [(6, 0, company_id.employees_approving_compensation.mapped('id'))]
        return res

    @api.multi
    def set_company_info(self):
        if not self.env.user.is_manager():
            return False
        res = super(CompanySettings, self).set_company_info()
        self.env.user.company_id.sudo().write({
            'employees_approving_compensation': [(6, 0, self.employees_approving_compensation.mapped('id'))],
        })
        return res


CompanySettings()


class WallessInvoiceExport(models.Model):

    _name = 'walless.invoice.export'

    invoice_id = fields.Many2one('account.invoice', string='Sąskaitos numeris', readonly=True)
    name_display = fields.Char(string='Sąskaitos numeris')
    shareholder_id = fields.Many2one('res.company.shareholder', string='Akcininkas')
    invoice_total_shareholder = fields.Float(string='Akcininko pajamos iš sąskaitos', readonly=True)
    status = fields.Selection([('failed', 'Klaida'), ('imported', 'Importuota'),
                               ('deleted', 'Ištrinta'),
                               ('failed_to_del', 'Nepavyko ištrinti'),
                               ('canceled', 'Atšaukta'),
                               ('failed_to_can', 'Nepavyko atšaukti')], readonly=True, string='Būsena')
    update_date = fields.Date(string='Paskutinio keitimo data',
                              help='Laukelis tuščias, jeigu sąskaita niekada nebuvo naujinta', readonly=True)

    # For failed to delete exports, whom invoice_id is empty
    reference = fields.Char()
    move_name = fields.Char()
    partner_code = fields.Char()
    walless_main_ext_id = fields.Integer(string='Sąskaitos ID pagrindinėje sistemoje')


WallessInvoiceExport()


class ResPartner(models.Model):

    _inherit = 'res.partner'

    vsd_with_royalty = fields.Boolean(string='VSD Pervesti su honoraru')

    # We specify it here, in res_partner, because walless employees aren't employed in the system,
    # thus they don't have the contract
    sodra_royalty_percentage = fields.Selection([('0', 'Nekaupiama'),
                                                 ('1.8', '2.7%'),
                                                 ('3', '3%')],
                                                string='Sodros kaupimo procentas (honorarams)', default='0')


ResPartner()


class AccountInvoice(models.Model):

    _inherit = 'account.invoice'

    export_ids = fields.One2many('walless.invoice.export', 'invoice_id', string='Išskaidytos sąskaitos')
    need_to_create = fields.Boolean(default=False)
    need_to_update = fields.Boolean(default=False)
    employee_invoice = fields.Boolean(compute='_employee_invoice')

    @api.onchange('payment_mode', 'ap_employee_id')
    def onchange_payment_mode(self):
        pass  # overridden from robo module, don't use any partner_id domains in walless

    @api.one
    @api.depends('type', 'partner_id.employee_ids')
    def _employee_invoice(self):
        if self.type in ['in_invoice', 'in_refund'] and self.partner_id.employee_ids:
            self.employee_invoice = True

    def prep_vals(self, iml, inv):
        if inv.employee_invoice:
            # 1.8% value is actually 2.7% value from 2022. Kept 1.8 so that data doesn't have to be updated.
            percentage_mapper = {
                '0': 0.1252,
                '1.8': 0.15221,
                '3': 0.1552,
            }
            try:
                tax_line = next(item for item in iml if 'type' in item and item.get('type') == 'tax')
            except StopIteration:
                tax_line = {}
            try:
                split_line = next(item for item in iml if 'type' in item and item.get('type') == 'dest')
            except StopIteration:
                raise exceptions.Warning(_('Nekorektiškos sąskaitos eilutės'))

            template = {
                'type': 'dest',
                'date_maturity': split_line.get('date_maturity'),
                'invoice_id': split_line.get('invoice_id'),
                'name': split_line.get('name')
            }
            aml_list = []
            if tax_line:
                tax_amt = tax_line.get('price', 0) * -1
                vals = {
                    'account_id': self.env['account.account'].search([('code', '=', '44311')]).id,
                    'price': tax_amt,
                }
                vals.update(template)
                aml_list.append(vals)
            else:
                tax_amt = 0
            split_amount = split_line.get('price', 0)
            split_amount -= tax_amt
            # Calculate amounts
            static_num = percentage_mapper.get(inv.partner_id.sodra_royalty_percentage)

            if not inv.partner_id.vsd_with_royalty:
                vsd_amount = tools.float_round(
                    ((split_amount - split_amount * 0.3) * 0.9) * static_num, precision_digits=2)
                vsd_account = self.env['account.account'].search([('code', '=', '44312')]).id
                vals = {
                    'account_id': vsd_account,
                    'price': vsd_amount,
                }
                vals.update(template)
                aml_list.append(vals)
            else:
                vsd_amount = 0.0
            psd_amount = tools.float_round(((split_amount - split_amount * 0.3) * 0.9) * 0.0698, precision_digits=2)
            psd_account = self.env['account.account'].search([('code', '=', '44313')]).id

            gpm_amount = tools.float_round((split_amount - split_amount * 0.3) * 0.15, precision_digits=2)
            gpm_account = self.env['account.account'].search([('code', '=', '44314')]).id

            old_amt = split_line.get('price', 0)
            total_amount = vsd_amount + psd_amount + gpm_amount + tax_amt
            amt = tools.float_round(old_amt - total_amount, precision_digits=2)
            if tools.float_compare(amt + total_amount, old_amt, precision_digits=2) != 0:
                leftovers = amt + total_amount - old_amt
                amt -= leftovers

            # Apply amount
            next(item for item in iml if 'type' in item and item.get('type') == 'dest')['price'] = amt

            vals = {
                'account_id': psd_account,
                'price': psd_amount,
            }
            vals.update(template)
            aml_list.append(vals)
            vals = {
                'account_id': gpm_account,
                'price': gpm_amount,
            }
            vals.update(template)
            aml_list.append(vals)
            iml += aml_list
        return super(AccountInvoice, self).prep_vals(iml, inv)

    @api.multi
    def action_invoice_proforma2(self):
        deletable = []
        res = super(AccountInvoice, self).action_invoice_proforma2()
        for rec in self:
            if rec.sudo().export_ids:
                for partial_id in rec.sudo().export_ids:
                    partial_id.write({'name_display': rec.name_get()[0][1] if rec.name_get() else ''})
                    shareholder = partial_id.shareholder_id
                    url = shareholder.api_extension + '/api/unlink_invoice'
                    api_secret = shareholder.api_key
                    invoice_data = {
                        'shareholder': shareholder.id,
                        'url': url,
                        'partial_id': partial_id.id,
                        'data': {
                            'secret': api_secret,
                            'walless_main_ext_id': rec.id,
                            'partner_code': rec.partner_id.kodas,
                            'reference': rec.reference,
                            'move_name': rec.move_name
                                }}
                    deletable.append(invoice_data)
        if deletable:
            self.sudo().unlink_exported_invoices(deletable)
        return res

    @api.multi
    def action_invoice_cancel_partners(self):
        self.action_invoice_cancel()
        for rec in self:
            for partial_id in rec.export_ids:
                shareholder = partial_id.shareholder_id
                api_route = '/api/cancel_invoice'
                url = shareholder.api_extension + api_route
                vals = {
                    'walless_main_ext_id': partial_id.invoice_id.id,
                    'secret': shareholder.api_key
                }
                resp = requests.post(url, json=vals)
                code, msg = validate_response(resp, shareholder)
                if code == codes['success']:
                    partial_id.write({'status': 'canceled'})
                else:
                    partial_id.write({'status': 'failed_to_can'})
                self.env.cr.commit()

    @api.multi
    def action_invoice_open(self):
        for rec in self:
            if rec.employee_invoice:
                self = self.with_context(skip_attachments=True)  # skip attachments if at least one invoice is employee
            if rec.move_name and not self._context.get('force_action_create', False) and rec.sudo().export_ids:
                rec.need_to_update = True
            else:
                rec.need_to_create = True
        return super(AccountInvoice, self).action_invoice_open()

    @api.multi
    def unlink(self):
        deletable = []
        for rec in self:
            if rec.export_ids:
                for partial_id in rec.export_ids:
                    partial_id.write({'name_display': rec.name_get()[0][1] if rec.name_get() else ''})
                    shareholder = partial_id.shareholder_id
                    url = shareholder.api_extension + '/api/unlink_invoice'
                    api_secret = shareholder.api_key
                    invoice_data = {
                        'shareholder': shareholder.id,
                        'url': url,
                        'partial_id': partial_id.id,
                        'data': {
                            'secret': api_secret,
                            'walless_main_ext_id': rec.id,
                            'partner_code': rec.partner_id.kodas,
                            'reference': rec.reference,
                            'move_name': rec.move_name
                                }}
                    deletable.append(invoice_data)
        res = super(AccountInvoice, self).unlink()
        self.unlink_exported_invoices(deletable)
        return res

    @api.multi
    def unlink_exported_invoices(self, deletable):
        bug_report = str()
        for rec in deletable:
            shareholder = self.env['res.company.shareholder'].browse(rec.get('shareholder'))
            partial_id = self.env['walless.invoice.export'].browse(rec.get('partial_id'))
            resp = requests.post(rec.get('url'), json=rec.get('data'))
            code, msg = validate_response(resp, shareholder)
            if code == codes['timeout']:
                resp = check_existence_manual(shareholder, partial_id.invoice_id)
            code, msg = validate_response(resp, shareholder)
            if msg and code != codes['timeout']:
                bug_report += msg + '. Partneris - {}\n'.format(shareholder.shareholder_name)
            if code in [codes['success'], codes['inv_not_found']]:
                partial_id.write({'status': 'deleted',
                                  'update_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)})
            else:
                partial_id.write({'status': 'failed_to_del',
                                  'update_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                                  'reference': rec.get('data').get('reference'),
                                  'move_name': rec.get('data').get('move_name'),
                                  'partner_code': rec.get('data').get('partner_code'),
                                  'walless_main_ext_id': rec.get('data').get('walless_main_ext_id'),
                                  })
            self.env.cr.commit()
        if bug_report:
            self.send_bug('REC UNLINK:\n' + bug_report)

    @api.model
    def export_to_shareholders(self):
        action_create = self.env['account.invoice'].search([('need_to_create', '=', True), ('export_ids', '=', False), ('state', 'in', ['open', 'paid', 'cancel'])])
        bug_report = str()
        for rec in action_create:
            if rec.type in ['in_invoice', 'in_refund']:
                shareholder_ids = self.env['res.company.shareholder'].search([('date_from', '<=', rec.date_invoice),
                                                                              '|', ('date_to', '=', False),
                                                                              ('date_to', '>=', rec.date_invoice)])
            else:
                shareholder_ids = self.env['res.company.shareholder'].search([('date_from_income', '<=', rec.date_invoice),
                                                                              '|', ('date_to', '=', False),
                                                                              ('date_to', '>=', rec.date_invoice)])
            total_shares = sum(x.shareholder_shares for x in shareholder_ids)
            api_route = '/api/create_invoice'
            for shareholder in shareholder_ids:
                url = shareholder.api_extension + api_route
                percentage = round(total_shares / shareholder.shareholder_shares, 2)
                data = self.form_dict(rec, shareholder, percentage)
                resp = requests.post(url, json=data)
                code, msg = validate_response(resp, shareholder)
                if code == codes['timeout']:
                    resp = check_existence_manual(shareholder, rec)
                    code, msg = validate_response(resp, shareholder)
                if msg and code != codes['timeout']:
                    bug_report += msg + '. Partneris - {}. Sąskaita - {}\n'.format(
                        shareholder.shareholder_name, rec.move_name or '')
                export_vals = {
                    'invoice_id': rec.id,
                    'name_display': rec.name_get()[0][1] if rec.name_get() else '',
                    'shareholder_id': shareholder.id,
                    'invoice_total_shareholder': tools.float_round(rec.amount_total / percentage, precision_digits=2),
                    'walless_main_ext_id': rec.id,
                }
                if code == codes['success']:
                    export_vals['status'] = 'imported'
                else:
                    export_vals['status'] = 'failed'
                self.env['walless.invoice.export'].create(export_vals)
                self.env.cr.commit()
            rec.need_to_create = False
            self.env.cr.commit()
        if bug_report:
            self.send_bug('REC CREATE:\n' + bug_report)

        bug_report = str()
        action_update = self.env['account.invoice'].search([('need_to_update', '=', True),
                                                            ('state', 'not in', ['proforma', 'proforma2'])])
        for rec in action_update:
            if rec.export_ids:
                total_shares = sum(x.shareholder_shares for x in rec.export_ids.mapped('shareholder_id'))
                for partial in rec.export_ids:
                    status = partial.status
                    shareholder = partial.shareholder_id
                    percentage = tools.float_round(total_shares / shareholder.shareholder_shares, precision_digits=2)
                    if status in ['imported', 'canceled'] or (status == 'failed' and partial.update_date):
                        api_route = '/api/update_invoice'
                        url = shareholder.api_extension + api_route
                        data = self.with_context(force_ref=True).form_dict(rec, shareholder, percentage)
                        resp = requests.post(url, json=data)
                        code, msg = validate_response(resp, shareholder)
                        if code == codes['timeout']:
                            resp = check_existence_manual(shareholder, partial.invoice_id)
                            code, msg = validate_response(resp, shareholder)
                        if msg and code != codes['timeout']:
                            bug_report += msg + '. Partneris - {}. Sąskaita - {}\n'.format(
                                shareholder.shareholder_name, partial.invoice_id.move_name or '')
                        if code == codes['success']:
                            partial.write({
                                'update_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                                'status': 'imported'
                            })
                        else:
                            partial.write({
                                'update_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                                'status': 'failed'
                            })
                    else:
                        api_route = '/api/create_invoice'
                        url = shareholder.api_extension + api_route
                        data = self.form_dict(rec, shareholder, percentage)
                        resp = requests.post(url, json=data)
                        code, msg = validate_response(resp, shareholder)
                        if code == codes['timeout']:
                            resp = check_existence_manual(shareholder, partial.invoice_id)
                            code, msg = validate_response(resp, shareholder)
                        if code == codes['success']:
                            partial.write({'status': 'imported'})
                        else:
                            partial.write({'status': 'failed'})
                    self.env.cr.commit()
            rec.need_to_update = False
            self.env.cr.commit()
        if bug_report:
            self.send_bug('REC UPDATE:\n' + bug_report)

    @api.model
    def check_existence(self):
        invoices = self.env['account.invoice'].search([('export_ids.status', '=', 'failed')])
        for rec in invoices:
            for partial_id in rec.export_ids:
                shareholder = partial_id.shareholder_id
                api_route = '/api/check_invoice'
                url = shareholder.api_extension + api_route
                vals = {
                    'walless_main_ext_id': partial_id.invoice_id.id,
                    'secret': shareholder.api_key
                }
                resp = requests.post(url, json=vals)
                code, msg = validate_response(resp, shareholder)
                if code == codes['success']:
                    partial_id.write({'status': 'imported'})
                else:
                    partial_id.write({'status': 'failed'})
                self.env.cr.commit()

    @api.model
    def re_delete_failed(self):
        exports = self.env['walless.invoice.export'].search([('status', '=', 'failed_to_del')])
        bug_report = str()
        for partial_id in exports:
            shareholder = partial_id.shareholder_id
            url = shareholder.api_extension + '/api/unlink_invoice'
            api_secret = shareholder.api_key
            data = {
                'secret': api_secret,
                'walless_main_ext_id': partial_id.walless_main_ext_id,
                'partner_code': partial_id.partner_code,
                'reference': partial_id.reference,
                'move_name': partial_id.move_name
            }
            resp = requests.post(url, json=data)
            code, msg = validate_response(resp, shareholder)
            if code == codes['timeout']:
                resp = check_existence_manual(shareholder, partial_id.invoice_id)
                code, msg = validate_response(resp, shareholder)
            if msg and code != codes['timeout']:
                bug_report += msg + '. Partneris - {}\n'.format(shareholder.shareholder_name)
            if code in [codes['success'], codes['inv_not_found']]:
                partial_id.write({'status': 'deleted'})
            else:
                partial_id.write({'status': 'failed_to_del',
                                  'update_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                })
            self.env.cr.commit()
        if bug_report:
            self.send_bug('REC RE-DELETE:\n' + bug_report)

    @api.model
    def re_export_failed(self):
        invoices = self.env['account.invoice'].search([('export_ids.status', '=', 'failed')])
        bug_report = str()
        for rec in invoices:
            total_shares = sum(x.shareholder_shares for x in rec.export_ids.mapped('shareholder_id'))
            for partial_id in rec.export_ids:
                shareholder = partial_id.shareholder_id
                percentage = tools.float_round(total_shares / shareholder.shareholder_shares, precision_digits=2)
                api_route = '/api/update_invoice' if partial_id.update_date else '/api/create_invoice'
                url = shareholder.api_extension + api_route
                data = self.with_context(force_ref=True).form_dict(rec, shareholder, percentage)
                resp = requests.post(url, json=data)
                code, msg = validate_response(resp, shareholder)
                if code == codes['timeout']:
                    resp = check_existence_manual(shareholder, partial_id.invoice_id)
                    code, msg = validate_response(resp, shareholder)
                if msg and code != codes['timeout']:
                    bug_report += msg + '. Partneris - {}\n'.format(shareholder.shareholder_name)
                if code == codes['success']:
                    partial_id.write({'status': 'imported'})
                else:
                    partial_id.write({'status': 'failed'})
                self.env.cr.commit()
        if bug_report:
            self.send_bug('REC RE-EXPORT:\n' + bug_report)

    def form_dict(self, invoice, shareholder, percentage):
        api_secret = shareholder.api_key
        if not api_secret:
            return {}
        lines = []
        for line in invoice.invoice_line_ids:
            tax_code = False
            if line.invoice_line_tax_ids:
                if len(line.invoice_line_tax_ids) > 1:
                    res = line.invoice_line_tax_ids.filtered(lambda x: not x.code.startswith('A'))
                    if len(res) == 1:
                        tax_code = res.code
                        if res.nondeductible:
                            tax_code += 'N'
                        if res.nondeductible_profit:
                            tax_code += 'NP'
                    else:
                        self.send_bug('WALLESS REC EXPORT: Found multiple tax lines '
                                      'after filtering out "A" codes. Invoice number %s' % invoice.number)
                else:
                    tax_code = line.invoice_line_tax_ids.code
                    if line.invoice_line_tax_ids.nondeductible and not line.invoice_line_tax_ids.nondeductible_profit:
                        tax_code += 'N'
                    elif line.invoice_line_tax_ids.nondeductible_profit:
                        tax_code += 'NP'
            lines.append(
                {
                    'product': line.product_id.name or line.name,
                    'description': line.name,
                    'price': tools.float_round(line.price_unit_tax_excluded / percentage, precision_digits=2),
                    'qty': line.quantity,
                    'vat_code': tax_code,
                    'analytic_code': line.account_analytic_id.code,
                })
        data = {
            'secret': api_secret,
            'debug': 'robotukai',
            'walless_main_ext_id': invoice.id,
            'force_ref': self._context.get('force_ref', False),
            'date_invoice': invoice.date_invoice,
            'date_due': invoice.date_due,
            'cancelled': True if invoice.state == 'cancel' else False,
            'number': invoice.reference if invoice.type in ['in_refund', 'in_invoice'] and invoice.reference else invoice.move_name,
            'move_name': invoice.reference if invoice.type in ['in_refund', 'in_invoice'] and invoice.reference else invoice.move_name,
            'reference': invoice.reference if invoice.type in ['in_refund', 'in_invoice'] and invoice.reference else invoice.move_name,
            'journal': invoice.journal_id.code,
            'skip_isaf': invoice.skip_isaf,
            'currency': invoice.currency_id.name,
            'proforma': False,
            'force_dates': True,
            'force_type': invoice.type,
            'registration_date': invoice.registration_date or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'supplier_invoice': True if invoice.type in ['in_invoice', 'in_refund'] else False,
            'partner': {
                'name': invoice.partner_id.name,
                'is_company': invoice.partner_id.is_company,
                'company_code': invoice.partner_id.kodas,
                'vat_code': invoice.partner_id.vat,
                'street': invoice.partner_id.street,
                'city': invoice.partner_id.city,
                'zip': invoice.partner_id.zip,
                'country': invoice.partner_id.country_id.code,
                'phone': invoice.partner_id.phone,
                'email': invoice.partner_id.email,
            },
            'invoice_lines': lines,
        }
        return data

    def send_bug(self, body):
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'error_message': body,
            'subject': 'WALLESS -- Export Errors [%s]' % self._cr.dbname,
        })


AccountInvoice()


class ResCompanyShareholder(models.Model):

    _inherit = 'res.company.shareholder'

    api_key = fields.Char(string='API Raktas', required=True)
    api_extension = fields.Char(string='Kliento internetinis adresas', required=True)
    date_from = fields.Date(string='Akcininkas nuo (Išlaidos)', required=True, inverse='check_expense_from')
    date_from_income = fields.Date(string='Akcininkas nuo (Pajamos)', required=True, inverse='check_income_from')
    date_to = fields.Date(string='Akcininkas iki', inverse='check_general_to')
    export_ids = fields.One2many('walless.invoice.export', 'shareholder_id',
                                 string='Walless eksportavimo operacijų sąrašas')

    @api.one
    def check_expense_from(self):
        if self.date_from:
            invoice_ids = self.env['account.invoice'].search([('date_invoice', '>=', self.date_from),
                                                              ('type', 'in', ['in_invoice', 'in_refund'])])
            if invoice_ids:
                body = 'WALLESS DUOMENŲ INTEGRALUMO PAŽEIDIMAS. Pridėtas partneris %s, ' \
                       'kurio išlaidų akcijos skaičiuojamos nuo %s. sistemoje rastos šios sąskaitos ' \
                       'nuo minimos datos: %s' % (self.shareholder_name, self.date_from,
                                               str(invoice_ids.mapped('reference')))
                self.send_bug(body)

    @api.one
    def check_income_from(self):
        if self.date_from_income:
            invoice_ids = self.env['account.invoice'].search([('date_invoice', '>=', self.date_from_income),
                                                              ('type', 'in', ['out_invoice', 'out_refund'])])
            if invoice_ids:
                body = 'WALLESS DUOMENŲ INTEGRALUMO PAŽEIDIMAS. Pridėtas partneris %s, ' \
                       'kurio pajamų akcijos skaičiuojamos nuo %s. sistemoje rastos šios saskaitos ' \
                       'nuo minimos datos: %s' % (self.shareholder_name, self.date_from_income,
                                               str(invoice_ids.mapped('move_name')))
                self.send_bug(body)

    @api.one
    def check_general_to(self):
        if self.date_from:
            invoice_ids = self.env['account.invoice'].search([('date_invoice', '>=', self.date_from)])
            if invoice_ids:
                exp_names = invoice_ids.filtered(lambda x: x.type in ['in_invoice', 'in_refund']).mapped('reference')
                inc_names = invoice_ids.filtered(lambda x: x.type in ['out_invoice', 'out_refund']).mapped('number')
                names = exp_names + inc_names
                body = 'WALLESS DUOMENŲ INTEGRALUMO PAŽEIDIMAS. Pridėtas partneris %s, ' \
                       'kurio akcijos baigiasi nuo %s. sistemoje rastos šios saskaitos ' \
                       'nuo minimos datos: %s' % (self.shareholder_name, self.date_from,
                                               str(names))
                self.send_bug(body)

    @api.multi
    def name_get(self):
        return [(rec.id, rec.shareholder_name) for rec in self]

    @api.multi
    @api.constrains('api_extension')
    def check_api_extension(self):
        for rec in self:
            if not ('http://' in rec.api_extension or 'https://' in rec.api_extension):
                raise exceptions.Warning(_('Neteisingas kliento adresas!'))

    def send_bug(self, body):
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'error_message': body,
        })


ResCompanyShareholder()


class AccountSepaImport(models.TransientModel):
    _inherit = 'account.sepa.import'

    def _complete_rpt_vals(self, rpts_vals):
        stmnts = []
        balance_vals = []
        num_orig_txs = 0
        notifications = []
        num_duplicate = 0
        num_errors = 0
        num_imported = 0
        for rpt_val in rpts_vals:
            num_orig_txs += len(rpt_val.get('transactions', []))
            currency_code, account_number = rpt_val.get('currency', 'EUR'), rpt_val.get('account_number')  # assume default currency EUR

            if not account_number:
                raise exceptions.ValidationError(_('Account number is not specified'))

            currency, journal = self._find_additional_data(currency_code, account_number)
            if not journal:
                raise exceptions.Warning(
                    _('Reikia pririšti sąskaitą %s (%s) prie žurnalo') % (account_number, currency_code))
            bank_code = account_number[4:9]
            company_codes = ['walless', '47707270036']
            if bank_code not in bank_codes_limitations:
                if rpt_val.get('stmt_company') and rpt_val.get('stmt_company') not in company_codes:
                    raise exceptions.Warning(_('Neatitikimas tarp kompanijų!'))

            values = self.get_statement_values(rpt_val, journal.id, currency)
            stmnts.extend(values['statements'])
            balance_end_real = rpt_val['balance_end_real']
            balance_end_date = rpt_val['balance_end_date']
            balance_vals.append({'journal_id': journal.id, 'date': balance_end_date, 'amount': balance_end_real})
            num_imported += values['num_imported']
            num_duplicate += values['num_duplicate']
            num_errors += values['num_errors']
            notifications.extend(values['notifications'])
        return stmnts, num_imported, balance_vals, num_orig_txs, num_duplicate, num_errors, notifications


AccountSepaImport()


class EDocumentBusinessTripWorkSchedule(models.Model):
    _inherit = 'e.document.business.trip.employee.line'

    @api.onchange('allowance_percentage', 'employee_id')
    def _onchange_allowance_percentage_or_employee_id(self):
        self.e_document_id._num_calendar_days()
        is_company_manager = self.employee_id.id == self.env.user.company_id.vadovas.id
        allowance_percentage = self.allowance_percentage
        if self.allowance_percentage < 50:
            allowance_percentage = 0
        elif 200 >= allowance_percentage > 100:
            if not is_company_manager:
                allowance_percentage = 100
        elif allowance_percentage > 200:
            allowance_percentage = 100 if is_company_manager else 200
        norma = allowance_percentage / 100.0
        self.allowance_percentage = allowance_percentage
        amount = self.e_document_id.country_allowance_id.get_amount(self.e_document_id.date_from,
                                                                    self.e_document_id.date_to)
        self.allowance_amount = tools.float_round(amount * norma, precision_digits=2)


EDocumentBusinessTripWorkSchedule()


class WallessExportWizard(models.TransientModel):
    _name = 'walless.export.wizard'

    export_type = fields.Selection([('split_invoices', 'Skaidyti sąskaitas'),
                                    ('re_export_failed', 'Eksportuoti suklydusias sąskaitas'),
                                    ('re_delete_failed', 'Ištrinti suklydusias sąskaitas')],
                                   required=True, default='split_invoices', string='Eksportavimo tipas')

    @api.multi
    def execute(self):
        self.ensure_one()
        vals = {
            'operation_code': self.export_type,
            'execution_start_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            'state': 'in_progress'
        }
        job_id = self.env['walless.export.jobs'].create(vals)
        threaded_calculation = threading.Thread(target=self.export_thread,
                                                args=(job_id.id, self.export_type, ))
        threaded_calculation.start()

    @api.multi
    def export_thread(self, job_id, export_type):
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, odoo.SUPERUSER_ID, {'lang': 'lt_LT'})
            job_id = env['walless.export.jobs'].browse(job_id)
            try:
                if export_type in ['split_invoices']:
                    env['account.invoice'].sudo().export_to_shareholders()
                elif export_type in ['split_invoices']:
                    env['account.invoice'].sudo().re_export_failed()
                else:
                    env['account.invoice'].sudo().re_delete_failed()
            except Exception as exc:
                new_cr.close()
                job_id.write({'state': 'failed',
                              'fail_message': str(exc.args[0]),
                              'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
            else:
                job_id.write({'state': 'finished',
                              'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
            new_cr.commit()
            new_cr.close()


class WallessExportJobs(models.Model):
    _name = 'walless.export.jobs'

    operation_code = fields.Char(string='Operacijos identifikatorius')
    execution_start_date = fields.Datetime(string='Vykdymo pradžia')
    execution_end_date = fields.Datetime(string='Vykdymo Pabaiga')
    state = fields.Selection([('in_progress', 'Vykdomas'),
                              ('finished', 'Sėkmingai įvykdytas'),
                              ('failed', 'Vykdymas nepavyko')],
                             string='Būsena')
    fail_message = fields.Char(string='Klaidos pranešimas')


WallessExportJobs()
