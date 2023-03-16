# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _
from odoo.addons.base_iban.models.res_partner_bank import validate_iban
from odoo.addons.sepa import api_bank_integrations as abi


class FrontBankStatements(models.Model):
    _name = 'front.bank.statement'
    _inherit = ['mail.thread', 'bank.export.base', 'exportable.bank.statement']
    _order = 'date desc, name'

    @api.model
    def _default_company_id(self):
        """Get default company_id"""
        return self.env.user.sudo().company_id.id

    charge_bearer = [
        ('CRED', 'moka gavejas'),
        ('DEBT', 'moka moketojas'),
        ('SHAR', 'mokėtojo banko mokesčius moka mokėtojas, gavėjo banko – gavėjas'),
    ]

    statement_id = fields.Many2one(
        'account.bank.statement', string='Bankinis išrašas', required=False,
        readonly=True, ondelete="set null"
    )
    name = fields.Char(string='Pavadinimas', store=True)
    journal_id = fields.Many2one('account.journal', string='Bankas', store=True)
    date = fields.Date(string='Sukūrimo data', store=True)
    state = fields.Selection(
        [('new', 'Naujas'), ('viewed', 'Peržiūrėtas')],
        string='Būsena', default='new', readonly=True, copy=False
    )
    line_ids = fields.One2many('front.bank.statement.line', 'statement_id', string='Eilutės', copy=True)
    amount = fields.Monetary(string='Suma', compute='_compute_amount')
    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id')
    show_sala = fields.Boolean(string='Rodyti grupinį eksportą', compute='_compute_show_sala')
    informed = fields.Boolean(string='Informuotas vadovas', readonly=True, copy=False)
    company_id = fields.Many2one(
        'res.company', string='Company',
        required=True, lt_string='Kompanija',
        default=_default_company_id
    )
    kas_sumoka = fields.Selection(charge_bearer, string='Banko mokesčių mokėtojas')
    active = fields.Boolean(string='Aktyvus', default=True, track_visibility='onchange')

    non_iban_account_warning = fields.Text(compute='_compute_non_iban_account_warning')
    show_non_iban_account_warning = fields.Boolean(compute='_compute_non_iban_account_warning')
    sepa_imported = fields.Boolean(compute='_compute_sepa_imported')

    has_international_lines = fields.Boolean(compute='_compute_has_international_lines')
    international_priority = fields.Selection([
        ('SDVA', 'Šiandieninis'), ('URGP', 'Skubus'), ('NURG', 'Neskubus')],
        string='Tarptautinių mokėjimų prioritetas', default='NURG'
    )
    allow_exporting = fields.Boolean(compute='_compute_allow_exporting')
    show_non_structured_warning = fields.Boolean(compute='_compute_show_non_structured_warning')

    # Computes / Inverses --------------------------------------------------------------------------------------

    @api.multi
    @api.depends('line_ids.info_type', 'line_ids.partner_id')
    def _compute_show_non_structured_warning(self):
        """Check whether warning about non structured references should be displayed"""
        partners = self.env['res.partner'].search([
            ('kodas', 'in', self.get_structured_reference_partner_codes())
        ])
        for rec in self:
            if any(x.partner_id in partners and x.info_type != 'structured' for x in rec.line_ids):
                rec.show_non_structured_warning = True

    @api.multi
    @api.depends('journal_id')
    def _compute_allow_exporting(self):
        """Checks whether front statement can be exported as SEPA XML"""
        for rec in self:
            rec.allow_exporting = rec.journal_id.import_file_type == 'sepa'

    @api.multi
    @api.depends('line_ids.bank_account_id.acc_number', 'journal_id.bank_acc_number')
    def _compute_has_international_lines(self):
        """
        Check whether statement has any international lines
        :return: None
        """
        # is_international is compute itself, thus dependencies on this method
        # are dotted fields and not is_international field itself
        for rec in self:
            rec.has_international_lines = any(x.is_international for x in rec.line_ids)

    @api.multi
    @api.depends('statement_id.sepa_imported')
    def _compute_sepa_imported(self):
        """Compute whether line is sepa_imported based on parent statement"""
        # Crucial to add it here, so api.depends does not crash
        # on front statement line, because of weird dependencies
        for rec in self:
            rec.sepa_imported = rec.statement_id.sepa_imported

    @api.multi
    @api.depends('line_ids', 'line_ids.bank_account_id.acc_number')
    def _compute_non_iban_account_warning(self):
        """
        Compute //
        Check whether statement lines contain any bank accounts that are not IBAN format.
        If so - display warning message to the user, because we cannot tell whether bank account
        number was unintentionally mistyped or if it was meant not to be an IBAN number.
        :return:  None
        """
        for rec in self:
            warning = str()
            for line in rec.line_ids:
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
    @api.depends('line_ids.partner_id')
    def _compute_show_sala(self):
        """Check whether group export button should be shown to the user"""
        for rec in self:
            # Iterable needs to be checked before all(), because it returns True on empty-set
            rec.show_sala = rec.line_ids and all(rec.line_ids.sudo().mapped('partner_id.is_employee'))

    @api.multi
    def _compute_currency_id(self):
        """Set default currency to company currency"""
        company_currency = self.env.user.sudo().company_id.currency_id.id
        for rec in self:
            rec.currency_id = company_currency

    @api.multi
    @api.depends('line_ids.amount')
    def _compute_amount(self):
        """Compute total amount of all of the lines"""
        for rec in self:
            rec.amount = sum(rec.sudo().line_ids.mapped('amount'))

    @api.multi
    @api.constrains('journal_id')
    def _check_journal_id(self):
        """
        Constraints //
        If journal_id is being changed, and some lines are already
        exported -- do not allow the change to take place
        :return: None
        """
        for rec in self:
            if any(x.bank_export_state not in ['no_action', 'rejected', 'file_export'] for x in rec.line_ids):
                raise exceptions.ValidationError(
                    _('Negalite keisti banko sąskaitos šiam išrašui - bent viena eilutė buvo eksportuota į banką')
                )

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        """On journal change, get default preferred banks for partners where it's not set"""
        if self.journal_id:
            for line in self.line_ids.filtered(lambda x: x.partner_id and not x.bank_account_id):
                line.bank_account_id = line.partner_id.get_preferred_bank(self.journal_id)

    # CRUD methods -----------------------------------------------------------------------------------------------

    @api.multi
    def unlink(self):
        """If user is not an accountant just archive the bank statement"""
        if self.env.user.is_accountant():
            return super(FrontBankStatements, self).unlink()
        self.write({'active': False})

    # Main methods ----------------------------------------------------------------------------------------------

    @api.multi
    def inform(self):
        """Inform partners about newly created front bank statement"""
        self.ensure_one()
        # If there's no mail channel partners -- nothing to inform
        partners = self.get_bank_mail_channel_partners()
        if not partners:
            return
        msg = {
            'body': _('Informuojame, kad platformoje paruoštas naujas mokėjimo ruošinys "%s".') % self.name,
            'subject': _('Paruoštas naujas mokėjimo ruošinys'),
            'priority': 'high',
            'front_message': True,
            'rec_model': 'front.bank.statement',
            'rec_id': self.id,
            'view_id': self.env.ref('robo.robo_payments_report_form_view').id,
            'partner_ids': partners.ids,
            'robo_chat': True,
            'client_message': True,
            'message_type': 'notification',
            'robo_message_post': True,
        }
        self.robo_message_post(**msg)
        self.informed = True
        if self.statement_id:
            self.statement_id.informed = True

    # Action methods --------------------------------------------------------------------------------------------------

    @api.multi
    def action_copy(self):
        """
        Copy the current record and return the JS
        action to the newly created records' form view
        :return: JS action (dict)
        """
        self.ensure_one()
        res = self.copy()
        return {
            'name': _('Mokėjimų ruošiniai'),
            'view_mode': 'form',
            'view_id': self.env.ref('robo.robo_payments_report_form_view').id,
            'view_type': 'form',
            'res_model': 'front.bank.statement',
            'res_id': res.id,
            'type': 'ir.actions.act_window',
            'context': dict(self._context),
            'flags': {'initial_mode': 'edit'},
        }

    @api.multi
    def action_front_bank_statement_merge_wizard(self):
        """
        Validate the records and create the wizard
        for front bank statement merging.
        :return: JS action (dict)
        """
        # Check the constraints
        if len(self) < 2:
            raise exceptions.ValidationError(_('Privalote pasirinkti bent du įrašus!'))
        if len(self.mapped('journal_id')) != 1:
            raise exceptions.ValidationError(_('Negalite apjungti skirtingų bankų mokėjimų!'))

        # Create the wizard record
        wizard = self.env['front.bank.statement.merge.wizard'].create({
            'front_statement_ids': [(4, statement.id) for statement in self],
            'destination_statement_id': self[0].id,
        })
        # Update the context
        context = self._context.copy()
        context.update({'detailed_name_get': True})
        # Return the action
        return {
            'name': _('Mokėjimo ruošinių apjungimas'),
            'type': 'ir.actions.act_window',
            'res_model': 'front.bank.statement.merge.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
            'res_id': wizard.id,
            'context': context,
            'view_id': self.env.ref('robo.form_front_bank_statement_merge_wizard').id,
        }

    @api.model
    def create_action_front_bank_statement_merge_wizard(self):
        """Creates action for multi statement merging wizard"""
        action = self.env.ref('robo.action_front_bank_statement_merge_wizard')
        if action:
            action.create_action()

    # Utility methods -------------------------------------------------------------------------------------------------

    @api.multi
    def name_get(self):
        """Add detailed name get based on the context"""
        if self._context.get('detailed_name_get'):
            return [(rec.id, '{} | {} | {}'.format(rec.name, rec.date, rec.amount)) for rec in self]
        return super(FrontBankStatements, self).name_get()

    # Bank Related Methods --------------------------------------------------------------------------------------------

    @api.multi
    def download(self):
        """Method that is used to download SEPA XML file"""
        self.ensure_one()
        # Write the state and mark objects as exported
        self.write({'state': 'viewed'})
        self.line_ids.mark_related_objects_as_exported()
        return self.export_sepa_attachment_download(
            self.get_bank_export_data(self.line_ids)
        )

    @api.multi
    def send_to_bank_validator(self):
        """
        Validate invoice data that is being send to bank
        by checking base wizard data (exportable states, partial payment)
        raises the error on constraint violation.
        :return: None
        """
        super(FrontBankStatements, self).send_to_bank_validator()
        for rec in self:
            # Check live export states for each of the exported jobs
            rec.mapped('line_ids.bank_export_job_ids').check_live_export_state()

            # Do not allow the export if at least one line is in 'waiting' state
            if any(line.bank_export_state == 'waiting' for line in rec.line_ids):
                raise exceptions.ValidationError(
                    _('Negalite eksportuoti ruošinio jeigu bent viena eilutei nebuvo grąžintas atsakymas iš banko'))

            if rec.bank_export_state and rec.bank_export_state not in abi.EXPORTABLE_STATES:
                state = str(dict(rec._fields['bank_export_state']._description_selection(self.env)).get(
                    rec.bank_export_state))
                raise exceptions.ValidationError(
                    "Mokėjimo ruošinys turi netinkamą banko eksportavimo būseną - '%s'. "
                    "Eksportas galimas tik šiose būsenose - 'Neeksportuota', 'Atmesta'\n" % state)

    @api.multi
    def send_to_bank(self):
        """
        Method that is used to send front bank statement data to bank.
        Validates the data-to-be send, determines what integration is used
        (SEPA or API, only those two at the moment), groups data
        accordingly, calls the method that is the initiator of
        bank statement export for specific journal.
        :return: result of export method for specific journal
        """
        self.ensure_one()
        self.write({'state': 'viewed'})
        return self.send_to_bank_base(self.get_bank_export_data(self.line_ids))
