# -*- coding: utf-8 -*-
import calendar
import logging
import math
import re
from datetime import datetime
from odoo.addons.l10n_lt_payroll.model.darbuotojai import correct_lithuanian_identification

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, tools, exceptions
from odoo.tools.translate import _

_logger = logging.getLogger(__name__)

SKYRIAI = [
    ('32', 'Akmenės skyriui'),
    ('11', 'Alytaus skyriui'),
    ('34', 'Anykščių skyriui'),
    ('12', 'Birštono skyriui'),
    ('36', 'Biržų skyriui'),
    ('15', 'Druskininkų skyriui'),
    ('42', 'Elektrėnų skyriui'),
    ('45', 'Ignalinos skyriui'),
    ('46', 'Jonavos skyriui'),
    ('47', 'Joniškio skyriui'),
    ('94', 'Jurbarko skyriui'),
    ('49', 'Kaišiadorių skyriui'),
    ('48', 'Kalvarijos skyriui'),
    ('nera', 'Karinių ir joms prilygintų struktūrų skyriui'),
    ('19', 'Kauno skyriui'),
    ('58', 'Kazlų Rūdos skyriui'),
    ('53', 'Kėdainių skyriui'),
    ('54', 'Kelmės skyriui'),
    ('21', 'Klaipėdos skyriui'),
    ('56', 'Kretingos skyriui'),
    ('57', 'Kupiškio skyriui'),
    ('59', 'Lazdijų skyriui'),
    ('18', 'Marijampolės skyriui'),
    ('61', 'Mažeikių skyriui'),
    ('62', 'Molėtų skyriui'),
    ('23', 'Neringos skyriui'),
    ('63', 'Pagėgių skyriui'),
    ('65', 'Pakruojo skyriui'),
    ('25', 'Palangos skyriui'),
    ('27', 'Panevėžio skyriui'),
    ('67', 'Pasvalio skyriui'),
    ('68', 'Plungės skyriui'),
    ('69', 'Prienų skyriui'),
    ('71', 'Radviliškio skyriui'),
    ('72', 'Raseinių skyriui'),
    ('74', 'Rietavo skyriui'),
    ('73', 'Rokiškio skyriui'),
    ('75', 'Skuodo skyriui'),
    ('84', 'Šakių skyriui'),
    ('85', 'Šalčininkų skyriui'),
    ('29', 'Šiaulių skyriui'),
    ('87', 'Šilalės skyriui'),
    ('88', 'Šilutės skyriui'),
    ('89', 'Širvintų skyriui'),
    ('86', 'Švenčionių skyriui'),
    ('77', 'Tauragės skyriui'),
    ('78', 'Telšių skyriui'),
    ('79', 'Trakų skyriui'),
    ('81', 'Ukmergės skyriui'),
    ('82', 'Utenos skyriui'),
    ('38', 'Varėnos skyriui'),
    ('39', 'Vilkaviškio skyriui'),
    ('13', 'Vilniaus skyriui'),
    ('30', 'Visagino skyriui'),
    ('43', 'Zarasų skyriui'),
    ('41', 'Vilniaus r.'),
]

