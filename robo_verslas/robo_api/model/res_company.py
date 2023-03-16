# -*- encoding: utf-8 -*-
import random
from odoo import models, fields, api, exceptions, _

API_FORCE_TAX_SELECTION = [('global', 'Globalus'), ('selective', 'Pasirenkamas')]


class ResCompany(models.Model):
    """
    Robo API extension to res.company
    """
    _inherit = 'res.company'

    api_secret = fields.Char(string='API raktas', groups='base.group_system')
    api_secret_gl = fields.Char(string='API raktas (apskaitos įrašams)', groups='base.group_system',
                                compute='_compute_api_secret_gl')
    api_allow_new_products = fields.Boolean(string='Leisti per sąskaitų API kurti produktus', default=True)
    api_allow_empty_partner_code = fields.Boolean(string='Leisti per API paduoti tuščią partnerio kodą', default=False)
    api_allow_rounding_error = fields.Boolean(string='Leisti kurti sąskaitas su apvalinimo paklaida',
                                              compute='_compute_api_allow_rounding_error',
                                              inverse='_set_api_allow_rounding_error')
    api_max_rounding_error_allowed = fields.Float(string='Maksimali leidžiama apvalinimo paklaida',
                                                  compute='_compute_api_max_rounding_error_allowed',
                                                  inverse='_set_api_max_rounding_error_allowed')
    api_default_product_type = fields.Selection([('service', 'Paslauga'), ('cost', 'Parduotų prekių savikaina'),
                                                 ('product', 'Produktas')],
                                                string='Per API kuriamų produktų tipas', default='cost')
    api_prestashop_integration = fields.Boolean(string='Aktyvuoti PrestaShop integraciją')
    api_woocommerce_integration = fields.Boolean(string='Aktyvuoti WooCommerce integraciją')
    current_woocommerce_plugin_version = fields.Char(string='Dabartinė WooCommerce įskiepio versija')
    current_prestashop_plugin_version = fields.Char(string='Dabartinė PrestaShop įskiepio versija')

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
        string='API priverstinių mokesčių nustatymai',
        inverse='_set_api_force_tax_condition'
    )
    api_force_tax_selection = fields.Selection(API_FORCE_TAX_SELECTION,
                                               string='API priverstinių mokesčių pasirinkimas',
                                               compute='_compute_api_force_tax_selection',
                                               inverse='_set_api_force_tax_selection')
    # Threaded mode fields
    enable_threaded_api = fields.Boolean(
        string='Įgalinti foninį API importą',
        groups='robo_basic.group_robo_premium_manager',
        inverse='_set_enable_threaded_api'
    )
    threaded_api_callback_url = fields.Char(
        string='Foninio API atsako URL', groups='robo_basic.group_robo_premium_manager')
    api_request_parsing_retries = fields.Integer(
        string='Pakartotinai apdoroti (kartai)', help='Pakartotinis nepavykusių užklausų apdorojimo skaičius')
    api_create_payer_partners = fields.Boolean(string='Kurti mokėtojų partnerius registruojant mokėjimus',
                                               compute='_compute_api_create_payer_partners',
                                               inverse='_set_api_create_payer_partners')

    @api.model_cr
    def init(self):
        """
        Generate API secret and create new products when robo_api module is installed
        :return: None
        """
        ProductProduct = self.env['product.product']
        chars = u'0123456789qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM'
        companies = self.env['res.company'].search([])
        for company in companies:
            if not company.api_secret:
                secret = ''.join(random.SystemRandom().choice(chars) for _ in xrange(40))
                company.api_secret = secret
            if not company.api_secret_gl:
                secret_gl = ''.join(random.SystemRandom().choice(chars) for _ in xrange(40))
                self.env['ir.config_parameter'].sudo().set_param('api_secret_gl', secret_gl, ['base.group_system'])

        category = self.env.ref('l10n_lt.product_category_2', raise_if_not_found=False)
        if not category:
            return

        base_values = {
            'categ_id': category.id,
            'type': 'service',
            'sale_ok': True,
            'acc_product_type': 'service',
            'robo_product': True,
        }
        if not ProductProduct.search_count([('default_code', '=', 'NL')]):
            discount_p_values = dict(base_values, **{
                'name': 'Nuolaida',
                'default_code': 'NL',
            })
            ProductProduct.create(discount_p_values)

        if not ProductProduct.search_count([('default_code', '=', 'DEL')]):
            delivery_p_values = dict(base_values, **{
                'name': 'Pristatymo paslauga',
                'default_code': 'DEL',
            })
            ProductProduct.create(delivery_p_values)

    @api.multi
    def _compute_api_force_tax_selection(self):
        self.ensure_one()
        force_tax_selection = self.env['ir.config_parameter'].sudo().get_param('api_force_tax_selection')
        self.api_force_tax_selection = force_tax_selection

    @api.multi
    def _set_api_force_tax_selection(self):
        self.ensure_one()
        if self.api_force_tax_selection in dict(API_FORCE_TAX_SELECTION).keys():
            self.env['ir.config_parameter'].sudo().set_param(
                'api_force_tax_selection', self.api_force_tax_selection
            )

    @api.multi
    def _compute_api_allow_rounding_error(self):
        self.ensure_one()
        self.api_allow_rounding_error = self.env['ir.config_parameter'].sudo().get_param(
            'api_allow_rounding_error') == 'True'

    @api.multi
    def _set_api_allow_rounding_error(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param('api_allow_rounding_error',
                                                         str(self.api_allow_rounding_error))

    @api.multi
    def _compute_api_max_rounding_error_allowed(self):
        self.ensure_one()
        self.api_max_rounding_error_allowed = float(self.env['ir.config_parameter'].sudo().get_param(
            'api_max_rounding_error_allowed', 0.01))

    @api.multi
    def _set_api_max_rounding_error_allowed(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param('api_max_rounding_error_allowed',
                                                         str(self.api_max_rounding_error_allowed))

    @api.multi
    def _compute_api_create_payer_partners(self):
        self.ensure_one()
        self.api_create_payer_partners = bool(
            self.env['ir.config_parameter'].sudo().get_param('api_create_payer_partners') == 'True'
        )

    @api.multi
    def _set_api_create_payer_partners(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param(
            'api_create_payer_partners', str(self.api_create_payer_partners)
        )

    @api.multi
    def _compute_api_secret_gl(self):
        self.ensure_one()
        self.api_secret_gl = self.env['ir.config_parameter'].sudo().get_param('api_secret_gl')

    @api.multi
    def _set_api_force_tax_condition(self):
        """
        Inverse //
        Reset forced API taxes if condition is not set
        or set to do_not_force
        :return: None
        """
        for rec in self:
            if not rec.api_force_tax_condition or rec.api_force_tax_condition == 'do_not_force' or \
                    rec.api_force_tax_selection == 'selective':
                rec.api_force_tax_id = False

    @api.multi
    def _set_enable_threaded_api(self):
        """
        Inverse //
        Add or remove special threaded API group that let's users see the menu if threaded reports are activated
        :return: None
        """
        threaded_group = self.env.ref('robo_api.group_robo_threaded_api')
        manager_group = self.env.ref('robo_basic.group_robo_premium_manager')
        for rec in self:
            if rec.enable_threaded_api:
                manager_group.sudo().write({
                    'implied_ids': [(4, threaded_group.id)]
                })
            else:
                manager_group.sudo().write({
                    'implied_ids': [(3, threaded_group.id)]
                })
                threaded_group.write({'users': [(5,)]})

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
            if rec.api_force_tax_condition in ['force_if_none', 'force_on_gaps'] and not rec.api_force_tax_id and \
                    rec.api_force_tax_selection == 'global':
                raise exceptions.ValidationError(_('Privalote nurodyti priverstinį API mokestį.'))
            price_include = rec.api_force_tax_type == 'price_include'
            if rec.api_force_tax_id and rec.api_force_tax_id.price_include != price_include:
                raise exceptions.ValidationError(_('Pasirinktas netinkamas mokesčio tipas'))


ResCompany()
