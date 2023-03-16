# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_del_darbo_uzmokescio_mokejimo_workflow(self):
        self.ensure_one()
        partner_id = self.employee_id1.address_home_id
        bank_account_id = self.env['res.partner.bank'].create({
            'acc_number': self.text_3,
            'partner_id': partner_id.id or False,
        })
        bank_account_id.onchange_acc_number()
        self.employee_id1.write({'bank_account_id': bank_account_id.id})


EDocument()
