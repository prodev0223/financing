# -*- coding: utf-8 -*-
from odoo import fields, models, api, _, tools, exceptions


class PeriodicInvoice(models.Model):
    _inherit = 'periodic.invoice'

    picking_action = fields.Selection([('no', 'Jokio veiksmo'),
                                       ('create', 'Sukurti'),
                                       ('confirm', 'Sukurti ir patvirtinti')], string='Automatinis važtaraščio veiksmas',
                                      required=True, default='no')
    warehouse_id = fields.Many2one('stock.warehouse', string='Automatinė važtaraščio atsargų lokacija')

    @api.multi
    @api.constrains('picking_action', 'warehouse_id')
    def _check_warehouse_id_set(self):
        for rec in self:
            if rec.picking_action in ('create', 'confirm') and not rec.warehouse_id:
                raise exceptions.ValidationError(
                    _('Jums reikia nustatyti lokaciją, kad sukurti važtaraštį')
                )
            if rec.picking_action == 'no' and rec.warehouse_id:
                raise exceptions.ValidationError(
                    _('Atsargų lokacija naudojama tik tuomet, kai yra automatinis važtaraščio veiksmas')
                )

    @api.constrains('picking_action', 'action')
    def _check_action_picking_action(self):
        if any(rec.action == 'no' and rec.picking_action != 'no' for rec in self):
            raise exceptions.ValidationError(
                _('Važtaraštis gali būti sukuriamas automatiškai tik tuo atveju, kai yra patvirtinama sąskaita.'))

    @api.multi
    def _extra_actions(self, invoice):
        """
        Extra actions to be performed after creating the invoice in the cron job
        :param invoice: account.invoice record -- the newly created invoice
        :return: None
        """
        self.ensure_one()
        super(PeriodicInvoice, self)._extra_actions(invoice)
        if invoice.state not in ('open', 'paid'):
            return
        if self.picking_action in ['create', 'confirm']:
            location = self.warehouse_id.lot_stock_id
            wiz = self.env['invoice.delivery.wizard'].sudo().with_context({'invoice_id': invoice.id}).create({
                'location_id': location.id,
            })
            wiz.create_delivery()
            if self.picking_action == 'confirm':
                wiz.confirm_delivery()


PeriodicInvoice()
