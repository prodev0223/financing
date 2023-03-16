# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models


class AccountInvoicePartnerChangeWizard(models.TransientModel):
    _name = 'account.invoice.partner.change.wizard'

    @api.multi
    def partner_id_domain(self):
        if self._context.get('inv_type', False) == 'out':
            return [('advance_payment', '=', False), '|', ('customer', '=', True), ('is_employee', '=', False)]
        else:
            return [('is_employee', '=', False)]

    invoice_id = fields.Many2one('account.invoice', string='Sąskaita faktūra')
    partner_id = fields.Many2one('res.partner', string='Partneris', domain=partner_id_domain)
    has_picking = fields.Boolean(compute='_compute_has_picking')

    @api.multi
    @api.depends('invoice_id')
    def _compute_has_picking(self):
        """Checks whether related invoice has pickings"""
        for rec in self:
            pickings = rec.invoice_id.get_related_pickings()
            if pickings:
                rec.has_picking = True

    @api.multi
    def change_partner_id(self):
        """
        Method used to change partner to account_invoice.
        if invoice is in open or paid state, remove outstanding payments, cancel,
        write partner_id to invoice and related payments, re-confirm
        and re-assign specific outstanding payments
        :return: None
        """

        self.ensure_one()
        if not self.env.user.is_accountant() and not \
                self.env.user.has_group('robo.group_robo_invoice_partner_change_wizard'):
            raise exceptions.AccessError(_('You do not have sufficient rights'))

        if not self.partner_id:
            raise exceptions.UserError(_('Privalote pasirinkti partnerį!'))

        invoice = self.with_context(skip_accountant_validated_check=True).invoice_id

        if not self.env.user.has_group('base.group_system'):
            invoice.check_access_rights('write')
            invoice.check_access_rule('write')
            if invoice.move_id:
                invoice.mapped('move_id')._check_lock_date()
            invoice = invoice.sudo()

        old_partner = invoice.partner_id
        re_open = True if invoice.state in ['open', 'paid'] else False

        res = invoice.action_invoice_cancel_draft_and_remove_outstanding()
        invoice.write({'partner_id': self.partner_id.id})
        invoice.partner_data_force()
        if re_open:
            invoice.action_invoice_open()
            invoice.action_re_assign_outstanding(res, raise_exception=False, forced_partner=self.partner_id.id)

        invoice.message_post(_("User \"{}\" ({}) has changed the invoice partner using the change partner wizard from "
                               "\"{}\" to \"{}\"").format(self.env.user.name, self.env.user.id, old_partner.name,
                                                          self.partner_id.name))
        return {'type': 'ir.actions.act_close_wizard_and_reload_view'}
