# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _


class AmazonRegion(models.Model):
    _name = 'amazon.region'

    name = fields.Char(string='Pavadinimas', readonly=1)
    code = fields.Char(string='Kodas', readonly=1)

    # API Keys
    amazon_account_id = fields.Char(
        string='Amazon profilio ID (Seller ID)', groups='robo_basic.group_robo_premium_manager')
    amazon_access_key = fields.Char(
        string='Amazon prisijungimo raktas (AWS Access Key ID)', groups='robo_basic.group_robo_premium_manager')
    amazon_secret_key = fields.Char(
        string='Amazon slaptasis raktas (Client Secret)', groups='robo_basic.group_robo_premium_manager')

    all_keys_passed = fields.Boolean(compute='_compute_all_keys_passed')
    activated = fields.Boolean(string='Aktyvuota')
    api_state = fields.Selection([('failed', 'Inicijavimas nepavyko (Neteisingi raktai)'),
                                  ('working', 'Veikiantis'),
                                  ('not_initiated', 'Neinicijuota')],
                                 string='API Būsena', default='not_initiated', readonly=True)

    # Computes // -----------------------------------------------------------------------------------------------------

    @api.multi
    def _compute_all_keys_passed(self):
        """
        Compute //
        Check whether all of the API keys are passed
        :return: None
        """
        for rec in self:
            rec.all_keys_passed = rec.amazon_access_key and rec.amazon_secret_key and rec.amazon_account_id

    # Main methods // -------------------------------------------------------------------------------------------------

    @api.multi
    def test_api(self):
        """
        Check whether all of the Amazon API keys are passed.
        If they are, check their validity by calling an API
        endpoint and checking the result
        :return: None
        """
        activated = self.filtered(lambda x: x.activated)
        if not activated:
            raise exceptions.ValidationError(_('Nė vienas regionas nėra aktyvuotas'))

        for rec in activated:
            if not rec.all_keys_passed:
                raise exceptions.ValidationError(_('Nepaduoti visi API raktai regionui "%s"!') % rec.name)
            # Check whether keys are valid
            valid_api = self.env['api.amazon.import'].test_api(
                account_id=rec.amazon_account_id,
                secret_key=rec.amazon_secret_key,
                access_key=rec.amazon_access_key,
                region_code=rec.code
            )
            # Determine API state based on the response
            api_state = 'working'
            if not valid_api:
                api_state = 'failed'
            rec.write({'api_state': api_state})

    # CRUD // ---------------------------------------------------------------------------------------------------------

    @api.model
    def create(self, vals):
        """Create override - Do not allow anyone but admin create the regions"""
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Negalite kurti Amazon regionų.'))
        return super(AmazonRegion, self).create(vals)

    @api.multi
    def unlink(self):
        """Unlink override - Do not allow anyone but admin delete the regions"""
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Negalite ištrinti Amazon regionų.'))
        return super(AmazonRegion, self).unlink()


AmazonRegion()
