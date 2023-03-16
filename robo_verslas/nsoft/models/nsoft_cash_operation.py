# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, _


class NsoftCashOperation(models.Model):
    _name = 'nsoft.cash.operation'
    _inherit = ['mail.thread']

    ext_document_id = fields.Char(string='External document ID')
    ext_register_id = fields.Integer(string='External POS ID', inverse='_set_ext_pos_data')
    cash_register_number = fields.Char(string='External POS code', inverse='_set_ext_pos_data')
    ext_cashier_id = fields.Integer(string='External cashier ID', inverse='_set_ext_cashier_id')

    receipt_number = fields.Char(string='External receipt number')
    fiscal_number = fields.Char(string='External fiscal number')

    operation_date = fields.Datetime(string='Operation date')
    operation_type = fields.Selection(
        [(1, 'Cash in'), (2, 'Cash out')],
        string='Operation type'
    )
    amount = fields.Float(string='Amount')

    state = fields.Selection([
        ('created', 'Created'),
        ('imported', 'Imported'),
        ('failed', 'Failed')],
        string='State', default='imported',
    )

    point_of_sale_id = fields.Many2one('nsoft.cash.register', string='Cash register')
    cashier_mapper_id = fields.Many2one('nsoft.cashier.mapper', string='Cashier mapper')
    payment_id = fields.Many2one('account.payment', string='Account payment')

    @api.multi
    def _set_ext_cashier_id(self):
        """Creates/relates cashier mapper record to current cash operation"""
        NsoftCashierMapper = self.env['nsoft.cashier.mapper']
        for rec in self:
            mapper = NsoftCashierMapper.search([('ext_cashier_id', '=', rec.ext_cashier_id)], limit=1)
            if not mapper:
                mapper = NsoftCashierMapper.search([('default_mapper', '=', True)], limit=1)
            if not mapper:
                mapper = NsoftCashierMapper.create({
                    'ext_cashier_id': rec.ext_cashier_id,
                    'created_automatically': True,
                })
            rec.cashier_mapper_id = mapper

    @api.multi
    def _set_ext_pos_data(self):
        """
        Connect external POS ID to nsoft cash register in the system.
        ext_pos_id name is conserved due to column name in the table
        """
        NsoftCashRegister = self.env['nsoft.cash.register'].sudo()
        NsoftSaleLine = self.env['nsoft.sale.line'].sudo()
        for rec in self:
            point_of_sale = NsoftCashRegister.search([('ext_id', '=', rec.ext_register_id)])
            if not point_of_sale:
                point_of_sale = NsoftCashRegister.search([('cash_register_number', '=', rec.cash_register_number)])
            if not point_of_sale:
                # Search for sale lines that have current register. This mix-up is due to inconsistency on nSoft part.
                # Some external nSoft tables have cash register ID, some cash register number,
                # thus we have to gather info from different places, and write it to the registers.
                sale_line = NsoftSaleLine.search([
                    ('ext_cash_register_id', '=', rec.ext_register_id),
                    ('cash_register_id', '!=', False)], limit=1
                )
                if sale_line:
                    # Write external ID to POS
                    point_of_sale = sale_line.cash_register_id
                    point_of_sale.write({'ext_id': rec.ext_register_id})
            rec.point_of_sale_id = point_of_sale

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def check_payment_creation_constraints(self):
        """
        Validate related nsoft cash operation records by checking various
        constrains before passing record-set to account payment creation
        :return: nsoft cash operation recordset
        """
        valid_operations = self.env[self._name]
        for rec in self.filtered(lambda x: not tools.float_is_zero(x.amount, precision_digits=2)):
            error_template = str()
            # Check base constraints
            if rec.point_of_sale_id.state != 'working':
                error_template += _('Operation point of sale was not found or is not configured\n')
            if not rec.cashier_mapper_id:
                error_template += _('Cashier mapper record does not exist for current payment\n')
            if rec.cashier_mapper_id and not rec.cashier_mapper_id.employee_id:
                error_template += _('Cashier mapper record does not have related employee set')
            if not rec.point_of_sale_id.cash_journal_id:
                error_template += _('Related point of sale does not have cash journal set')

            # If there's any errors write it to the record
            if error_template:
                error_template = _(
                    'Failed to create the operation due to following errors: \n\n'
                ) + error_template
                rec.post_message(error_template, state='failed')
            else:
                valid_operations |= rec
        return valid_operations

    @api.multi
    def create_account_payments_prep(self):
        """Prepares cash operation account payment creation"""
        # Filter out created cash operations
        operations = self.filtered(
            lambda x: not x.payment_id and x.state != 'created'
        )
        # Check constraints and filter records that have any warnings
        validated_operations = operations.check_payment_creation_constraints()
        # Create moves for validated cash operations
        validated_operations.create_account_payments()

    @api.multi
    def create_account_payments(self):
        """
        Creates account payments from passed nsoft cash operation data.
        All the cash operations are validated before this creation step
        :return: None
        """
        AccountPayment = self.env['account.payment'].sudo()
        company_currency = self.env.user.company_id.currency_id

        # Prepare static data for payment types
        static_data = {
            1: {
                'payment_method_id': self.env.ref(
                    'account.account_payment_method_manual_in').id,
                'payment_type': 'inbound',
            },
            2: {
                'payment_method_id': self.env.ref(
                    'account.account_payment_method_manual_out').id,
                'payment_type': 'outbound',
            }
        }

        for operation in self:
            # Skip zero amount operations
            if tools.float_is_zero(operation.amount, precision_digits=2):
                continue

            # Get the cash journal and the mapper from the point of sale
            journal = operation.point_of_sale_id.cash_journal_id
            mapper = operation.cashier_mapper_id

            # Get the operation data and calculate the amount
            op_data = static_data.get(operation.operation_type)
            reference = operation.receipt_number or operation.fiscal_number or _('Cash Operation')

            # Prepare the values
            values = {
                'journal_id': journal.id,
                'amount': abs(operation.amount),
                'currency_id': company_currency.id,
                'payment_date': operation.operation_date,
                'cashier_id': mapper.employee_id.id,
                'payment_type': op_data['payment_type'],
                'payment_method_id': op_data['payment_method_id'],
                'communication': reference,
            }

            # Create account payment record, leave it in draft,
            # as partner must be assigned manually
            try:
                payment = AccountPayment.create(values)
            except Exception as e:
                operation.custom_rollback(e.args)
                continue

            # Assign create move to the operation and update the state
            operation.write({
                'payment_id': payment.id, 'state': 'created',
            })
            self.env.cr.commit()

    @api.multi
    def custom_rollback(self, error_message):
        """
        Rollback current transaction, post message to the object and commit
        :return: None
        """
        self.env.cr.rollback()
        # Compose the body, write the state and post the message to nsoft move
        body = _('Failed to create nSoft cash operation payment, error: %s') % str(error_message)
        self.post_message(body, state='failed')
        self.env.cr.commit()

    @api.multi
    def post_message(self, message, state):
        """Post the message to related operations and write the state"""
        self.write({'state': state})
        for rec in self:
            rec.message_post(body=message)

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(rec.id, _('Operation - {}'.format(rec.ext_document_id))) for rec in self]