SKYRIAI_VALUES = {
    '32': 'Akmenės skyriui',
    '11': 'Alytaus skyriui',
    '34': 'Anykščių skyriui',
    '12': 'Birštono skyriui',
    '36': 'Biržų skyriui',
    '15': 'Druskininkų skyriui',
    '42': 'Elektrėnų skyriui',
    '45': 'Ignalinos skyriui',
    '46': 'Jonavos skyriui',
    '47': 'Joniškio skyriui',
    '94': 'Jurbarko skyriui',
    '49': 'Kaišiadorių skyriui',
    '48': 'Kalvarijos skyriui',
    'nera': 'Karinių ir joms prilygintų struktūrų skyriui',
    '19': 'Kauno skyriui',
    '58': 'Kazlų Rūdos skyriui',
    '53': 'Kėdainių skyriui',
    '54': 'Kelmės skyriui',
    '21': 'Klaipėdos skyriui',
    '56': 'Kretingos skyriui',
    '57': 'Kupiškio skyriui',
    '59': 'Lazdijų skyriui',
    '18': 'Marijampolės skyriui',
    '61': 'Mažeikių skyriui',
    '62': 'Molėtų skyriui',
    '23': 'Neringos skyriui',
    '63': 'Pagėgių skyriui',
    '65': 'Pakruojo skyriui',
    '25': 'Palangos skyriui',
    '27': 'Panevėžio skyriui',
    '67': 'Pasvalio skyriui',
    '68': 'Plungės skyriui',
    '69': 'Prienų skyriui',
    '71': 'Radviliškio skyriui',
    '72': 'Raseinių skyriui',
    '74': 'Rietavo skyriui',
    '73': 'Rokiškio skyriui',
    '75': 'Skuodo skyriui',
    '84': 'Šakių skyriui',
    '85': 'Šalčininkų skyriui',
    '29': 'Šiaulių skyriui',
    '87': 'Šilalės skyriui',
    '88': 'Šilutės skyriui',
    '89': 'Širvintų skyriui',
    '86': 'Švenčionių skyriui',
    '77': 'Tauragės skyriui',
    '78': 'Telšių skyriui',
    '79': 'Trakų skyriui',
    '81': 'Ukmergės skyriui',
    '38': 'Varėnos skyriui',
    '39': 'Vilkaviškio skyriui',
    '13': 'Vilniaus skyriui',
    '30': 'Visagino skyriui',
    '43': 'Zarasų skyriui',
    '41': 'Vilniaus r.',
}


class SAM_pasiruosimas(models.Model):

    _inherit = 'res.company'

    draudejo_kodas = fields.Char(string='Draudėjo kodas')

    def get_sodra_data(self):
        company = self.env.user.company_id
        pareigu_pavadinimas = u'Įgaliotas asmuo'
        findir = company.findir
        findir_name = findir.name or ''
        phone_number = findir.work_phone
        # findir_data_list = [findir_name, findir.login, phone_number]
        findir_data_list = [findir_name, findir.login]
        findir_data = '; '.join(d for d in findir_data_list if d) or ''
        return {'job_title': pareigu_pavadinimas or '',
                'findir_name': findir_name or '',
                'findir_data': findir_data or '',
                'phone_number': phone_number or '',
                'draudejo_kodas': company.draudejo_kodas or '',
                }

    @api.multi
    def get_sanitized_sodra_name(self, to_sanitize):
        self.ensure_one()
        index = None
        work_forms = ['uab', 'mb', 'vsi', 'vši', 'všį', 'ab']
        w_form = str()
        for work_form in work_forms:
            if work_form in to_sanitize.lower():
                index = to_sanitize.lower().find(work_form)
                w_form = work_form
                break
        if index is not None:
            sanitize_rules = [',', '.', '"']
            if not index:
                form, name = to_sanitize.split(' ', 1)
            else:
                form = to_sanitize[index: index + len(w_form)]
                name = to_sanitize.replace(form, '')
            for rule in sanitize_rules:
                name = name.replace(rule, '')
            name = name.strip()
            sanitized_name = '{0} "{1}"'.format(form.upper(), name)
        else:
            sanitized_name = to_sanitize
        return sanitized_name[:68]


SAM_pasiruosimas()


class SAMDownloadLine(models.TransientModel):

    _name = 'sam.download.line'

    download_id = fields.Many2one('sd2.download', required=True, ondelete='cascade')
    file = fields.Binary(string='Dokumentas', readonly=True)
    file_name = fields.Char(string='Failo pavadinimas')
    url = fields.Char(string='URL')

    @api.multi
    def open(self):
        self.ensure_one()
        if self.url:
            return {
                'type': 'ir.actions.act_url',
                'url': self.url,
                'target': 'new',
                'context': {'on_close': False},
            }


SAMDownloadLine()


