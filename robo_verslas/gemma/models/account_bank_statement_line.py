# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools
from datetime import datetime
from . import gemma_tools as gt
import json


class AccountBankStatementLine(models.Model):
    _name = 'account.bank.statement.line'
    _inherit = ['account.bank.statement.line', 'mail.thread']

    polis_export_state = fields.Selection([('not_exported', 'Neeksportuota'),
                                           ('exported', 'Eksportuota'),
                                           ('failed', 'Nepavyko eksportuoti')],
                                          string='POLIS eksportavimo būsena', default='not_exported')
    potential_polis_error = fields.Boolean(
        compute='_compute_potential_polis_error', string='Potenciali klaida', store=True)

    @api.multi
    @api.depends('journal_entry_ids', 'account_id')
    def _compute_potential_polis_error(self):
        """
        if line is exported to POLIS and journal_entry_ids or account_id is changed
        mark the line as potential error
        :return: None
        """
        for rec in self:
            rec.potential_polis_error = True if rec.polis_export_state == 'exported' else False

    @api.model
    def cron_push_statement_lines_polis(self):
        """
        Export account.bank.statement.lines to external POLIS system
        using JSON data.
        Lines must meet following criteria:
            -Partner record must have external partner code in it,
            -Partner record must have 'kodas' field set,
            -It must be reconciled in ROBO
            -Date always must be greater or equal to threshold date or sync date
        :return: None
        """
        # Do not execute the operation if statement sync is False
        if not self.env.user.company_id.polis_bank_statement_sync:
            return

        lines_to_push = self.env['account.bank.statement.line'].search([
            ('partner_id.gemma_ext_id', '!=', False),
            ('partner_id.kodas', '!=', False),
            ('statement_id.sepa_imported', '=', True),
            ('date', '>=', gt.STATEMENT_LINE_THRESHOLD_DATE),
            '|',
            ('polis_export_state', '!=', 'exported'),
            ('polis_export_state', '=', False)
        ]).filtered(lambda x: x.reconciled)

        data_to_push = []
        for line in lines_to_push:
            line_date = line.date
            if not line_date:
                line_date = line.statement_id.date
            line_datetime = datetime.strptime(line_date, tools.DEFAULT_SERVER_DATE_FORMAT).strftime(
                tools.DEFAULT_SERVER_DATETIME_FORMAT)
            data_to_push.append({
                gt.BANK_STATEMENT_FIELD_MAPPING['date']: line_datetime,
                gt.BANK_STATEMENT_FIELD_MAPPING['amount_company_currency']: line.amount_company_currency,
                gt.BANK_STATEMENT_FIELD_MAPPING['partner_code']: line.partner_id.kodas,
                gt.BANK_STATEMENT_FIELD_MAPPING['name']: line.name,
                gt.BANK_STATEMENT_FIELD_MAPPING['line_id']: line.id,
            })
        if data_to_push:
            data_to_push_json = json.dumps(data_to_push, ensure_ascii=False).encode('utf8')
            client, code = self.env['gemma.data.import'].get_api()

            # Try to export data to POLIS
            error = str()
            try:
                result = client.service.RlSetBankoPavedimai(code, data_to_push_json)
                if not result:
                    error += 'Nenumatyta klaida'
                elif result and isinstance(result, (unicode, str)) and gt.STATIC_SUCCESS_RESPONSE_MESSAGE not in result:
                    error += result
            except Exception as exc:
                error = exc.args[0]

            # If error message is received, write failed state
            # and post message to the record otherwise mark state as exported
            if error:
                error = gt.FAIL_MESSAGE_TEMPLATE + error
                for line in lines_to_push:
                    line.message_post(body=error)
                lines_to_push.write({'polis_export_state': 'failed'})
            else:
                lines_to_push.write({'polis_export_state': 'exported'})


AccountBankStatementLine()
