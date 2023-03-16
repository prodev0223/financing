# -*- coding: utf-8 -*-
from odoo import fields, models, api, _, exceptions
from odoo.tools import float_is_zero
import json

STATES = {
    'draft': _('Juodraštis'),
    'open': _('Laukiama'),
    'proforma': _('Išankstinė'),
    'proforma2': _('Išankstinė'),
    'paid': _('Apmokėta'),
    'cancel': _('Atšaukta'),
    'imported': _('Laukia papildymo'),
}

STATE_CLASS = {
    'draft': 'draftClass',
    'open': 'openClass',
    'proforma': 'proformaClass',
    'proforma2': 'proforma2Class',
    'paid': 'paidClass',
    'cancel': 'cancelClass',
    'imported': 'importedClass',
}


class AccountInvoice(models.Model):

    _inherit = 'account.invoice'

    accountant_validated = fields.Boolean(string='Validated by accountant', default=False, readonly=True, copy=False, track_visibility='onchange')
    reconciled = fields.Boolean(compute='_compute_residual')
    residual = fields.Monetary(compute='_compute_residual')
    residual_signed = fields.Monetary(compute='_compute_residual')
    residual_company_signed = fields.Monetary(compute='_compute_residual')
    pdf = fields.Binary(compute='_pdf')
    show_pdf = fields.Boolean(compute='_pdf')
    state_amount = fields.Text(string='Neapmokėta suma', compute='_state_amount')
    accountant_validated_text = fields.Text(string='Is validated by accountant', default=_("Patvirtinta buhalterio"),
                                            compute='get_accountant_validated_text', readonly=1, store=False)
    show_image_gallery = fields.Boolean(compute='_compute_show_image_gallery')
    attached_images = fields.Many2many('ir.attachment', compute='_compute_attached_images')

    @api.one
    def _compute_show_image_gallery(self):
        self.show_image_gallery = any(attachment.index_content == 'image' for attachment in self.attachment_ids)

    @api.one
    def _compute_attached_images(self):
        self.attached_images = self.attachment_ids.filtered(lambda a: a.index_content == 'image')

    @api.one
    def get_accountant_validated_text(self):
        self.accountant_validated_text = _('Patvirtinta buhalterio')

    @api.one
    @api.depends('residual_signed', 'currency_id', 'state', 'type')
    def _state_amount(self):
        if self.type in ['in_invoice', 'in_refund']:
            state = self.expense_state
        else:
            state = self.state
        result = {
            'amount': self.residual_signed,
            'digits': self.currency_id.decimal_places,
            'position': self.currency_id.position,
            'state': STATES.get(state, 'Juodraštis'),
            'symbol': self.currency_id.symbol,
            'class': STATE_CLASS.get(self.state, 'draftClass')
        }
        self.state_amount = json.dumps(result)

    @api.multi
    def mark_validated(self):
        self.write({'accountant_validated': True})

    @api.multi
    def mark_invalidated(self):
        self.write({'accountant_validated': False})

    @api.model
    def create_invoice_validation_actions(self):
        action = self.env.ref('robo_accountants.invoice_mark_validated_server_action')
        if action:
            action.create_action()
        action = self.env.ref('robo_accountants.invoice_mark_invalidated_server_action')
        if action:
            action.create_action()

    @api.one
    @api.depends(
        'state', 'currency_id', 'invoice_line_ids.price_subtotal',
        'distributed_move_id.line_ids.amount_residual', 'distributed_move_id.line_ids.currency_id',
        'move_id.line_ids.amount_residual', 'move_id.line_ids.currency_id',
        'amount_total_company_signed',
        'proforma_paid')
    def _compute_residual(self):
        residual = 0.0
        residual_company_signed = 0.0
        sign = self.type in ['in_refund', 'out_refund'] and -1 or 1
        if self.state in ['proforma', 'proforma2']:
            if self.proforma_paid:
                self.residual = 0.0
                self.residual_company_signed = 0.0
                self.residual_signed = 0.0
            else:
                self.residual = abs(self.amount_total)
                self.residual_company_signed = self.amount_total_company_signed
                self.residual_signed = self.amount_total * sign
        else:
            if self.distributed_payment and self.distributed_move_id:
                lines = self.sudo().env['account.move.line'].search([('move_id', '=', self.distributed_move_id.id),
                                                                     ('account_id', '=', self.distributed_account_id.id)])
            else:
                lines = self.sudo().move_id.line_ids
            account_id = self.sudo().account_id
            for line in lines:
                if line.account_id.id == account_id.id:
                    residual_company_signed += line.amount_residual
                    if line.currency_id == self.currency_id:
                        residual += line.amount_residual_currency if line.currency_id else line.amount_residual
                    else:
                        from_currency = (line.currency_id and line.currency_id.with_context(
                            date=line.date)) or line.company_id.currency_id.with_context(date=line.date)
                        residual += from_currency.compute(line.amount_residual, self.currency_id)
            self.residual_company_signed = abs(residual_company_signed) * sign
            self.residual_signed = abs(residual) * sign
            self.residual = abs(residual)
            self.reconciled = float_is_zero(self.residual, precision_rounding=self.currency_id.rounding)

    @api.one
    def _pdf(self):
        if 'out' in self.type:
            order = 'create_date desc'
        else:
            order = 'create_date asc'
        attachment_ids = self.env['ir.attachment'].search([('res_model', '=', 'account.invoice'),
                                                          ('res_id', '=', self.id)],
                                                         order=order)
        for attachment_id in attachment_ids:
            if attachment_id and attachment_id.mimetype == 'application/pdf':
                self.show_pdf = True
                self.pdf = attachment_id.datas
                break
        if not self.pdf and self.hr_expense_id:
            # if self.hr_expense_id.attachment:
            #     self.show_pdf = True
            #     self.pdf = self.hr_expense_id.attachment
            # else:
            attachment_id = self.env['ir.attachment'].search([('res_model', '=', 'hr.expense'),
                                                              ('res_id', '=', self.hr_expense_id.id)],
                                                             order='create_date desc', limit=1)
            if attachment_id and attachment_id.mimetype == 'application/pdf':
                self.show_pdf = True
                self.pdf = attachment_id.datas

    # @api.multi
    # def _get_self_sudo(self):
    #     try:
    #         self.check_access_rights('write')
    #         self.check_access_rule('write')
    #         self.check_access_rights('unlink')
    #         self.check_access_rule('unlink')
    #         self.ensure_not_accounant_validated()
    #         self = self.sudo()
    #     except:
    #         pass
    #     return self
    #
    # @api.multi
    # def action_invoice_cancel(self):
    #     self = self._get_self_sudo()
    #     return super(AccountInvoice, self).action_invoice_cancel()
    #
    # @api.multi
    # def action_invoice_open(self):
    #     self = self._get_self_sudo()
    #     return super(AccountInvoice, self).action_invoice_open()

    @api.multi
    def ensure_not_accountant_validated(self):
        if not self.env.user.is_accountant() and not self._context.get('skip_accountant_validated_check', False):
            for rec in self:
                if rec.accountant_validated and rec.state not in ['proforma', 'proforma2']:
                    raise exceptions.Warning(_('Negalima keisti sąskaitos, kurią peržiūrėjo buhalteris.'))

    @api.multi
    def write(self, vals):
        if not self.env.user.is_accountant():
            if 'accountant_validated' in vals:
                vals.pop('accountant_validated')
            bypass_values = {'date_due_report', 'state', 'bank_export_state', 'bank_export_residual', 'picking_id', 'partner_lang'}
            if not self._context.get('skip_accountant_validated_check') and not set(vals).issubset(bypass_values):
                # Unless invoice is in proforma state, if an invoice has been validated by accountant, a normal user can
                # only change its state (e.g. by paying it) or date_due_report
                for rec in self:
                    if rec.accountant_validated and rec.state not in ['proforma', 'proforma2']:
                        raise exceptions.UserError(_('Negalima keisti sąskaitos, kurią peržiūrėjo buhalteris.'))
        return super(AccountInvoice, self).write(vals)


AccountInvoice()


class AccountInvoiceLine(models.Model):

    _inherit = 'account.invoice.line'

    @api.multi
    def write(self, vals):
        allow = self.env.user.sudo().company_id.change_analytic_on_accountant_validated
        if not self.env.user.is_accountant() and not ('account_analytic_id' in vals and len(vals) == 1 and allow):
            self.mapped('invoice_id').ensure_not_accountant_validated()
        return super(AccountInvoiceLine, self).write(vals)


AccountInvoiceLine()
