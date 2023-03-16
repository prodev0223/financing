
# -*- encoding: utf-8 -*-
from odoo import fields, models, _, api, exceptions, tools
from datetime import datetime
from six import iteritems


class PayseraWallet(models.Model):
    _name = 'paysera.wallet'

    paysera_configuration_id = fields.Many2one('paysera.configuration')
    wallet_id = fields.Integer(string='External wallet ID')
    paysera_account_number = fields.Char(string='Paysera account number')
    iban_account_number = fields.Char(string='Main wallet IBAN number')
    ext_active = fields.Boolean(string='Active (External system)', default=True)

    # Owner information
    ext_user_id = fields.Integer(string='External user ID')
    user_type = fields.Selection([('natural', 'Person'),
                                  ('legal', 'Legal entity')], string='User type')
    user_name = fields.Char(string='User name')
    user_code = fields.Char(string='User code')

    # List of IBANs that belong to specific wallet
    paysera_wallet_iban_ids = fields.One2many(
        'paysera.wallet.iban', 'paysera_wallet_id', string='Related bank accounts')
    state = fields.Selection([('non_configured', 'Disabled (Not-configured)'),
                              ('configuration_error', 'Configuration error'),
                              ('configured', 'Configured')],
                             string='Wallet state', default='non_configured', inverse='_set_state')
    error_message = fields.Char(string='Error message')

    # Did not use field 'active' because it has some base related functionality
    activated = fields.Boolean(string='Active (Robo)', inverse='_set_activated', default=True)
    paysera_wallet_iban_display = fields.Char(string='Related bank accounts',
                                              compute='_compute_paysera_wallet_iban_display')

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    def _set_state(self):
        """
        Inverse //
        On state change, recompute related journal
        integration status
        :return: None
        """
        for rec in self:
            journals = rec.paysera_wallet_iban_ids.mapped('journal_id')
            journals._compute_api_integrated_bank()

    @api.multi
    def _set_activated(self):
        """
        Inverse //
        On wallet deactivation clear the state
        and error message.
        :return: None
        """
        for rec in self:
            journals = rec.paysera_wallet_iban_ids.mapped('journal_id')
            if not rec.activated:
                rec.state = 'non_configured'
                rec.error_message = str()
                journals.write({'active': False})
            else:
                journals.write({'active': True})

    @api.multi
    @api.depends('paysera_wallet_iban_ids')
    def _compute_paysera_wallet_iban_display(self):
        """
        Compute //
        Compute a display string using paysera_wallet_iban_ids
        :return: None
        """
        for rec in self:
            rec.paysera_wallet_iban_display = ' / '.join(['{} ({})'.format(
                x.iban, x.currency_id.name or 'EUR') for x in rec.paysera_wallet_iban_ids])

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def button_toggle_activated(self):
        """
        Method to either deactivate
        or activate the wallet
        :return: None
        """
        for rec in self:
            rec.activated = not rec.activated

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(x.id, _('Paysera wallet #%s') % x.wallet_id) for x in self]

    @api.model
    def get_wallets(self, fully_functional=False):
        """
        Method that returns configured and active Paysera wallets
        :param fully_functional: If checked to True, extends domain to fetch wallets
            that have configured journals as well.
        :return: paysera.wallet recordset
        """
        domain = [('ext_active', '=', True), ('state', '=', 'configured'), ('activated', '=', True)]
        if fully_functional:
            domain += [('paysera_wallet_iban_ids.journal_id', '!=', False)]
        return self.search(domain)

    @api.model
    def get_related_wallet(self, journal, raise_exception=True):
        """
        Method that gets related paysera.wallet record
        based on passed account.journal record
        :param journal: account.journal record
        :param raise_exception: indicates whether exception should be raised
        :return: paysera.wallet record
        """

        # Try to find related wallet of the journal
        related_wallet = self.env['paysera.wallet.iban'].search(
            [('journal_id', '=', journal.id),
             ('paysera_wallet_id.state', '=', 'configured'),
             ('paysera_wallet_id.activated', '=', True)], limit=1).paysera_wallet_id
        if not related_wallet and raise_exception:
            raise exceptions.ValidationError(
                _('Paysera settings are not configured, '
                  'related wallet for this journal - "{}" was not found!').format(journal.name))
        return related_wallet

    @api.multi
    def distribute_end_balances(self, balance_data):
        """
        Method that distributes balances fetched from API
        to related IBANs of the wallet. If IBAN record does not
        exist yet, method creates it
        :param balance_data:
        :return: None
        """
        self.ensure_one()
        # Do this to not use filtered
        accounts_by_currency = {}
        for related_iban in self.paysera_wallet_iban_ids:
            accounts_by_currency.setdefault(related_iban.currency_id.id, related_iban)

        for currency, balances in iteritems(balance_data):
            related_iban = accounts_by_currency.get(currency.id)

            # Get balance amounts
            end_balance = balances.get('end_balance', 0)
            reserved_amount = balances.get('reserved_amount', 0)
            update_date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

            values = {
                'api_end_balance': end_balance,
                'api_reserved_amount': reserved_amount,
                'api_balance_update_date': update_date
            }

            # If related IBAN exists, write values to it
            # otherwise, create new IBAN record.
            if related_iban:
                related_iban.write(values)
            else:
                values.update({
                    'iban': self.iban_account_number,
                    'paysera_wallet_id': self.id,
                    'currency_id': currency.id,
                })
                self.env['paysera.wallet.iban'].create(values)

    # Cron-jobs -------------------------------------------------------------------------------------------------------

    @api.model
    def cron_inform_about_failed_wallets(self):
        """
        Cron-job
        Inform the user about failed wallets if any
        :return: None
        """

        # Get paysera configuration
        configuration = self.env['paysera.configuration'].search([])
        if not configuration or not configuration.initially_authenticated:
            return

        # If there are no failed wallets -- return
        failed_wallets = self.search_count(
            [('activated', '=', True), ('state', '!=', 'configured'), ('ext_active', '=', True)])
        if not failed_wallets:
            return

        # Otherwise prepare the message and post it to the user
        user = configuration.user_id or self.env.user.company_id.vadovas.user_id
        body = _('''
            Check Paysera wallet configuration - some wallets have received error messages from the Paysera API.
            Either the wallets require additional authentication or they are disabled in external system. 
            If latter is the case case, please go toPaysera configuration, open a specific wallet and click "Archive"
        ''')

        msg = {
            'body': body,
            'subject': _('Request to configure or deactivate Paysera wallets'),
            'priority': 'medium',
            'front_message': True,
            'rec_model': 'paysera.configuration',
            'rec_id': configuration.id,
            'partner_ids': user.partner_id.ids,
            'view_id': self.env.ref('sepa.form_paysera_configuration').id,
        }
        configuration.robo_message_post(**msg)


PayseraWallet()
