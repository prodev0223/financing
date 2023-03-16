# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions
from odoo.tools.translate import _


class ResPartnerBank(models.Model):

    _name = 'res.partner.bank'
    _inherit = ['res.partner.bank', 'mail.thread']

    def _track_subtype(self, init_values):
        res = super(ResPartnerBank, self)._track_subtype(init_values)
        if 'partner_id' in init_values:
            prev_partner = init_values['partner_id']
            if prev_partner:
                if 'acc_number' in init_values:
                    prev_acc_number = init_values['acc_number']
                else:
                    prev_acc_number = self.acc_number
                message = _('Banko sąskaita %s buvo perduota kitam partneriui') % prev_acc_number
                prev_partner.message_post(body=message)
        elif 'acc_number' in init_values:
            partner = self.partner_id
            prev_acc_number = init_values['acc_number']
            new_acc_number = self.acc_number
            message = _('Banko sąskaita %s buvo pakeista į %s') % (prev_acc_number, new_acc_number)
            partner.message_post(message)
        return res

    @api.multi
    def unlink(self):
        for rec in self:
            message = _('Banko sąskaita %s buvo ištrinta') % rec.acc_number
            rec.partner_id.message_post(message)
        return super(ResPartnerBank, self).unlink()

    @api.onchange('acc_number')
    def onchange_acc(self):
        if self.acc_number:
            self.acc_number = self.acc_number.replace(' ', '').upper()

    acc_number = fields.Char(track_visibility='onchange')
    partner_id = fields.Many2one('res.partner', track_visibility='onchange')
