# -*- encoding: utf-8 -*-
from odoo import fields, models, _, api, exceptions


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    activate_e_invoices = fields.Boolean(compute='_compute_activate_e_invoices')

    @api.multi
    def _compute_activate_e_invoices(self):
        """
        Compute //
        Check whether eInvoicing is activated
        :return: None
        """
        activate = self.sudo().env.user.company_id.activate_e_invoices
        for rec in self:
            rec.activate_e_invoices = activate

    @api.multi
    def action_e_invoice_export_wizard(self):
        multi = True if self._context.get('multi') else False
        ctx = self._context.copy()
        invoices = self.filtered(lambda x: x.state in ['open'] and x.currency_id.name == 'EUR')
        if not invoices:
            if multi:
                raise exceptions.Warning(_('Pasirinktų sąskaitų sąraše nerasta sąskaitų kurios laukia mokėjimo, '
                                           'arba dalies sąskaitų valiuta nėra EUR.'))
            else:
                raise exceptions.Warning(_('Ši sąskaita yra apmokėta arba sąskaitos valiuta nėra EUR.'))
        ctx.update({'invoice_ids': invoices.ids, 'custom_name_get': True})
        wizard_id = self.env['swed.bank.api.import.invoice'].with_context(ctx).create({})
        action = {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'swed.bank.api.import.invoice',
            'type': 'ir.actions.act_window',
            'target': 'new',
            'res_id': wizard_id.id,
            'context': ctx
        }
        if multi:
            action['name'] = _('Swedbank eSąskaitų importavimo vedlys')
            action['view_id'] = self.env.ref('sepa.e_invoice_import_wizard_form_multi').id
        else:
            action['name'] = _('Swedbank eSąskaitos importavimo vedlys')
            action['view_id'] = self.env.ref('sepa.e_invoice_import_wizard_form').id
        return action


AccountInvoice()
