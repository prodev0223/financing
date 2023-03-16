# -*- coding: utf-8 -*-
from odoo import models, api


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    @api.multi
    def preprocess_payment_post(self):
        """Prepare the records for mass payment confirmation"""
        draft_payments = self.filtered(lambda x: x.state == 'draft').sorted(key='payment_date')
        for payment in draft_payments:
            payment.post()

    @api.model
    def create_action_account_payment_confirm_multi(self):
        """Creates action for multiset account payment confirmation"""
        action = self.env.ref('nsoft.action_account_payment_confirm_multi')
        if action:
            action.create_action()
