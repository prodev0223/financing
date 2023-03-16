# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_del_darbo_uzmokescio_pervedimo_i_banko_saskaita_workflow(self):
        self.ensure_one()
        partner_id = self.employee_id1.address_home_id
        bank_account_id = self.env['res.partner.bank'].create({
            'acc_number': self.acc_number,
            'partner_id': partner_id.id or False,
        })
        bank_account_id.onchange_acc_number()
        self.employee_id1.write({'bank_account_id': bank_account_id.id})


EDocument()
