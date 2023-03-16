# -*- encoding: utf-8 -*-
import pytz
import werkzeug
import logging
import base64
import json
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import fields, models, _, api, exceptions, tools

_logger = logging.getLogger(__name__)


class RevolutApiImport(models.TransientModel):
    _name = 'revolut.api.import'
    _description = 'Wizard to import revolut data from Business API'

    def _default_date_to(self):
        # Revolut date_to is not inclusive
        offset = int(datetime.now(pytz.timezone(self._context.get('tz', 'Europe/Vilnius'))).strftime('%z')[:3])
        return (datetime.now() - relativedelta(hour=0, minute=0, second=0) - relativedelta(hours=offset)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

    def _default_date_from(self):
        offset = int(datetime.now(pytz.timezone(self._context.get('tz', 'Europe/Vilnius'))).strftime('%z')[:3])
        return (datetime.now() + relativedelta(day=1, hour=0, minute=0, second=0) - relativedelta(hours=offset)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

    journal_id = fields.Many2one('account.journal', string='Žurnalas')
    date_from = fields.Datetime(string='Data nuo', default=_default_date_from)
    date_to = fields.Datetime(string='Data iki', default=_default_date_to)
    apply_import_rules = fields.Boolean(string='Taikyti importavimo taisykles', default=True)

    @api.multi
    def btn_fetch_transactions(self):
        self.ensure_one()
        if not self.journal_id:
            raise exceptions.UserError(_('Nenustatyta žurnalas'))
        if not self.journal_id.revolut_api_id:
            raise exceptions.UserError(_('Nenustatyta API'))
        revolut_api = self.journal_id.revolut_api_id
        transactions = revolut_api.with_context(importing_to_journal=self.journal_id).get_transactions(date_from=self.date_from, date_to=self.date_to, count=-1)
        return self._process_transactions(transactions)

    @api.multi
    def btn_fetch_and_save_transactions(self):
        self.ensure_one()
        if not self.journal_id:
            raise exceptions.UserError(_('Nenustatyta žurnalas'))
        if not self.journal_id.revolut_api_id:
            raise exceptions.UserError(_('Nenustatyta API'))
        revolut_api = self.journal_id.revolut_api_id
        transactions = revolut_api._fetch_transactions(date_from=self.date_from, date_to=self.date_to, count=-1)
        base64_file = base64.b64encode(json.dumps(transactions, indent=4, sort_keys=True))

        attach_id = self.env['ir.attachment'].create({
            'res_model': 'revolut.api',
            'res_id': revolut_api.id,
            'type': 'binary',
            'name': 'revolut.json',
            'datas_fname': 'revolut.json',
            'datas': base64_file
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download?res_model=revolut.api&res_id=%s&attach_id=%s' % (revolut_api.id, attach_id.id),
            'target': 'self',
        }

    @api.multi
    def _process_transactions(self, transactions):
        statements = transactions.mapped('leg_ids').create_statements(filtered_journal=self.journal_id,
                                                                      apply_import_rules=self.apply_import_rules)
        if statements:
            action = self.env.ref('account.action_bank_statement_tree')
            return {
                'name': action.name,
                'view_type': 'form',
                'view_mode': 'tree,form',
                'res_model': action.res_model,
                'domain': [('id', 'in', statements.ids)],
                'context': action.context,
                'type': 'ir.actions.act_window',
            }
        else:
            return {'type': 'ir.actions.do_nothing'}



RevolutApiImport()
