# -*- coding: utf-8 -*-


from odoo import api, fields, models


class RoboUsage(models.Model):
    _name = 'robo.usage'

    invoice_id = fields.Many2one('account.invoice', string='Sąskaita')
    name = fields.Char(string='Operacija')
    quantity = fields.Float(string='Kiekis')
    quantity_free = fields.Float(string='Įskaičiuota į planą, vnt.', lt_string='Įskaičiuota į planą, vnt.',
                                 compute='_quantity_free')
    quantity_paid = fields.Float(string='Apmokestintas kiekis, vnt.', lt_string='Apmokestintas kiekis, vnt.')
    amount_paid = fields.Float(string='Papildomas mokestis')

    @api.one
    @api.depends('quantity', 'quantity_paid')
    def _quantity_free(self):
        self.quantity_free = self.quantity - self.quantity_paid
