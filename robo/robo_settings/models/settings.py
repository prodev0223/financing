# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, tools
from email.utils import formataddr


# class ResCompany(models.Model):
#
#     _inherit = 'res.company'
#
#     @api.model_cr
#     def init(self):
#         self.env['web.planner'].search([('active', '=', True)]).write({'active': False})
#         # self.search([]).write({'vat_check_vies': True})
#         lt = self.env['res.lang'].search([('code', '=', 'lt_LT')], limit=1)
#         if lt:
#             lt.write({'thousands_sep': "'"})
#
#
# ResCompany()


class BaseImport(models.TransientModel):

    _inherit = 'base_import.import'

    @api.model
    def get_fields(self, model, depth=2):
        if self.env.user.has_group('robo_basic.group_robo_import_export'):
            return super(BaseImport, self).get_fields(model, depth)
        else:
            return []

    @api.multi
    def do(self, fields, options, dryrun=False):
        if self.env.user.has_group('robo_basic.group_robo_import_export'):
            return super(BaseImport, self).do(fields, options, dryrun)
        else:
            return []

BaseImport()


class ResUsers(models.Model):

    _inherit = 'res.users'

    mobile = fields.Char(string='Mobile phone')

    # @api.multi
    # def is_back_user(self):
    #     self.ensure_one()
    #     if not self.is_accountant() and self.is_user():
    #         return False
    #     else:
    #         return True


ResUsers()


class MailMessage(models.Model):
    _inherit = 'mail.message'

    @api.model
    def _get_default_universal_from(self):
        param_obj = self.sudo().env['ir.config_parameter']
        if self._context.get('custom_layout', False) in ['account.mail_template_data_notification_email_account_invoice',
                                                         'due_payments.apr_email_template_res_partner_before_invoice',
                                                         'due_payments.apr_email_template_res_partner_on_date_invoice',
                                                         'due_payments.apr_email_template_res_partner_after_invoice'] or \
                self._context.get('client_company', False):
            company_name = self.sudo().env.user.company_id.name
        else:
            company_name = param_obj.get_param('email_sender_name')
        email_address = self._context.get('force_email_sender_mail', False) or param_obj.get_param('email_sender_mail')
        if self._context.get('force_email_sender_name'):
            company_name = self._context.get('force_email_sender_name')
        if not company_name or not email_address:
            return self._get_default_from()
        return formataddr((company_name, email_address))

    @api.model
    def create(self, values):
        if 'email_from' not in values:
            values['email_from'] = self._get_default_universal_from()
        return super(MailMessage, self).create(values)


MailMessage()
