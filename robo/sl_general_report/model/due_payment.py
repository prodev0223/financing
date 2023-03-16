# -*- encoding: utf-8 -*-
from odoo import models, fields, _, api, exceptions, tools
import datetime


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.multi
    def open_partner_filter_wizard(self):
        form_id = self.env.ref('sl_general_report.payment_reminder_wizard').id
        return {
            'name': _('Partner Selection'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'payment.reminder',
            'views': [(form_id, 'form')],
            'view_id': form_id,
            'target': 'new',
            'context': self._context,
        }


ResPartner()


class PaymentReminder(models.TransientModel):

    _name = 'payment.reminder'

    filter = fields.Selection([('due_payment', 'Send email to partners who have due payments'),
                               ('unpaid_payment', 'Send email to partners who have unpaid payments')],
                              string='Partner Filter', required=True, default='due_payment')

    @api.multi
    def open_email_compose(self):

        ctx = dict(self._context)
        active_ids = ctx['active_ids'] if 'active_ids' in ctx else False
        filter = self.filter
        if filter == 'due_payment':
            due_payments = self.env['account.invoice'].search([('state', 'in', ['open']),
                                                               ('date_due', '<', datetime.datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)),
                                                               ('partner_id', 'in', active_ids)])
            partner_ids = set(due_payments.mapped('partner_id.id'))
            if not partner_ids:
                raise exceptions.UserError(_('There are no customers with due payments.'))
        else:
            due_payments = self.env['account.invoice'].search([('state', 'in', ['open']),
                                                               ('partner_id', 'in', active_ids)])
            partner_ids = set(due_payments.mapped('partner_id.id'))
            if not partner_ids:
                raise exceptions.UserError(_('There are no customers with unpaid payments.'))
        active_ids = list(partner_ids)
        template_id = self.env.ref('due_payments.email_template_partner_due_payment').id
        ctx.update({
            'default_model': 'res.partner',
            'default_use_template': bool(template_id),
            'default_template_id': template_id,
            'default_composition_mode': 'mass_mail',
            'active_ids': active_ids,
        })
        compose_form_id = self.env.ref('mail.email_compose_message_wizard_form').id
        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form_id, 'form')],
            'view_id': compose_form_id,
            'target': 'new',
            'context': ctx,
        }


PaymentReminder()
