# -*- coding: utf-8 -*-
from odoo import models, fields, tools, api, _, exceptions
from odoo.addons.sepa import api_bank_integrations as abi
from odoo.addons.two_factor_otp_auth import decorators as actions_2fa
from datetime import datetime
from six import iteritems
import hashlib


def get_int_hash(s):
    """
    Generate sha1 hash for the passed string
    :param s: passed string
    :return: hash (str)
    """
    s = str(s)
    return str(int(hashlib.sha1(s).hexdigest(), 16) % (10 ** 8))


class BankExportJob(models.Model):
    _name = 'bank.export.job'
    _order = 'date_exported desc, id desc'

    # Identifier fields
    sepa_instruction_id = fields.Char(string='SEPA Instrukcijos ID')  # Used in SEPA XML based integrations
    journal_id = fields.Many2one('account.journal', string='Mokėtojo banko sąskaita')
    export_batch_id = fields.Many2one('bank.export.job.batch', string='Export file batch')

    # partner_id of the user who initiated the actual export
    partner_id = fields.Many2one('res.partner', string='Įkėlęs naudotojas (Partneris)')

    # Objects that can be exported
    invoice_ids = fields.Many2many('account.invoice', string='Sąskaitos faktūros', ondelete='cascade')
    move_line_ids = fields.Many2many('account.move.line', string='Žurnalo elementai', ondelete='cascade')
    bank_statement_line_id = fields.Many2one(
        'account.bank.statement.line', string='Bankinio išrašo eilutė', ondelete='cascade'
    )

    # Partial payment fields
    post_export_residual = fields.Float(string='Menamas sąskaitos likutis atėmus eksportuotą sumą')
    partial_payment = fields.Boolean(compute='_compute_partial_payment', string='Dalinis apmokėjimas')

    # Extra information fields
    last_error_message = fields.Text(string='Pranešimas')
    system_notification = fields.Text(string='Sisteminis klaidos pranešimas')
    api_external_id = fields.Char(string='ID išorinėje sistemoje')
    available_for_signing = fields.Boolean(string='Laukiama pasirašymo', compute='_compute_available_for_signing')
    e_signed_export = fields.Boolean(string='Pasirašytas')
    date_signed = fields.Datetime(string='Pasirašymo data')
    date_exported = fields.Datetime(string='Eksportavimo data')
    ceo_informed = fields.Boolean(string='Vadovas informuotas')
    group_payment_export = fields.Boolean(string='Grupinis mokėjimas')
    state_update_retries = fields.Integer(string='State update retries')

    # Exported transaction data
    tr_name = fields.Char(string='Pavadinimas')
    tr_ref = fields.Char(string='Nuoroda')
    tr_date = fields.Date(string='Data')
    tr_amount = fields.Float(string='Suma')
    tr_partner_id = fields.Many2one('res.partner', string='Partneris')
    tr_currency_id = fields.Many2one('res.currency', string='Valiuta')
    tr_bank_account_id = fields.Many2one('res.partner.bank', string='Gavėjo sąskaita')
    tr_structured = fields.Boolean(string='Struktūruota')
    tr_account_id = fields.Many2one('account.account', string='Sąskaita')

    # States / types
    export_state = fields.Selection(
        abi.BANK_EXPORT_STATES, string='Būsena',
        default='no_action', copy=False, inverse='_set_export_state'
    )
    export_data_type = fields.Selection(
        abi.BANK_EXPORT_TYPES,
        string='Eksportuoti objektai', default='non_exported',
    )
    xml_file_download = fields.Boolean(
        string='Atsisiųstas failas',
        help='Požymis indikuojantis, kad mokėjimas buvo atsisiųstas kaip XML failas'
    )

    # eInvoice fields
    e_invoice_file_id = fields.Char(string='Failo Identifikatorius')
    e_invoice_global_unique_id = fields.Char(string='Globalus identifikatorius')
    e_invoice_auto_payment_partner_id = fields.Many2one(
        'res.partner', string='eSąskaitos automatinių mokėjimų gavėjas')

    @api.multi
    @api.constrains('tr_bank_account_id', 'journal_id')
    def _check_bank_account_integrity(self):
        """Ensure that receiver and payer accounts differ"""
        for rec in self.filtered(lambda x: x.journal_id and x.tr_bank_account_id):
            if rec.journal_id.bank_acc_number == rec.tr_bank_account_id.acc_number:
                raise exceptions.ValidationError(_(
                    'You cannot initiate the payment to the account from which the payment is made. IBAN - {}'
                ).format(rec.journal_id.bank_acc_number))

    @api.multi
    def _set_export_state(self):
        """
        Inverse //
        Set various data based on bank.export.job state changes
        :return: None
        """
        for rec in self.sudo():
            # Invoices block (only this for now)
            if rec.invoice_ids or rec.move_line_ids:
                if rec.export_state in abi.REJECTED_STATES:
                    vals = {'exported_sepa': False, 'exported_sepa_date': False}
                    rec.invoice_ids.write(vals)
                    rec.move_line_ids.with_context(check_move_validity=False).write(vals)

                    # If current export is rejected and it was exported in group
                    # transfer batch, mark all other exports from the batch as revoked
                    if rec.export_batch_id.group_transfer:
                        other_exports = rec.export_batch_id.bank_export_job_ids.filtered(
                            lambda x: x.id != rec.id)
                        other_exports.write({'export_state': 'revoked'})

                elif rec.export_state in abi.POSITIVE_STATES:
                    # Loop through records and write correct date
                    accepted_date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    for invoice in rec.invoice_ids:
                        if invoice.expense_state in ['proforma', 'proforma2'] and not rec.partial_payment:
                            invoice.mark_proforma_paid()
                        if not invoice.exported_sepa:
                            invoice.exported_sepa_date = accepted_date

                    for aml in rec.move_line_ids:
                        if not aml.exported_sepa:
                            aml.with_context(check_move_validity=False).exported_sepa_date = accepted_date

                    # Write sepa_exported value invoices
                    rec.invoice_ids.write({'exported_sepa': True})
                    # Write sepa_exported value to AMLs
                    rec.move_line_ids.with_context(check_move_validity=False).write({'exported_sepa': True})

    @api.multi
    @api.depends('e_signed_export')
    def _compute_available_for_signing(self):
        """
        Compute //
        Check whether specific bank.export.job record
        can be e_signed by the user
        :return: None
        """
        for rec in self:
            allow_signing = self.env['api.bank.integrations'].allow_transaction_signing(rec.journal_id)
            rec.available_for_signing = \
                allow_signing and not rec.e_signed_export and rec.export_state in abi.NON_SIGNED_ACCEPTED_STATES \
                and rec.export_data_type in ['move_lines', 'invoices', 'front_statement']

    @api.multi
    @api.depends('post_export_residual')
    def _compute_partial_payment(self):
        """
        Compute //
        Check whether specific export is partial payment.
        If export has amount specified - it is partial
        :return: None
        """
        for rec in self:
            rec.partial_payment = not tools.float_is_zero(rec.post_export_residual, precision_digits=2)

    @api.multi
    @api.constrains('tr_structured', 'tr_ref')
    def _check_structured_payment_ref(self):
        """
        Constraints //
        Payment must have structured reference if it's being
        exported to partner that is listed in ST_REF_PARTNER_CODES
        :return: None
        """
        for rec in self:
            if rec.partner_id.kodas in abi.ST_REF_PARTNER_CODES and not (rec.tr_ref and rec.tr_structured):
                raise exceptions.ValidationError(
                    _('Eksportuojant mokėjimą į partnerio "{}" banko sąskaitą, privaloma nurodyti '
                      'struktūruotą mokėjimo paskirtį.').format(rec.partner_id.display_name))

    @api.multi
    def post_message_to_related(self, message=str()):
        """
        Write passed message to related objects - account.invoice,
        account.move (line) or res.partner.
        If no message is passed, try to compose the default message
        based on export type and export state
        :return: None
        """
        msg_provided = message
        for rec in self:
            if not msg_provided:
                if rec.export_state in abi.REJECTED_STATES:
                    if rec.export_data_type == 'e_invoice':
                        message = _('eInvoice export was rejected')
                    elif rec.export_data_type == 'automatic_e_invoice_payment':
                        message = _('Automatic eInvoice payment agreement was rejected')
                    else:
                        message = _('Last bank payment export was rejected')
                elif rec.export_state in abi.ACCEPTED_STATES:
                    if rec.export_data_type == 'e_invoice':
                        message = _('eInvoice export was accepted')
                    elif rec.export_data_type == 'automatic_e_invoice_payment':
                        message = _('Automatic eInvoice payment agreement was accepted')
                    else:
                        message = _('Last bank payment export was accepted')
                elif rec.export_state in abi.REVOKED_STATES:
                    message = _('Last bank payment export was accepted, but it was revoked by the user')
                else:
                    message = ''
            else:
                message = msg_provided
            if message:
                for invoice in rec.mapped('invoice_ids'):
                    invoice.message_post(body=message)

                for partner in rec.mapped('e_invoice_auto_payment_partner_id'):
                    partner.message_post(body=message)

                # Since AMLs do not have the mail inherited, we extend the message
                move_data = {}
                for line in rec.mapped('move_line_ids'):
                    move_data.setdefault(line.move_id, self.env['account.move.line'])
                    move_data[line.move_id] |= line

                for move, affected_lines in iteritems(move_data):
                    line_base = '. Paveikti žurnalo elementai:\n'
                    for line in affected_lines:
                        line_base += '{}, '.format(line.name)
                    move.message_post(body=message + line_base)

    @api.multi
    def sign_bank_transaction(self):
        """
        Try to sign bank export job by checking whether
        the bank that journal corresponds to, has integrated
        signing, and whether it's enabled.
        :return: result of transaction signing method (based on bank)
        """
        self.ensure_one()
        # Check whether current export is not yet signed
        if self.e_signed_export:
            raise exceptions.ValidationError(_('Ši transakcija jau pasirašyta!'))

        if not self.env.user.enable_2fa:
            raise exceptions.ValidationError(
                _('Negalite pasirašinėti transakcijų, neįgalintas patvirtinimas dviem veiksmais'))

        # Check whether signing should be allowed based on the bank
        allow_signing = self.env['api.bank.integrations'].allow_transaction_signing(self.journal_id)
        if self.api_external_id and self.export_state in abi.NON_SIGNED_ACCEPTED_STATES and allow_signing:

            # Redirect to transitional 2FA wizard
            wizard_2fa = self.env['transitional.2fa.wizard'].create({
                'redirect_method_name': 'auth_sign_bank_transaction',
                'redirect_model_name': self._name,
            })
            return {
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'transitional.2fa.wizard',
                'res_id': wizard_2fa.id,
                'type': 'ir.actions.act_window',
                'target': 'new',
                'context': {'redirect_res_ids': self.ids}
            }

    @api.multi
    @actions_2fa.authenticate
    def auth_sign_bank_transaction(self):
        """
        2FA auth method //
        Decorator checks whether passed OTP code is correct
        code is authenticated with real time checker
        if it is correct - proceed with bank transaction signing.
        :return: sign_transaction method instance result
        """
        self.ensure_one()

        # Fetch model and method name for signing
        model_name, method_name = self.env['api.bank.integrations'].get_bank_method(
            self.journal_id, m_type='sign_transaction')
        method_instance = getattr(self.env[model_name], method_name)
        # Signing method must always expect singleton bank.export.job record
        return method_instance(self)

    @api.multi
    def create_bank_export_jobs(self, data):
        """
        Create bank.export.job records from records that are being exported to bank
        Group payable lines into a dictionary that is not wizard bound
        (used if export_type is not sepa_xml)
        :param data: Dictionary with needed values, structure is the following:
            - parent_lines:
            either account.bank.statement.line, front.bank.statement.line or invoice.export.line (records)
            - export_type: sepa_xml or api (str)
            - journal: journal that payment is being exported from (record)
            - origin: pseudo-model from which the method was called (str)
            - xml_file_download: Indicates whether current action sends the payment directly to bank (Bool/None)
            or whether it was used to manually export the XML file
        :return: bank.export.job records
        """

        # Check if current batch is group transfer
        group_transfer = self._context.get('group_transfer')

        # Get the required fields
        parent_lines = data.get('parent_lines')
        export_type = data.get('export_type')
        journal = data.get('journal')
        file_data = data.get('xml_file_data')

        # Check if all required fields are passed
        if not parent_lines or not export_type or not journal:
            raise exceptions.ValidationError(
                _('Nepavyko sukurti bankinio eksporto. Nepaduotos visos reikalingos reikšmės.')
            )
        # Get other, non-required fields
        origin = data.get('origin', 'account.invoice.export.wizard')
        xml_file_download = data.get('xml_file_download')

        # If we just export an XML file there's no bank action
        export_state = 'file_export' if xml_file_download else 'waiting'
        st_export = origin in ['front.bank.statement', 'account.bank.statement']
        # Prepare grouped values to return if export_type is not SEPA XML
        batch_exports = self.env['bank.export.job']
        date_exported = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

        # Loop through lines and create exports
        for line in parent_lines:
            # Front statement has it's columns backwards...
            # Can't change them quickly since they impact lot's of places
            # so this is more of a hotfix, might be improved in the future
            tr_name = line.ref if st_export else line.name
            tr_ref = line.name if st_export else line.ref
            # Prepare the values
            vals = {
                'export_state': export_state,
                'partner_id': self.env.user.partner_id.id,
                'date_exported': date_exported,
                'journal_id': journal.id,
                'post_export_residual': line.post_export_residual if hasattr(line, 'post_export_residual') else 0,
                'tr_name': tr_name,
                'tr_ref': tr_ref,
                'tr_amount': line.amount,
                'tr_date': line.date,
                'tr_partner_id': line.partner_id.id,
                'tr_currency_id': line.currency_id.id,
                'tr_bank_account_id': line.bank_account_id.id,
                'tr_account_id': line.account_id.id,
                'tr_structured': line.info_type == 'structured',
                'group_payment_export': self._context.get('group_transfer'),
                'xml_file_download': xml_file_download,
            }
            # If export type is SEPA, calculate composite instruction ID from the
            # account.bank.statement.line record
            if export_type == 'sepa_xml':
                composite_instr_id = self.calculate_composite_instruction_id(line)
                vals['sepa_instruction_id'] = composite_instr_id

            # Export wizard origin can either be exporting
            # account invoice records and/or account move line records
            if origin == 'account.invoice.export.wizard':
                export_data_type = 'move_lines'
                if line.invoice_ids:
                    vals['invoice_ids'] = [(4, x.id) for x in line.invoice_ids]
                    export_data_type = 'invoices'
                if line.aml_ids:
                    vals['move_line_ids'] = [(4, x.id) for x in line.aml_ids]
            elif origin == 'front.bank.statement':
                vals['front_statement_line_id'] = line.id
                export_data_type = 'front_statement'
            else:
                vals['bank_statement_line_id'] = line.id
                export_data_type = 'bank_statement'

            # Create the export job
            vals['export_data_type'] = export_data_type
            export_job = self.sudo().with_context(sepa_export=True).create(vals)
            batch_exports |= export_job

        # Create batch record and store the file
        if file_data and export_type == 'sepa_xml' and not xml_file_download:
            self.env['bank.export.job.batch'].sudo().create({
                'date_exported': date_exported,
                'xml_file_data': file_data,
                'group_transfer': group_transfer,
                'bank_export_job_ids': [(4, export.id) for export in batch_exports],
            })
        return batch_exports

    @api.model
    def create_e_invoice_export_job(self, data, export_type='e_invoice'):
        """
        Create bank export record for eInvoice or automatic eInvoice payment that is being exported.
        :param data: dict of data required to create eInvoice exports (dict)
        :param export_type: for now only two types are expected
                           'e_invoice' and 'e_invoice_auto_payment' (str)
        :return: bank.export.job records
        """

        # eInvoice exportable objects
        invoice = data.get('invoice')
        partner = data.get('partner')

        journal = data.get('journal')
        file_export_data = data.get('export_data', {})
        # Export data and journal must always be passed
        if (export_type != 'automatic_e_invoice_payment' and
            (not file_export_data or not journal or (not invoice and not partner))) or\
                (export_type == 'automatic_e_invoice_payment' and not partner):
            raise exceptions.ValidationError(_('Nepaduoti reikiami eSąskaitų eksporto duomenys!'))

        vals = {
            'export_state': 'waiting',
            'partner_id': self.env.user.partner_id.id,
            'date_exported': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            'journal_id': journal and journal.id or False,
            'export_data_type': export_type,
            'e_invoice_file_id': file_export_data.get('file_id'),
            'e_invoice_global_unique_id': data.get('global_unique_id'),
        }

        if partner:
            vals.update({
                'e_invoice_auto_payment_partner_id': partner.id,
                'tr_name': partner.name,
            })
        if invoice:
            vals.update({
                'invoice_ids': [(4, invoice.id)],
                'tr_name': invoice.number,
            })

        bank_export = self.sudo().with_context(sepa_export=True).create(vals)

        # Create export job batch if type is eInvoice
        if export_type == 'e_invoice':
            self.env['bank.export.job.batch'].sudo().create({
                'xml_file_data': file_export_data.get('payload_xml'),
                'xml_file_name': file_export_data.get('payload_filename'),
                'request_xml_file_data': file_export_data.get('req_xml'),
                'request_xml_file_name': file_export_data.get('req_filename'),
                'bank_export_job_ids': [(4, bank_export.id)],
                'date_exported': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            })

    @api.multi
    def check_live_export_state(self):
        """
        Checks live export state in the bank,
        used in following scenario:
        1. User exports the statement
        2. Bank receives the statement and returns success code
        3. We mark it as exported, but then user cancels
           the statement in their bank profile
        4. Later user wants to export it again, but they he can't
           because state in our system does not match the state
           in the bank.
        Method is only called on export action
        :return: None
        """

        # Only valid for bank integrations that provide end-to-end ID
        for rec in self.filtered(lambda x: x.api_external_id):
            allow_checking = self.env['api.bank.integrations'].allow_live_export_state_checking(rec.journal_id)
            if allow_checking:
                # Fetch model and method name for checking
                model_name, method_name = self.env['api.bank.integrations'].get_bank_method(
                    rec.journal_id, m_type='check_live_tr_state')
                method_instance = getattr(self.env[model_name], method_name)
                # Signing method must always expect singleton bank.export.job record
                method_instance(rec)

    # SEPA Instruction ID calculators ---------------------------------------------------------------------------------

    @api.model
    def get_next_sepa_code(self):
        """Get unused sepa instruction sequence number"""
        res = get_int_hash(self.env['ir.sequence'].next_by_code('SEPAINSTRID'))
        while (self.env['account.bank.statement.line'].sudo().search([('sepa_instruction_id', '=', res)])
               or self.env['front.bank.statement.line'].sudo().search([('sepa_instruction_id', '=', res)])
               or self.env['account.move.line'].sudo().search([('sepa_instruction_id', '=', res)])
               or self.env['account.invoice'].sudo().search([('sepa_instruction_id', '=', res)])):
            res = get_int_hash(self.env['ir.sequence'].next_by_code('SEPAINSTRID'))
        return res

    @api.model
    def calculate_composite_instruction_id(self, statement_line):
        """
        Calculate composite sepa_instruction_id value.
            -If bank.statement.line does not have base instruction ID, get it from the sequence,
        and calculate the ID based on the base value and the amount that is being exported.

            -If bank.statement.line has related invoices use composite base ID hash from
        invoice instruction IDs, and assign it to the statement line.
        :param statement_line: account.bank.statement.line record
        :return: composite_instruction_id hash (str)
        """
        amount_hash = get_int_hash(int(statement_line.amount))
        if not statement_line.sepa_instruction_id:
            composite_instr_id = str()
            for invoice in statement_line.invoice_ids:
                if not invoice.sepa_instruction_id:
                    invoice.sudo().sepa_instruction_id = self.get_next_sepa_code()
                composite_instr_id += invoice.sepa_instruction_id
            for move_line in statement_line.aml_ids:
                if not move_line.sepa_instruction_id:
                    move_line.sudo().with_context(
                        check_move_validity=False).sepa_instruction_id = self.get_next_sepa_code()
                composite_instr_id += move_line.sepa_instruction_id
            if composite_instr_id:
                statement_line.sepa_instruction_id = get_int_hash(composite_instr_id)
            else:
                statement_line.sepa_instruction_id = self.get_next_sepa_code()
        composite_instruction_id = get_int_hash(
            '{}{}'.format(statement_line.sepa_instruction_id, amount_hash))
        return composite_instruction_id
