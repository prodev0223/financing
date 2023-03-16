# -*- encoding: utf-8 -*-
from odoo import models, api


class RoboAPIBase(models.AbstractModel):
    """
    Override some methods in robo.api.base
    """
    _inherit = 'robo.api.base'

    @api.model
    def add_extra_vals_overridable(self, invoice_vals, post):
        """
        Used to add extra values to invoice_vals
        :param invoice_vals: account.invoice values
        :param post: API post
        :return: updated invoice values
        """
        # Use post variable, for now it's unused
        walless_main_ext_id = post.get('walless_main_ext_id', False)
        vals = {
            'walless_main_ext_id': walless_main_ext_id
        }
        invoice_vals.update(vals)
        return invoice_vals

    @api.model
    def cancel_unlink_domain_search_overridable(self, post):
        """
        Overridable method used to extend the domain
        for account.invoice cancel or unlink operation
        :param post: API post
        :return: account.invoice, error_str
        """
        walless_main_ext_id = post.get('walless_main_ext_id', False)
        invoice_obj = self.env['account.invoice'].sudo()
        error_str = str()
        if not walless_main_ext_id:
            error_str = 'Missing | Walless ext invoice_id'
            return False, error_str

        domain = [('walless_main_ext_id', '=', walless_main_ext_id)]
        invoice_id = invoice_obj.search(domain)
        if not invoice_id:
            error_str = 'Invoice not found. External Walless ID %s' % str(walless_main_ext_id)
            return False, error_str
        else:
            return invoice_id, error_str

    @api.model
    def update_domain_search_overridable(self, post):
        """
        Overridable method used to extend the domain
        for account.invoice update operation
        :param post: API post
        :return: account.invoice, error_str
        """
        walless_main_ext_id = post.get('walless_main_ext_id', False)
        invoice_obj = self.env['account.invoice'].sudo()
        error_str = str()
        if not walless_main_ext_id:
            error_str = 'Missing | Walless ext invoice_id'
            return False, error_str

        domain = [('walless_main_ext_id', '=', walless_main_ext_id)]
        invoice_id = invoice_obj.search(domain)
        if not invoice_id:
            error_str = 'Invoice not found. External Walless ID %s' % str(walless_main_ext_id)
            return False, error_str
        else:
            return invoice_id, error_str


RoboAPIBase()
