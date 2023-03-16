from odoo.tests.common import tagged, SingleTransactionCase
from dateutil.relativedelta import relativedelta
from datetime import datetime
from odoo import tools

# Error messages
FAILED_TO_CREATE = 'Invoice creation failed in the previous step'
FAILED_TO_OPEN = 'Invoice opening failed'
FAILED_TO_CANCEL = 'Invoice cancelling failed'


class TestAccountInvoiceBase(SingleTransactionCase):

    @classmethod
    def setUpClass(cls):
        # Declare the values
        super(TestAccountInvoiceBase, cls).setUpClass()
        cls.i_invoice_values = cls.o_invoice_values = None

        company = cls.env.user.company_id
        # Setup the users
        cls.manager_user = company.vadovas.user_id

        # Setup other data
        date_now_dt = datetime.utcnow()
        date_now_str = date_now_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        vat_payer = company.sudo().with_context(date=date_now_str).vat_payer

        # Setup global invoice fields. Return if no product is found
        product_template = cls.env.ref('l10n_lt.product_template_2')
        product = product_template.product_variant_ids and product_template.product_variant_ids[0]
        tax_domain = [('amount', '=', '21'), ('price_include', '=', True)]
        if not product:
            return

        # Prepare base invoice and it's line values
        product_account = product.get_product_income_account(return_default=True)
        base_line_values = {
            'product_id': product.id,
            'name': product.name,
            'quantity': 5,
            'price_unit': 10,
            'uom_id': product.product_tmpl_id.uom_id.id,
            'account_id': product_account.id,
        }
        base_invoice_values = {
            'date_invoice': date_now_str,
            'date_due': date_now_dt + relativedelta(days=7),
            'price_include_selection': 'inc'
        }

        # Setup the out_invoice fields
        o_account_tax = cls.env['account.tax'].search(
            [('type_tax_use', '=', 'sale')] + tax_domain, limit=1)
        o_res_partner = cls.env['res.partner'].search(
            [('customer', '=', True)], limit=1)
        o_account_journal = cls.env['account.journal'].search(
            [('type', '=', 'sale')], limit=1)
        o_account_account = cls.env.ref('l10n_lt.1_account_229')  # 2410

        # Only prepare out invoice data if these fields exist
        if o_account_tax and o_res_partner and o_account_journal and o_account_account:

            # Copy base values
            o_line_values = base_line_values.copy()
            if vat_payer:
                o_line_values.update({
                    'invoice_line_tax_ids': [(6, 0, o_account_tax.ids)],
                })

            o_invoice_values = base_invoice_values.copy()
            # Prepare invoice number
            invoice_number_case_1 = 'TEST_INV_OUT_{}'.format(date_now_dt.strftime('%s'))
            o_invoice_values.update({
                'number': invoice_number_case_1,
                'move_name': invoice_number_case_1,
                'journal_id': o_account_journal.id,
                'account_id': o_account_account.id,
                'partner_id': o_res_partner.id,
                'type': 'out_invoice',
                'invoice_line_ids': [(0, 0, o_line_values)],
            })
            cls.o_invoice_values = o_invoice_values

        # Setup the in_invoice fields
        in_account_tax = cls.env['account.tax'].search(
            [('type_tax_use', '=', 'purchase')] + tax_domain, limit=1)
        in_res_partner = cls.env['res.partner'].search(
            [('supplier', '=', True)], limit=1)
        in_account_journal = cls.env['account.journal'].search(
            [('type', '=', 'purchase')], limit=1)
        in_account_account = cls.env.ref('l10n_lt.1_account_378')  # 4430

        # Only prepare out invoice data if these fields exist
        if in_account_tax and in_res_partner and in_account_journal and in_account_account:
            # Copy base values
            in_line_values = base_line_values.copy()
            if vat_payer:
                in_line_values.update({
                    'invoice_line_tax_ids': [(6, 0, in_account_tax.ids)],
                })

            in_invoice_values = base_invoice_values.copy()
            # Prepare invoice number
            invoice_number_case_1 = 'TEST_INV_IN_{}'.format(date_now_dt.strftime('%s'))
            in_invoice_values.update({
                'number': invoice_number_case_1,
                'reference': invoice_number_case_1,
                'move_name': invoice_number_case_1,
                'journal_id': in_account_journal.id,
                'account_id': in_account_account.id,
                'partner_id': in_res_partner.id,
                'type': 'in_invoice',
                'invoice_line_ids': [(0, 0, in_line_values)],
            })
            cls.in_invoice_values = in_invoice_values


