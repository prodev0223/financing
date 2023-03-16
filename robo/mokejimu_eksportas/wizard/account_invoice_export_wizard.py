# -*- coding: utf-8 -*-
from odoo.addons.base_iban.models.res_partner_bank import validate_iban
from odoo import models, fields, tools, api, _, exceptions
from odoo.addons.sepa import api_bank_integrations as abi
from datetime import datetime
from odoo.tools import float_compare, float_round
from six import iteritems
import itertools as it
import base64

# Code that is used in payable invoices on
# account move lines. Agreed on hard-coding it
AML_INVOICES_CODE = '4430'


class AccInvoiceExpWizard(models.TransientModel):
    _name = 'account.invoice.export.wizard'
    _inherit = 'bank.export.base'

    @api.model
    def get_preferred_bank(self, banks, journal):
        """
        Filter out and get preferred bank based on several criteria
        :param banks: res.partner.bank records
        :param journal: account.journal record
        :return: res.partner.bank record
        """
        if len(banks) > 1:
            sorted_banks_by_write_date = banks.sorted(key='write_date', reverse=True)
            write_dates = sorted_banks_by_write_date.mapped('write_date')
            last_bank_date = datetime.strptime(write_dates[0], tools.DEFAULT_SERVER_DATETIME_FORMAT)
            sec_bank_date = datetime.strptime(write_dates[1], tools.DEFAULT_SERVER_DATETIME_FORMAT)
            days_diff = (last_bank_date - sec_bank_date).days
            if days_diff > 30:
                return sorted_banks_by_write_date[0]

        bank = banks.filtered(lambda r: r.bank_id.id == journal.bank_id.id)
        if not bank:
            bank = banks.filtered(lambda x: x.bank_id.bic in abi.INTEGRATED_BANK_BIC_CODES)
        if not bank:
            bank = banks.filtered(
                lambda r: r.currency_id and r.currency_id.id == journal.currency_id.id)
        if not bank:
            bank = banks[0] if banks else self.env['res.partner.bank']
        return bank[0] if bank else self.env['res.partner.bank']

    @api.model
    def _payable_lines(self):
        """
        Method that is used to initialize the wizard export lines.
        Invoice/Move line data is processed and prepared for the user
        :return: None
        """
        line_ids = []

        # Prepare default values
        date_to_use = self.date_to_use if self else 'today'
        group_lines = self.group_lines if self else True
        journal = self.journal_id or self.env['account.journal'].browse(
            self.env.context.get('default_journal_id')
        )
        company = self.env.user.company_id

        # Ref needed objects
        HrEmployee = self.env['hr.employee']
        InvoiceExportLine = self.env['invoice.export.line']

        # Get data of the objects that are being exported
        export_data = self.get_export_data()
        if export_data:
            # Get export data from previous method
            objects_to_pay = export_data.get('objects_to_pay')
            model_name = export_data.get('model_name')

            # Initiate other values
            values_to_create = {}
            counter = it.count()

            for object_to_pay in objects_to_pay:
                # Get data for payable objects
                partner = object_to_pay.partner_id.get_bank_export_partner()
                account = object_to_pay.account_id
                currency = object_to_pay.currency_id

                # Check whether object was paid by user's own account,
                # and use company currency instead if it was
                own_account_paid = model_name == 'account.invoice' and object_to_pay.state \
                    not in ['open', 'proforma', 'proforma2'] \
                    and object_to_pay.payment_mode == 'own_account' \
                    and not object_to_pay.is_cash_advance_repaid \
                    and object_to_pay.type != 'out_refund'
                if own_account_paid:
                    currency = object_to_pay.company_currency_id

                # Used for grouping
                key = '{}/{}/{}'.format(partner.id, currency.id, account.structured_code)
                vals = values_to_create.get(key, {})

                # Extract the data and initialize variables
                data = self.extract_data({
                    'object_to_pay': object_to_pay,
                    'model_name': model_name,
                    'own_account_paid': own_account_paid,
                    'date_to_use': date_to_use,
                })
                amount, date, name = data['amount'], data['date'], data['name']

                if not group_lines or not vals:
                    # Get bank account from employee otherwise from partner bank list
                    employee = HrEmployee.search([('address_home_id', '=', partner.id)], limit=1)
                    bank_account = employee.bank_account_id
                    if not bank_account:
                        bank_account = self.get_preferred_bank(partner.bank_ids, journal)
                    # Prepare the line values
                    vals = {
                        'company_id': company.id,
                        'date': date,
                        'name': name,
                        'ref': name,
                        'account_id': account.id,
                        'amount': amount,
                        'partner_id': partner.id,
                        'currency_id': currency.id,
                        'bank_account_id': bank_account.id,
                        'aml_ids': [],
                        'invoice_ids': [],
                    }
                else:
                    # Otherwise, update the line values
                    if date < vals.get('date'):
                        vals.update({'date': date})

                    # Update name and reference
                    for field in ['name', 'ref']:
                        current_value = vals.get(field, str())
                        if name not in current_value:
                            vals.update({field: '{}, {}'.format(current_value, name)})

                    # Lastly, update amount
                    vals.update({'amount': vals.get('amount', 0.0) + amount})

                # Update account move line data
                if model_name == 'account.move.line':
                    vals['aml_ids'] += [(4, object_to_pay.id)]
                    invoice = object_to_pay.invoice_id
                    # Add invoice to the list as well if accounts do match
                    if invoice.account_id.id == account.id:
                        vals['invoice_ids'] += [(4, invoice.id)]

                # Update account invoice data
                elif model_name == 'account.invoice':
                    vals['invoice_ids'] += [(4, object_to_pay.id)]
                    move_lines = object_to_pay.move_id.line_ids.filtered(
                        lambda l: l.account_id.id == account.id)
                    if move_lines:
                        vals['aml_ids'] += [(4, line.id) for line in move_lines]

                # Append the data to the main structure
                if not group_lines:
                    key += '/{}'.format(next(counter))
                values_to_create[key] = vals

            line_ids = []
            for key, vals in iteritems(values_to_create):
                line = InvoiceExportLine.create(vals)
                line_ids.append(line.id)

        # Check if GPM entries should be created
        if self._context.get('form_gpm_payments_for_holidays'):
            base_wizard_data = {
                'journal': journal,
                'date_to_use': date_to_use,
                'group_lines': group_lines,
            }
            self.prepare_gpm_payments(line_ids, base_wizard_data)

        lines_to_round = InvoiceExportLine.browse(line_ids).filtered(lambda l: l.account_id.use_rounding)
        for line in lines_to_round:
            line.amount = float_round(line.amount, precision_rounding=1)
        return [(6, 0, line_ids)]

    @api.multi
    def get_export_data(self):
        """
        Parses the data that is received from the context,
        browses for the objects and prepares the recordset
        of objects that are being exported.
        :return: dict: Structure containing records, model name
        """

        object_data = {}
        # Check what object is being exported
        if self._context.get('invoice_ids'):
            object_name, model_name = 'invoice_ids', 'account.invoice'
        elif self._context.get('aml_ids'):
            object_name, model_name = 'aml_ids', 'account.move.line'
        else:
            return object_data

        # If we get the object that is being exported, create payments
        if self and self.payable_lines:
            _ids = self.payable_lines.mapped(object_name).ids
        else:
            _ids = self._context.get(object_name)
        to_pay = self.env[model_name].browse(_ids)

        # Only two types of objects are exportable at the moment
        if model_name == 'account.move.line':
            objects_to_pay = to_pay.filtered(
                lambda l:
                not l.currency_id and
                float_compare(l.amount_residual, 0.0, precision_rounding=0.01) < 0 or
                l.currency_id and float_compare(
                    l.amount_residual_currency, 0.0, precision_rounding=0.01) < 0
            )
        else:
            objects_to_pay = to_pay.filtered(
                lambda r:
                r.state in ['open', 'proforma', 'proforma2'] or
                (r.payment_mode == 'own_account' and not r.is_cash_advance_repaid)
            ).sorted(key='date_due', reverse=True)

            # Ensure that out invoices are not exported to the bank
            if any(x.type in ['out_invoice', 'in_refund'] for x in objects_to_pay):
                raise exceptions.ValidationError(
                    _('You cannot export out invoices or in refunds to the bank!'))

        return {
            'model_name': model_name,
            'objects_to_pay': objects_to_pay,
        }

    @api.multi
    def extract_data(self, unstructured_data):
        """
        Method that is used to extract the data from different objects
        and prepare it for further object creation/initialization
        :param unstructured_data: Unstructured data from the wizard
        :return: dict: Extracted data
        """

        # Prepare needed data
        object_to_pay = unstructured_data.get('object_to_pay')
        model_name = unstructured_data.get('model_name')
        own_account_paid = unstructured_data.get('own_account_paid')
        date_to_use = unstructured_data.get('date_to_use')
        invoice_export = model_name == 'account.invoice'
        HrPayslip = self.env['hr.payslip']

        # Check whether current report is out_refund export,
        # if it is, amounts should behave in the same way as in_invoice export
        out_refund_export = self._context.get('out_refund_export')

        # Extract the amount ------------------------------------------

        # Get the amount of the object, it's always bank export residual
        # unless invoice is paid by own account
        tr_amount = object_to_pay.bank_export_residual
        if invoice_export and own_account_paid:
            tr_amount = object_to_pay.amount_total_company_signed

        # If invoice is fully paid, populate the amount with original value,
        # since boolean constraint does not let the export happen unless user marks it
        if invoice_export and tools.float_is_zero(tr_amount, precision_digits=2):
            tr_amount = object_to_pay.amount_total_company_signed

        # If current operation in refund invoice export, ABS the amount
        if out_refund_export:
            tr_amount = abs(tr_amount)

        # Extract the date --------------------------------------------

        tr_date = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        if date_to_use != 'today':
            if invoice_export:
                date = object_to_pay.date_due or object_to_pay.move_id.date
            else:
                date = object_to_pay.date
            tr_date = max(date, tr_date)

        # Extract the name --------------------------------------------

        if invoice_export:
            # Get the name of the invoice and append the message if it's advance payment
            tr_name = object_to_pay.reference or object_to_pay.number or object_to_pay.proforma_number
            if tr_name and object_to_pay.state in ['proforma', 'proforma2']:
                tr_name += _(' (Išankstinis mokėjimas)')
        else:
            # Get the name of the move line
            tr_name = object_to_pay.ref or object_to_pay.name
            # Check if payment meets following criteria, and forcibly
            # use 'name' field if it does TODO, probably could be improved
            is_mok = object_to_pay.ref and object_to_pay.ref[:3] == 'MOK'
            is_holiday_account = object_to_pay.account_code == '4480'
            is_compensation = 'Kompensacijos' in object_to_pay.name
            if is_mok and is_holiday_account or is_compensation:
                tr_name = object_to_pay.name

            # Afterwards, if we get static payslip string in the name
            # search and use payslip display name instead TODO, probably could be improved
            if 'Algalapis' in tr_name or 'SLIP' in tr_name:
                slip = HrPayslip.search([('move_id', '=', object_to_pay.move_id.id)])
                if slip and len(slip) == 1:
                    tr_name = slip.display_name

        # If no name was found, use static string for it
        if not tr_name:
            tr_name = _('Išankstinis mokėjimas')

        # Return the data that was extracted
        return {
            'name': tr_name,
            'amount': tr_amount,
            'date': tr_date,
        }

    @api.multi
    def prepare_gpm_payments(self, line_ids, base_wizard_data):
        """
        Creates the wizard lines for GPM payments if there's any holidays passed
        :param line_ids: list: Values for lines to be created
        :param base_wizard_data: dict: Base wizard data
        :return: None
        """

        # Search for holidays passed in context. If there's no holidays, return
        holiday_ids = self._context.get('form_gpm_payments_for_holidays', [])
        holidays = self.env['hr.holidays'].browse(holiday_ids)
        if not holidays:
            return

        # Get base wizard data
        journal = base_wizard_data.get('journal')
        date_to_use = base_wizard_data.get('date_to_use')
        group_lines = base_wizard_data.get('group_lines')

        def create_line(env, holiday_rec):
            """Inner method to create the lines, initialize after checking holidays and getting the data"""
            date = now if date_to_use == 'today' else holiday_rec.payment_id.date_payment
            vals = base_holiday_gpm_payment_vals.copy()
            vals.update({
                'date': date, 'name': name,
                'ref': name, 'amount': amount,
            })
            line = env['invoice.export.line'].create(vals)
            line_ids.append(line.id)

        # Get needed objects
        gpm_account_id = self.env.user.company_id.default_saskaita_gpm()
        gpm_salary_rule = self.env.ref('l10n_lt_payroll.hr_payroll_rules_pajamu')
        gpm_partner = gpm_salary_rule.register_id.partner_id
        employee = self.env['hr.employee'].search([('address_home_id', '=', gpm_partner.id)], limit=1)

        # Init current date and get the bank account
        now = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        bank_account = employee.bank_account_id
        if not bank_account:
            bank_account = self.get_preferred_bank(gpm_partner.bank_ids, journal)

        # Prepare base values
        base_holiday_gpm_payment_vals = {
            'account_id': gpm_account_id.id if gpm_account_id else False,
            'partner_id': gpm_partner.id,
            'currency_id': False,
            'invoice_ids': False,
            'bank_account_id': bank_account.id,
            'company_id': self.env.user.company_id.id,
        }

        # Either loop through holidays, or use a single
        # grouped record and prepare the lines
        holidays = holidays.filtered(lambda h: h.payment_id)
        if not group_lines:
            for holiday in holidays:
                name = _('GPM mokėjimas už atostoginius {0} {1}').format(
                    holiday.employee_id.display_name, holiday.date_from_date_format)
                amount = sum(holiday.payment_id.mapped('payment_line_ids.amount_gpm'))
                create_line(self.env, holiday)
        elif holidays:
            holiday = holidays[0]
            name = _('GPM mokėjimas už atostoginius {0}').format(holiday.date_from_date_format)
            amount = sum(holidays.mapped('payment_id.payment_line_ids.amount_gpm'))
            create_line(self.env, holiday)

    journal_id = fields.Many2one('account.journal', string='Banko sąskaita')
    payable_lines = fields.Many2many('invoice.export.line', string='Mokėjimai', default=_payable_lines)
    download = fields.Boolean(compute='_compute_download')
    group_lines = fields.Boolean(string='Apjungti mokėjimus', default=True)
    date_to_use = fields.Selection([('today', 'Šiandienos data'),
                                    ('date_due', 'Mokėjimo termino data')], string='Naudojama data',
                                   required=True, default='today')
    international_priority = fields.Selection([('SDVA', 'Šiandieninis'),
                                               ('URGP', 'Skubus'),
                                               ('NURG', 'Neskubus')],
                                              string='Tarptautinių mokėjimų prioritetas', default='NURG', required=True)

    api_integrated_journal = fields.Boolean(compute='_compute_api_integrated_data', compute_sudo=True)
    api_full_integration = fields.Boolean(compute='_compute_api_integrated_data', compute_sudo=True)
    skip_full_export_warning = fields.Boolean(string='Praleisti apmokėtų sąskaitų įspėjimus')
    show_skip_full_export_warning = fields.Boolean(compute='_compute_show_skip_full_export_warning')

    # Banners in the wizard
    unpaid_e_invoice_names = fields.Text(compute='_compute_unpaid_e_invoice_names')
    show_unpaid_e_invoice_banner = fields.Boolean(compute='_compute_unpaid_e_invoice_names')

    outstanding_invoice_names = fields.Text(compute='_compute_outstanding_invoice_names')
    show_outstanding_invoice_banner = fields.Boolean(compute='_compute_outstanding_invoice_names')

    move_line_warning = fields.Text(compute='_compute_move_line_warning')
    show_move_line_warning = fields.Boolean(compute='_compute_move_line_warning')

    non_iban_account_warning = fields.Text(compute='_compute_non_iban_account_warning')
    show_non_iban_account_warning = fields.Boolean(compute='_compute_non_iban_account_warning')
    show_group_transfer = fields.Boolean(compute='_compute_show_group_transfer')
    has_multiple_bank_accounts = fields.Boolean(compute='_compute_has_multiple_bank_accounts')

    @api.multi
    def _compute_show_skip_full_export_warning(self):
        """Check whether wizard has any fully exported and accepted invoices"""
        for rec in self:
            states = set(
                rec.payable_lines.mapped('invoice_ids.bank_export_state') +
                rec.payable_lines.mapped('aml_ids.bank_export_state')
            )
            rec.show_skip_full_export_warning = 'accepted' in states or 'processed' in states

    @api.multi
    @api.depends('payable_lines.partner_id')
    def _compute_show_group_transfer(self):
        """Check whether group transfer button should be shown - each partner must be employee"""
        for rec in self:
            rec.show_group_transfer = \
                rec.payable_lines and all(rec.payable_lines.mapped('partner_id.is_employee'))

    @api.multi
    @api.depends('payable_lines', 'payable_lines.bank_account_id.acc_number')
    def _compute_non_iban_account_warning(self):
        """
        Compute //
        Check whether payable lines contain any bank accounts that are not IBAN format.
        If so - display warning message to the user, because we cannot tell whether bank account
        number was unintentionally mistyped or if it was meant not to be an IBAN number.
        :return:  None
        """
        for rec in self:
            warning = str()
            for line in rec.payable_lines:
                if line.bank_account_id.acc_number:
                    try:
                        validate_iban(line.bank_account_id.acc_number)
                    except exceptions.ValidationError:
                        warning += ', {}'.format(line.name) if warning else '{}'.format(line.name)
            if warning:
                warning = _('Apačioje pateiktos eilutės turi netinkamą IBAN banko sąskaitos formatą. Jeigu manote, '
                            'kad šie numeriai yra korektiškos kliento banko sąskaitos identifikacijos reikšmės, '
                            'ignoruokite šį pranešimą.\n') + warning
                rec.non_iban_account_warning = warning
                rec.show_non_iban_account_warning = True

    @api.multi
    @api.depends('payable_lines')
    def _compute_move_line_warning(self):
        """
        Compute //
        Check whether payable lines contain any AMLs that have invoices
        or belong to the payable invoice account account record
        :return:  None
        """
        for rec in self:
            warning = str()
            # Only check this part if initially passed AMLs exist
            if self._context.get('aml_ids'):
                for line in rec.payable_lines:
                    for aml in line.aml_ids.filtered(lambda x: x.invoice_id or x.account_id.code == AML_INVOICES_CODE):
                        warning += ', {}'.format(aml.name) if warning else '{}'.format(aml.name)
            rec.move_line_warning = warning
            rec.show_move_line_warning = True if warning else False

    @api.multi
    @api.depends('payable_lines')
    def _compute_outstanding_invoice_names(self):
        """
        Compute //
        Check whether invoices on any payable line have outstanding amounts
        if they do -- collect their names
        :return:  None
        """
        for rec in self:
            text = str()
            for line in rec.payable_lines:
                for invoice in line.invoice_ids.filtered(lambda x: x.has_outstanding):
                    name = invoice.reference if invoice.reference else \
                        invoice.number or invoice.proforma_number
                    text += ', {}'.format(name) if text else '{}'.format(name)
            rec.outstanding_invoice_names = text
            rec.show_outstanding_invoice_banner = True if text else False

    @api.multi
    @api.depends('payable_lines')
    def _compute_unpaid_e_invoice_names(self):
        """
        Compute //
        Check whether invoices on any payable line are unpaid e_invoices
        if they are -- collect their names
        :return:  None
        """
        for rec in self:
            text = str()
            for line in rec.payable_lines:
                for invoice_id in line.invoice_ids.filtered(lambda x: x.robo_unpaid_e_invoice and x.state in ['open']):
                    name = invoice_id.reference if invoice_id.reference else \
                        invoice_id.number or invoice_id.proforma_number
                    text += ', {}'.format(name) if text else '{}'.format(name)
            rec.unpaid_e_invoice_names = text
            rec.show_unpaid_e_invoice_banner = True if text else False

    @api.multi
    @api.depends('journal_id')
    def _compute_api_integrated_data(self):
        """
        Compute //
        Check whether the journal that the invoices
        are being exported to is API integrated
        and whether the integration is non-partial
        :return: None
        """
        for rec in self:
            rec.api_full_integration = rec.journal_id.sudo().api_full_integration
            rec.api_integrated_journal = rec.journal_id.sudo().api_integrated_journal

    @api.onchange('group_lines', 'journal_id')
    def _onchange_group_lines(self):
        self.payable_lines = self._payable_lines()

    @api.onchange('date_to_use')
    def _onchange_date_to_use(self):
        if self.date_to_use == 'today':
            today = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            self.payable_lines = [(1, line.id, {'date': today}) for line in self.payable_lines]
        else:
            vals = []
            date_today = datetime.utcnow()
            for line in self.payable_lines:
                if self._context.get('invoice_ids'):
                    dates = [datetime.strptime(d, tools.DEFAULT_SERVER_DATE_FORMAT)
                             for d in line.invoice_ids.mapped(lambda i: i.date_due or i.move_id.date if i.type not in (
                            'out_invoice', 'in_refund') else False) if d]
                elif self._context.get('aml_ids'):
                    dates = [datetime.strptime(d, tools.DEFAULT_SERVER_DATE_FORMAT)
                             for d in line.mapped('aml_ids.date')]
                else:
                    continue
                line_date = date_today if not dates else max(date_today, min(dates))
                vals.append((1, line.id, {'date': line_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)}))
            self.payable_lines = vals

    @api.multi
    @api.depends('payable_lines', 'journal_id')
    def _compute_download(self):
        for rec in self:
            # Download is only allowed for SEPA import file types
            rec.download = bool(self._context.get('download')) and rec.journal_id.import_file_type == 'sepa'

    @api.multi
    @api.depends('payable_lines.has_multiple_bank_accounts')
    def _compute_has_multiple_bank_accounts(self):
        for rec in self:
            rec.has_multiple_bank_accounts = any(rec.payable_lines.mapped('has_multiple_bank_accounts'))

    @api.onchange('journal_id')
    def _onchange_journal_set_preferred_bank_account(self):
        preferred_bank = self.journal_id.bank_id
        # Do not set preferred bank account for employees
        for pay_line in self.payable_lines.filtered(lambda p: not p.partner_id.is_employee):
            bank = pay_line.partner_id.bank_ids.filtered(lambda r: r.bank_id.id == preferred_bank.id)
            if bank:
                pay_line.bank_account_id = bank[0].id

    @api.model
    def create(self, vals):
        # bug in api, it provides values with (1, id, vals), so doesn't link to them see bug #21285, #14761
        #  This overload is needed because there is api.onchange method
        commands = []
        if 'payable_lines' in vals:
            commands = vals['payable_lines']
            new_commands = [(5,)]
            if isinstance(commands, list):
                for comm in commands:
                    if len(comm) == 3 and comm[0] == 1:
                        new_commands.append((4, comm[1]))
            vals['payable_lines'] = new_commands
        res = super(AccInvoiceExpWizard, self).create(vals)
        res.write({'payable_lines': commands})
        return res

    @api.multi
    def button_create_bank_statement(self):
        return self.create_bank_statement()

    @api.multi
    def create_bank_statement(self, return_mode='action'):
        self.ensure_one()

        holiday_ids = self._context.get('form_gpm_payments_for_holidays', [])
        holidays = self.env['hr.holidays'].browse(holiday_ids).filtered(lambda h: h.payment_id)
        holidays.write({'gpm_paid': True})
        if not self.journal_id:
            raise exceptions.UserError(_('Please select Journal before creating a statement.'))
        journal_currency_id = self.journal_id.currency_id if self.journal_id.currency_id else self.env.user.company_id.currency_id
        bank_statement_lines = []
        lines_sum = 0.0
        if any(line.amount < 0 for line in self.payable_lines):
            raise exceptions.UserError(_(
                'Visų kuriamų eilučių mokėtinos sumos privalo būti didesnės už 0! Netraukite kreditinių sąskaitų'))
        for pay_line in self.payable_lines:
            if pay_line.currency_id != journal_currency_id:
                amount_journal = pay_line.currency_id.with_context(date=pay_line.date).compute(pay_line.amount,
                                                                                               journal_currency_id)
            else:
                amount_journal = pay_line.amount
            vals = {'company_id': self.env.user.company_id.id,
                    'date': pay_line.date if pay_line.date else datetime.utcnow().strftime(
                        tools.DEFAULT_SERVER_DATE_FORMAT),
                    'name': pay_line.name,
                    'ref': pay_line.ref,
                    'amount': - amount_journal,
                    'partner_id': pay_line.partner_id.id,
                    'invoice_ids': [(6, 0, pay_line.invoice_ids.ids)],
                    'aml_ids': [(6, 0, pay_line.aml_ids.ids)],
                    }
            if pay_line.partial_payment:
                vals.update({'post_export_residual': pay_line.post_export_residual})

            structured_code = pay_line.partner_id.imokos_kodas or pay_line.account_id.structured_code
            if structured_code or pay_line.info_type == 'structured':
                vals.update({
                    'info_type': 'structured',
                    'name': structured_code or pay_line.name
                })

            vals['bank_account_id'] = pay_line.bank_account_id.id

            if pay_line.currency_id and (journal_currency_id != pay_line.currency_id or
                                         journal_currency_id != self.env.user.company_id.currency_id):
                vals['amount_currency'] = - pay_line.amount
                vals['currency_id'] = pay_line.currency_id.id
            lines_sum += - pay_line.amount
            bank_statement_lines.append((0, 0, vals))

        if self.journal_id.default_credit_account_id:
            credit_account_id = self.journal_id.default_credit_account_id.id
        else:
            raise exceptions.Warning(_('Nenurodyta žurnalo kredito sąskaita'))

        if self._context.get('front_statement', False):
            vals_front = {'company_id': self.env.user.company_id.id,
                          'name': datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT) + ' TK',
                          'date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                          'journal_id': self.journal_id.id,
                          'line_ids': bank_statement_lines,
                          }
            front_st = self.sudo().env['front.bank.statement'].create(vals_front)
            front_st.inform()
            if return_mode in ['statement']:
                return front_st
            else:
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'front.bank.statement',
                    'view_mode': 'form',
                    'view_type': 'form',
                    'views': [(False, 'form')],
                    'target': 'current',
                    'robo_front': True,
                    'res_id': front_st.id,
                    'context': self._context,
                }
        else:
            starto_data = datetime(datetime.utcnow().year, 1, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            pabaigos_data = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            self._cr.execute('''select sum(debit) as debit, sum(credit) as credit from account_move_line AS line,
                                    account_move as move
                                    WHERE line.move_id = move.id AND line.date >= %s AND line.date <= %s
                                    AND account_id = %s AND move.state = 'posted' AND move.company_id = %s ''',
                             (starto_data, pabaigos_data, credit_account_id, self.env.user.company_id.id))
            result = self._cr.dictfetchall()
            if len(result) > 0:
                result = result[0]
                if 'debit' in result.keys():
                    d = result['debit'] or 0
                else:
                    d = 0
                if 'credit' in result.keys():
                    k = result['credit'] or 0
                else:
                    k = 0
                balance_start = d - k
                balance_end_real = balance_start + lines_sum
            else:
                balance_start = 0
                balance_end_real = lines_sum

            bank_vals_name = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT) + ' TK'
            if self._context.get('pvm_bank_statement'):
                bank_vals_name = 'PVM ' + datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            vals_bank = {'name': bank_vals_name,
                         'date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                         'company_id': self.env.user.company_id.id,
                         'journal_id': self.journal_id.id,
                         'line_ids': bank_statement_lines,
                         'balance_start': balance_start,
                         'balance_end_real': balance_end_real,
                         'state': 'open'
                         }
            bank_st = self.sudo().env['account.bank.statement'].create(vals_bank)
            if return_mode in ['statement']:
                return bank_st
            else:
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'account.bank.statement',
                    'view_mode': 'form',
                    'view_type': 'form',
                    'views': [(False, 'form')],
                    'target': 'current',
                    'res_id': bank_st.id,
                    'context': self._context,
                }

    @api.multi
    def write_gpm_paid_holidays(self):
        self.ensure_one()
        holiday_ids = self._context.get('form_gpm_payments_for_holidays', [])
        holidays = self.env['hr.holidays'].browse(holiday_ids).filtered(lambda h: h.payment_id)
        holidays.write({'gpm_paid': True})

    @api.multi
    def download_sepa(self):
        if not self.env.user.has_group('robo_basic.group_robo_payment_export'):
            return
        if not self.journal_id:
            raise exceptions.ValidationError(_('Nepasirinktas bankas!'))
        self.write_gpm_paid_holidays()
        if self.download:
            if not all([l.bank_account_id for l in self.payable_lines]):
                raise exceptions.UserError(
                    _('Visos eksportuojamos eilutės privalo turėti nurodytas banko sąskaitas.'))
            if any([x.amount < 0 for x in self.payable_lines]):
                raise exceptions.UserError(_('Visų eksportuojamų eilučių mokėtinos sumos privalo būti didesnės už 0! '
                                             'Netraukite kreditinių sąskaitų'))
            # Prepare statement export data and return the action
            return self.export_sepa_attachment_download(
                self.get_bank_export_data(self.payable_lines)
            )
        return {'type': 'ir.actions.act_window_close'}

    # -----------------------------------------------------------------------------------------------------------------
    # Bank Sending Methods --------------------------------------------------------------------------------------------
    # -----------------------------------------------------------------------------------------------------------------

    @api.multi
    def send_to_bank_validator(self):
        """
        Validate invoice data that is being send to bank
        by checking base wizard data (exportable states, partial payment)
        raises the error on constraint violation.
        :return: None
        """

        def validate_lines(data_set):
            return any(x.bank_export_state not in abi.EXPORTABLE_STATES or tools.float_compare(
                0.0, x.bank_export_residual, precision_digits=2) > 0 for x in data_set)

        super(AccInvoiceExpWizard, self).send_to_bank_validator()
        for rec in self:
            # Check live export states for each of the exported jobs
            total_export_jobs = self.env['bank.export.job']
            total_export_jobs |= rec.payable_lines.mapped('invoice_ids.bank_export_job_ids')
            total_export_jobs |= rec.payable_lines.mapped('aml_ids.bank_export_job_ids')
            total_export_jobs.check_live_export_state()
            # Check if lines to be exported are of correct state
            # And are not grouped if payment is partial
            body = str()
            for line in rec.payable_lines:
                # Ensure that the amount is not zero
                if tools.float_is_zero(line.amount, precision_digits=2):
                    body += _('Eilutė "%s" neturi nurodytos pavedimo sumos\n') % line.name
                # Recompute the states
                line.invoice_ids.with_context(skip_accountant_validated_check=True)._compute_bank_export_state()
                line.aml_ids.with_context(check_move_validity=False)._compute_bank_export_state()
                # Validate the lines and gather errors if any
                if not rec.skip_full_export_warning and (
                        validate_lines(line.invoice_ids) or validate_lines(line.aml_ids)):
                    body += _('''Bent vienas eilutės '%s' elementas turi netinkamą eksportavimo būseną. 
                        Eksportas galimas tik šiose būsenose - 'Neeksportuota', 'Atmesta', 'Dalinis mokėjimas'. 
                        Jeigu norite pakartotinai eksportuoti priimtą mokėjimą, pažymėkite varnelę eksportavimo 
                        vedlio formoje. Ši varnelė rodoma tik tuomet, jei paskutinis eksportas yra priimtas
                        \n''') % line.name

                if rec.group_lines and line.partial_payment and (len(line.invoice_ids) > 1 or len(line.aml_ids) > 1):
                    body += _(
                        'Negalite eksportuoti dalinio mokėjimo apjungtai eilutei! Suklydusi eilutė %s'
                    ) % line.name
            # Raise an error if any of the lines did not pass the validation
            if body:
                raise exceptions.ValidationError(body)

    @api.multi
    def send_to_bank(self):
        """
        Method that is used to send payable invoice data to bank.
        Validates the data-to-be send, determines what integration is used
        (SEPA or API, only those two at the moment), groups data
        accordingly, calls the method that is the initiator of
        bank statement export for specific journal.
        :return: result of export method for specific journal
        """
        self.ensure_one()
        self.write_gpm_paid_holidays()
        return self.send_to_bank_base(self.get_bank_export_data(self.payable_lines))

    @api.multi
    def prepare_sepa_xml_bank_export(self, data):
        """
        Creates export jobs for the data that is
        being exported, creates artificial bank statement
        and generates attachment - data structure that is
        acceptable for bank integrations of SEPA type.
        :return: Grouped data (str)
        """
        self.ensure_one()
        # Create artificial statement and export it's attachment
        statement = self.sudo().with_context(sepa_export=True).create_bank_statement(return_mode='statement')
        statement.line_ids.mark_related_objects_as_exported()
        attachment = statement.export_sepa_attachment()
        # Read base attachment values
        attach_vals = attachment.read(['datas', 'datas_fname', 'name'])[0]
        # Create bank export jobs and unlink artificial statement
        bank_exports = self.env['bank.export.job'].create_bank_export_jobs(data={
            'parent_lines': statement.line_ids,
            'export_type': 'sepa_xml',
            'journal': self.journal_id,
            'origin': data.get('origin'),
            'xml_file_download': data.get('xml_file_download'),
            'xml_file_data': attach_vals['datas'],
        })
        statement.unlink()
        # Prepare the XML stream value
        xml_stream = base64.b64decode(attach_vals['datas'])
        # When statement is unlinked, attachment is unlinked as well
        # thus we create a new one that is attached to res company
        attach_vals['res_model'] = 'res.company'
        attach_vals['res_id'] = self.env.user.company_id.id
        attachment = self.env['ir.attachment'].sudo().with_context({}).create(attach_vals)
        return {
            'attachment': attachment,
            'bank_exports': bank_exports,
            'xml_stream': xml_stream,
            'forced_origin': attach_vals['res_model'],
            'forced_res_id': attach_vals['res_id'],
        }