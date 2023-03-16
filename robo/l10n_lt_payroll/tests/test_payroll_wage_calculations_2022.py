# -*- coding: utf-8 -*-

from odoo.tests import tagged
from ..tests.test_payroll_wage_calculations import CommonPayrollTest


@tagged('post_install', 'robo', 'payroll')
class TestPayrollWageConversions2022(CommonPayrollTest):
    # Tests payroll calculations performed by Hr.Payroll for various GROSS values for the year 2022

    @classmethod
    def setUpClass(cls):
        super(TestPayrollWageConversions2022, cls).setUpClass()
        cls.calculation_date = '2022-02-01'

    def test_00_under_minimum_wage(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, no disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 300.0,
            'npd': 300.0,
            'gpm': 0.00,
            'employee_health_tax': 20.94,
            'employee_pension_tax': 37.56,
            'voluntary_sodra': 0.0,
            'neto': 241.5,
            'darbdavio_sodra': 5.31,
            'workplace_costs': 305.31,
        }
        kwargs['bruto'] = expected_values['bruto']
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_01_under_minimum_wage_exponential_sodra(self):
        kwargs = {'date': self.calculation_date}
        # Check the values with exponential additional voluntary SoDra, no disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 300.0,
            'npd': 300.0,
            'gpm': 0.00,
            'employee_health_tax': 20.94,
            'employee_pension_tax': 37.56,
            'voluntary_sodra': 8.1,
            'neto': 233.4,
            'darbdavio_sodra': 5.31,
            'workplace_costs': 305.31,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'voluntary_pension': 'exponential'})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_02_under_minimum_wage_full_sodra(self):
        kwargs = {'date': self.calculation_date}
        # Check the values with full additional voluntary SoDra, no disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 300.0,
            'npd': 300.0,
            'gpm': 0.00,
            'employee_health_tax': 20.94,
            'employee_pension_tax': 37.56,
            'voluntary_sodra': 9.0,
            'neto': 232.5,
            'darbdavio_sodra': 5.31,
            'workplace_costs': 305.31,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'voluntary_pension': 'full'})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_03_under_minimum_wage_0_25_disability(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, 0-25% disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 300.0,
            'npd': 300.0,
            'gpm': 0.00,
            'employee_health_tax': 20.94,
            'employee_pension_tax': 37.56,
            'voluntary_sodra': 0.0,
            'neto': 241.5,
            'darbdavio_sodra': 5.31,
            'workplace_costs': 305.31,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'disability': '0_25'})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_04_under_minimum_wage_30_55_disability(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, 30-55% disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 300.0,
            'npd': 300.0,
            'gpm': 0.00,
            'employee_health_tax': 20.94,
            'employee_pension_tax': 37.56,
            'voluntary_sodra': 0.0,
            'neto': 241.5,
            'darbdavio_sodra': 5.31,
            'workplace_costs': 305.31,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'disability': '30_55'})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_05_under_minimum_wage_illness_amount(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, no disability, 100 EUR illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 400.0,
            'npd': 400.0,
            'gpm': 0.00,
            'employee_health_tax': 20.94,
            'employee_pension_tax': 37.56,
            'voluntary_sodra': 0.0,
            'neto': 341.5,
            'darbdavio_sodra': 7.08,
            'workplace_costs': 407.08,
        }
        kwargs.update({'bruto': 300.0, 'illness_amount': 100.0})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_06_under_minimum_wage_fixed_term(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, no disability, no illness amount,
        # contract is fixed term
        expected_values = {
            'bruto': 300.0,
            'npd': 300.0,
            'gpm': 0.00,
            'employee_health_tax': 20.94,
            'employee_pension_tax': 37.56,
            'voluntary_sodra': 0.0,
            'neto': 241.5,
            'darbdavio_sodra': 7.47,
            'workplace_costs': 307.47,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'is_fixed_term': True})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_07_minimum_wage(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, no disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 642.0,
            'npd': 460,
            'gpm': 36.4,
            'employee_health_tax': 44.81,
            'employee_pension_tax': 80.38,
            'voluntary_sodra': 0.0,
            'neto': 480.41,
            'darbdavio_sodra': 11.36,
            'workplace_costs': 653.36,
        }
        kwargs['bruto'] = expected_values['bruto']
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_08_minimum_wage_exponential_sodra(self):
        kwargs = {'date': self.calculation_date}
        # Check the values with exponential additional voluntary SoDra, no disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 642.0,
            'npd': 460,
            'gpm': 36.4,
            'employee_health_tax': 44.81,
            'employee_pension_tax': 80.38,
            'voluntary_sodra': 17.33,
            'neto': 463.08,
            'darbdavio_sodra': 11.36,
            'workplace_costs': 653.36,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'voluntary_pension': 'exponential'})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_09_minimum_wage_full_sodra(self):
        kwargs = {'date': self.calculation_date}
        # Check the values with full additional voluntary SoDra, no disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 642.0,
            'npd': 460,
            'gpm': 36.4,
            'employee_health_tax': 44.81,
            'employee_pension_tax': 80.38,
            'voluntary_sodra': 19.26,
            'neto': 461.15,
            'darbdavio_sodra': 11.36,
            'workplace_costs': 653.36,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'voluntary_pension': 'full'})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_10_minimum_wage_0_25_disability(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, 0-25% disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 642.0,
            'npd': 642.0,
            'gpm': 0.0,
            'employee_health_tax': 44.81,
            'employee_pension_tax': 80.38,
            'voluntary_sodra': 0.0,
            'neto': 516.81,
            'darbdavio_sodra': 11.36,
            'workplace_costs': 653.36,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'disability': '0_25'})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_11_minimum_wage_30_55_disability(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, 30-55% disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 642.0,
            'npd': 642.0,
            'gpm': 0.0,
            'employee_health_tax': 44.81,
            'employee_pension_tax': 80.38,
            'voluntary_sodra': 0.0,
            'neto': 516.81,
            'darbdavio_sodra': 11.36,
            'workplace_costs': 653.36,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'disability': '30_55'})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_12_minimum_wage_illness_amount(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, no disability, 100 EUR illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 742.0,
            'npd': 456.88,
            'gpm': 55.1,
            'employee_health_tax': 44.81,
            'employee_pension_tax': 80.38,
            'voluntary_sodra': 0.0,
            'neto': 561.71,
            'darbdavio_sodra': 13.13,
            'workplace_costs': 755.13,
        }
        kwargs.update({'bruto': 642.0, 'illness_amount': 100.0})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_13_minimum_wage_fixed_term(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, no disability, no illness amount,
        # contract is fixed term
        expected_values = {
            'bruto': 642.0,
            'npd': 460,
            'gpm': 36.4,
            'employee_health_tax': 44.81,
            'employee_pension_tax': 80.38,
            'voluntary_sodra': 0.0,
            'neto': 480.41,
            'darbdavio_sodra': 15.99,
            'workplace_costs': 657.99,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'is_fixed_term': True})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_14_above_minimum_wage(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, no disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 1000.0,
            'npd': 389.8,
            'gpm': 122.04,
            'employee_health_tax': 69.8,
            'employee_pension_tax': 125.2,
            'voluntary_sodra': 0.0,
            'neto': 682.96,
            'darbdavio_sodra': 17.7,
            'workplace_costs': 1017.7,
        }
        kwargs['bruto'] = expected_values['bruto']
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_15_above_minimum_wage_exponential_sodra(self):
        kwargs = {'date': self.calculation_date}
        # Check the values with exponential additional voluntary SoDra, no disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 1000.0,
            'npd': 389.8,
            'gpm': 122.04,
            'employee_health_tax': 69.8,
            'employee_pension_tax': 125.2,
            'voluntary_sodra': 27.0,
            'neto': 655.96,
            'darbdavio_sodra': 17.7,
            'workplace_costs': 1017.7,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'voluntary_pension': 'exponential'})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_16_above_minimum_wage_full_sodra(self):
        kwargs = {'date': self.calculation_date}
        # Check the values with full additional voluntary SoDra, no disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 1000.0,
            'npd': 389.8,
            'gpm': 122.04,
            'employee_health_tax': 69.8,
            'employee_pension_tax': 125.2,
            'voluntary_sodra': 30.0,
            'neto': 652.96,
            'darbdavio_sodra': 17.7,
            'workplace_costs': 1017.7,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'voluntary_pension': 'full'})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_17_above_minimum_wage_0_25_disability(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, 0-25% disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 1000.0,
            'npd': 740.00,
            'gpm': 52.00,
            'employee_health_tax': 69.8,
            'employee_pension_tax': 125.2,
            'voluntary_sodra': 0.0,
            'neto': 753,
            'darbdavio_sodra': 17.7,
            'workplace_costs': 1017.7,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'disability': '0_25'})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_18_above_minimum_wage_30_55_disability(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, 30-55% disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 1000.0,
            'npd': 690.00,
            'gpm': 62.00,
            'employee_health_tax': 69.8,
            'employee_pension_tax': 125.2,
            'voluntary_sodra': 0.0,
            'neto': 743.00,
            'darbdavio_sodra': 17.7,
            'workplace_costs': 1017.7,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'disability': '30_55'})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_19_above_minimum_wage_illness_amount(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, no disability, 100 EUR illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 1100.0,
            'npd': 363.8,
            'gpm': 143.89,
            'employee_health_tax': 69.8,
            'employee_pension_tax': 125.2,
            'voluntary_sodra': 0.0,
            'neto': 761.11,
            'darbdavio_sodra': 19.47,
            'workplace_costs': 1119.47,
        }
        kwargs.update({'bruto': 1000.0, 'illness_amount': 100.0})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_20_above_minimum_wage_fixed_term(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, no disability, no illness amount,
        # contract is fixed term
        expected_values = {
            'bruto': 1000.0,
            'npd': 389.8,
            'gpm': 122.04,
            'employee_health_tax': 69.8,
            'employee_pension_tax': 125.2,
            'voluntary_sodra': 0.0,
            'neto': 682.96,
            'darbdavio_sodra': 24.9,
            'workplace_costs': 1024.9,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'is_fixed_term': True})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_21_exceeds_non_taxable_amount_wage(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, no disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 3000.0,
            'npd': 0.0,
            'gpm': 600.00,
            'employee_health_tax': 209.4,
            'employee_pension_tax': 375.6,
            'voluntary_sodra': 0.0,
            'neto': 1815,
            'darbdavio_sodra': 53.1,
            'workplace_costs': 3053.1,
        }
        kwargs['bruto'] = expected_values['bruto']
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_22_exceeds_non_taxable_amount_wage_exponential_sodra(self):
        kwargs = {'date': self.calculation_date}
        # Check the values with exponential additional voluntary SoDra, no disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 3000.0,
            'npd': 0.0,
            'gpm': 600.00,
            'employee_health_tax': 209.4,
            'employee_pension_tax': 375.6,
            'voluntary_sodra': 81.0,
            'neto': 1734,
            'darbdavio_sodra': 53.1,
            'workplace_costs': 3053.1,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'voluntary_pension': 'exponential'})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_23_exceeds_non_taxable_amount_wage_full_sodra(self):
        kwargs = {'date': self.calculation_date}
        # Check the values with full additional voluntary SoDra, no disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 3000.0,
            'npd': 0.0,
            'gpm': 600.00,
            'employee_health_tax': 209.4,
            'employee_pension_tax': 375.6,
            'voluntary_sodra': 90.0,
            'neto': 1725,
            'darbdavio_sodra': 53.1,
            'workplace_costs': 3053.1,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'voluntary_pension': 'full'})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_24_exceeds_non_taxable_amount_wage_0_25_disability(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, 0-25% disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 3000.0,
            'npd': 740,
            'gpm': 452.00,
            'employee_health_tax': 209.4,
            'employee_pension_tax': 375.6,
            'voluntary_sodra': 0.0,
            'neto': 1963,
            'darbdavio_sodra': 53.1,
            'workplace_costs': 3053.1,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'disability': '0_25'})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_25_exceeds_non_taxable_amount_wage_30_55_disability(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, 30-55% disability, no illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 3000.0,
            'npd': 690.0,
            'gpm': 462.00,
            'employee_health_tax': 209.4,
            'employee_pension_tax': 375.6,
            'voluntary_sodra': 0.0,
            'neto': 1953,
            'darbdavio_sodra': 53.1,
            'workplace_costs': 3053.1,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'disability': '30_55'})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_26_exceeds_non_taxable_amount_wage_illness_amount(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, no disability, 100 EUR illness amount,
        # contract is not fixed term
        expected_values = {
            'bruto': 3100.0,
            'npd': 0.0,
            'gpm': 615.00,
            'employee_health_tax': 209.4,
            'employee_pension_tax': 375.6,
            'voluntary_sodra': 0.0,
            'neto': 1900,
            'darbdavio_sodra': 54.87,
            'workplace_costs': 3154.87,
        }
        kwargs.update({'bruto': 3000.0, 'illness_amount': 100.0})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_27_exceeds_non_taxable_amount_wage_fixed_term(self):
        kwargs = {'date': self.calculation_date}
        # Check the values without additional voluntary SoDra, no disability, no illness amount,
        # contract is fixed term
        expected_values = {
            'bruto': 3000.0,
            'npd': 0.0,
            'gpm': 600.00,
            'employee_health_tax': 209.4,
            'employee_pension_tax': 375.6,
            'voluntary_sodra': 0.0,
            'neto': 1815,
            'darbdavio_sodra': 74.7,
            'workplace_costs': 3074.7,
        }
        kwargs.update({'bruto': expected_values['bruto'], 'is_fixed_term': True})
        payroll_values = self.HrPayroll.get_payroll_values(**kwargs)
        self._check_payroll_values_match_expected_values(payroll_values=payroll_values, expected_values=expected_values)

    def test_28_convert_under_minimum_NET_wage_to_GROSS(self):
        net_wage = 241.5
        expected_gross_wage = 300
        self._check_net_conversion(net_wage, expected_gross_wage)

    def test_29_convert_minimum_NET_wage_to_GROSS(self):
        net_wage = 480.41
        expected_gross_wage = 642
        self._check_net_conversion(net_wage, expected_gross_wage)

    def test_30_convert_above_minimum_NET_wage_to_GROSS(self):
        net_wage = 682.96
        expected_gross_wage = 1000
        self._check_net_conversion(net_wage, expected_gross_wage)

    def test_31_convert_exceeds_non_taxable_NET_wage_to_GROSS(self):
        net_wage = 1815
        expected_gross_wage = 3000
        self._check_net_conversion(net_wage, expected_gross_wage)

    def test_32_convert_exceeds_non_taxable_NET_wage_to_GROSS(self):
        net_wage = 1500
        expected_gross_wage = 2454.99
        self._check_net_conversion(net_wage, expected_gross_wage)
