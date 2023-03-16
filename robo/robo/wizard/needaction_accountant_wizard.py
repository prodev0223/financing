# -*- coding: utf-8 -*-


from datetime import datetime

from odoo import _, api, fields, models, tools


class NeedactionAccountantWizard(models.TransientModel):
    _name = 'needaction.accountant.wizard'

    comment = fields.Text(string='Komentaras', required=True)

    @api.multi
    def post(self):
        self.ensure_one()
        invoice = self.env['account.invoice'].browse(self._context.get('invoice_id'))
        body = """Ar šios sąnaudos yra laikomos įmonės reprezentacinėmis sąnaudomis?
        <br/> Buhalterio komentaras: %s <br/> Data: %s</p>""" % \
               (self.comment, datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
        msg = {
            'body': _(body),
        }
        invoice.message_post(**msg)
        invoice.need_action_text_accountant = self.comment
        invoice.expense_state = 'awaiting'
        if self._context.get('accountant'):
            invoice.action_shift = 'ceo'
            invoice.accountant_state = 'agree' if self._context.get('agree') else 'disagree'
