# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions, tools, SUPERUSER_ID
from odoo.api import Environment
import threading
import odoo
from datetime import datetime
from validate_email import validate_email

static_invoice_prefix = 'SF-'


class EtaksiInvoiceMassMailing(models.TransientModel):
    """
    Transient model used to mass mail account.invoice records to related partners
    """
    _name = 'etaksi.invoice.mass.mailing'

    invoice_ids = fields.Many2many('account.invoice', string='Siunčiamos sąskaitos')

    @api.multi
    def name_get(self):
        return [(rec.id, _('Sąskaitų siuntimo darbai')) for rec in self]

    @api.multi
    def mass_mail_invoices(self):
        """
        Prepare for mass invoice mailing, check for active jobs
        and start the thread
        :return: None
        """
        self.ensure_one()
        if not self.invoice_ids:
            raise exceptions.ValidationError(_('Nepateikta nė viena sąskaita!'))

        active_jobs = self.env['etaksi.invoice.mass.mailing.job'].search([('state', '=', 'in_progress')])
        if active_jobs:
            raise exceptions.ValidationError(_('Negalite atlikti šio veiksmo, sąskaitos yra siunčiamos šiuo metu!'))

        vals = {
            'execution_start_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            'state': 'in_progress'
        }
        job_id = self.env['etaksi.invoice.mass.mailing.job'].create(vals)
        self.env.cr.commit()
        threaded_calculation = threading.Thread(target=self.mass_mail_invoices_thread,
                                                args=(self.invoice_ids.ids, job_id.id,))
        threaded_calculation.start()

    @api.multi
    def mass_mail_invoices_thread(self, invoice_ids, job_id):
        """
        Mass mail invoices // THREADED
        :param invoice_ids: account_invoice IDS
        :param job_id: etaksi.invoice.mass.mailing.job ID
        :return: None
        """
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, odoo.SUPERUSER_ID, {'lang': 'lt_LT'})
            job_id = env['etaksi.invoice.mass.mailing.job'].browse(job_id)
            invoice_ids = env['account.invoice'].browse(invoice_ids)
            try:
                for invoice_id in invoice_ids:
                    if not invoice_id.partner_id.email or any(not validate_email(
                            x.strip()) for x in invoice_id.partner_id.email.split(';')):
                        body = _('Nepavyko išsiųsti sąskaitos %s, '
                                 'partneris %s neturi teisingai sukonfigūruoto el.pašto' %
                                 (invoice_id.move_name, invoice_id.partner_id.display_name))
                        job_id.write({'state': 'failed',
                                      'fail_message': body,
                                      'execution_end_date': datetime.utcnow().strftime(
                                          tools.DEFAULT_SERVER_DATETIME_FORMAT)})
                        new_cr.commit()
                        new_cr.close()
                        return
                    action = invoice_id.action_invoice_sent()
                    ctx = action['context']
                    user_id = invoice_id.user_id if \
                        invoice_id.user_id.id != SUPERUSER_ID else env.user.company_id.vadovas.user_id
                    mail = env['mail.compose.message'].sudo(user=user_id).with_context(ctx).create({})
                    mail.onchange_template_id_wrapper()
                    attachment_ids = invoice_id.attachment_ids.filtered(
                        lambda x: x.datas_fname and x.datas_fname.startswith(static_invoice_prefix))
                    if attachment_ids:
                        mail.attachment_ids |= attachment_ids
                    mail.send_mail_action()
            except Exception as exc:
                new_cr.rollback()
                job_id.write({'state': 'failed',
                              'fail_message': str(exc.args[0]),
                              'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
            else:
                job_id.write({'state': 'finished',
                              'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
            new_cr.commit()
            new_cr.close()


EtaksiInvoiceMassMailing()
