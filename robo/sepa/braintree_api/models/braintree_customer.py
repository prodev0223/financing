# -*- coding: utf-8 -*-
from odoo import api, fields, models


class BraintreeCustomer(models.Model):
    _name = 'braintree.customer'

    # Identifiers
    gateway_id = fields.Many2one('braintree.gateway', string='Related gateway')
    customer_id = fields.Char(string='External ID')
    # Customer information
    first_name = fields.Char(string='First name')
    last_name = fields.Char(string='Last name')
    company = fields.Char(string='Company')
    email = fields.Char(string='Email')
    phone = fields.Char(string='Phone')

    # Related partner
    partner_id = fields.Many2one('res.partner', string='Internal partner')

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.model
    def get_from_customer_details(self,  customer_details, extra_data=None):
        """
        Creates or finds related customer record based on API fetched
        customer details. On new record creation res.partner is also created.
        :param customer_details: Main customer API data (object)
        :param extra_data: Extra customer related data (dict)
        :return: braintree.customer (record)
        """

        # Check for related extra data (gateway ID, detected partner ID)
        extra_data = {} if extra_data is None else extra_data
        gateway_id = extra_data.get('gateway_id')
        partner_id = extra_data.get('detected_partner_id')
        # Search for related customer
        customer_domain = [('customer_id', '=', customer_details.id)]
        if gateway_id:
            customer_domain += [('gateway_id', '=', gateway_id)]
        customer = self.search(customer_domain)
        if not customer:
            # Prepare values for new customer
            vals = {
                'gateway_id': gateway_id,
                'first_name': customer_details.first_name,
                'last_name': customer_details.last_name,
                'email': customer_details.email,
                'company': customer_details.company,
                'phone': customer_details.phone,
                'customer_id': customer_details.id,
            }
            # If there was no detected partner, try to find it using the name
            if not partner_id:
                # Compose a name from first and last names
                first_name = customer_details.first_name
                if first_name:
                    partner_name = '{} {}'.format(customer_details.first_name, customer_details.last_name)
                else:
                    partner_name = customer_details.email

                partner_id = self.env['account.sepa.import'].get_partner_id(
                    partner_name=partner_name,
                )
            # Otherwise create the partner
            if not partner_id:
                partner_id = self.create_partner(customer_details)
            # Update the values with found partner if any
            if partner_id:
                vals['partner_id'] = partner_id
            # Create the customer record
            customer = self.create(vals)
        return customer

    @api.model
    def create_partner(self, customer_details):
        """Creates res partner from customer details and returns created ID"""
        first_name = customer_details.first_name
        if first_name:
            partner_name = '{} {}'.format(customer_details.first_name, customer_details.last_name)
        else:
            partner_name = customer_details.email

        partner = self.env['res.partner'].create({
            'name': partner_name,
            'email': customer_details.email,
        })
        return partner.id

    # Actions ---------------------------------------------------------------------------------------------------------

    @api.multi
    def action_open_transactions(self):
        """Returns JS actions to open related transactions"""
        self.ensure_one()
        action = self.env.ref('sepa.braintree_transaction_action')
        action = action.read()[0]
        action['domain'] = [('customer_id', '=', self.id)]
        action['view_mode'] = 'tree'
        return action

    # Auxiliary methods -----------------------------------------------------------------------------------------------

    @api.multi
    def name_get(self):
        return [(rec.id, '%s %s' % (rec.first_name, rec.last_name)) for rec in self]
