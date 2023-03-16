# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, tools, _
from odoo.addons.queue_job.job import job
from datetime import datetime
import StringIO
import base64
import csv


class AmazonSPOrderImportJob(models.Model):
    """
    Model that holds information about failed/imported amazon tasks
    """
    _name = 'amazon.sp.order.import.job'

    file_data = fields.Binary(string='File data')
    file_name = fields.Char(string='File name')
    execution_start_date = fields.Datetime(string='Execution date start')
    execution_end_date = fields.Datetime(string='Execution date end')
    execution_state = fields.Selection([
        ('in_progress', 'In progress'),
        ('finished', 'Processed successfully'),
        ('failed', 'Processing failed')],
        string='Execution state', default='in_progress',
    )
    fail_message = fields.Char(string='Fail message')

    corrected_invoice_ids = fields.Many2many('account.invoice')
    corrected_order_ids = fields.Many2many('amazon.sp.order')
    show_corrected_record_button = fields.Boolean(compute='_compute_show_corrected_record_button')

    @api.multi
    def _compute_show_corrected_record_button(self):
        """Check whether corrected record opening button should be shown"""
        for rec in self:
            rec.show_corrected_record_button = rec.execution_state == 'finished' and (
                    rec.corrected_invoice_ids or rec.corrected_order_ids
            )

    @api.multi
    def action_open_invoices(self):
        """
        Open invoice tree with domain filtering the invoices that
        were created by this data import job
        :return: JS action (dict)
        """
        self.ensure_one()
        action = self.env.ref('account.action_invoice_tree1').read()[0]
        action['domain'] = [('id', 'in', self.corrected_invoice_ids.ids)]
        return action

    @api.multi
    def action_open_orders(self):
        """
        Open invoice tree with domain filtering the invoices that
        were created by this data import job
        :return: JS action (dict)
        """
        self.ensure_one()
        action = self.env.ref('amazon_sp_api.action_open_amazon_sp_order_back').read()[0]
        action['domain'] = [('id', 'in', self.corrected_order_ids.ids)]
        return action

    @job
    @api.multi
    def process_import_job(self):
        """Processes import job that is not in finished state"""
        self.ensure_one()
        if self.execution_state == 'finished':
            return

        updated_orders = self.env['amazon.sp.order']
        recreated_invoices = self.env['account.invoice']

        parsed_lines = []
        # If job was created, file is already validated
        string_io = StringIO.StringIO(base64.decodestring(self.file_data))
        csv_reader = csv.reader(string_io, delimiter=',', quotechar='"')
        header = csv_reader.next()

        # Loop through the rows and gather the results
        for row in csv_reader:
            mapped_results = dict(zip(header, row))
            parsed_lines.append(mapped_results)

        # Loop through mapped results and check what invoices need to be updated
        for line_data in parsed_lines:
            ext_order_id = line_data.get('Order ID')
            # Check whether current order exists, otherwise skip
            refund_order = line_data.get('Transaction Type') == 'REFUND'
            order = self.env['amazon.sp.order'].search(
                [('ext_order_id', '=', ext_order_id), ('refund_order', '=', refund_order)]
            )
            if order:
                updated_order, recreated_invoice = self.update_related_order(order, line_data)
                updated_orders |= updated_order
                recreated_invoices |= recreated_invoice

        # Write the state
        self.write({
            'execution_state': 'finished',
            'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            'corrected_invoice_ids': [(4, inv.id) for inv in recreated_invoices],
            'corrected_order_ids': [(4, order.id) for order in updated_orders],
        })

    @api.model
    def update_related_order(self, order, parsed_data):
        """
        Updates related order's and invoice's data
        :param order: Order record
        :param parsed_data: Newly parsed order data
        :return: None
        """

        updated_order = self.env['amazon.sp.order']
        recreated_invoice = self.env['account.invoice']

        order_changes = {}
        ResCountry = self.env['res.country'].sudo()
        # Get initial values
        initial_tax_rule = order.amazon_sp_tax_rule_id
        initial_partner = order.partner_id
        # Get origin country code and update it if it differs
        origin_country_code = parsed_data.get('Seller Tax Registration Jurisdiction')
        if origin_country_code:
            origin_country = ResCountry.search([('code', '=', origin_country_code)])
            if not origin_country:
                raise exceptions.ValidationError(
                    _('Amazon SP order import: Got an unrecognized country code %s') % origin_country_code
                )
            if order.origin_country_id != origin_country:
                order_changes.update({'origin_country_code': origin_country_code, })

        # Compare these two fields for now, since they are inconsistent from API
        buyer_vat_code = parsed_data.get('Buyer Tax Registration')
        if buyer_vat_code and order.buyer_vat_code != buyer_vat_code:
            order_changes.update({'buyer_vat_code': buyer_vat_code, })
        # Write collected changes to the order
        if order_changes:
            order.write(order_changes)
            updated_order |= order

        invoice = order.invoice_id
        # Check whether invoice should be recreated
        if invoice and (
                initial_tax_rule != order.amazon_sp_tax_rule_id or
                initial_partner != order.partner_id
        ):
            # Reset order state and unlink current invoice
            order.write({'state': 'imported'})
            invoice.action_invoice_cancel_draft()
            invoice.write({'move_name': False, 'name': False, 'number': False})
            invoice.unlink()
            # Recreate the invoice with newly written values
            order.invoice_creation_prep()
            recreated_invoice |= order.invoice_id

        return updated_order, recreated_invoice

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(x.id, _('Amazon order CSV job - %s') % x.id) for x in self]
