# -*- coding: utf-8 -*-

from datetime import datetime

from odoo import api, exceptions, models, tools, _


class ReportOverpayTransferRequest(models.AbstractModel):
    _name = 'report.robo.report_overpay_transfer_request'

    @api.model
    def render_html(self, doc_ids, data=None):
        force_lang = data.get('force_lang') or 'lt_LT'
        if force_lang:
            self = self.with_context(lang=force_lang)
        report_obj = self.env['report']
        # Force language on report name
        report_obj.with_context(force_lang=force_lang)._get_report_from_name(
            'robo.report_overpay_transfer_request')
        docs = self.env['res.partner'].browse(data.get('partner_id'))

        account_journal = self.env['account.journal'].search([('id', '=', data.get('journal_id'))])
        if not account_journal:
            raise exceptions.ValidationError(_('Bank account was not found'))
        currency = account_journal.currency_id.name if account_journal.currency_id else 'EUR'
        bank_account_number = account_journal.bank_acc_number

        current_user = self.env.user
        job_name = current_user.employee_ids[0].job_id.name if current_user.employee_ids else ''
        name = current_user.display_name
        company_representative = job_name + ' ' + name
        is_representative_accountant = current_user.is_accountant() and not current_user.has_group('base.group_system')

        lines = self.env['overpay.transfer.request.wizard.lines'].browse(data.get('overpay_line_ids'))
        document_date = datetime.strptime(data.get('date'), tools.DEFAULT_SERVER_DATE_FORMAT) or datetime.utcnow()

        docargs = {
            'docs': docs,
            'date': document_date,
            'company': self.env.user.company_id.name,
            'representative': company_representative,
            'is_accountant': is_representative_accountant,
            'current_user_timestamp': self.env.user.get_current_timestamp(),
            'bank_account_number': bank_account_number,
            'currency': currency,
            'lines': lines,
            'total': "{:.2f}".format(data.get('total')),
            'force_lang': force_lang,
        }
        return report_obj.render('robo.report_overpay_transfer_request', docargs)
