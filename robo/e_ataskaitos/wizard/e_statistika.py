# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta
from odoo.addons.l10n_lt_payroll.model.payroll_codes import PAYROLL_CODES

from odoo import models, fields, api, tools, _

NUOSAVYBE = [
    ('11', 'Valstybės ar savivaldybės nuosavybė sudaro  50% ir daugiau subjekto įstatinio kapitalo'),
    ('12',
     'Valstybės ar savivaldybės nuosavybė sudaro 50% ir daugiau subjekto įstatinio kapitalo ir yra užsienio investuotojų kapitalo'),
    ('21', 'Privati nuosavybė, nėra užsienio investuotojų kapitalo'),
    ('22', 'Privati nuosavybė, yra užsienio investuotojų kapitalo'),
    ('23', 'Privati nuosavybė, kurioje užsienio nuosavybė sudaro daugiau kaip 50% subjekto įstatinio kapitalo'),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    da01_report_teachers_and_medical_staff_job_ids = fields.Many2many('hr.job',
                                                                      relation='rel_da01_report_teachers_and_medical_staff_job_ids',
                                                                      string='Gydytojų ir mokytojų pareigos')


ResCompany()


class DA01(models.TransientModel):
    _name = 'e.stat.da01'

    def _company_id(self):
        return self.env.user.company_id.id

    def _pradzia(self):
        now = datetime.utcnow()
        ketvirtis = ((now.month - 1) // 3) + 1
        metai = now.year
        menuo = ketvirtis * 3 - 3 + 1
        return datetime(metai, menuo, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _pabaiga(self):
        now = datetime.utcnow()
        ketvirtis = ((now.month - 1) // 3) + 1
        metai = now.year
        menuo = ketvirtis * 3
        return (datetime(metai, menuo, 1) + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    def auto_load(self):
        return self._context['failas'] if 'failas' in self._context.keys() else ''

    def failo_pavadinimas(self):
        return 'DA-01.ffdata'

    def default_teachers_and_medical_staff_job_ids(self):
        return self.env.user.company_id.da01_report_teachers_and_medical_staff_job_ids.mapped('id')

    company_id = fields.Many2one('res.company', string='Kompanija', default=_company_id, required=True)
    data_nuo = fields.Date(string='Periodą nuo', default=_pradzia, required=True)
    data_iki = fields.Date(string='Periodas iki', default=_pabaiga, required=True)
    failas = fields.Binary(string='Ataskaitos dokumentas', readonly=True, default=auto_load)
    failo_pavadinimas = fields.Char(string='Failo pavadinimas', default=failo_pavadinimas)
    nuosavybes_kodas = fields.Selection(NUOSAVYBE, string='Nuosavybės forma', default='21', required=True)
    employees_change = fields.Selection(
        [('often', _('Didelė')), ('not_often', _('Nedidelė'))],
        string='Darbuotojų kaita',
        default='not_often',
        required=True,
        help='Priklausomai nuo pasirinkimo, skirtingai paskaičiuojamas vidutinis ne pilną darbo laiką dirbančių darbuotojų skaičius'
    )
    teachers_and_medical_staff_job_ids = fields.Many2many(
        'hr.job',
        relation='rel_teachers_and_medical_staff_job_ids',
        string='Gydytojų ir mokytojų pareigos',
        default=default_teachers_and_medical_staff_job_ids,
        help='Darbuotojai pagal šias pareigas bus traukiami į mokytojų ar gydytojų statistikos stulpelį'
    )
    end_of_quarter_number_of_vacancies_available = fields.Integer(
        string='Laisvų darbo vietų skaičius paskutinę ketvirčio darbo dieną',
        required=True,
        default=0.0
    )

    @api.multi
    def da01(self):
        company = self.sudo().env.user.company_id
        company.write({
            'da01_report_teachers_and_medical_staff_job_ids': [
                (6, 0, self.teachers_and_medical_staff_job_ids.mapped('id'))]
        })

        NOT_INCLUDED_EMPLOYEES_HOLIDAY_STATUS = [
            self.env.ref('hr_holidays.holiday_status_G').id,
            self.env.ref('hr_holidays.holiday_status_KT').id,
            self.env.ref('hr_holidays.holiday_status_VP').id
        ]

        def _strf(date):
            return date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        def _strft(date):
            return date.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

        def _dt(date):
            try:
                formatted = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
            except:
                formatted = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            return formatted

        def find_partial_worked_time_employees(date_dt):
            date_start = _strft(date_dt + relativedelta(hour=0, minute=0, second=0))
            date_end = _strft(date_dt + relativedelta(hour=23, minute=59, second=59))

            date_holidays = holidays.filtered(lambda h: h.date_from <= date_end and h.date_to >= date_start)
            employees_on_holiday_ids = date_holidays.mapped('employee_id.id')

            partial_appointments = self.env['hr.contract.appointment'].search([('schedule_template_id.etatas_stored', '<', 1.0),
                                                                               ('employee_id.id', 'not in', employees_on_holiday_ids),
                                                                               ('date_start', '<=', date_end),
                                                                              '|',
                                                                               ('date_end', '=', False),
                                                                               ('date_end', '>=', date_start)
                                                                               ])
            return partial_appointments.mapped('employee_id')

        def filter_employees(employees):
            return {
                'all': employees,
                'female': employees.filtered(lambda e: e.gender == 'female'),
                'special': employees.filtered(
                    lambda e: e.job_id.id in self.teachers_and_medical_staff_job_ids.mapped('id'))
            }

        max_date_from = _strft(_dt(self.data_nuo) + relativedelta(hour=0, minute=0, second=0))
        max_date_to = _strft(_dt(self.data_iki) + relativedelta(days=1, hour=0, minute=0, second=0))

        HrPayslip = self.env['hr.payslip']
        HrEmployee = self.env['hr.employee']

        holidays = self.env['hr.holidays'].search([
            ('date_from', '<', max_date_to),
            ('date_to', '>=', max_date_from),
            ('holiday_status_id', 'in', NOT_INCLUDED_EMPLOYEES_HOLIDAY_STATUS)
        ])

        employees_not_worked_full_time = HrEmployee

        if self.employees_change == 'often':
            date_from_dt = _dt(self.data_nuo)
            date_to_dt = _dt(self.data_iki)

            empl_count = {
                'all': 0.0,
                'female': 0.0,
                'special': 0.0
            }

            while date_from_dt <= date_to_dt:
                date_employees = find_partial_worked_time_employees(date_from_dt)

                filtered_employees = filter_employees(date_employees)
                employees_not_worked_full_time |= filtered_employees.get('all', HrEmployee)
                all_empl_len = len(filtered_employees.get('all', HrEmployee).mapped('id'))
                female_empl_len = len(filtered_employees.get('female', HrEmployee).mapped('id'))
                special_empl_len = len(filtered_employees.get('special', HrEmployee).mapped('id'))
                empl_count.update({
                    'all': empl_count.get('all', 0.0) + all_empl_len,
                    'female': empl_count.get('female', 0.0) + female_empl_len,
                    'special': empl_count.get('special', 0.0) + special_empl_len,
                })
                date_from_dt += relativedelta(days=1)

            quarter_day_length = float((_dt(self.data_iki) - _dt(self.data_nuo)).days) + 1

            avg_empl_count = {
                'all': empl_count.get('all', 0.0) / quarter_day_length,
                'female': empl_count.get('female', 0.0) / quarter_day_length,
                'special': empl_count.get('special', 0.0) / quarter_day_length
            }
        else:
            half_date_count = {
                'all': 0.0,
                'female': 0.0,
                'special': 0.0
            }
            full_date_count = {
                'all': 0.0,
                'female': 0.0,
                'special': 0.0
            }

            half_dates = [
                self.data_nuo,
                self.data_iki
            ]
            full_dates = [
                _strf(_dt(self.data_nuo) + relativedelta(day=31)),
                _strf(_dt(self.data_nuo) + relativedelta(months=1, day=31)),
            ]
            for date in half_dates + full_dates:
                date_employees = find_partial_worked_time_employees(_dt(date))

                filtered_employees = filter_employees(date_employees)
                employees_not_worked_full_time |= filtered_employees.get('all', HrEmployee)
                all_empl_len = len(filtered_employees.get('all', HrEmployee).mapped('id'))
                female_empl_len = len(filtered_employees.get('female', HrEmployee).mapped('id'))
                special_empl_len = len(filtered_employees.get('special', HrEmployee).mapped('id'))
                if date in half_dates:
                    half_date_count.update({
                        'all': half_date_count.get('all', 0.0) + all_empl_len,
                        'female': half_date_count.get('female', 0.0) + female_empl_len,
                        'special': half_date_count.get('special', 0.0) + special_empl_len,
                    })
                else:
                    full_date_count.update({
                        'all': full_date_count.get('all', 0.0) + all_empl_len,
                        'female': full_date_count.get('female', 0.0) + female_empl_len,
                        'special': full_date_count.get('special', 0.0) + special_empl_len,
                    })

            avg_empl_count = {
                'all': (half_date_count.get('all', 0.0) / 2.0 + full_date_count.get('all', 0.0)) / 3.0,
                'female': (half_date_count.get('female', 0.0) / 2.0 + full_date_count.get('female', 0.0)) / 3.0,
                'special': (half_date_count.get('special', 0.0) / 2.0 + full_date_count.get('special', 0.0)) / 3.0
            }

        avg_empl_count = {
            'all': round(avg_empl_count.get('all', 0.0), 2),
            'female': round(avg_empl_count.get('female', 0.0), 2),
            'special': round(avg_empl_count.get('special', 0.0), 2)
        }

        all_payslips = HrPayslip.search([
            ('date_from', '<=', self.data_iki),
            ('date_to', '>=', self.data_nuo),
            ('state', '=', 'done'),
        ])
        all_employees = filter_employees(all_payslips.mapped('employee_id'))
        partial_employees = filter_employees(employees_not_worked_full_time)
        partial_payslips = all_payslips.filtered(
            lambda s: s.employee_id.id in partial_employees.get('all', HrEmployee).mapped('id'))

        all_slips = {
            'all': all_payslips,
            'female': all_payslips.filtered(
                lambda s: s.employee_id.id in all_employees.get('female', HrEmployee).mapped('id')),
            'special': all_payslips.filtered(
                lambda s: s.employee_id.id in all_employees.get('special', HrEmployee).mapped('id')),
        }

        partial_slips = {
            'all': partial_payslips,
            'female': partial_payslips.filtered(
                lambda s: s.employee_id.id in partial_employees.get('female', HrEmployee).mapped('id')),
            'special': partial_payslips.filtered(
                lambda s: s.employee_id.id in partial_employees.get('special', HrEmployee).mapped('id')),
        }

        LIGA_CODE = 'L'

        all_slip_worked_hours = {
            'all': sum(all_slips.get('all', HrPayslip).mapped('worked_days_line_ids').filtered(
                lambda l: l.code != LIGA_CODE).mapped('number_of_hours')),
            'female': sum(all_slips.get('female', HrPayslip).mapped('worked_days_line_ids').filtered(
                lambda l: l.code != LIGA_CODE).mapped('number_of_hours')),
            'special': sum(all_slips.get('special', HrPayslip).mapped('worked_days_line_ids').filtered(
                lambda l: l.code != LIGA_CODE).mapped('number_of_hours')),
        }

        partial_slip_worked_hours = {
            'all': sum(partial_slips.get('all', HrPayslip).mapped('worked_days_line_ids').filtered(
                lambda l: l.code != LIGA_CODE).mapped('number_of_hours')),
            'female': sum(partial_slips.get('female', HrPayslip).mapped('worked_days_line_ids').filtered(
                lambda l: l.code != LIGA_CODE).mapped('number_of_hours')),
            'special': sum(partial_slips.get('special', HrPayslip).mapped('worked_days_line_ids').filtered(
                lambda l: l.code != LIGA_CODE).mapped('number_of_hours')),
        }

        INCLUDED_HOUR_CODES = PAYROLL_CODES['NORMAL']

        total_worked_time_lines = all_slips.get('all', HrPayslip).mapped('worked_days_line_ids').filtered(
            lambda l: l.code in INCLUDED_HOUR_CODES)
        total_worked_time = sum(total_worked_time_lines.mapped('number_of_hours'))

        all_slip_line_ids = all_slips.get('all', HrPayslip).mapped('line_ids').filtered(
            lambda l: not tools.float_is_zero(l.total, precision_digits=2))

        dont_include_codes = ['IST', 'AK'] + ['NTR'] + ['KM'] + ['L']

        all_lines = all_slip_line_ids
        all_du_amount = sum(all_lines.filtered(lambda r: r.code in ['MEN', 'VAL']).mapped('total')) - \
                        sum(all_lines.filtered(lambda r: r.code in dont_include_codes).mapped('total'))
        all_female_lines = all_slips.get('female', HrPayslip).mapped('line_ids')
        all_female_du_amount = sum(all_female_lines.filtered(lambda r: r.code in ['MEN', 'VAL']).mapped('total')) - \
                               sum(all_female_lines.filtered(lambda r: r.code in dont_include_codes).mapped('total'))
        all_special_lines = all_slips.get('special', HrPayslip).mapped('line_ids')
        all_special_du_amount = sum(all_special_lines.filtered(lambda r: r.code in ['MEN', 'VAL']).mapped('total')) - \
                                sum(all_special_lines.filtered(lambda r: r.code in dont_include_codes).mapped('total'))

        all_bruto = {
            'all': all_du_amount,
            'female': all_female_du_amount,
            'special': all_special_du_amount
        }

        bonus_codes = ['P', 'PNVDU', 'KR', 'MA', 'PD', 'PDN', 'PR', 'PRI', 'PDNM']  # TODO Compensations?
        bonus_amount = sum(all_slip_line_ids.filtered(lambda l: l.code in bonus_codes).mapped('total'))
        not_worked_enough_amount = sum(all_slip_line_ids.filtered(lambda l: l.code in ['NDL', 'PN']).mapped(
            'total'))
        subsidijos_amount = 0.0  # TODO What is this

        partial_bruto = sum(
            partial_slips.get('all', HrPayslip).mapped('line_ids').filtered(lambda r: r.code in ['MEN', 'VAL']).mapped(
                'total'))

        iseitines_and_holidays_amounts = sum(
            all_slip_line_ids.filtered(lambda l: l.code in ['IST', 'AK']).mapped('total'))
        natura_amounts = sum(all_slip_line_ids.filtered(lambda l: l.code in ['NTR']).mapped('total'))

        savanoriskas_draudimas_amount = 0.0  # TODO ??
        darbdavio_ismokos_amount = sum(all_slip_line_ids.filtered(lambda l: l.code in ['L']).mapped('total'))

        if self.company_id.partner_id.street:
            adresas = self.company_id.partner_id.street + ', ' + self.company_id.partner_id.city or ''
            if len(adresas) > 129:
                adresas = adresas[:129]
        else:
            adresas = ' '

        pavad = self.company_id.name or ''
        if len(pavad) > 129:
            pavad = pavad[:129]

        company = self.company_id
        vadovas = company.with_context(date=self.data_iki).vadovas

        ketvirtis = ((_dt(self.data_nuo).month - 1) // 3) + 1

        DATA = {
            # FIRST PAGE START
            'pavadinimas': pavad,
            'periodo_metai': datetime.strptime(self.data_iki, tools.DEFAULT_SERVER_DATE_FORMAT).strftime("%Y"),
            'periodo_ketvirtis': ketvirtis,
            'pildymo_data': datetime.now().strftime("%Y-%m-%d"),
            'imones_kodas': company.company_registry,
            'adresas': adresas,
            'nuosavybes_kodas': self.nuosavybes_kodas or '21',
            'evrk': (self.company_id.evrk.code or '')[-6:] if company.evrk else '',
            'evrk_pavadinimas': company.evrk.name if company.evrk else '',
            # FIRST PAGE END

            # SECOND PAGE START
            'laisvu_darbo_vietu': self.end_of_quarter_number_of_vacancies_available,
            'nevisas_darbas_drb_skaicius': int(round(avg_empl_count.get('all', 0.0), 0)),
            'nevisas_darbas_drb_skaicius_mot': int(round(avg_empl_count.get('female', 0.0), 0)),
            'nevisas_darbas_drb_skaicius_special': int(round(avg_empl_count.get('special', 0.0), 0)),
            'apmoketos_h': int(round(all_slip_worked_hours.get('all', 0.0), 0)),
            'apmoketos_h_mot': int(round(all_slip_worked_hours.get('female', 0.0), 0)),
            'apmoketos_h_special': int(round(all_slip_worked_hours.get('special', 0.0), 0)),
            'nevisas_darbo_h': int(round(partial_slip_worked_hours.get('all', 0.0), 0)),
            'nevisas_darbo_h_mot': int(round(partial_slip_worked_hours.get('female', 0.0), 0)),
            'nevisas_darbo_h_special': int(round(partial_slip_worked_hours.get('special', 0.0), 0)),
            'faktiskai_dirbtos_h': int(round(total_worked_time, 0)),
            'bruto_DU': int(round(all_bruto.get('all', 0.0), 0)),
            'bruto_DU_mot': int(round(all_bruto.get('female', 0.0), 0)),
            'bruto_DU_special': int(round(all_bruto.get('special', 0.0), 0)),
            'premijos_priedai': int(round(bonus_amount, 0)),
            'priverstinai_trumpesnis_laikas': int(round(not_worked_enough_amount, 0)),
            'subsidijos_du': int(round(subsidijos_amount, 0)),
            'bruto_DU_nevisa_darbo_laika': int(round(partial_bruto, 0)),
            'iseitines_nepanaud_atostogos': int(round(iseitines_and_holidays_amounts, 0)),
            'natura': int(round(natura_amounts, 0)),
            'savanoriskas_draudimas': int(round(savanoriskas_draudimas_amount, 0)),
            'ligos_pasalpos_is_darbdavio': int(round(darbdavio_ismokos_amount, 0)),
            # SECOND PAGE END

            # THIRD PAGE START
            'vadovas': vadovas.job_id.name if vadovas and vadovas.job_id else '',
            'vadovo_vardas': vadovas.name if vadovas else '',
            'telefonas': company.phone or '',
            'epastas': company.email or '',
            # THIRD PAGE END
        }

        XML = '''<?xml version="1.0" encoding="UTF-8"?>
            <FFData Version="1" CreatedByApp="Odoo" CreatedByLogin="Robolabs" CreatedOn="%(pildymo_data)s">
                <Form FormDefId="{6ADF147B-0603-4086-BD39-C88D4764D5E6}">
                    <DocumentPages>
                        <Group Name="Visa forma">
                            <ListPages>
                                <ListPage>DA01_1</ListPage>
                                <ListPage>DA01_2</ListPage>
                                <ListPage>DA01_3</ListPage>
                            </ListPages>
                        </Group>
                    </DocumentPages>
                    <Pages Count="3">
                        <Page PageDefName="DA01_1" PageNumber="1">
                            <Fields Count="10">
                                <Field Name="B_MM_Pavad">%(pavadinimas)s</Field>
                                <Field Name="B_Metai">%(periodo_metai)s</Field>
                                <Field Name="B_Ketv">%(periodo_ketvirtis)s</Field>
                                <Field Name="B_UzpildData">%(pildymo_data)s</Field>
                                <Field Name="B_Nr"></Field>
                                <Field Name="B_MM_ID">%(imones_kodas)s</Field>
                                <Field Name="B_MM_Adresas">%(adresas)s</Field>
                                <Field Name="B_MM_Nuosav">%(nuosavybes_kodas)s</Field>
                                <Field Name="EVRK_Kodas">%(evrk)s</Field>
                                <Field Name="EVRK_Pavad">%(evrk_pavadinimas)s</Field>
                            </Fields>
                        </Page>
                        <Page PageDefName="DA01_2" PageNumber="2">
                            <Fields Count="24">
                                <Field Name="B_MM_ID">%(imones_kodas)s</Field>
                                <Field Name="B_Ketv">%(periodo_ketvirtis)s</Field>
                                <Field Name="D1-1">%(laisvu_darbo_vietu)s</Field>
                                <Field Name="D1-2">%(nevisas_darbas_drb_skaicius)d</Field>
                                <Field Name="D2-2">%(nevisas_darbas_drb_skaicius_mot)d</Field>
                                <Field Name="D3-2">%(nevisas_darbas_drb_skaicius_special)d</Field>
                                <Field Name="D1-3">%(apmoketos_h)d</Field>
                                <Field Name="D2-3">%(apmoketos_h_mot)d</Field>
                                <Field Name="D3-3">%(apmoketos_h_special)d</Field>
                                <Field Name="D1-4">%(nevisas_darbo_h)s</Field>
                                <Field Name="D2-4">%(nevisas_darbo_h_mot)s</Field>
                                <Field Name="D3-4">%(nevisas_darbo_h_special)s</Field>
                                <Field Name="D1-5">%(faktiskai_dirbtos_h)s</Field>
                                <Field Name="D1-6">%(bruto_DU)s</Field>
                                <Field Name="D2-6">%(bruto_DU_mot)s</Field>
                                <Field Name="D3-6">%(bruto_DU_special)s</Field>
                                <Field Name="D1-7">%(premijos_priedai)s</Field>
                                <Field Name="D1-8">%(priverstinai_trumpesnis_laikas)s</Field>
                                <Field Name="D1-9">%(subsidijos_du)s</Field>
                                <Field Name="D1-10">%(bruto_DU_nevisa_darbo_laika)s</Field>
                                <Field Name="D1-11">%(iseitines_nepanaud_atostogos)s</Field>
                                <Field Name="D1-12">%(natura)s</Field>
                                <Field Name="D1-14">%(savanoriskas_draudimas)s</Field>
                                <Field Name="D1-15">%(ligos_pasalpos_is_darbdavio)s</Field>
                            </Fields>
                        </Page>
                        <Page PageDefName="DA01_3" PageNumber="3">
                            <Fields Count="20">
                                <Field Name="B_MM_ID">%(imones_kodas)s</Field>
                                <Field Name="B_Ketv">%(periodo_ketvirtis)s</Field>
                                <Field Name="D1">0</Field>
                                <Field Name="D2">0</Field>
                                <Field Name="D3">0</Field>
                                <Field Name="D4">0</Field>
                                <Field Name="D5">0</Field>
                                <Field Name="D6">0</Field>
                                <Field Name="D7">0</Field>
                                <Field Name="D8">0</Field>
                                <Field Name="D9">0</Field>
                                <Field Name="D10">0</Field>
                                <Field Name="DT16"></Field>
                                <Field Name="Pastabos"></Field>
                                <Field Name="B_Val"></Field>
                                <Field Name="B_Min"></Field>
                                <Field Name="B_MM_Vadovas">%(vadovas)s</Field>
                                <Field Name="B_MM_VardPav">%(vadovo_vardas)s</Field>
                                <Field Name="B_MM_Tel">%(telefonas)s</Field>
                                <Field Name="B_MM_Epastas">%(epastas)s</Field>
                            </Fields>
                        </Page>
                    </Pages>
                </Form>
            </FFData>
        ''' % DATA

        # -------------------------------
        attach_vals = {
            'res_model': 'res.company',
            'name': 'DA-01.ffdata',
            'datas_fname': 'DA-01.ffdata',
            'res_id': company.id,
            'type': 'binary',
            'datas': XML.encode('utf8').encode('base64')}
        self.env['ir.attachment'].sudo().create(attach_vals)
        # --------------------------------------

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'e.stat.da01',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'nodestroy': True,
            'target': 'new',
            'context': {'failas': XML.encode('utf8').encode('base64')},
        }


DA01()
