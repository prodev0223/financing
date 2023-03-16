# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions


class Transitional2FAWizard(models.TransientModel):
    """
    Wizard that is used to 2FA authenticate various
    system operations. Redirect model and method names
    must be passed, and the wizard record must be created.
    Redirect model record IDs can be passed in the context
    so multi-set operations can be executed after validation.
    """
    _name = 'transitional.2fa.wizard'

    otp_code = fields.Char(string='Confirmation code')
    redirect_method_name = fields.Char(string='Redirect method', required=True)
    redirect_model_name = fields.Char(string='Redirect model', required=True)

    @api.multi
    def redirect_to_auth_endpoint(self):
        """
        Check some base constraints and  redirect control
        to given method of given model. Model must contain
        'authenticate' decorator, code given by user in this wizard
        will be passed to redirect_method and validated by decorator.
        If record ID/IDs were provided
        in the context, browse them.
        :return: result of redirect method
        """
        self.ensure_one()
        user = self.env.user
        # Check basic constraints
        if not self.otp_code:
            raise exceptions.ValidationError(_('OTP code is not provided!'))
        secret_code = user.secret_code_2fa
        if not secret_code:
            raise exceptions.ValidationError(_('2FA is not yet configured!'))
        # Instantiate the environment, add otp code to the context
        redirect_model = self.env[self.redirect_model_name].with_context(otp_code=self.otp_code)
        redirect_res_ids = self._context.get('redirect_res_ids', [])
        if not redirect_res_ids:
            redirect_res_ids = self._context.get('active_ids', [])
        # Check whether passed IDs are of correct format
        if not isinstance(redirect_res_ids, list):
            raise exceptions.ValidationError(_('Format of passed res IDs is incorrect'))
        if redirect_res_ids:
            # If IDs are passed browse the records
            redirect_model = redirect_model.browse(redirect_res_ids)
        # Get the method and execute it
        method_instance = getattr(redirect_model, self.redirect_method_name)

        # Method instance must be decorated with 'authenticate'
        return method_instance()

    @api.multi
    @api.constrains('redirect_model_name', 'redirect_method_name')
    def _check_redirect_values(self):
        """
        Check whether passed redirect method name and model
        exists in the system.
        :return: None
        """
        for rec in self:
            try:
                redirect_model = self.env[rec.redirect_model_name]
            except KeyError:
                raise exceptions.ValidationError(_('Incorrect redirect model passed!'))
            if not hasattr(redirect_model, rec.redirect_method_name):
                raise exceptions.ValidationError(_('Incorrect redirect method passed!'))


Transitional2FAWizard()
