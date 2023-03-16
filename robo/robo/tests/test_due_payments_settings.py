from odoo.tests import common, tagged
from six import iteritems


@tagged('post_install', 'robo')
class TestDuePaymentsSettings(common.SingleTransactionCase):
    """ Test the due payment settings """

    @classmethod
    def setUpClass(cls):
        super(TestDuePaymentsSettings, cls).setUpClass()

        # Reset all settings on company settings
        cls.company_id = cls.env.user.company_id
        cls.company_id.write({
            'apr_send_reminders': False,
            'apr_enabled_by_default': False,
            'apr_send_before': False,
            'apr_send_before_ndays': False,
            'apr_send_on_date': False,
            'apr_send_after': False,
            'apr_send_after_ndays': False,
            'apr_min_amount_to_send': False,
            'apr_email_cc': False,
            'apr_email_reply_to': False,
        })
        cls.earlier_partner = cls.env['res.partner'].create({
            'name': 'Earlier Partner',
            'customer': True,
            'email': 'noreply@robolabs.lt',
            'apr_send_reminders': False,
            'apr_send_before': False,
            'apr_send_before_ndays': False,
            'apr_send_on_date': False,
            'apr_send_after': False,
            'apr_send_after_ndays': False,
            'apr_min_amount_to_send': False,
            'apr_email_cc': False,
        })

        cls.test_values = {
            'apr_send_reminders': True,
            'apr_send_on_date': True,
            'apr_send_after': True,
            'apr_send_after_ndays': 3,
            'apr_min_amount_to_send': 10,
        }

    @staticmethod
    def check_apr_settings(record, values):
        """ Check that record has its fields set to the value passed in the dictionary """
        for field, value in iteritems(values):
            try:
                if record[field] != value:
                    return False
            except KeyError:
                continue
        return True

    def test_00_set_company_settings(self):
        """ Ensure that Company profile wizard saves settings"""
        self.assertFalse(self.check_apr_settings(self.company_id, self.test_values),
                         'Company settings are already matching the test settings')
        wizard = self.env['robo.company.settings'].create({})
        wizard.write(self.test_values)
        wizard.execute()
        self.assertTrue(self.check_apr_settings(self.company_id, self.test_values),
                        'Company settings were not saved properly')

    def test_01_default_values_for_partners(self):
        """ Ensure that new partners get the default settings, as well as update the existing ones when selected """
        # Create a partner before APR are enabled by default
        self.assertFalse(self.earlier_partner.apr_send_reminders, 'The early partner already get reminders enabled')
        # Enable APR by default
        wizard = self.env['robo.company.settings'].create({})
        wizard.write({'apr_enabled_by_default': True})
        wizard.execute()
        self.assertTrue(self.check_apr_settings(self.company_id, {'apr_enabled_by_default': True}),
                        'Could not set APR by default on company settings')
        # Create a new partner which should have APR enabled
        new_partner = self.env['res.partner'].create({
            'name': 'New Partner',
            'customer': True,
            'email': 'noreply@robolabs.lt',
        })
        self.assertTrue(self.check_apr_settings(new_partner, self.test_values),
                        'New partner does not have the right settings')
        self.assertFalse(self.check_apr_settings(self.earlier_partner, self.test_values),
                         'Earlier partner got settings enabled')
        # Enable APR with company default settings on all partners
        wizard.write({'apply_default_apr_settings_to_all': True})
        wizard.execute()
        self.assertTrue(self.check_apr_settings(self.earlier_partner, self.test_values),
                        'Earlier partner does not have the right settings')
        self.assertTrue(self.check_apr_settings(new_partner, self.test_values),
                        'New partner does not have the right settings')
