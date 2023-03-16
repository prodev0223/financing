# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _, tools
from .. import amazon_tools as at
from datetime import datetime
from odoo.api import Environment
import threading
import odoo


class AmazonConfigurationWizard(models.TransientModel):
    """
    Transient model/wizard that allows user to import Amazon XML files
    accepted types -- Amazon order/Amazon product. XML's are validated
    using XSD Schemas
    """
    _name = 'amazon.configuration.wizard'

    amazon_accounting_threshold_date = fields.Date(string='Amazon apskaitos pradžios data')
    amazon_creation_interval = fields.Selection(
        [('weekly', 'Savaitinis'), ('daily', 'Dieninis')], string='Sąskaitų kūrimo intervalas')
    amazon_creation_weekday = fields.Selection(
        [(1, 'Pirmadienis'), (2, 'Antradienis'), (3, 'Trečiadienis'),
         (4, 'Ketvirtadienis'), (5, 'Penktadienis'), (6, 'Šeštadienis')], string='Savaitės diena')

    amazon_marketplace_ids = fields.Many2many('amazon.marketplace', string='Amazon Prekiavietės')
    amazon_region_ids = fields.Many2many('amazon.region', string='Amazon Regionai')

    api_state = fields.Selection([('failed', 'konfigūracija nepavyko'),
                                  ('working', 'Veikiantis'),
                                  ('not_initiated', 'Nebandyta')],
                                 string='Būsena', compute='_compute_api_state')
    include_amazon_commission_fees = fields.Boolean(string='Traukti komisinį mokestį į Amazon sąskaitas')
    include_amazon_tax = fields.Boolean(string='Traukti papildomai pateikiamus PVM mokesčius į Amazon sąskaitas')

    # Integration type
    amazon_integration_type = fields.Selection(
        [('sum', 'Suminė'), ('quantitative', 'Kiekinė')], string='Integracijos tipas', default='quantitative')

    @api.multi
    def _compute_api_state(self):
        """
        Compute //
        Compute api_state based on amazon.region configuration state
        :return: None
        """
        for rec in self:
            if any(x.api_state == 'working' for x in rec.amazon_region_ids):
                rec.api_state = 'working'
            elif rec.amazon_region_ids and all(x.api_state == 'failed' for x in rec.amazon_region_ids):
                rec.api_state = 'failed'
            else:
                rec.api_state = 'not_initiated'

    @api.model
    def default_get(self, field_list):
        """
        Default get Amazon settings from res.company record
        :param field_list: wizard field list
        :return: default wizard values
        """
        if not self.env.user.is_manager():
            return {}
        company = self.sudo().env.user.company_id
        res = {
            'amazon_creation_interval': company.amazon_creation_interval,
            'amazon_creation_weekday': company.amazon_creation_weekday,
            'include_amazon_commission_fees': company.include_amazon_commission_fees,
            'include_amazon_tax': company.include_amazon_tax,
            'amazon_integration_type': company.amazon_integration_type,
            'amazon_marketplace_ids': [(4, x.id) for x in self.env['amazon.marketplace'].search([])],
            'amazon_region_ids': [(4, x.id) for x in self.env['amazon.region'].search([])],
            'amazon_accounting_threshold_date': company.sudo().amazon_accounting_threshold_date
        }
        return res

    @api.multi
    def test_api(self):
        """
        Test API connection for each region
        :return: None
        """
        self.ensure_one()
        self.amazon_region_ids.test_api()

    @api.multi
    def finish_configuration(self):
        """
        Finish configuration (records are modified directly) and write state to res.company
        :return: None
        """
        self.ensure_one()
        company = self.sudo().env.user.company_id

        if self.api_state != 'working':
            raise exceptions.UserError(_('Bent vienas regionas turi turėti validžius API raktus!'))
        if not self.amazon_marketplace_ids or all(not x.activated for x in self.amazon_marketplace_ids):
            raise exceptions.UserError(_('Turite aktyvuoti bent vieną prekiavietę!'))

        # If marketplace is activated, corresponding region must be
        # configured as well - raise an error otherwise
        region_statuses = {}
        # Map region codes to working api state
        for region in self.amazon_region_ids:
            region_statuses[region.code] = region.api_state == 'working'

        for marketplace in self.amazon_marketplace_ids.filtered(lambda x: x.activated):
            region_code = at.MARKETPLACE_COUNTRY_TO_MAIN_REGION_MAPPING.get(marketplace.marketplace_code)
            if not region_statuses[region_code]:
                raise exceptions.UserError(
                    _('Prekiavietė "%s" priklausanti regionui "%s" yra aktyvuota, '
                      'tačiau regionas nėra aktyvuotas arba jo API raktai nėra sukonfigūruoti!') % (
                        marketplace.name, region_code)
                )

        if self.amazon_integration_type != company.amazon_integration_type and self.env['amazon.order'].search([]):
            raise exceptions.UserError(_('Negalite keisti Amazon integracijos tipo, jau yra importuotų įrašų!'))

        # Only allow quantitative if robo_stock is installed
        rec = self.sudo().env['ir.module.module'].search([('name', '=', 'robo_stock')])
        if rec.state not in ['installed', 'to upgrade'] and self.amazon_integration_type == 'quantitative':
            raise exceptions.UserError(
                _('Privalote aktyvuoti sandėlį, kad galėtumėte sukonfigūruoti kiekinę integraciją!'))

        values = {
            'amazon_creation_interval': self.amazon_creation_interval,
            'amazon_creation_weekday': self.amazon_creation_weekday,
            'amazon_integration_type': self.amazon_integration_type,
            'amazon_integration_configured': True,
            'amazon_accounting_threshold_date': self.amazon_accounting_threshold_date,
            'include_amazon_commission_fees': self.include_amazon_commission_fees,
            'include_amazon_tax': self.include_amazon_tax,
        }
        company.write(values)

        # Recompute fields of spec products
        self.env['amazon.product'].search([('spec_product', '=', True)]).recompute_fields()

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(x.id, _('Amazon konfigūracijos vedlys')) for x in self]

    # Methods at the bottom are not used at the moment
    # ------------------------------------------------

    @api.multi
    def get_api_state(self):
        """
        ! METHOD NOT USED AT THE MOMENT!
        Check API state based on import jobs
        :return: None
        """
        if self.env['amazon.import.wizard.job'].search_count(
                [('operation_type', '=', 'init_api'), ('state', '=', 'in_progress')]):
            state = 'in_progress'
        elif self.env['amazon.import.wizard.job'].search_count(
                [('operation_type', '=', 'init_api'), ('state', '=', 'failed')]) and not \
                self.env.user.company_id.valid_api_keys:
            state = 'failed'
        elif self.env['amazon.import.wizard.job'].search_count(
            [('operation_type', '=', 'init_api'), ('state', '=', 'finished')]) and \
                self.env.user.company_id.valid_api_keys:
            state = 'working'
        else:
            state = 'not_initiated'
        return state

    @api.multi
    def initiate_amazon_keys(self):
        """
        ! METHOD NOT USED AT THE MOMENT !
        Write Amazon configuration settings to res.company record
        :return: None
        """
        self.ensure_one()
        if not self.env.user.is_manager():
            return

        company = self.sudo().env.user.company_id
        config = self.sudo().env['ir.config_parameter']
        values = {
            'amazon_account_id': self.amazon_account_id,
            'amazon_access_key': self.amazon_access_key,
            'amazon_secret_key': self.amazon_secret_key,
            'amazon_accounting_threshold_date': self.amazon_accounting_threshold_date
        }
        company.write(values)

        if not self.env['amazon.marketplace'].search([]).filtered(lambda x: x.state == 'configured'):
            raise exceptions.UserError(_('Neaktkyvavote nei vienos parduotuvės!'))

        if self.env['amazon.import.wizard.job'].search_count(
                [('operation_type', '=', 'init_api'), ('state', '=', 'in_progress')]):
            raise exceptions.UserError(_('API yra inicijuojamas šiuo metu!'))

        vals = {
            'execution_start_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            'state': 'in_progress',
            'operation_type': 'init_api'
        }
        import_job = self.env['amazon.import.wizard.job'].create(vals)
        self.env.cr.commit()

        # Recompute API state and start the job
        self.api_state = self.get_api_state()
        threaded_calculation = threading.Thread(
            target=self.init_api_threaded, args=(import_job.id, ))
        threaded_calculation.start()

    @api.model
    def init_api_threaded(self, job_id):
        """
        ! METHOD NOT USED AT THE MOMENT !
        Parse data from passed Amazon XML and create corresponding objects // THREADED
        :param job_id: amazon.import.wizard.job ID
        :return: None
        """
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, odoo.SUPERUSER_ID, {'lang': 'lt_LT'})
            job = env['amazon.import.wizard.job'].browse(job_id)
            try:
                # Try fetching product category data
                try:
                    env['api.amazon.import'].init_api_fetch_product_categories()
                except Exception as exc:
                    error = 'Neteisingi Amazon API raktai arba šis profilis neturi nė vienos prekiavietės!'
                    if self.env.user.has_group('base.group_system'):
                        error += ' Klaidos pranešimas: {}'.format(exc.args[0])
                    raise exceptions.UserError(_(error))
                env['res.company'].search([]).write({'valid_api_keys': True})
            except Exception as exc:
                new_cr.rollback()
                env['res.company'].search([]).write({'valid_api_keys': False})
                job.write({'state': 'failed',
                           'fail_message': str(exc.args[0]),
                           'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
            else:
                job.write({'state': 'finished',
                           'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
            new_cr.commit()
            new_cr.close()


AmazonConfigurationWizard()