class SAM(models.TransientModel):

    _name = 'e.sodra.sam'

    def _pradzia(self):
        metai = datetime.utcnow().year
        menuo = datetime.utcnow().month - 1
        if menuo == 0:
            metai -= 1
            menuo = 12
        return datetime(metai, menuo, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _pabaiga(self):
        metai = datetime.utcnow().year
        menuo = datetime.utcnow().month - 1
        if menuo == 0:
            metai -= 1
            menuo = 12
        return datetime(metai, menuo, calendar.monthrange(metai, menuo)[1]).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    def auto_load1(self):
        if 'failas1' in self._context.keys():
            return self._context['failas1']
        else:
            return ''

    @api.multi
    def auto_load2(self):
        if 'failas2' in self._context.keys():
            return self._context['failas2'] and self._context['failas2'] or ''
        else:
            return ''

    def _failo_pavadinimas1(self):
        return 'SAM1.ffdata'

    def _failo_pavadinimas2(self):
        return 'SAM2.ffdata'

    def _metai(self):
        return str(datetime.utcnow().year)

    def _menuo(self):
        return str(datetime.utcnow().month)

    def _company_id(self):
        return self.env.user.company_id.id

    def default_download_line_ids(self):
        lines = []
        failai = self._context.get('failai', [])
        urls = self._context.get('urls', [])
        for i, failas in enumerate(failai):
            val = {'file': failas,
                   'file_name': 'SAM%s.ffdata' % (i+1),
                   }
            if urls and str(i) in urls:
                val['url'] = urls[str(i)]
            lines.append((0, 0, val))
        return lines

    data_nuo = fields.Date(string='Periodas nuo', default=_pradzia, required=True)
    data_iki = fields.Date(string='Periodas iki', default=_pabaiga, required=True)
    patikslinta = fields.Boolean(string='Ar patikslinta ataskaita?', default=False)
    metai = fields.Char(string='Metai', default=_metai)
    menuo = fields.Char(string='Mėnuo', default=_menuo)
    failas1 = fields.Binary(string='SAM', readonly=True, default=auto_load1)
    failas2 = fields.Binary(string='SAM su 1%', readonly=True, default=auto_load2)
    failo_pavadinimas1 = fields.Char(string='Failo pavadinimas', default=_failo_pavadinimas1)
    failo_pavadinimas2 = fields.Char(string='Failo pavadinimas', default=_failo_pavadinimas2)
    company_id = fields.Many2one('res.company', string='Kompanija', default=_company_id, required=True)
    skyrius = fields.Selection(SKYRIAI, string='Padalinys', default='13', required=True)
    download_line_ids = fields.One2many('sam.download.line', 'download_id', default=default_download_line_ids, readonly=True)
    warning_message = fields.Html(string='Informacinio pranešimo tekstas', default='<span style="color: red">Paskaičiavus pagal įmokų sumą ir apmokestinamą sumą nesutampa įmokų tarifas!</span>')
    show_warning_message = fields.Boolean(string='Rodyti informacinį pranešimą', default=False)

    @api.onchange('data_nuo')
    def onchange_data_nuo(self):
        if self.data_nuo:
            self.menuo = str(datetime.strptime(self.data_nuo, tools.DEFAULT_SERVER_DATE_FORMAT).month) or str(datetime.utcnow().month)

    @api.onchange('company_id')
    def onchange_company(self):
        if self.company_id:
            self.skyrius = self.company_id.savivaldybe

    @api.multi
    def sam(self):
        REPORT_HEADER = \
'''<?xml version="1.0" encoding="UTF-8"?>
<FFData Version="1" CreatedByApp="Robo" CreatedByLogin="Robo" CreatedOn="%(created_on)s">
    <Form FormDefId="{963BF380-47C3-4B69-A7F7-1B4593572CFE}">
        <DocumentPages>
            <Group Name="Forma">
                <ListPages>
                    <ListPage>SAM</ListPage>
                </ListPages>
                <Group Name="Priedas SAM3SD">
                    <ListPages>
                        <ListPage>SAM3SD</ListPage>
                    </ListPages>
                </Group>
                <Group Name="Priedas SAM3SDP">
                    <ListPages>
                        <ListPage>SAM3SDP</ListPage>
                    </ListPages>
                </Group>
            </Group>
        </DocumentPages>
        <Pages Count="%(pages_count)i">'''

        SAM_PAGE = \
'''         
            <Page PageDefName="SAM" PageNumber="1">
                <Fields Count="27">
                    <Field Name="InsurerName">%(insurer_name)s</Field>
                    <Field Name="InsurerCode">%(insurer_code)s</Field>
                    <Field Name="JuridicalPersonCode">%(juridical_person_code)s</Field>
                    <Field Name="InsurerPhone">%(insurer_phone)s</Field>
                    <Field Name="InsurerAddress">%(insurer_address)s</Field>
                    <Field Name="DocDate">%(doc_date)s</Field>
                    <Field Name="DocNumber"></Field>
                    <Field Name="CycleYear">%(cycle_year)s</Field>
                    <Field Name="CycleMonth">%(cycle_month)s</Field>
                    <Field Name="RevisedDocument">%(revised_document)d</Field>
                    <Field Name="RevisedCycleYear">%(revised_cycle_year)s</Field>
                    <Field Name="RevisedCycleMonth">%(revised_cycle_month)s</Field>
                    <Field Name="Appendixes2">1</Field>
                    <Field Name="Apdx2PageCount">%(apdx2_page_count)s</Field>
                    <Field Name="Apdx2PersonCount">%(apdx2_person_count)s</Field>
                    <Field Name="Apdx2InsIncomeSum">%(apdx2_ins_income_sum)s</Field>
                    <Field Name="Apdx2PaymentSum">%(apdx2_payment_sum)s</Field>
                    <Field Name="Appendixes3">0</Field>
                    <Field Name="Apdx3PageCount">1</Field>
                    <Field Name="Apdx3PersonCount"></Field>
                    <Field Name="Apdx3InsIncomeSum"></Field>
                    <Field Name="Apdx3PaymentSum"></Field>
                    <Field Name="ApdxPageCountTotal">%(apdx_page_count_total)s</Field>
                    <Field Name="ManagerFullName">%(manager_full_name)s</Field>
                    <Field Name="PreparatorDetails">%(preparator_details)s</Field>
                    <Field Name="FormCode">SAM</Field>
                    <Field Name="FormVersion">07</Field>
                </Fields>
            </Page>'''

        SAM3SD_PAGE = \
'''         
            <Page PageDefName="SAM3SD" PageNumber="%(page_number)i">
                <Fields Count="63">
                    %(main_fields)s
                    %(footer_fields)s
                </Fields>
            </Page>'''

        SAM3SD_PERSON_FIELDS = \
'''         
                    <Field Name="RowNumber_%(row)i">%(row)i</Field>
                    <Field Name="PersonCode_%(row)i">%(person_code)s</Field>
                    <Field Name="InsuranceSeries_%(row)i">%(insurer_series)s</Field>
                    <Field Name="InsuranceNumber_%(row)i">%(insurer_number)s</Field>
                    <Field Name="InsIncomeSum_%(row)i">%(ins_income_sum)s</Field>
                    <Field Name="TaxRate_%(row)i">%(tax_rate)s</Field>
                    <Field Name="PaymentSum_%(row)i">%(payment_sum)s</Field>
                    <Field Name="PersonFirstName_%(row)i">%(person_first_name)s</Field>
                    <Field Name="PersonLastName_%(row)i">%(person_last_name)s</Field>'''

        SAM3SD_FOOTER_FIELDS = \
'''<Field Name="InsIncomePage">%(ins_income_page)s</Field>
                    <Field Name="PaymentPage">%(payment_page)s</Field>
                    <Field Name="InsurerCode">%(insurer_code)s</Field>
                    <Field Name="PageNumber">%(prev_page_number)i</Field>
                    <Field Name="PageTotal">%(page_total)i</Field>
                    <Field Name="DocDate">%(doc_date)s</Field>
                    <Field Name="DocNumber"></Field>
                    <Field Name="FormCode">SAM3SD</Field>
                    <Field Name="FormVersion">07</Field>'''

        REPORT_FOOTER = \
'''     
        </Pages>
    </Form>
</FFData>'''

        EMPLOYEES_PER_PAGE = 6

        # Find contracts without the exclude from SAM report flag for the specified period
        contracts = self.env['hr.contract'].with_context(active_test=False).search([
            ('employee_id.exclude_from_sam', '=', False),
            ('date_start', '<=', self.data_iki),
            '|',
            ('date_end', '>=', self.data_iki),
            ('date_end', '=', False)
        ])

        # Include only non-internship contracts that don't end, end after data_iki or end the work relation
        contracts = contracts.filtered(lambda contract: not contract.is_internship_contract and
                    (
                        not contract.date_end or
                        contract.date_end > self.data_iki or
                        contract.date_end != contract.work_relation_end_date
                    )
        )

        page_amount = int(math.ceil(len(contracts) / float(EMPLOYEES_PER_PAGE))) + 1
        MAIN_SAM_REPORT = REPORT_HEADER % {'created_on': datetime.now().strftime("%Y-%m-%d"), 'pages_count': page_amount}

        company = self.company_id
        elpastas = company.findir.partner_id.email
        if len(elpastas) > 68:
            elpastas = elpastas[:68]
        ataskaitine_data = datetime.strptime(self.data_iki, tools.DEFAULT_SERVER_DATE_FORMAT)
        company_data = company.get_sodra_data()
        imones_kodas = company.company_registry or ''
        if imones_kodas and len(imones_kodas) > 9:
            imones_kodas = ''
        elif imones_kodas and imones_kodas != ''.join(re.findall(r'\d+', imones_kodas)):
            imones_kodas = ''
        company_name = company.get_sanitized_sodra_name(self._context.get('force_company_name', company.name) or '')
        draudejo_kodas = self._context.get('force_draudejo_kodas', company.draudejo_kodas) or ''
        imones_kodas = self._context.get('force_imones_kodas', imones_kodas) or ''
        telefonas = self._context.get('force_telefonas', company_data.get('phone_number')) or ''
        if draudejo_kodas and not draudejo_kodas.isdigit():
            draudejo_kodas = ''
        if imones_kodas and not imones_kodas.isdigit():
            imones_kodas = ''
        if not company_name or not draudejo_kodas or not imones_kodas:
            raise exceptions.UserError(_('Nenurodyta kompanijos informacija'))

        SAM_DATA = {
            'insurer_name': company_name,
            'insurer_code': draudejo_kodas,
            'juridical_person_code': imones_kodas,
            'insurer_phone': telefonas,
            'insurer_address': elpastas,
            'doc_date': datetime.now().strftime("%Y-%m-%d"),
            'cycle_year': ataskaitine_data.year if not self.patikslinta else '',
            'cycle_month': ataskaitine_data.month if not self.patikslinta else '',
            'revised_document': 1 if self.patikslinta else 0,
            'revised_cycle_year': self.metai if self.patikslinta else '',
            'revised_cycle_month': self.menuo if self.patikslinta else '',
            'apdx2_page_count': page_amount - 1,
            'apdx2_person_count': len(contracts),
            'apdx2_ins_income_sum': '%(apdx2_ins_income_sum)s',
            'apdx2_payment_sum': '%(apdx2_payment_sum)s',
            'apdx_page_count_total': page_amount - 1,
            'manager_full_name': company_data.get('findir_name') or '',
            'preparator_details': company_data.get('findir_data') and company_data.get('findir_data')[:68] or '',
        }
        MAIN_SAM_REPORT += SAM_PAGE % SAM_DATA

        viso_apmokestinama_suma = 0
        viso_mokama_suma = 0

        page = 2
        row = 1
        main_fields = ''
        page_apmokestinama_suma = 0
        page_imoku_suma = 0
        for contract in contracts:
            if row == 1:
                MAIN_SAM_REPORT += SAM3SD_PAGE % {
                    'page_number': page,
                    'main_fields': '%(main_fields)s',
                    'footer_fields': '%(footer_fields)s',
                }
                main_fields = ''

                page_apmokestinama_suma = 0
                page_imoku_suma = 0

            employee = contract.employee_id

            slips = self.env['hr.payslip'].search([('employee_id', '=', employee.id),
                                                   ('contract_id', '=', contract.id),
                                                   ('date_from', '<=', self.data_nuo),
                                                   ('date_to', '>=', self.data_iki),
                                                   ('credit_note', '=', False),
                                                   ('state', '=', 'done')])

            apmokestinama_suma = 0
            imoku_suma = 0
            payslip_lines_obj = self.env['hr.payslip.line']
            if len(slips) > 1:
                slips = slips[-1:]
            menb = payslip_lines_obj.search([('slip_id', '=', slips.id), ('code', '=', 'MEN')])
            if len(menb) <= 0:
                menb = payslip_lines_obj.search([('slip_id', '=', slips.id), ('code', '=', 'VAL')])
            liga = payslip_lines_obj.search([('slip_id', '=', slips.id), ('code', '=', 'L')])
            if menb and liga:
                apmokestinama_suma += menb.total - liga.total
            sodra_codes = ['SDB', 'SDP', 'EMPLRSDB', 'EMPLRSDP', 'EMPLRSDDMAIN']
            if slips.date_to < '2018-06-30':
                sodra_codes.append('SDD')
            else:
                sodra_codes.append('SDDMAIN')
            sodra = payslip_lines_obj.search([('slip_id', '=', slips.id), ('code', 'in', sodra_codes)])
            if len(sodra) > 0:
                for s in sodra:
                    imoku_suma += s.total

            employee_rate = contract.with_context(date=self.data_iki).effective_employee_tax_rate_proc_sodra
            employer_rate = contract.with_context(date=self.data_iki).effective_employer_tax_rate_proc

            page_apmokestinama_suma += apmokestinama_suma
            page_imoku_suma += imoku_suma
            viso_apmokestinama_suma += apmokestinama_suma
            viso_mokama_suma += imoku_suma

            employee_name = employee.get_split_name()
            tax_rate = employee_rate + employer_rate
            is_correct_identification_id = correct_lithuanian_identification(employee.identification_id or '')
            main_fields += SAM3SD_PERSON_FIELDS % {
                'row': row,
                'person_code': employee.identification_id.strip() if is_correct_identification_id else '',
                'insurer_series': employee.sodra_id and employee.sodra_id[:2] or '',
                'insurer_number': employee.sodra_id and employee.sodra_id[2:].strip() or '',
                'ins_income_sum': ('%.2f' % apmokestinama_suma).replace('.', ','),
                'tax_rate': ('%.2f' % tax_rate).replace('.', ','),
                'payment_sum': ('%.2f' % imoku_suma).replace('.', ','),
                'person_first_name': employee_name['first_name'],
                'person_last_name': employee_name['last_name'],
            }

            try:
                calc = (tax_rate / 100 * apmokestinama_suma)
            except:
                calc = 0.0
            diff = abs(imoku_suma - calc)
            if tools.float_compare(diff, 0.01, precision_digits=2) > 0:
                self.warning_message = '<span style="color: red">Paskaičiavus pagal įmokų sumą ir apmokestinamą sumą nesutampa darbuotojo %s %s įmokų tarifas! (%s != %s)</span>' % (employee_name['first_name'], employee_name['last_name'], imoku_suma, calc)
                self.show_warning_message = True



            if row >= EMPLOYEES_PER_PAGE:
                footer = SAM3SD_FOOTER_FIELDS % {
                    'ins_income_page': ('%.2f' % page_apmokestinama_suma).replace('.', ','),
                    'payment_page': ('%.2f' % page_imoku_suma).replace('.', ','),
                    'insurer_code': draudejo_kodas,
                    'prev_page_number': (page - 1),
                    'page_total': EMPLOYEES_PER_PAGE,
                    'doc_date': datetime.now().strftime("%Y-%m-%d"),
                }
                MAIN_SAM_REPORT = MAIN_SAM_REPORT % {
                    'main_fields': main_fields,
                    'footer_fields': footer,
                    'apdx2_ins_income_sum': '%(apdx2_ins_income_sum)s',
                    'apdx2_payment_sum': '%(apdx2_payment_sum)s',
                }
                row = 0
                page_apmokestinama_suma = 0
                page_imoku_suma = 0
                page += 1
            row += 1

        if (row - 1) != EMPLOYEES_PER_PAGE:
            contract_amount = row
            for m in range(row, EMPLOYEES_PER_PAGE+1):
                main_fields += SAM3SD_PERSON_FIELDS % {
                    'row': m,
                    'person_code': '',
                    'insurer_series': '',
                    'insurer_number': '',
                    'ins_income_sum': '',
                    'tax_rate': '',
                    'payment_sum': '',
                    'person_first_name': '',
                    'person_last_name': '',
                }

            footer = SAM3SD_FOOTER_FIELDS % {
                'ins_income_page': ('%.2f' % page_apmokestinama_suma).replace('.', ','),
                'payment_page': ('%.2f' % page_imoku_suma).replace('.', ','),
                'insurer_code': draudejo_kodas,
                'prev_page_number': (page - 1),
                'page_total': contract_amount,
                'doc_date': datetime.now().strftime("%Y-%m-%d"),
            }
            MAIN_SAM_REPORT = MAIN_SAM_REPORT % {
                'main_fields': main_fields,
                'footer_fields': footer,
                'apdx2_ins_income_sum': '%(apdx2_ins_income_sum)s',
                'apdx2_payment_sum': '%(apdx2_payment_sum)s',
            }
        MAIN_SAM_REPORT += REPORT_FOOTER

        MAIN_SAM_REPORT = MAIN_SAM_REPORT % {
            'apdx2_ins_income_sum': ('%.2f' % viso_apmokestinama_suma).replace('.', ','),
            'apdx2_payment_sum': ('%.2f' % viso_mokama_suma).replace('.', ','),
        }
        Failai = [MAIN_SAM_REPORT]
        # -------------------------------
        for failas in Failai:
            attach_vals1 = {'res_model': 'res.company',
                            'name': 'SAM1.ffdata',
                            'datas_fname': 'SAM1.ffdata',
                            'res_id': company.id,
                            'type': 'binary',
                            'datas': failas.encode('utf8').encode('base64')}
            self.env['ir.attachment'].sudo().create(attach_vals1)
        # --------------------------------------
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'e.sodra.sam',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'view_id': self.env.ref('sodra.sodra_sam_download').id,
            'target': 'new',
            'context': {'failai': map(lambda r: r and r.encode('utf8').encode('base64'), Failai),
                        'default_show_warning_message': self.show_warning_message,
                        'default_warning_message': self.warning_message},
        }

    def send(self):
        res = self.sam()
        urls = {}
        if res and 'context' in res and res['context'] and 'failai' in res['context']:
            failai = res.get('context', {}).get('failai', [])
            for i, failas in enumerate(failai):
                client = self.env.user.get_sodra_api()
                file_name = 'SAM-'+str(i+1)+'-'+datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)+'.ffdata'
                upload = client.service.uploadEdasDraft(file_name, failas)
                if upload and type(upload) == tuple and upload[0] in [500, 403]:
                    client = self.sudo().env.user.get_sodra_api()
                    upload = client.service.uploadEdasDraft(file_name, failas)
                if upload and type(upload) == tuple:
                    try:
                        data = dict(upload[1])
                    except Exception as exc:
                        _logger.info('SODRA SAM ERROR: %s' % str(exc.args))
                        try:
                            error_msg = '{} {}'.format(str(upload[0]), str(upload[1]))
                        except Exception as exc:
                            _logger.info('SODRA SAM ERROR: %s' % str(exc.args))
                            raise exceptions.UserError(_('Nenumatyta klaida, bandykite dar kartą.'))
                        raise exceptions.UserError(_('Klaida iš SODRA centrinio serverio: %s' % error_msg))
                    ext_id = data.get('docUID', False)
                    if ext_id:
                        state = 'sent' if upload[0] in [500, 403] else 'confirmed'
                        vals = {
                            'doc_name': 'SAM',
                            'signing_url': data.get('signingURL', False),
                            'ext_id': ext_id,
                            'upload_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                            'last_update_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                            'state': state,
                            'document_date': self.data_nuo
                        }
                        self.env['sodra.document.export'].create(vals)
                if upload and type(upload) == tuple and upload[0] in [500, 403]:
                    _logger.info('Exception: %s' % str(upload))
                    if len(upload) > 1:
                        try:
                            raise exceptions.UserError(upload[1]['detail']['dataServiceFault']['errorMsg'])
                        except AttributeError:
                            try:
                                raise exceptions.UserError(upload[1]['dataServiceFault']['errorMsg'])
                            except AttributeError:
                                raise exceptions.UserError(_('Nenumatyta klaida'))
                elif upload and type(upload) == tuple and upload[0] == 200:
                    url = upload[1]['signingURL']
                    urls[i] = url
        if urls:
            res['context']['urls'] = urls
            res['context']['sodra'] = True
            return res


SAM()