@tagged('post_install', 'robo')
class TestInAccountInvoiceSuperuser(TestAccountInvoiceBase):

    # Global test case variable
    in_invoice = None

    def test_01__create_in_invoice_superuser(self):
        """Test in invoice creation workflow with SU"""
        if self.in_invoice_values:
            # Try to create the invoice
            TestInAccountInvoiceSuperuser.in_invoice = \
                self.env['account.invoice'].sudo().create(self.in_invoice_values)

    def test_02__open_in_invoice_superuser(self):
        """Test in invoice opening workflow with SU"""
        self.assertTrue(TestInAccountInvoiceSuperuser.in_invoice, FAILED_TO_CREATE)
        TestInAccountInvoiceSuperuser.in_invoice.with_context(skip_attachments=True).action_invoice_open()
        self.assertEqual(TestInAccountInvoiceSuperuser.in_invoice.state, 'open', FAILED_TO_OPEN)

    def test_03__cancel_in_invoice_superuser(self):
        """Test in invoice cancelling workflow with SU"""
        self.assertTrue(TestInAccountInvoiceSuperuser.in_invoice, FAILED_TO_CREATE)
        TestInAccountInvoiceSuperuser.in_invoice.action_invoice_cancel()
        self.assertEqual(TestInAccountInvoiceSuperuser.in_invoice.state, 'cancel', FAILED_TO_CANCEL)


@tagged('post_install', 'robo')
class TestOutAccountInvoiceSuperuser(TestAccountInvoiceBase):

    # Global test case variable
    out_invoice = None

    def test_04__create_out_invoice_superuser(self):
        """Test out invoice creation workflow with SU"""
        if self.o_invoice_values:
            # Try to create the invoice
            TestOutAccountInvoiceSuperuser.out_invoice = \
                self.env['account.invoice'].sudo().create(self.o_invoice_values)

    def test_05__open_out_invoice_superuser(self):
        """Test out invoice opening workflow with SU"""
        self.assertTrue(TestOutAccountInvoiceSuperuser.out_invoice, FAILED_TO_CREATE)
        TestOutAccountInvoiceSuperuser.out_invoice.action_invoice_open()
        self.assertEqual(TestOutAccountInvoiceSuperuser.out_invoice.state, 'open', FAILED_TO_OPEN)

    def test_06__cancel_out_invoice_superuser(self):
        """Test out invoice cancelling workflow with SU"""
        self.assertTrue(TestOutAccountInvoiceSuperuser.out_invoice, FAILED_TO_CREATE)
        TestOutAccountInvoiceSuperuser.out_invoice.action_invoice_cancel()
        self.assertEqual(TestOutAccountInvoiceSuperuser.out_invoice.state, 'cancel', FAILED_TO_CANCEL)


@tagged('post_install', 'robo')
class TestInAccountInvoiceManager(TestAccountInvoiceBase):

    # Global test case variable
    in_invoice = None

    def test_07__create_in_invoice_manager(self):
        """Test in invoice creation workflow with manager"""
        if self.in_invoice_values:
            # Try to create the invoice
            TestInAccountInvoiceManager.in_invoice = \
                self.env['account.invoice'].sudo(user=self.manager_user.id).create(self.in_invoice_values)

    def test_08__open_in_invoice_manager(self):
        """Test in invoice opening workflow with manager"""
        self.assertTrue(TestInAccountInvoiceManager.in_invoice, FAILED_TO_CREATE)
        TestInAccountInvoiceManager.in_invoice.sudo(
            user=self.manager_user.id).with_context(skip_attachments=True).action_invoice_open()
        self.assertEqual(TestInAccountInvoiceManager.in_invoice.state, 'open', FAILED_TO_OPEN)

    def test_09__cancel_in_invoice_manager(self):
        """Test in invoice cancelling workflow with manager"""
        self.assertTrue(TestInAccountInvoiceManager.in_invoice, FAILED_TO_CREATE)
        TestInAccountInvoiceManager.in_invoice.sudo(user=self.manager_user.id).action_invoice_cancel()
        self.assertEqual(TestInAccountInvoiceManager.in_invoice.state, 'cancel', FAILED_TO_CANCEL)


@tagged('post_install', 'robo')
class TestOutAccountInvoiceManager(TestAccountInvoiceBase):

    # Global test case variable
    out_invoice = None

    def test_10__create_out_invoice_manager(self):
        """Test out invoice creation workflow with manager"""
        if self.o_invoice_values:
            # Try to create the invoice
            TestOutAccountInvoiceManager.out_invoice = \
                self.env['account.invoice'].sudo(user=self.manager_user.id).create(self.o_invoice_values)

    def test_11__open_out_invoice_manager(self):
        """Test out invoice opening workflow with manager"""
        self.assertTrue(TestOutAccountInvoiceManager.out_invoice, FAILED_TO_CREATE)
        TestOutAccountInvoiceManager.out_invoice.sudo(user=self.manager_user.id).action_invoice_open()
        self.assertEqual(TestOutAccountInvoiceManager.out_invoice.state, 'open', FAILED_TO_OPEN)

    def test_12__cancel_out_invoice_manager(self):
        """Test out invoice cancel workflow with manager"""
        self.assertTrue(TestOutAccountInvoiceManager.out_invoice, FAILED_TO_CREATE)
        TestOutAccountInvoiceManager.out_invoice.sudo(user=self.manager_user.id).action_invoice_cancel()
        self.assertEqual(TestOutAccountInvoiceManager.out_invoice.state, 'cancel', FAILED_TO_CANCEL)
