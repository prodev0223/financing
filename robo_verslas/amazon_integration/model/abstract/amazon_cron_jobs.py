# -*- coding: utf-8 -*-

from odoo import models, api, tools, _
from datetime import datetime


class AmazonCronJobs(models.AbstractModel):
    """
    Abstract model that is used to store cron job methods
    """
    _name = 'amazon.cron.jobs'

    @api.model
    def cron_synchronize_orders(self):
        """
        Cron-job //
        Fetch order list from Amazon API, create orders based on grouped data
        and proceed with record creation/re-creation
        :return: None
        """
        # Only activate order creation if amazon integration is configured
        if not self.env.user.company_id.amazon_integration_configured:
            return

        order_list = self.env['api.amazon.import'].api_fetch_orders_prep()
        # Create Amazon orders
        error_body = str()
        for order_values in order_list:
            try:
                self.env['amazon.order'].create(order_values)
                self.env.cr.commit()
            except Exception as exc:
                self.env.cr.rollback()
                error_body += 'Order ID {}. Exception - {}\n'.format(order_values.get('order_id'), exc.args[0])

        # Create products/categories before recreating invoices
        categories = self.env['amazon.product.category'].search(
            [('product_category_id', '=', False), ('activated', '=', True)])
        categories.create_system_category()
        self.env.cr.commit()

        if error_body:
            error_body = 'Failed to create following Amazon orders: \n\n' + error_body
            self.send_bug(error_body)

        # Recreate amazon orders as invoices
        if self.check_amazon_creation_day():
            orders = self.env['amazon.order'].search(
                [('invoice_id', '=', False), ('state', 'in', ['imported', 'failed'])])
            orders.invoice_creation_prep()

    @api.model
    def send_bug(self, body):
        """
        Send bug report
        :param body: bug body (str)
        :return: None
        """
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'error_message': body,
            'subject': 'Amazon Integration Error [%s]' % self._cr.dbname,
        })

    @api.model
    def check_amazon_creation_day(self):
        """
        Check Amazon creation day. If creation interval is weekly and current weekday
        is not the selected day, then deny the creation, otherwise allow.
        :return: True if creation should be allowed, otherwise False
        """
        company = self.sudo().env.user.company_id
        if company.amazon_creation_interval == 'weekly' and isinstance(company.amazon_creation_weekday, int) and \
                datetime.utcnow().weekday() != company.amazon_creation_weekday - 1:
            return False
        return True


AmazonCronJobs()
