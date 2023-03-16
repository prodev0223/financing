# -*- coding: utf-8 -*-
import logging

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)


class AccountInvoiceTaxChangeWizard(models.TransientModel):
    _name = 'account.invoice.tax.change.wizard'

    @api.multi
    def tax_line_ids_domain(self):
        domain = []
        if self._context.get('inv_type', False) == 'out':
            domain.append(('type_tax_use', '=', 'sale'))
        else:
            domain.append(('type_tax_use', '=', 'purchase'))

        if self._context.get('price_include_selection', str()) == 'inc':
            domain.append(('price_include', '=', True))
        else:
            domain.append(('price_include', '=', False))
        return domain

    invoice_id = fields.Many2one('account.invoice', string='Sąskaita faktūra')
    tax_ids = fields.Many2many('account.tax', string='Mokesčiai', domain=tax_line_ids_domain)
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
    def change_invoice_tax_ids(self):
        """
        Method used to change tax_ids to all of the invoice lines.
        if invoice is in open or paid state, remove outstanding payments, cancel, write values, re-confirm
        and re-assign specific outstanding payments
        :return: None
        """
        self.ensure_one()
        invoice = self.invoice_id
        re_open = True if invoice.state in ['open', 'paid'] else False

        if re_open and (not invoice.price_include_selection or invoice.price_include_selection in ['exc']):
            raise exceptions.UserError(_('Negalite keisti mokesčių patvirtintai sąskaitai, jeigu mokesčiai nėra '
                                         'traukiami į galutinę kainą. Atšaukite sąskaitą ir kartotike veiksmą'))

        res = invoice.action_invoice_cancel_draft_and_remove_outstanding()
        for line in invoice.invoice_line_ids:
            line.write({'invoice_line_tax_ids': [(6, 0, self.tax_ids.ids)]})

        if re_open:
            invoice.action_invoice_open()
            invoice.action_re_assign_outstanding(res, raise_exception=False)

        return {'type': 'ir.actions.act_close_wizard_and_reload_view'}

