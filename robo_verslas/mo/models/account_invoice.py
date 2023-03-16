# -*- coding: utf-8 -*-
from odoo import models, _, api, tools
from odoo.addons.queue_job.job import job


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.multi
    def action_invoice_open(self):
        module_id = self.sudo().env['ir.module.module'].search([('name', '=', 'robo_konsignacija')])
        if module_id and module_id.state in ['installed', 'to upgrade']:
            account_id = self.env['account.account'].search([('code', '=', '6000')])
            if not self._context.get('skip_consignation_account_force', False):
                for rec in self:
                    invoice_lines = rec.invoice_line_ids
                    for line in invoice_lines:
                        if line.product_id.consignation and rec.type in ['in_invoice', 'in_refund']:
                            line.account_id = account_id
        return super(AccountInvoice, self).action_invoice_open()

    @api.multi
    @job
    def action_invoice_cancel_draft(self):
        if not self.env.user.has_group('base.group_system'):
            self.check_access_rights('write')
            self.check_access_rule('write')
            self.mapped('move_id')._check_lock_date()
            for rec in self:
                rec.message_post('Resetting invoice to draft')
        return super(AccountInvoice, self.sudo()).action_invoice_cancel_draft()

    @api.multi
    def action_invoice_cancel(self):
        if not self.env.user.has_group('base.group_system'):
            self.check_access_rights('write')
            self.check_access_rule('write')
            self.mapped('move_id')._check_lock_date()
            for rec in self:
                rec.message_post('Cancelling invoice')
        return super(AccountInvoice, self.sudo()).action_invoice_cancel()

    @api.multi
    def action_invoice_draft(self):
        if not self.env.user.has_group('base.group_system'):
            self.check_access_rights('write')
            self.check_access_rule('write')
            self.mapped('move_id')._check_lock_date()
            for rec in self:
                rec.message_post('Resetting invoice to draft')
        return super(AccountInvoice, self.sudo()).action_invoice_draft()

    @api.model
    def send_bug(self, body):
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'error_message': body,
        })


AccountInvoice()
