# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import api, exceptions, fields, models, tools, _


class OverpayTransferRequestWizard(models.TransientModel):
    _name = 'overpay.transfer.request.wizard'

    def _get_bank_account_domain(self):
        return [
            ('type', '=', 'bank'),
            ('show_on_dashboard', '=', True),
            ('bank_account_id.acc_number', '!=', False),
            ('display_on_footer', '=', True)
        ]

    date = fields.Date(string='Date', default=fields.Date.today)
    bank_account = fields.Many2one('account.journal', string='Bank account',
                                   domain=_get_bank_account_domain,
                                   default=lambda self: self.env.user.company_id.payroll_bank_journal_id)
    amount = fields.Float(string='Amount total')
    overpay_line_ids = fields.One2many('overpay.transfer.request.wizard.lines', 'wizard_id')
    force_lang = fields.Selection([
        ('lt_LT', 'Lithuanian'),
        ('en_US', 'English'),
    ], string='Report language', )
    show_button_send_report_en = fields.Boolean(compute='_compute_show_button_send_report_en')

    @api.multi
    @api.depends('force_lang')
    def _compute_show_button_send_report_en(self):
        for rec in self:
            lang = rec.force_lang or self.env.user.lang
            rec.show_button_send_report_en = True if lang == 'en_US' else False

    @api.multi
    def get_data(self):
        self.ensure_one()
        if not self.overpay_line_ids:
            raise exceptions.ValidationError(_('In order to generate the request, please fill in at least one line'))
        amount_total = sum(line.amount for line in self.overpay_line_ids)
        if tools.float_compare(amount_total, 0, precision_digits=2) <= 0:
            raise exceptions.ValidationError(
                _('The sum of all lines is less than or equal to zero ({})').format(amount_total))
        data = {
            'date': self.date,
            'partner_id': self._context.get('partner_ids')[0],
            'journal_id': self.bank_account.id,
            'overpay_line_ids': self.overpay_line_ids.ids,
            'total': amount_total,
            'force_lang': self.force_lang or self._context.get('lang') or self.env.user.lang or 'lt_LT'
        }
        return data

    @api.multi
    def generate_overpay_transfer_request(self):
        self.ensure_one()
        if not (self.env.user.is_accountant() or self.env.user.has_group('robo.group_overpay_transfer_requests')):
            raise exceptions.AccessError(_('User does not have the correct rights to form overpay transfer request'))
        data = self.get_data()
        self.amount = data.get('total')
        return self.env['report'].with_context(lang=data.get('force_lang')).get_action(
            self, 'robo.report_overpay_transfer_request', data=data)

    @api.onchange('overpay_line_ids')
    def _onchange_overpay_line_ids(self):
        if self.overpay_line_ids:
            self.amount = sum(line.amount for line in self.overpay_line_ids)

    def send_overpay_transfer_request(self):
        self.ensure_one()

        if not (self.env.user.is_accountant() or self.env.user.has_group('robo.group_overpay_transfer_requests')):
            raise exceptions.AccessError(_('User does not have the correct rights to form overpay transfer request'))

        email_template = self.env.ref('robo.email_template_overpay_transfer_request', False)
        compose_form = self.env.ref('robo.email_compose_message_wizard_form', False)
        if not email_template or not compose_form:
            raise exceptions.ValidationError(
                _('Overpay transfer request could not be sent. Please, contact the system administrator.'))

        partner_ids = self._context.get('partner_ids')
        partners = self.env['res.partner'].browse(partner_ids)
        partner_data = []
        for partner in partners:
            partner_data.append({
                'partner_id': partner.id,
                'email': partner.email,
                'name': partner.name,
            })

        document_data = self.get_data()

        ctx = {
            'default_model': 'robo.mail.mass.mailing.partners',
            'default_use_template': bool(email_template),
            'default_template_id': email_template.id,
            'default_composition_mode': 'mass_mail',
            'partner_ids': partner_ids,
            'partner_data': partner_data,
            'document_data': document_data,
            'group_email_send': 'robo.group_overpay_transfer_requests',
            'cron_send_mail': True,
        }

        return {
            'name': _('Rašyti laišką'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'robo.mail.compose.message',
            'views': [(compose_form.id, 'form')],
            'view_id': compose_form.id,
            'target': 'current',
            'context': ctx,
            'flags': {'form': {'action_buttons': False}}
        }


class OverpayTransferRequestWizardLines(models.TransientModel):
    _name = 'overpay.transfer.request.wizard.lines'

    wizard_id = fields.Many2one('overpay.transfer.request.wizard', string='Wizard', ondelete='cascade')
    date = fields.Date(string='Payment date')
    purpose = fields.Char(string='Payment purpose')
    amount = fields.Float(string='Payment amount')
