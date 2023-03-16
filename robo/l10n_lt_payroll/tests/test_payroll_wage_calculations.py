# -*- coding: utf-8 -*-
from six import iteritems

from odoo.tests.common import SingleTransactionCase
from odoo.tools import float_round


class CommonPayrollTest(SingleTransactionCase):

    @classmethod
    def setUpClass(cls):
        super(CommonPayrollTest, cls).setUpClass()
        cls.HrPayroll = cls.env['hr.payroll']
        cls.precision_rounding = 0.01

    def _check_payroll_values_match_expected_values(self, payroll_values, expected_values):
        for (key, value_expected) in iteritems(expected_values):
            value_retrieved = payroll_values.get(key)
            self.assertIsNotNone(value_retrieved, 'Payroll did not calculate value for key: {}'.format(key))
            value_retrieved = float_round(value_retrieved, precision_rounding=self.precision_rounding)
            value_expected = float_round(value_expected, precision_rounding=self.precision_rounding)
            self.assertEquals(
                value_retrieved,
                value_expected,
                'Retrieved value ({}) does not match expected value ({}) for key: {}'.format(
                    value_retrieved, value_expected, key
                )
            )

    def _check_net_conversion(self, net_wage, expected_gross_wage):
        retrieved_gross_wage = self.HrPayroll.convert_net_income_to_gross(net_wage, date=self.calculation_date)
        retrieved_gross_wage = float_round(retrieved_gross_wage, precision_rounding=self.precision_rounding)
        net_wage = float_round(net_wage, precision_rounding=self.precision_rounding)
        expected_gross_wage = float_round(expected_gross_wage, precision_rounding=self.precision_rounding)
        self.assertEquals(
            retrieved_gross_wage, expected_gross_wage,
            'Retrieved gross wage ({}) does not match expected ({}) gross wage when converting NET wage ({}) to '
            'GROSS'.format(retrieved_gross_wage, expected_gross_wage, net_wage)
        )