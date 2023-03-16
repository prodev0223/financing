# -*- coding: utf-8 -*-


from datetime import datetime

from odoo import _, api, fields, models, tools


class NeedactionCeoWizard(models.TransientModel):
    _name = 'needaction.ceo.wizard'

    comment = fields.Text(string='Komentaras')
    agree = fields.Boolean(compute='get_answer')

    @api.one
    def get_answer(self):
        self.agree = self._context.get('agree', False)

    @api.multi
    def post(self):
        self.ensure_one()
        invoice = self.env['account.invoice'].with_context(
            skip_accountant_validated_check=True).browse(self._context.get('invoice_id'))
        answer = 'Taip' if self._context.get('agree') else 'Ne'
        body = """Ar šios sąnaudos yra laikomos įmonės reprezentacinėmis sąnaudomis?
                <br/> Vadovo atsakymas: %s <br/> Vadovo komentaras: %s <br/> Data: %s</p>""" % \
               (answer, self.comment, datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
        msg = {
            'body': _(body),
        }
        invoice.message_post(**msg)
        invoice.need_action_text = self.comment
        invoice.expense_state = 'awaiting'
        invoice.action_shift = 'accountant'
        invoice.ceo_state = 'agree' if self.agree else 'disagree'
