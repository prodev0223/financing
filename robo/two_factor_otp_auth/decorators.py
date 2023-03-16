# -*- coding: utf-8 -*-

from odoo import exceptions, _
from exceptions import InvalidOtpError


# Method used as a decorator
def authenticate(func):
    """
    // Decorator
    Used to decorate functions that must be OTP authenticated before execution.
    Method gets the passed code from the context, and does a realtime check,
    based on the user that is executing the action. Constraints concerning
    the OTP code are checked as well.
    :param func: decorated function instance
    :return: result of decorated function
    """
    def f(*args, **data):
        # Try to check whether the first argument of the function is 'record' type
        # it must have '_context' attribute, otherwise an error is raised
        try:
            record = args[0]
            context = record._context
        except (KeyError, ValueError, IndexError):
            raise exceptions.UserError(
                _('Incorrect usage of "authenticate" decorator. Must be used on methods contained in model class'))
        # Try to get OTP code from the context, check if it exists
        otp_code = context.get('otp_code')
        if not otp_code:
            raise exceptions.ValidationError(
                _('Methods with "authenticate" decorator must have "otp_code" variable passed in the context'))

        # Get the current user from the env
        user = record.env.user
        # Check if decorated method model depends on two_factor_otp_auth
        # If it does not, raise an error
        if not getattr(user, '_check_otp_code'):
            raise NotImplementedError()

        # Get the secret code from the actual user record
        # if it does not exit, raise an error
        secret_code = user.secret_code_2fa
        if not secret_code:
            raise exceptions.ValidationError(
                _('User has not configured the OTP code, operation is not allowed!'))
        # Try to execute realtime validation
        # raise an error on invalid OTP code
        try:
            user._check_otp_code(
                otp_code,
                secret_code,
            )
        except InvalidOtpError:
            raise exceptions.ValidationError(
                _('Invalid OTP code!'))
        # Return the flow to the decorated function
        # if everything checks out correctly
        return func(*args, **data)

    f.func_name = func.func_name
    return f
