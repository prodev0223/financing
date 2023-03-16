# -*- coding: utf-8 -*-
from odoo import models, api, _


class BankStatementFetchJob(models.Model):
    _inherit = 'bank.statement.fetch.job'

    @api.multi
    def post_message(self):
        """
        Send a message to the user after bank statement fetch JOB is finished
        :return: None
        """
        super(BankStatementFetchJob, self).post_message()
        # Be sure not to spam user with the same message several times
        for rec in self.filtered(lambda x: x.state != 'in_progress' and not x.message_posted):
            # Prepare subject and body of the message based on the state
            base_body = _('Banko sąskaita - {}. Periodas - {} / {}').format(
                rec.journal_id.name, rec.statement_start_date, rec.statement_end_date)
            if rec.state == 'succeeded':
                subject = _('Sėkmingai gautas banko išrašas.')
            else:
                subject = _('Nepavyko sinchronizuoti banko išrašo.')
                base_body = _('Klaidos pranešimas - {}. ').format(rec.error_message) + base_body

            msg = {
                'body': base_body,
                'subject': subject,
                'priority': 'medium',
                'front_message': True,
                'rec_model': 'bank.statement.fetch.job',
                'rec_id': rec.id,
                'partner_ids': rec.user_id.partner_id.ids,
                'view_id': self.env.ref('sepa.form_bank_statement_fetch_job').id,
            }
            rec.robo_message_post(**msg)
            rec.message_posted = True
