# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, fields, api, tools, SUPERUSER_ID, _
from odoo.addons.sepa import api_bank_integrations as abi
from datetime import datetime
import logging


_logger = logging.getLogger(__name__)


class BankExportJob(models.Model):
    _inherit = 'bank.export.job'

    front_statement_line_id = fields.Many2one(
        'front.bank.statement.line', string='Mokėjimo ruošinio eilutė', ondelete='cascade')

    @api.multi
    def _set_export_state(self):
        """
        Inverse //
        Set various data based on bank.export.job state changes
        :return: None
        """
        # Check whether inverse should be skipped
        if self._context.get('skip_set_export_state'):
            return

        # Call super of the inverse
        super(BankExportJob, self)._set_export_state()
        for rec in self:
            # If SEPA group export line is rejected, reject all of the export lines and post the message.
            if rec.group_payment_export and rec.export_state in abi.REJECTED_STATES \
                    and rec.sepa_instruction_id and rec.front_statement_line_id:
                # Force failed state to all of the front statement lines
                line = rec.front_statement_line_id
                statement = line.statement_id

                # Get all waiting exports of the statement, and force the failed state
                total_exports = statement.line_ids.mapped('bank_export_job_ids').filtered(
                    lambda x: x.export_state == 'waiting' and rec.group_payment_export)
                total_exports.with_context(skip_set_export_state=True).write({'export_state': 'rejected'})

                # Post warning message to the parent statement
                error_message = _('Bent viena grupinio mokėjimo eilutė buvo atmesta, dėl to visas grupinis mokėjimas '
                                  'nebuvo priimtas. Suklydusi eilutė: {} || {}. \n Klaidos pranešimą galite pamatyti '
                                  'atsidarę konkrečios eilutės eksporto objektą.').format(
                    line.name, line.partner_id.name)
                statement.message_post(body=error_message)

    @api.model
    def create(self, vals):
        res = super(BankExportJob, self).create(vals)
        invoices = res.sudo().invoice_ids.filtered(lambda i: i.banking_export_status and i.banking_export_status.startswith('asked'))
        if invoices:
            invoices.write({'banking_export_status': 'informed'})
        return res

    @api.multi
    def inform_ceo(self):
        """
        Inform CEO of the company about received response
        of exported bank statement if it was successful
        :return: None
        """
        company = self.sudo().env.user.company_id

        # Prepare table header template
        table_header_template = '''
        <table width="100%" style="border:1px solid black; border-collapse: collapse; text-align: left;">
            <td style="border:1px solid black;"><b>{}</b></td>
            <td style="border:1px solid black;"><b>{}</b></td>
            <td style="border:1px solid black;"><b>{}</b></td>
            <td style="border:1px solid black;"><b>{}</b></td>
            <td style="border:1px solid black;"><b>{}</b></td>
        </td></tr>'''.format(_('Pavadinimas'), _('Partneris'), _('Suma'), _('Valiuta'), _('Tipas'))

        # Map out the specific lines, since informing method differs
        accepted_exports = self.filtered(
            lambda x: x.export_state in abi.ACCEPTED_STATES and not x.ceo_informed)

        if accepted_exports:
            main_table = table_header_template
            journals = accepted_exports.mapped('journal_id')

            # Group accepted exports by journal
            for journal in journals:
                by_journal = accepted_exports.filtered(lambda x: x.journal_id.id == journal.id)
                # Loop through the exports and form the table, mark the export as ceo informed
                for export in by_journal:
                    export.ceo_informed = True
                    exp_type = str(dict(
                        export._fields['export_data_type']._description_selection(
                            self.env)).get(export.export_data_type))
                    main_table += '''
                     <tr style="border:1px solid black;">
                     <td style="border:1px solid black;">{}</td>
                     <td style="border:1px solid black;">{}</td>
                     <td style="border:1px solid black;">{}</td>
                     <td style="border:1px solid black;">{}</td>
                     <td style="border:1px solid black;">{}</td>'''.format(
                        export.tr_name,
                        export.tr_partner_id.display_name,
                        export.tr_amount,
                        export.tr_currency_id.name or company.currency_id.name,
                        exp_type
                    )

                # After table is built, post the message
                main_table += '''</table>\n\n\n'''
                subject = _('Sėkmingai eksportuoti mokėjimai.')
                report = _('Apačioje pateikti mokėjimai buvo sėkingai '
                           'eksportuoti į banką. Sąskaita - %s:\n') % journal.display_name + main_table
                self.post_message(body=report, subject=subject)

    @api.multi
    def post_message(self, body, subject):
        """
        Post message to the res.company.message record
        :param body: body of the message
        :param subject: subject of the message
        :return: None
        """
        company = self.sudo().env.user.company_id
        comp_message = self.env['res.company.message'].create({
            'body': body,
            'subject': subject,
            'company_id': company.id
        })
        msg = {
            'body': body,
            'subject': subject,
            'priority': 'medium',
            'front_message': True,
            'rec_model': 'res.company.message',
            'rec_id': comp_message.id,
            'partner_ids': company.vadovas.address_home_id.ids or company.vadovas.user_id.partner_id.ids,
            'view_id': self.env.ref('robo.res_company_message_form').id,
        }
        comp_message.robo_message_post(**msg)

    @api.multi
    def post_message_to_related(self, message=str()):
        """
        Write passed object state to related object - account.invoice or front.bank.statement.line
        :return: None
        """
        super(BankExportJob, self).post_message_to_related(message)
        # TODO: Do not post the message to the statement for now
        # self.mapped('front_statement_line_id.statement_id').message_post(body=message)

    @api.model
    def cron_check_pending_bank_exports(self):
        """
        Check recently exported account.invoice and front.bank.statement.line objects. If objects are still
        in 'imported' state after 1h from the initial export,
        send message to findir and update objects' state to failed
        :return: None
        """

        def export_overdue(current_date, export_date):
            """Checks if current export date is overdue"""
            export_date_dt = datetime.strptime(export_date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            date_difference = current_date - export_date_dt
            # P3:DivOK
            hour_difference = (date_difference.total_seconds() / 3600.0)
            return tools.float_compare(hour_difference, re_interval, precision_digits=2) >= 0

        param_obj = self.sudo().env['ir.config_parameter']

        # Get the needed config parameters, use defaults if int conversion fails
        try:
            re_interval = int(param_obj.get_param('pending_bank_export_resend_interval', default=10))
            re_count = int(param_obj.get_param('pending_bank_export_resend_count', default=2))
        except (ValueError, TypeError):
            re_interval, re_count = 10, 2

        now_date = datetime.utcnow()
        pending_exports = self.search([('export_state', '=', 'waiting'), ('xml_file_download', '=', False)])

        # Group the exports by batch and journal
        grouped_exports = {}
        for export in pending_exports:
            batch = export.export_batch_id
            journal = export.journal_id
            # Build data dict
            grouped_exports.setdefault(journal, {})
            grouped_exports[journal].setdefault(batch, self)
            grouped_exports[journal][batch] |= export

        grouped_responses = {}

        # Loop through exports and check them
        for journal, by_journal in grouped_exports.items():
            overdue_exports = self.env['bank.export.job']
            for batch, exports in by_journal.items():
                # If batch exists, and at least one export from the batch is waiting - all of the batch
                # exports are waiting, since they were sent using the same file.
                if batch and export_overdue(now_date, batch.date_exported):
                    # Increase failed resend count, if it's below the threshold - resend the data
                    batch.write({'no_response_upload_count': batch.no_response_upload_count + 1})
                    if batch.no_response_upload_count < re_count:
                        # TODO: Do not re-export for now, log the data and gather the potential errors
                        # batch.re_export_data()
                        export_data = ['{} -- {}\n'.format(x.create_date, x.export_state) for x in exports]
                        # Update date exported
                        batch.write({
                            'date_exported': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                        })
                        _logger.info(
                            'Bank Batch Re-export info: Batch ID - {} | {}'.format(batch.id, str(export_data))
                        )
                        continue
                    overdue_exports = exports
                elif not batch:
                    overdue_exports |= exports.filtered(lambda x: export_overdue(now_date, x.date_exported))

            for export in overdue_exports:
                partner = export.partner_id
                d_type = export.export_data_type

                # If current export's data type is in inform types, compose a message
                if d_type in abi.INFORM_EXPORT_DATA_TYPES:
                    # Group export responses by sender and by the type
                    grouped_responses.setdefault(partner, {})
                    grouped_responses[partner].setdefault(journal, {})
                    for line in abi.INFORM_EXPORT_DATA_TYPES:
                        grouped_responses[partner][journal].setdefault(line, str())
                    # Front statement name is appended to the line message
                    if d_type == 'front_statement':
                        statement = export.front_statement_line_id.statement_id
                        grouped_responses[partner][journal][d_type] += _('{}. Ruošinys - {}\n').format(
                            export.tr_name, statement.name)
                    else:
                        # Otherwise just add the export name
                        grouped_responses[partner][journal][d_type] += '{}\n'.format(export.tr_name)
                # Force failed state
                export.export_state = 'rejected'

        # Prepare the fields for email sending
        response_to_type_mapping = {
            'invoices': _('Negautas atsakymas šioms sąskaitoms:\n{}\n'),
            'e_invoice': _('Negautas atsakymas šioms eSąskaitoms:\n{}\n'),
            'move_lines': _('Negautas atsakymas šiems žurnalo įrašams:\n{}\n'),
            'front_statement': _('Negautas atsakymas šioms mokėjimo ruošinio eilutėms:\n{}\n\n'),
        }
        database = self._cr.dbname
        subject = '{} // [{}]'.format('Bank export', database)
        findir_email = self.sudo().env.user.company_id.findir.partner_id.email

        # Loop through grouped response data, and format a report that must be sent
        for partner, by_partner in grouped_responses.items():
            partner_report = str()
            for journal, inform_types in by_partner.items():
                partner_report = _('Žurnalas - [{}]\n\n').format(journal.display_name)
                for inform_type, rejected_objects in inform_types.items():
                    if rejected_objects:
                        partner_report += response_to_type_mapping[inform_type].format(rejected_objects)

            if partner_report:
                # Determine email address and send the message
                mail_to_send = partner.email or findir_email
                # If partner is superusers partner, use findir email
                if partner.user_ids and SUPERUSER_ID in partner.user_ids.ids:
                    mail_to_send = findir_email
                    partner_report += '. {}'.format(_('Automatiškai pateikė sistema.'))

                self.env['script'].send_email(
                    emails_to=[mail_to_send], subject=subject, body=partner_report,
                )
