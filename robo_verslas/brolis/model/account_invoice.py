# -*- coding: utf-8 -*-
from odoo import models, _, api, tools
from odoo.addons.queue_job.job import job


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

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


AccountInvoice()
