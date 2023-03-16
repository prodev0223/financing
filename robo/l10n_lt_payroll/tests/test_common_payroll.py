from odoo.tests import tagged, SingleTransactionCase
from odoo.tools import float_round


@tagged('post_install', 'robo', 'payroll')
class TestCommonPayroll(SingleTransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestCommonPayroll, cls).setUpClass()

        cls.createDepartmentAndJob()

        cls.createEmployeeForMonthlySalaryStructure()
        cls.createEmployeeForHourlySalaryStructure()

        cls.createContractForMonthlySalaryStructureEmployee()
        cls.createContractForHourlySalaryStructureEmployee()

    @classmethod
    def createDepartmentAndJob(cls):
        # Create a programmer job
        cls.programmer_job = cls.env['hr.job'].create({'name': 'Programmer'})
        # Create an IT department
        cls.it_department = cls.env['hr.department'].create({'name': 'IT'})

    @classmethod
    def createEmployeeForMonthlySalaryStructure(cls):
        # Create a new employee for the monthly salary structure
        cls.monthly_salary_structure_employee = cls.env['hr.employee'].create({
            'name': "Employee With Monthly Salary Structure",
            'identification_id': '39006010013',
            'department_id': cls.it_department.id,
            'job_id': cls.programmer_job.id,
            'work_email': 'monthly.salary.structure.employee@robolabs.lt',
            'type': 'employee',
            'robo_access': False,
            'robo_group': 'employee',
        })

    @classmethod
    def createEmployeeForHourlySalaryStructure(cls):
        # Create a new employee for the monthly salary structure
        cls.hourly_salary_structure_employee = cls.env['hr.employee'].create({
            'name': "Employee With Hourly Salary Structure",
            'identification_id': '39006020013',
            'department_id': cls.it_department.id,
            'job_id': cls.programmer_job.id,
            'work_email': 'hourly.salary.structure.employee@robolabs.lt',
            'type': 'employee',
            'robo_access': False,
            'robo_group': 'employee',
        })

    @staticmethod
    def getFixedAttendanceValues():
        # Prepare schedule attendance values. 5 days per week, 8-12 and 13-17 (8 hrs total)
        fixed_attendance_values = [(5,)]
        for i in range(0, 5):
            fixed_attendance_values += [
                (0, 0, {'hour_from': 8.0, 'hour_to': 12.0, 'dayofweek': str(i)}),
                (0, 0, {'hour_from': 13.0, 'hour_to': 17.0, 'dayofweek': str(i)})
            ]
        return fixed_attendance_values

    @classmethod
    def createContractForMonthlySalaryStructureEmployee(cls):
        # Find appropriate salary structure
        monthly_salary_structure = cls.env['hr.payroll.structure'].search([('code', '=', 'MEN')], limit=1)

        fixed_attendance_values = cls.getFixedAttendanceValues()

        # Create two schedule templates, one for monthly salary and one for hourly.
        monthly_schedule_template = cls.env['schedule.template'].create({
            'template_type': 'fixed',
            'etatas_stored': 1.0,
            'work_norm': 1.0,
            'wage_calculated_in_days': True,
            'shorter_before_holidays': True,
            'fixed_attendance_ids': fixed_attendance_values,
            'work_week_type': 'five_day'
        })

        # Create contract and appointment
        cls.monthly_salary_structure_contract = cls.env['hr.contract.create'].create({
            'employee_id': cls.monthly_salary_structure_employee.id,
            'job_id': cls.programmer_job.id,
            'struct_id': monthly_salary_structure.id,
            'date_start': '2021-12-01',
            'date_end': False,
            'wage': 700.0,
            'rusis': 'neterminuota',
            'sodra_papildomai': False,
            'trial_date_end': False,
            'use_npd': True,
            'schedule_template_id': monthly_schedule_template.id,
            'avansu_politika': False,
            'freeze_net_wage': False,
            'order_date': '2021-11-26',
        }).with_context(no_action=True).create_contract()

    @classmethod
    def createContractForHourlySalaryStructureEmployee(cls):
        # Find appropriate salary structure
        hourly_salary_structure = cls.env['hr.payroll.structure'].search([('code', '=', 'VAL')], limit=1)

        # Create schedule template
        hourly_schedule_template = cls.env['schedule.template'].create({
            'template_type': 'sumine',
            'etatas_stored': 0.5,
            'work_norm': 0.95,
            'wage_calculated_in_days': False,
            'shorter_before_holidays': False,
            'work_week_type': 'five_day'
        })

        # Create contract and appointment
        cls.hourly_salary_structure_contract = cls.env['hr.contract.create'].create({
            'employee_id': cls.hourly_salary_structure_employee.id,
            'job_id': cls.programmer_job.id,
            'struct_id': hourly_salary_structure.id,
            'date_start': '2021-12-01',
            'date_end': False,
            'wage': 4.0,
            'rusis': 'neterminuota',
            'sodra_papildomai': False,
            'trial_date_end': False,
            'use_npd': True,
            'schedule_template_id': hourly_schedule_template.id,
            'avansu_politika': False,
            'freeze_net_wage': False,
            'order_date': '2021-11-26',
        }).with_context(no_action=True).create_contract()

    def test_00_monthly_salary_structure_appointment_created(self):
        appointment = self.env['hr.contract.appointment'].search([
            ('employee_id', '=', self.monthly_salary_structure_employee.id),
            ('date_start', '=', '2021-12-01')
        ], limit=1)
        self.assertIsNotNone(
            appointment, 'Appointment for employee working by monthly salary structure was not created'
        )
        wage = float_round(appointment.wage, precision_digits=2)
        self.assertEqual(wage, 700.0)

    def test_01_hourly_salary_structure_appointment_created(self):
        appointment = self.env['hr.contract.appointment'].search([
            ('employee_id', '=', self.hourly_salary_structure_employee.id),
            ('date_start', '=', '2021-12-01')
        ], limit=1)
        self.assertIsNotNone(
            appointment, 'Appointment for employee working by hourly salary structure was not created'
        )
        wage = float_round(appointment.wage, precision_digits=2)
        self.assertEqual(wage, 4.0)
