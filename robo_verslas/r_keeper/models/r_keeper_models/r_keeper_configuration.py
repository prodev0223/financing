# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class RKeeperConfiguration(models.Model):
    _name = 'r.keeper.configuration'
    _description = '''
    Model that stores various rKeeper settings
    '''

    # Accounting fields
    accounting_threshold_date = fields.Date(string='Apskaitos pradžios data')
    cron_job_creation_interval = fields.Selection(
        [('weekly', 'Savaitinis'),
         ('daily', 'Dieninis')
         ], string='Sąskaitų kūrimo intervalas', default='daily'
    )
    cron_job_creation_weekday = fields.Selection(
        [(1, 'Pirmadienis'),
         (2, 'Antradienis'),
         (3, 'Trečiadienis'),
         (4, 'Ketvirtadienis'),
         (5, 'Penktadienis'),
         (6, 'Šeštadienis')
         ], string='Savaitės diena'
    )

    # Manufacturing fields
    enable_automatic_sale_manufacturing = fields.Boolean(
        string='Įgalinti automatinę parduotų produktų gamybą'
    )
    automatic_sale_manufacturing_mode = fields.Selection(
        [('always_produce', 'Visada gaminti pardavimų produktus'),
         ('produce_no_stock', 'Gaminti tik tada kai trūksta atsargų')],
        string='Automatinės gamybos tipas', default='always_produce'
    )
    automatic_surplus_manufacturing_mode = fields.Selection(
        [('produce_surplus', 'Neužtekus atsargų gaminti su pertėkliumi'),
         ('do_not_produce', 'Negaminti su pertėkliumi')],
        string='Automatinis pertėklinės gamybos tipas', default='do_not_produce'
    )
    manufacturing_surplus_enabled = fields.Boolean(
        compute='_compute_manufacturing_surplus_enabled'
    )
    auto_surplus_skip_uom_id = fields.Many2one(
        'product.uom', string='Praleidžiami vienetai (perteklinė gamyba)'
    )
    # Other fields
    integration_configured = fields.Boolean(
        string='Integracija sukonfigūruota',
        compute='_compute_integration_configured'
    )
    enable_pos_product_filtering = fields.Boolean(
        string='Filtruoti kasos produktus',
        help='Pažymėjus, kasos produktai bus filtruojami gamybos ir važtaraščių dokumentuose',
        inverse='_set_enable_pos_product_filtering'
    )

    split_resources_between_new_production_creation_and_reservation = fields.Boolean(
        string='Kurti naujus gamybos įrašus paskirstant resursus tarp gamybų laukiančių rezervavimo'
    )

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    def _set_enable_pos_product_filtering(self):
        """
        Method that resets filtered POS products and categories
        if functionality is deactivated globally.
        :return: None
        """
        for rec in self:
            if not rec.enable_pos_product_filtering:
                products = self.env['product.product'].search([('r_keeper_pos_filter', '=', True)])
                products.write({'r_keeper_pos_filter': False})
                categories = self.env['product.category'].search([('r_keeper_pos_category', '=', True)])
                categories.write({'r_keeper_pos_category': False})

    @api.multi
    def _compute_manufacturing_surplus_enabled(self):
        """
        Checks if surplus production is activated in the
        company and shows the rKeeper surplus mode selection
        field if it is
        :return: None
        """
        surplus_enabled = self.sudo().env.user.company_id.enable_production_surplus
        for rec in self:
            rec.manufacturing_surplus_enabled = surplus_enabled

    @api.multi
    @api.depends('accounting_threshold_date', 'cron_job_creation_interval')
    def _compute_integration_configured(self):
        """
        Compute //
        Check whether rKeeper integration is configured
        :return: None
        """
        # Get the connection parameters, and check if they're set
        connection_parameters = self.sudo().env['r.keeper.ssh.connector'].get_r_keeper_connection_parameters()
        configured = all(value for key, value in connection_parameters.items())

        for rec in self:
            rec.integration_configured = \
                rec.accounting_threshold_date and rec.cron_job_creation_interval and configured

    # Main Methods ----------------------------------------------------------------------------------------------------

    @api.model_cr
    def init(self):
        """
        Automatically set duplicate product code
        prevention when rKeeper module is installed
        :return: None
        """
        if not self.env.user.company_id.prevent_duplicate_product_code:
            self.env.user.company_id.write({'prevent_duplicate_product_code': True})

    @api.model
    def initiate_configuration(self):
        """
        Initiate rKeeper configuration record.
        If settings record exists, return it.
        :return: rKeeper configuration record
        """
        configuration = self.get_configuration(raise_exception=False)
        if not configuration:
            configuration = self.create({})
        return configuration

    @api.model
    def get_configuration(self, raise_exception=True):
        """Return rKeeper configuration record"""
        configuration = self.env['r.keeper.configuration'].search([])
        if not configuration and raise_exception:
            raise exceptions.ValidationError(_('Nerastas rKeeper konfigūracijos įrašas!'))
        return configuration

    @api.model
    def check_r_keeper_configuration(self, partial_check=False):
        """
        Check rKeeper configuration creation day. If creation interval is weekly and current weekday
        is not the selected day, then deny the creation, otherwise allow.
        :return: True if creation should be allowed, otherwise False
        """
        # If integration is not configured, do not allow the creation
        configuration = self.get_configuration()
        if not configuration.integration_configured:
            return False

        # If check is not partial, also check creation weekday
        if not partial_check:
            weekday = configuration.cron_job_creation_weekday
            if configuration.cron_job_creation_interval == 'weekly' and isinstance(weekday, int) and \
                    datetime.utcnow().weekday() != weekday - 1:
                return False
        return True

    # CRUD Methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def create(self, vals):
        """
        Create method override, if settings record already exists,
        do not allow to create another instance
        :param vals: record values
        :return: super of create method
        """
        if self.search_count([]):
            raise exceptions.ValidationError(_('Negalite sukurti kelių rKeeper konfigūracijos nustatymų!'))
        return super(RKeeperConfiguration, self).create(vals)

    # Utility Methods -------------------------------------------------------------------------------------------------

    @api.multi
    def name_get(self):
        return [(rec.id, _('rKeeper konfigūracija')) for rec in self]
