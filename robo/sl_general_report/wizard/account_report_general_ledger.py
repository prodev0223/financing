# -*- coding: utf-8 -*-
import xlsxwriter
import cStringIO as StringIO
from odoo import _, api, exceptions, fields, models


class AccReportGeneralLedgerSL(models.TransientModel):

    _inherit = "account.report.general.ledger"

    filtered_account_ids = fields.Many2many('account.account', string='Filtruoti DK sąskaitas')
    display_account = fields.Selection(
        [('all', 'Visas'), ('movement', 'Su įrašais'), ('filter', 'Filtruoti')],
        # ('not_zero', 'With balance is not equal to 0'),
        string='Rodyti sąskaitas', required=True, default='movement')
    filtered_partner_ids = fields.Many2many('res.partner', string='Filtruoti partnerius')
    display_partner = fields.Selection(
        [('all', 'Visus'), ('filter', 'Filtruoti partnerius')],
        string='Rodyti partnerius', required=True, default='all')

    # Date of the very first entry is used most commonly in this report,
    # thus default behaviour is leaving this field empty
    date_from = fields.Date()
    date_to = fields.Date(default=fields.Date.today)
    detail_level = fields.Selection([('detail', 'Detalu'), ('sum', 'Tik sumos')], string='Detalumas',
                                    default='detail', required=True)

    @api.multi
    def name_get(self):
        return [(rec.id, _('Didžioji knyga')) for rec in self]

    @api.multi
    def check_report(self):
        res = super(AccReportGeneralLedgerSL, self).check_report()
        res['data']['form']['filtered_account_ids'] = self.read(['filtered_account_ids'])[0]
        res['data']['form']['display_partner'] = self.read(['display_partner'])[0]['display_partner']
        res['data']['form']['filtered_partner_ids'] = self.filtered_partner_ids.ids
        res['data']['form']['detail_level'] = self.detail_level
        if 'report_type' in res:
            if self._context.get('force_pdf'):
                res['report_type'] = 'qweb-pdf'
            if self._context.get('force_html'):
                res['report_type'] = 'qweb-html'
        return res

    def action_open_account_move_line_report(self):
        self.ensure_one()
        action = self.env.ref('sl_general_report.action_account_move_line_report_all').read()[0]

        domain = [('journal_id', 'in', self.with_context(active_test=False).journal_ids.ids)]
        if self.display_partner == 'filter':
            domain.append(('partner_id', 'in', self.filtered_partner_ids.ids))
        if self.filtered_account_ids:
            domain.append(('account_id', 'in', self.filtered_account_ids.ids))
        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        if self.date_to:
            domain.append(('date', '<=', self.date_to))

        context = {
            'search_default_posted': True
        }
        # If no dates are set in the wizard, add defaults
        if not self.date_from and not self.date_to:
            context.update({
                'search_default_current_month': 1,
            })

        action.update({
            'domain': domain,
            'context': context,
        })

        return action

    def _print_report(self, data):
        data = self.pre_print_report(data)
        data['form'].update(self.read(['initial_balance', 'sortby'])[0])
        if data['form'].get('initial_balance') and not data['form'].get('date_from'):
            raise exceptions.UserError(_("You must define a Start Date"))
        return self.env['report'].with_context(landscape=True).get_action(self, 'sl_general_report.report_generalledger_sl', data=data)

    @api.multi
    def xls_export(self):
        if self.date_to or self.date_from:
            date_header = ' / {} - {}'.format(self.date_from or '', self.date_to or '')
            self = self.with_context(date_header=date_header)
        return self.check_report()

    @api.multi
    def btn_download_xlsx(self):
        """ Use Fast SQL query to write into XLSX file """
        base64_file = self.generate_xlsx()
        filename = 'DK_%s_%s_%s.xlsx' % (self.env.user.company_id.name, self.date_from, self.date_to)
        attach_id = self.env['ir.attachment'].create({
            'res_model': 'account.report.general.ledger',
            'res_id': self.id,
            'type': 'binary',
            'name': filename,
            'datas_fname': filename,
            'datas': base64_file
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download?res_model=account.report.general.ledger&res_id=%s&attach_id=%s' % (self.id, attach_id.id),
            'target': 'self',
        }

    @api.multi
    def generate_xlsx(self):
        """ Use Fast SQL query to write into XLSX file """
        if not self.env.user.is_accountant():
            raise exceptions.AccessError(_('Tik buhalteriai gali atlikti šį veiksmą.'))
        if not self.date_from:
            raise exceptions.UserError(_('Nenurodyta data nuo'))
        if not self.date_to:
            raise exceptions.UserError(_('Nenurodyta data iki'))
        headers_sorted = [
            'date',
            'name',
            'ref',
            'debit',
            'credit',
            'partner_name',
            'partner_code',
            'account_code',
            'account_name',
            'user',
            'journal',
            'currency',
            'amount_currency'
        ]

        f = StringIO.StringIO()

        wb = xlsxwriter.Workbook(f)
        ws = wb.add_worksheet('DK')
        ws.freeze_panes(1, 0)
        header_style = wb.add_format({'bold': True,
                                      'align': 'center',
                                      'valign': 'center',
                                      'border': 1})
        query =  '''
    SELECT
        account_move_line.date,
        account_move_line.name,
        account_move_line.ref,
        account_move_line.debit,
        account_move_line.credit,
        rp.name as partner_name,
        rp.kodas as partner_code,
        account_account.code as account_code,
        account_account.name as account_name,
        res_partner.name as user,
        account_journal.name as journal,
        res_currency.name as currency,
        account_move_line.amount_currency                      
    FROM
        account_move_line                      
    INNER JOIN
        account_account 
            ON account_account.id = account_move_line.account_id                     
    INNER JOIN
        res_users 
            ON res_users.id = account_move_line.create_uid                     
    INNER JOIN
        res_partner 
            ON res_partner.id = res_users.partner_id                     
    LEFT JOIN
        res_partner rp 
            ON rp.id = account_move_line.partner_id                     
    INNER JOIN
        account_journal 
            ON account_journal.id = account_move_line.journal_id                     
    INNER JOIN
        account_move 
            ON account_move.id = account_move_line.move_id                     
    LEFT JOIN
        res_currency 
            ON res_currency.id = account_move_line.currency_id                     
    WHERE
        account_move_line.date >= %s 
        AND account_move_line.date <= %s 
        AND                     account_move.state = 'posted'
                '''
        params = [self.date_from, self.date_to]
        if self.display_partner == 'filter':
            query += ''' AND account_move_line.partner_id IN %s'''
            params.append(tuple(self.filtered_partner_ids.ids))
        if self.filtered_account_ids:
            query += ''' AND account_move_line.account_id IN %s'''
            params.append(tuple(self.filtered_account_ids.ids))

        self.env.cr.execute(query, params)

        for r, row in enumerate(self.env.cr.fetchall()):
            if r == 0:
                for c, h in enumerate(headers_sorted):
                    ws.write(r, c, h, header_style)
            for c, data in enumerate(row):
                ws.write(r + 1, c, data)
        wb.close()
        base64_file = f.getvalue().encode('base64')
        return base64_file


AccReportGeneralLedgerSL()
