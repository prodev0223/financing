# -*- encoding: utf-8 -*-
from datetime import datetime
from odoo import models, fields, api, exceptions, tools, _
from dateutil.relativedelta import relativedelta

MAX_ROUNDING_ERROR_ALLOWED = 1.0


class RoboCompanySettings(models.TransientModel):
    """
    Robo API extension to robo.company.settings
    """
    _inherit = 'robo.company.settings'

    api_secret = fields.Char(string='API raktas', readonly=True, groups='robo_basic.group_robo_premium_manager')
    api_allow_new_products = fields.Boolean(string='Leisti per API kurti produktus',
                                            groups='robo_basic.group_robo_premium_accountant', default=True)
    api_allow_empty_partner_code = fields.Boolean(string='Leisti per API paduoti tuščią partnerio kodą',
                                                  groups='robo_basic.group_robo_premium_accountant', default=False)
    api_allow_rounding_error = fields.Boolean(string='Leisti kurti sąskaitas su apvalinimo paklaida',
                                              groups='robo_basic.group_robo_premium_accountant')
    api_max_rounding_error_allowed = fields.Float(string='Maksimali leidžiama apvalinimo paklaida',
                                                  groups='robo_basic.group_robo_premium_accountant', default=0.01)
    api_default_product_type = fields.Selection([('service', 'Paslauga'), ('cost', 'Parduotų prekių savikaina'),
                                                 ('product', 'Produktas')],
                                                groups='robo_basic.group_robo_premium_accountant',
                                                string='Per sąskaitų API kuriamų produktų tipas', default='cost')
    api_prestashop_integration = fields.Boolean(string='Aktyvuoti PrestaShop integraciją',
                                                groups='robo_basic.group_robo_premium_accountant')
    api_woocommerce_integration = fields.Boolean(string='Aktyvuoti WooCommerce integraciją',
                                                 groups='robo_basic.group_robo_premium_accountant')

    # Original field is only visible by accountant, however,
    # in form views we need to execute some checks with this field
    # and we want manager to be able to access it
    api_woocommerce_enabled = fields.Boolean(compute='_compute_api_woocommerce_enabled')

    # For now only used on Woocommerce: Forced API tax settings
    api_force_tax_id = fields.Many2one(
        'account.tax', string='Priverstiniai API kliento sąskaitų mokesčiai',
        domain="[('price_include', '=', True), ('type_tax_use', '=', 'sale')]"
    )
    api_force_tax_type = fields.Selection(
        [('price_include', 'Su PVM'),
         ('price_exclude', 'Be PVM')],
        string='eParduotuvės pateikiamos kainos', default='price_include'
    )
    api_force_tax_condition = fields.Selection(
        [('do_not_force', 'Netaikyti'),
         ('force_if_none', 'Taikyti jei nė viena eilutė neturi mokesčių'),
         ('force_on_gaps', 'Taikyti visose eilutėse')],
        string='API priverstinių mokesčių nustatymai', default='do_not_force'
    )
    api_force_tax_selection = fields.Selection(
        [('global', 'Globalus'),
         ('selective', 'Pasirenkamas')],
        string='API priverstinių mokesčių pasirinkimas', default='global'
    )
    api_force_tax_position = fields.One2many('robo.company.settings.api.force.tax.position', 'settings_id',
                                             string='Priverstiniai API kliento sąskaitų mokesčiai')
    show_prestashop_plugin = fields.Boolean(string='Rodyti PrestaShop įskiepį')
    show_woocommerce_plugin = fields.Boolean(string='Rodyti WooCommerce įskiepį')
    current_woocommerce_plugin_version = fields.Char(string='Dabartinė WooCommerce įskiepio versija', readonly=True)
    current_prestashop_plugin_version = fields.Char(string='Dabartinė PrestaShop įskiepio versija', readonly=True)
    # Threaded mode fields
    enable_threaded_api = fields.Boolean(string='Įgalinti foninį API importą')
    threaded_api_callback_url = fields.Char(string='Foninio API atsako URL')
    api_request_parsing_retries = fields.Integer(
        string='Pakartotinai apdoroti (kartai)', help='Pakartotinis nepavykusių užklausų apdorojimo skaičius')

    # Threaded API cron customisation
    api_execution_interval_number = fields.Integer(string='Intervalo numeris (kartoti kas)')
    api_execution_interval_type = fields.Selection(
        [('minutes', 'Minutės'),
         ('hours', 'Valandos'),
         ('work_days', 'Darbo dienos'),
         ('days', 'Dienos'),
         ('weeks', 'Savaitės'),
         ('months', 'Mėnesiai')], string='Intervalas')
    api_next_execution_call = fields.Datetime(string='Kito vykdymo data')
    api_create_payer_partners = fields.Boolean(string='Create payer partners',
                                               groups='robo_basic.group_robo_premium_accountant')

    @api.model
    def default_get(self, field_list):
        """
        Default get override -- get API field values from the company record
        :param field_list: current models' field list
        :return: default values
        """
        if not self.env.user.is_manager():
            return {}
        res = super(RoboCompanySettings, self).default_get(field_list)
        company = self.sudo().env.user.company_id
        api_cron = self.env.ref('robo_api.cron_execute_api_job', raise_if_not_found=False)

        force_tax_positions = []
        for position in self.env['robo.api.force.tax.position'].search([]):
            force_tax_positions.append((0, 0, {
                'name': position.name,
                'position_id': position.id,
                'country_id': position.country_id.id if position.country_id else False,
                'country_group_id': position.country_group_id.id if position.country_group_id else False,
                'not_country_id': position.not_country_id.id if position.not_country_id else False,
                'not_country_group_id': position.not_country_group_id.id if position.not_country_group_id else False,
                'force_tax_id': position.force_tax_id.id if position.force_tax_id else False,
                'force_tax_type': position.force_tax_type,
                'product_type': position.product_type,
                'partner_type': position.partner_type,
                'partner_vat_payer_type': position.partner_vat_payer_type,
                'date_from': position.date_from,
                'date_to': position.date_to,
            }))

        res.update({
            'api_secret': company.api_secret,
            'enable_threaded_api': company.enable_threaded_api,
            'threaded_api_callback_url': company.threaded_api_callback_url,
            'api_request_parsing_retries': company.api_request_parsing_retries,
            'show_prestashop_plugin': company.api_prestashop_integration,
            'show_woocommerce_plugin': company.api_woocommerce_integration,
            'current_woocommerce_plugin_version': company.current_woocommerce_plugin_version,
            'current_prestashop_plugin_version': company.current_prestashop_plugin_version,
            'api_woocommerce_integration': company.sudo().api_woocommerce_integration,
            'api_woocommerce_enabled': company.sudo().api_woocommerce_integration,
            'api_force_tax_condition': company.api_force_tax_condition,
            'api_force_tax_type': company.api_force_tax_type,
            'api_force_tax_id': company.api_force_tax_id.id,
            'api_force_tax_selection': company.api_force_tax_selection,
            'api_force_tax_position': force_tax_positions,
        })
        if api_cron:
            res.update({
                'api_execution_interval_number': api_cron.interval_number,
                'api_execution_interval_type': api_cron.interval_type,
                'api_next_execution_call': api_cron.nextcall,
            })

        if self.env.user.is_accountant():
            res.update({
                'api_allow_new_products': company.api_allow_new_products,
                'api_allow_empty_partner_code': company.api_allow_empty_partner_code,
                'api_prestashop_integration': company.api_prestashop_integration,
                'api_default_product_type': company.api_default_product_type,
                'api_allow_rounding_error': company.api_allow_rounding_error,
                'api_max_rounding_error_allowed': company.api_max_rounding_error_allowed,
                'api_create_payer_partners': company.api_create_payer_partners,
            })
        return res

    @api.multi
    def write_api_cron_dates(self):
        """
        Write time related changes to api cron-job record
        :return: None
        """
        self.ensure_one()
        api_job_execute_cron = self.sudo().env.ref('robo_api.cron_execute_api_job', raise_if_not_found=False)
        api_attach_invoice_documents_cron = self.sudo().env.ref('robo_api.cron_attach_invoice_documents',
                                                                raise_if_not_found=False)
        api_cron_values = {
                'interval_number': self.api_execution_interval_number,
                'interval_type': self.api_execution_interval_type,
                'nextcall': self.api_next_execution_call
            }
        if api_job_execute_cron:
            api_job_execute_cron.write(api_cron_values)
        if api_attach_invoice_documents_cron:
            # Run attaching invoice documents cron after executing all the waiting jobs
            next_call_dt = datetime.strptime(api_cron_values['nextcall'], tools.DEFAULT_SERVER_DATETIME_FORMAT) \
                if api_cron_values['nextcall'] else False
            if next_call_dt:
                api_cron_values['nextcall'] = (next_call_dt + relativedelta(minutes=30)).\
                    strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            api_attach_invoice_documents_cron.write(api_cron_values)

    @api.model
    def _get_company_info_field_list(self):
        res = super(RoboCompanySettings, self)._get_company_info_field_list()
        res.extend((
            'api_secret',
            'enable_threaded_api',
            'threaded_api_callback_url',
            'api_request_parsing_retries',
            'current_woocommerce_plugin_version',
            'current_prestashop_plugin_version',
            'api_force_tax_condition',
            'api_force_tax_type',
            'api_force_tax_id',
            'api_force_tax_selection',
        ))
        return res

    @api.model
    def _get_company_policy_field_list(self):
        res = super(RoboCompanySettings, self)._get_company_policy_field_list()
        res.extend((
            'api_allow_new_products',
            'api_allow_empty_partner_code',
            'api_prestashop_integration',
            'api_woocommerce_integration',
            'api_default_product_type',
            'api_allow_rounding_error',
            'api_max_rounding_error_allowed',
            'api_create_payer_partners',
        ))
        return res

    @api.multi
    def _compute_api_woocommerce_enabled(self):
        """
        Compute //
        Method is a dummy. Compute is not called until record
        is saved, in this case, wizard is not created
        thus we have to set it on default get
        :return: None
        """
        for rec in self:
            rec.api_woocommerce_enabled = rec.sudo().api_woocommerce_integration

    @api.onchange('api_woocommerce_integration')
    def _onchange_api_woocommerce_integration(self):
        if self.api_woocommerce_integration:
            self.prevent_empty_product_code = True
            self.prevent_duplicate_product_code = True

    @api.onchange('api_force_tax_type')
    def _onchange_api_force_tax_type(self):
        """
        Onchange //
        Reset the tax abd domain of api_force_tax_id based on
        forced tax type settings
        :return: JS readable domain (dict)
        """
        if self._context.get('trigger_tax_reset'):
            self.api_force_tax_id = None
        domain = [('price_include', '=', self.api_force_tax_type == 'price_include'), ('type_tax_use', '=', 'sale')]
        return {'domain': {'api_force_tax_id': domain}}

    @api.multi
    @api.constrains('api_force_tax_condition', 'api_force_tax_id', 'api_force_tax_type', 'api_force_tax_selection')
    def _check_api_force_tax_id(self):
        """
        Constraints //
        Check whether forced API tax record is set
        if forced condition is set, and check whether tax
        type corresponds to the selection field
        :return: None
        """
        for rec in self:
            if rec.api_force_tax_condition in ['force_if_none', 'force_on_gaps'] and not rec.api_force_tax_id \
                    and rec.api_force_tax_selection == 'global':
                raise exceptions.ValidationError(_('Privalote nurodyti priverstinį API mokestį.'))
            price_include = rec.api_force_tax_type == 'price_include'
            if rec.api_force_tax_id and rec.api_force_tax_id.price_include != price_include:
                raise exceptions.ValidationError(_('Pasirinktas netinkamas mokesčio tipas'))

    @api.multi
    @api.constrains('api_max_rounding_error_allowed')
    def _check_api_max_rounding_error_allowed(self):
        """
        Constraints //
        Check whether rounding error is is not exceeding maximum valid value
        :return: None
        """
        for rec in self:
            if rec.api_allow_rounding_error and tools.float_compare(rec.api_max_rounding_error_allowed,
                                                                    MAX_ROUNDING_ERROR_ALLOWED, precision_digits=2) > 0:
                raise exceptions.ValidationError(
                    _('Didžiausia galima apvalinimo paklaida negali būti didesnė, nei %s.') %
                    MAX_ROUNDING_ERROR_ALLOWED)

    @api.multi
    def set_default_api_force_tax_position(self):
        self.ensure_one()
        ForceTaxPosition = self.env['robo.api.force.tax.position']
        existing_positions = ForceTaxPosition.search([])
        positions_to_unlink = existing_positions.\
            filtered(lambda x: x.id not in self.api_force_tax_position.mapped('position_id').ids)
        positions_to_unlink.unlink()
        for position in self.api_force_tax_position:
            existing_position = position.position_id
            position_values = {
                'name': position.name,
                'country_id': position.country_id.id if position.country_id else False,
                'country_group_id': position.country_group_id.id if position.country_group_id else False,
                'not_country_id': position.not_country_id.id if position.not_country_id else False,
                'not_country_group_id': position.not_country_group_id.id if position.not_country_group_id else False,
                'force_tax_id': position.force_tax_id.id if position.force_tax_id else False,
                'force_tax_type': position.force_tax_type,
                'product_type': position.product_type,
                'partner_type': position.partner_type,
                'partner_vat_payer_type': position.partner_vat_payer_type,
                'date_from': position.date_from,
                'date_to': position.date_to,
            }
            if not existing_position:
                ForceTaxPosition.create(position_values)
            else:
                existing_position.write(position_values)

    @api.multi
    def execute(self):
        res = super(RoboCompanySettings, self).execute()
        self.set_default_api_force_tax_position()
        return res
