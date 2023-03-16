# -*- coding: utf-8 -*-
from odoo import models, fields, tools, api, _, exceptions
from odoo.addons.sepa import api_bank_integrations as abi


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    sepa_instruction_id = fields.Char(readonly=True, copy=False, string='SEPA InstrID', sequence=100)
    exported_sepa = fields.Boolean(string='Eksportuotas SEPA', default=False, readonly=True, copy=False, sequence=100)
    exported_sepa_date = fields.Date(string='Eksporto į SEPA data', copy=False, sequence=100)

    # HTML alerts (one is used in form view, another one in tree view)
    bank_export_state_alert_html = fields.Html(
        compute='_compute_bank_export_state_alert_html',
        groups='robo_basic.group_robo_payment_export'
    )
    bank_export_state_html = fields.Text(
        compute='_compute_bank_export_state_html',
        groups='robo_basic.group_robo_payment_export'
    )
    # Bank export data fields
    bank_export_job_ids = fields.Many2many(
        'bank.export.job', string='Banko eksporto darbai', copy=False, sequence=100,
    )
    # Fields that are computed from base bank export jobs,
    # these are split since different views are used to display them
    e_invoice_job_ids = fields.Many2many('bank.export.job', compute='_compute_export_job_data')
    general_export_job_ids = fields.Many2many('bank.export.job', compute='_compute_export_job_data')

    has_export_job_ids = fields.Boolean(
        string='Turi susijusių eksportų',
        compute='_compute_export_job_data',
        groups='robo_basic.group_robo_payment_export'
    )
    has_e_invoice_export_job_ids = fields.Boolean(
        string='Has eInvoice export jobs',
        compute='_compute_export_job_data',
        groups='robo_basic.group_robo_payment_export'
    )
    last_bank_export_partner = fields.Many2one(
        'res.partner', compute='_compute_last_bank_export_partner',
    )
    bank_exports_to_sign = fields.Boolean(
        string='Turi eksportuotų transakcijų kurias galima pasirašyti',
        compute='_compute_export_job_data',
        groups='robo_basic.group_robo_premium_manager'
    )
    bank_export_residual = fields.Float(
        compute='_compute_bank_export_residual',
        groups='robo_basic.group_robo_payment_export'
    )
    bank_export_state = fields.Selection(
        abi.BANK_EXPORT_STATES, string='Paskutinė eksportavimo būsena', store=True,
        compute='_compute_bank_export_state', copy=False,
        sequence=100,
    )
    paid_using_online_payment_collection_system = fields.Boolean(
        string='Paid using an online payment collection system',
        help='Has been paid using an online payment collection system, such as Neopay',
        readonly=True,
        sequence=100,
        copy=False,
    )

    skip_global_reconciliation = fields.Boolean(
        help='Indicates whether automatic reconciliation cron should skip this record',
    )

    @api.multi
    @api.depends(
        'bank_export_job_ids',
        'bank_export_job_ids.available_for_signing',
        'bank_export_job_ids.export_data_type',
    )
    def _compute_export_job_data(self):
        """
        Computes separate fields for bank exports that are general ones
        (every export except e_invoice export),and ones that are related to e_invoices.
        Computed fields are used only for visual purposes.
        Separate boolean fields indicating the status and presence of the fields are computed as well.
        :return: None
        """
        BankExportJob = self.env['bank.export.job']
        for rec in self:
            # Split export jobs into general ones and eInvoice related ones
            general_jobs = e_invoice_jobs = BankExportJob
            for export_job in rec.bank_export_job_ids:
                if export_job.export_data_type == 'e_invoice':
                    e_invoice_jobs |= export_job
                else:
                    general_jobs |= export_job

            # Compute two different sets for general and eInvoice jobs
            rec.e_invoice_job_ids = [(4, job_id) for job_id in e_invoice_jobs.ids]
            rec.general_export_job_ids = [(4, job_id) for job_id in general_jobs.ids]

            # Compute other fields
            rec.has_export_job_ids = bool(general_jobs)
            rec.has_e_invoice_export_job_ids = bool(e_invoice_jobs)
            rec.bank_exports_to_sign = any(x.available_for_signing for x in rec.bank_export_job_ids)

    @api.multi
    @api.depends('bank_export_job_ids.partner_id')
    def _compute_last_bank_export_partner(self):
        """
        Get latest export partner from related jobs
        :return: None
        """
        for rec in self:
            if rec.sudo().bank_export_job_ids:
                # Get the partner from latest export
                latest_export = rec.sudo().bank_export_job_ids.sorted(key=lambda c: c.id, reverse=True)[0]
                rec.last_bank_export_partner = latest_export.sudo().partner_id

    @api.multi
    @api.depends('bank_export_job_ids.export_state')
    def _compute_bank_export_state(self):
        """
        Compute //
        Compute latest bank export state based on
        related bank_export_job_ids records
        :return: None
        """
        for rec in self:
            bank_export_state = 'no_action'
            live_exports = rec.bank_export_job_ids.filtered(lambda x: not x.xml_file_download)
            if live_exports:
                # Get the state from latest export
                latest_export = live_exports.sorted(key=lambda c: c.id, reverse=True)[0]
                bank_export_state = latest_export.export_state
            rec.bank_export_state = bank_export_state

    @api.multi
    @api.depends('bank_export_job_ids', 'residual')
    def _compute_bank_export_residual(self):
        """
        Compute //
        Compute latest bank export residual and based on
        related bank_export_job_ids records
        :return: None
        """
        for rec in self.filtered(lambda x: x.type in ['out_refund', 'in_invoice']):
            # ABS the residual since it always must be a positive number
            residual = abs(rec.residual)
            live_exports = rec.bank_export_job_ids.filtered(lambda x: not x.xml_file_download)
            if live_exports:
                # Get the residual from the latest successful export
                latest_successful_exports = live_exports.filtered(
                    lambda x: x.export_state in abi.ACCEPTED_STATES).sorted(key=lambda c: c.id, reverse=True)
                if latest_successful_exports and tools.float_compare(
                        residual, latest_successful_exports[0].post_export_residual, precision_digits=2) > 0:
                    residual = latest_successful_exports[0].post_export_residual
            rec.bank_export_residual = residual

    @api.multi
    @api.depends('bank_export_state', 'exported_sepa', 'exported_sepa_date')
    def _compute_bank_export_state_alert_html(self):
        """
        Compute //
        Compose html for exported bank state alert box
        :return: None
        """
        for rec in self:
            rec.bank_export_state_alert_html = self.env['api.bank.integrations'].get_bank_export_state_alert_html_data(
                state=rec.bank_export_state,
                model='account.invoice',
                extra_data={
                    'exported_sepa_date': rec.exported_sepa_date,
                    'exported_sepa': rec.exported_sepa,
                    'inv_type': rec.type,
                    'last_export_partner_name': rec.last_bank_export_partner.display_name,
                }
            )

    @api.multi
    @api.depends('bank_export_state', 'exported_sepa', 'paid_using_online_payment_collection_system')
    def _compute_bank_export_state_html(self):
        """
        Compute //
        Composes HTML element (button) of the bank export state
        for the specific account.invoice record (displayed in the tree view)
        :return: None
        """
        # Loop through records and compose HTML of the button
        # that is displayed in the tree view (title, color, image)
        for rec in self:
            rec.bank_export_state_html = self.env['api.bank.integrations'].get_bank_export_state_html_data(
                model='account.invoice',
                state=rec.bank_export_state,
                extra_data={
                    'exported_sepa': rec.exported_sepa,
                    'expense_state': rec.expense_state,
                    'inv_type': rec.type,
                    'paid_using_online_payment_collection_system': rec.sudo().paid_using_online_payment_collection_system
                }
            )

    @api.multi
    def auto_reconcile_with_accounting_entries(self):
        """
        Automatically reconcile open account invoices
        with account move lines based on exclusion criteria
        and best matching amounts.
        :return: None
        """
        # Get base reconciliation criteria values
        aml_obj = self.env['account.move.line']
        company = self.env.user.company_id
        company_currency = company.currency_id
        excluded_partners = company.auto_reconciliation_excluded_partner_ids
        excluded_accounts = company.auto_reconciliation_excluded_account_ids
        excluded_journals = company.auto_reconciliation_excluded_journal_ids
        order = 'date_maturity asc'
        if company.automatic_reconciliation_sorting == 'date_desc':
            order = 'date_maturity desc'

        for invoice in self:
            partner = invoice.partner_id.commercial_partner_id or invoice.partner_id
            if partner in excluded_partners or invoice.account_id in excluded_accounts or \
                    invoice.journal_id in excluded_journals:
                continue

            # If invoice currency is not company currency, convert the residual amount
            invoice_currency = invoice.currency_id
            amount = invoice.residual
            if invoice_currency and invoice_currency != company_currency:
                amount = invoice_currency.with_context(date=invoice.date_invoice).compute(amount, company_currency)

            # Build search domain fro account move lines
            domain = [('account_id', '=', invoice.account_id.id),
                      ('partner_id', '=', partner.id),
                      ('reconciled', '=', False),
                      ('amount_residual', '!=', 0.0)]

            if invoice.type == 'out_invoice':
                domain.extend([('debit', '=', 0)])
            elif invoice.type == 'in_invoice':
                domain.extend([('credit', '=', 0)])

            # Search for the unreconciled lines, and find best matching results for the invoices
            lines = aml_obj.search(domain, order=order)
            # Add extra filtering, because leaf in search does not always filter correctly,
            # but don't remove it, because most of the entries are filtered, and it's quicker than .filtered method
            filtered_lines = aml_obj
            for line in lines:
                # Check cluster currencies and append only those lines that have less than two
                cluster_currencies = line.get_reconcile_cluster().mapped('currency_id') | invoice.currency_id
                if len(cluster_currencies - self.env.user.company_id.currency_id) < 2 \
                        and not tools.float_is_zero(line.amount_residual, precision_digits=2):
                    filtered_lines |= line
            if filtered_lines:
                # Check whether specific line(s) can be matched by number
                matched_lines = filtered_lines.get_best_matching_lines_by_name(invoice.number)
                if not matched_lines and invoice.reference:
                    # Check whether specific line(s) can be matched by reference, otherwise match by amount
                    matched_lines = filtered_lines.get_best_matching_lines_by_name(invoice.reference)
                if not matched_lines:
                    matched_lines = aml_obj.get_best_matching_lines_by_amount(filtered_lines, amount)
                for line in matched_lines:
                    invoice.assign_outstanding_credit(line.id)

    @api.model
    def call_multiple_invoice_export_wizard(self, out_refund_export=False):
        """
        Method that returns the action for invoice bank export wizard
        :param out_refund_export: Indicates whether current operation is export for
        out refunds, or not (all in invoices and our refunds are permitted)
        :return: dict: JS server action
        """
        ctx = self._context.copy()

        # Since income tree contains refunds and sales, we filter by type as well
        state_domain = ['open', 'proforma', 'proforma2']
        if out_refund_export:
            invoices_to_pay = self.filtered(lambda r: r.state in state_domain and r.type == 'out_refund')
        else:
            invoices_to_pay = self.filtered(
                lambda r: r.state in state_domain or (
                        r.payment_mode == 'own_account' and not r.is_cash_advance_repaid)
            )
        if not invoices_to_pay:
            raise exceptions.UserError(_('Nėra sąskaitų faktūrų, kurias būtų galima apmokėti.'))

        ctx.update({'invoice_ids': invoices_to_pay.ids, 'out_refund_export': out_refund_export})
        wizard = self.env['account.invoice.export.wizard'].with_context(ctx).create({})

        return {
            'name': _('Apmokėti sąskaitas banke'),
            'context': ctx,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.invoice.export.wizard',
            'view_id': False,
            'res_id': wizard.id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.model
    def create_acc_invoice_action(self):
        """Multi-record tree action"""
        action = self.env.ref('mokejimu_eksportas.invoice_bank_statement_action')
        if action:
            action.create_action()

    @api.multi
    def get_vat_payer_date(self):
        """Returns invoice date to check vat payer status against"""
        self.ensure_one()
        # Method meant to be overridden
        return self.date_invoice
