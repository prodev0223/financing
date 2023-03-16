# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions, _
from datetime import datetime
from dateutil.relativedelta import relativedelta
import re
import logging

_logger = logging.getLogger(__name__)

valstybiuKodaiEU = [
    ('IE', 'Airija'),
    ('AT', 'Austrija'),
    ('BY', 'Baltarusija'),
    ('BE', 'Belgija'),
    ('BG', 'Bulgarija'),
    ('CZ', 'Čekija'),
    ('DK', 'Danija'),
    ('GB', 'Didžioji Britanija'),
    ('EE', 'Estija'),
    ('GR', 'Graikija'),
    ('IS', 'Islandija'),
    ('ES', 'Ispanija'),
    ('IT', 'Italija'),
    ('CA', 'Kanada'),
    ('CY', 'Kipras'),
    ('LV', 'Latvija'),
    ('PL', 'Lenkija'),
    ('LI', 'Lichtenšteinas'),
    ('LT', 'Lietuva'),
    ('LU', 'Liuksemburgas'),
    ('MT', 'Malta'),
    ('NL', 'Nyderlandai'),
    ('NO', 'Norvegija'),
    ('PT', 'Portugalija'),
    ('FR', 'Prancūzija'),
    ('RO', 'Rumunija'),
    ('SK', 'Slovakija'),
    ('SI', 'Slovėnija'),
    ('FI', 'Suomija'),
    ('SE', 'Švedija'),
    ('CH', 'Šveicarija'),
    ('UA', 'Ukraina'),
    ('HU', 'Vengrija'),
    ('DE', 'Vokietija'),
]

valstybesEU = {
    'IE': 'AIRIJA',
    'AT': 'AUSTRIJA',
    'BY': 'BALTARUSIJA',
    'BE': 'BELGIJA',
    'BG': 'BULGARIJA',
    'CZ': 'ČEKIJA',
    'DK': 'DANIJA',
    'GB': 'DIDŽIOJI BRITANIJA',
    'EE': 'ESTIJA',
    'GR': 'GRAIKIJA',
    'IS': 'ISLANDIJA',
    'ES': 'ISPANIJA',
    'IT': 'ITALIJA',
    'CA': 'KANADA',
    'CY': 'KIPRAS',
    'LV': 'LATVIJA',
    'PL': 'LENKIJA',
    'LI': 'LICHTENŠTEINAS',
    'LT': 'LIETUVA',
    'LU': 'LIUKSEMBURGAS',
    'MT': 'MALTA',
    'NL': 'NYDERLANDAI',
    'NO': 'NORVEGIJA',
    'PT': 'PORTUGALIJA',
    'FR': 'PRANCŪZIJA',
    'RO': 'RUMUNIJA',
    'SK': 'SLOVAKIJA',
    'SI': 'SLOVĖNIJA',
    'FI': 'SUOMIJA',
    'SE': 'ŠVEDIJA',
    'CH': 'ŠVEICARIJA',
    'UA': 'UKRAINA',
    'HU': 'VENGRIJA',
    'DE': 'VOKIETIJA',
}
valstybiuKodaiKitos = [
    ('BY', 'Baltarusija'),
    ('CA', 'Kanada'),
    ('UA', 'Ukraina'),
    ('RU', 'Rusija'),
    ('US', 'JAV'),
]

valstybesKitos = {
    'BY': 'BALTARUSIJA',
    'CA': 'KANADA',
    'UA': 'UKRAINA',
    'RU': 'RUSIJA',
    'US': 'JAV',
}

PranesimoPriezasciuKodai = [
    ('01', 'priėmimas į darbą (pagal darbo sutartį)'),
    ('03', 'reorganizavimas'),
    ('05', 'socialinė apsauga pagal Europos Sąjungos Reglamentus'),
    ('06', 'socialinė apsauga pagal dvišalę sutartį'),
    ('07', 'valstybės tarnautojo perkėlimas (kitoje valstybėje)'),
    ('08', 'valstybės tarnautojo perkėlimas (Lietuvoje)'),
    ('09', 'valstybės lėšomis draudžiamas sutuoktinis'),
    ('10', 'darbo biržos siųstas praktikantas'),
    ('11', 'švietimo įstaigos praktikantas'),
    ('12', 'dvasininkas'),
    ('13', 'privalomoji pradinė karo tarnyba'),
    ('14', 'perkėlimas į kitą struktūrinį padalinį'),
    ('15', 'priėmimas į pareigas valstybės tarnyboje'),
    ('17', 'savanoriška praktika'),
    ('18', 'kursantas'),
    ('19', 'užsienietis su viza'),
    ('20', 'kariūnas'),
    ('96', 'darbo sutarties rūšies priskyrimas/pakeitimas'),
    ('99', 'kiti atvejai'),

]

PranesimoPriezastys = {
    '01': 'priėmimas į darbą (pagal darbo sutartį)',
    '03': 'reorganizavimas',
    '05': 'socialinė apsauga pagal Europos Sąjungos Reglamentus',
    '06': 'socialinė apsauga pagal dvišalę sutartį',
    '07': 'valstybės tarnautojo perkėlimas (kitoje valstybėje)',
    '08': 'valstybės tarnautojo perkėlimas (Lietuvoje)',
    '09': 'valstybės lėšomis draudžiamas sutuoktinis',
    '10': 'darbo biržos siųstas praktikantas',
    '11': 'švietimo įstaigos praktikantas',
    '12': 'dvasininkas',
    '13': 'privalomoji pradinė karo tarnyba',
    '14': 'perkėlimas į kitą struktūrinį padalinį',
    '15': 'priėmimas į pareigas valstybės tarnyboje',
    '17': 'savanoriška praktika',
    '18': 'kursantas',
    '19': 'užsienietis su viza',
    '20': 'kariūnas',
    '96': 'darbo sutarties rūšies priskyrimas/pakeitimas',
    '99': 'kiti atvejai',
}

sutarciu_tipai_map = {
     'neterminuota': '01',
     'terminuota': '02',
     'laikina_terminuota': '03',
     'laikina_neterminuota': '03',
     'pameistrystes': '04',
     'projektinio_darbo': '05',
     'vietos_dalijimosi': '06',
     'keliems_darbdaviams': '07',
     'sezoninio': '08',
}

sutarciu_tipai = {
    '01': 'neterminuota darbo sutartis',
    '02': 'terminuota darbo sutartis',
    '03': 'laikinojo darbo sutartis',
    '04': 'pameistrystės darbo sutartis',
    '05': 'projektinio darbo sutartis',
    '06': 'darbo vietos dalijimosi darbo sutartis',
    '07': 'darbo keliems darbdaviams sutartis',
    '08': 'sezoninio darbo sutartis',
}

SD1_FORM = '''<?xml version="1.0" encoding="UTF-8"?>
<FFData Version="1" CreatedOn="{created_on}" CreatedByApp="ROBO" CreatedByLogin="ROBO">
    <Form FormDefId="{form_id}">
        <DocumentPages>
            <Group Name="Forma">
                <ListPages>
                    <ListPage>1-SD</ListPage>
                </ListPages>
                {form_extension_groups}
            </Group>
        </DocumentPages>
        <Pages Count="{total_number_of_pages}">
            {pages}
        </Pages>
    </Form>
</FFData>
'''

SD1_PAGE_EXTENSION_GROUP_DECLARATION = '''<Group Name="Tęsinys">
    <ListPages>
        <ListPage>1-SD-T</ListPage>
    </ListPages>
</Group>
'''

SD1_PAGE = '''<Page PageDefName="{page_def_name}" PageNumber="{page_number}">
    <Fields Count="{page_field_count}">
        {page_fields}
    </Fields>
</Page>
'''

SD1_FORM_FIELDS = '''<Field Name="InsurerName">{insurer_name}</Field>
<Field Name="JuridicalPersonCode">{company_code}</Field>
<Field Name="InsurerPhone">{phone}</Field>
<Field Name="InsurerAddress">{address}</Field>
<Field Name="PersonCountTotal">{person_count}</Field>
<Field Name="ManagerFullName">{accountant_name}</Field>
<Field Name="PreparatorDetails">{preparator_details}</Field>
'''  # 7 Fields that only appear on the first page

SD1_PAGE_INFO_FIELDS = '''<Field Name="PageNumber">{page_number}</Field>
<Field Name="PageTotal">{total_number_of_pages}</Field>
<Field Name="InsurerCode">{insurer_code}</Field>
<Field Name="DocDate">{document_date}</Field>
<Field Name="DocNumber">{document_number}</Field>
<Field Name="FormCode">1-SD</Field>
<Field Name="FormVersion">{form_version}</Field>
'''  # 7 Fields related to form info that are on each page

SD1_PAGE_EMPLOYEE_FIELDS = '''<Field Name="RowNumber_{row_number}">{row_number}</Field>
<Field Name="PersonCode_{row_number}">{person_code}</Field>
<Field Name="PersonBirthDate_{row_number}">{birth_date}</Field>
<Field Name="InsuranceSeries_{row_number}">{insurance_series}</Field>
<Field Name="InsuranceNumber_{row_number}">{insurance_number}</Field>
<Field Name="InsuranceStartDate_{row_number}">{insurance_start_date}</Field>
<Field Name="PersonFirstName_{row_number}">{first_name}</Field>
<Field Name="PersonLastName_{row_number}">{last_name}</Field>
<Field Name="U1Group_{row_number}">{u1_group}</Field>
<Field Name="PersonForeignCode_{row_number}">{person_foreign_code}</Field>
<Field Name="PersonProfession_1_{row_number}">{profession_1}</Field>
<Field Name="PersonProfession_2_{row_number}">{profession_2}</Field>
<Field Name="PersonProfession_3_{row_number}">{profession_3}</Field>
<Field Name="PersonProfession_4_{row_number}">{profession_4}</Field>
<Field Name="ReasonCode_{row_number}">{reason_code}</Field>
<Field Name="ReasonText_{row_number}">{reason_text}</Field>
<Field Name="ReasonDetCode_{row_number}">{reason_det_code}</Field>
<Field Name="ReasonDetText_{row_number}">{reason_det_text}</Field>
<Field Name="ReasonDetTypeCode_{row_number}">{reason_det_type_code}</Field>
<Field Name="ReasonDetTypeText_{row_number}">{reason_det_type_text}</Field>
'''  # 20 Fields for each employee

SD1_PAGE_BLANK_FIELDS = '''<Field Name="RowNumber_{row_number}"></Field>
<Field Name="PersonCode_{row_number}"/>
<Field Name="PersonBirthDate_{row_number}"/>
<Field Name="InsuranceSeries_{row_number}"/>
<Field Name="InsuranceNumber_{row_number}"/>
<Field Name="InsuranceStartDate_{row_number}"/>
<Field Name="PersonFirstName_{row_number}"/>
<Field Name="PersonLastName_{row_number}"/>
<Field Name="U1Group_{row_number}"/>
<Field Name="PersonForeignCode_{row_number}"/>
<Field Name="PersonProfession_1_{row_number}"/>
<Field Name="PersonProfession_2_{row_number}"/>
<Field Name="PersonProfession_3_{row_number}"/>
<Field Name="PersonProfession_4_{row_number}"/>
<Field Name="ReasonCode_{row_number}"/>
<Field Name="ReasonText_{row_number}"/>
<Field Name="ReasonDetCode_{row_number}"/>
<Field Name="ReasonDetText_{row_number}"/>
<Field Name="ReasonDetTypeCode_{row_number}"/>
<Field Name="ReasonDetTypeText_{row_number}"/>
'''


class DarboKodai(models.Model):

    _name = 'darbo.kodai'

    kodas = fields.Char(string='Profesijos Kodas', required=True)
    name = fields.Char(string='Aprašymas', required=True)


DarboKodai()


class Sd1(models.TransientModel):

    _name = 'e.sodra.sd1'

    def _company_id(self):
        return self.env.user.company_id

    def _pradzia(self):
        return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _siandiena(self):
        return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _pabaiga(self):
        return (datetime.utcnow() + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    def auto_load(self):
        if 'failas' in self._context.keys():
            return self._context['failas']
        else:
            return ''

    def failo_pavadinimas(self):
        return 'sd1.ffdata'

    company_id = fields.Many2one('res.company', string='Kompanija', default=_company_id, required=True)
    data_nuo = fields.Date(string='Periodas nuo', default=_pradzia, required=True)
    data_iki = fields.Date(string='Periodas iki', default=_pabaiga, required=True)
    failas = fields.Binary(string='Ataskaitos dokumentas', readonly=True, default=auto_load)
    failo_pavadinimas = fields.Char(string='Failo pavadinimas', default=failo_pavadinimas)
    dokumento_data = fields.Date(string='Dokumento Data', default=_siandiena, required=True)

    @api.multi
    def sd1(self):
        contracts = self.env['hr.contract'].search([('date_start', '>=', self.data_nuo), ('date_start', '<=', self.data_iki)])
        all_contracts = self.env['hr.contract'].search([('employee_id', 'in', contracts.mapped('employee_id.id')), ('date_end', '<=', self.data_iki), ('date_end', '>=', self.data_nuo)])
        pradedantys_dabar = []
        voluntary_internships = []
        educational_internships = []
        sutarties_pasikeitimas = []
        for contract in contracts:
            if not contract.employee_id:
                continue
            if contract.employee_id.id in pradedantys_dabar:
                continue
            # todo: is there a better way to know if it's a new contract or a change? We could check for eDocument? Or check for SD2?
            # previous_contract = self.env['hr.contract'].search([('employee_id', '=', contract.employee_id.id),
            #                                                     ('date_start', '<', contract.date_start),
            #                                                     '|',
            #                                                         ('date_end', '=', False),
            #                                                         ('date_end', '<=', contract.date_start)], limit=1)
            # if previous_contract:
            #     continue
            possible_prev_contract_date_end = (datetime.strptime(contract.date_start, tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            prev_contract = all_contracts.filtered(lambda c: c.employee_id.id == contract.employee_id.id and c.date_end == possible_prev_contract_date_end)
            if prev_contract and contract.employee_id.id not in sutarties_pasikeitimas and prev_contract.rusis != contract.rusis:
                sutarties_pasikeitimas.append(contract.employee_id.id)
            if contract.rusis == 'voluntary_internship':
                voluntary_internships.append(contract.employee_id.id)
            if contract.rusis == 'educational_internship':
                educational_internships.append(contract.employee_id.id)
            pradedantys_dabar.append(contract.employee_id.id)
        ctx = {}
        if len(pradedantys_dabar) > 0:
            ctx = self._context.copy()
            if ctx is None:
                ctx = {}
            ctx.update({
                'pradedantys': pradedantys_dabar,
                'pasikeitimai': sutarties_pasikeitimas,
                'voluntary_internships': voluntary_internships,
                'educational_internships': educational_internships,
            })
        ctx.update({
            'company_id': self.company_id.id,
            'dokumento_data': self.dokumento_data,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sodra.darbuotojai',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'view_id': self.env.ref('sodra.sodra_sd1_kitas_meniu').id,
            'context': ctx,
            }


Sd1()


class DarbuotojoParametrai(models.TransientModel):

    _name = 'sodra.parametrai'

    sodra_id = fields.Many2one('sodra.darbuotojai', string='Sodros parametrai', required=True, ondelete='cascade')

    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', required=True, ondelete='cascade')
    priezastis = fields.Selection(PranesimoPriezasciuKodai, string='Priežastis', required=True)

    kodas1 = fields.Many2one('darbo.kodai', string='Profesijos kodas')
    kodas2 = fields.Many2one('darbo.kodai', string=' ')
    kodas3 = fields.Many2one('darbo.kodai', string=' ')
    kodas4 = fields.Many2one('darbo.kodai', string=' ')

    domenas1 = fields.Char(string='Domenas', default='zzz')
    domenas2 = fields.Char(string='Domenas', default='zzz')
    domenas3 = fields.Char(string='Domenas', default='zzz')
    patikslinimoKodas5 = fields.Selection(valstybiuKodaiEU, string='Patikslinimo kodas', default=False)
    patikslinimoKodas6 = fields.Selection(valstybiuKodaiKitos, string='Patikslinimo kodas', default=False)
    patikslinimoKodas10_11 = fields.Char(string='Patikslinimo kodas')
    patikslinimoPaaiskinimas = fields.Char(string='Patikslinimo paaiškinimas')
    pranesimoPriezastisKiti = fields.Char(string='Pranešimo priežastis')

    @api.onchange('priezastis')
    def change(self):
        if self.priezastis in ['09', '10', '11', '12', '13', '17']:
            if not self.employee_id.job_id.kodas1:
                self.kodas1 = False
            if not self.employee_id.job_id.kodas2:
                self.kodas2 = False
            if not self.employee_id.job_id.kodas3:
                self.kodas3 = False
            if not self.employee_id.job_id.kodas4:
                self.kodas4 = False
        self.patikslinimoKodas5 = False
        self.patikslinimoKodas6 = False
        self.patikslinimoKodas10_11 = self.employee_id.contract_id.educational_institution_code if \
            self.priezastis == '11' else False
        self.patikslinimoPaaiskinimas = False
        self.pranesimoPriezastisKiti = False

    @api.onchange('patikslinimoKodas10_11')
    def change1(self):
        self.patikslinimoPaaiskinimas = False

    @api.onchange('employee_id')
    def change_employee(self):
        if self.employee_id.job_id.kodas1:
            self.kodas1 = self.employee_id.job_id.kodas1
        else:
            self.kodas1 = False

    @api.onchange('kodas1')
    def loadsarasas2(self):
        if self.kodas1:
            self.domenas1 = self.kodas1.kodas + '_'
        if self.employee_id.job_id.kodas2 and self.kodas1:
            self.kodas2 = self.employee_id.job_id.kodas2
            self.domenas2 = False
            self.domenas3 = False
            self.kodas3 = False
            self.kodas4 = False
        else:
            self.domenas2 = False
            self.domenas3 = False
            self.kodas2 = False
            self.kodas3 = False
            self.kodas4 = False

    @api.onchange('kodas2')
    def loadsarasas3(self):
        if self.kodas2:
            self.domenas2 = self.kodas2.kodas + '_'
        if self.employee_id.job_id.kodas3 and self.kodas2:
            self.kodas3 = self.employee_id.job_id.kodas3
            self.domenas3 = False
            self.kodas4 = False
        else:
            self.domenas3 = False
            self.kodas3 = False
            self.kodas4 = False

    @api.onchange('kodas3')
    def loadsarasas4(self):
        if self.kodas3:
            self.domenas3 = self.kodas3.kodas + '_'
        if self.employee_id.job_id.kodas4 and self.kodas3:
            self.kodas4 = self.employee_id.job_id.kodas4
        else:
            self.kodas4 = False

    @api.onchange('patikslinimoKodas5')
    def change2(self):
        if not self.patikslinimoKodas5:
            self.patikslinimoPaaiskinimas = False
        else:
            self.patikslinimoPaaiskinimas = valstybesEU[self.patikslinimoKodas5]

    @api.onchange('patikslinimoKodas6')
    def change3(self):
        if not self.patikslinimoKodas6:
            self.patikslinimoPaaiskinimas = False
        else:
            self.patikslinimoPaaiskinimas = valstybesEU[self.patikslinimoKodas6]


DarbuotojoParametrai()


class DarbuotojuParametrai(models.TransientModel):

    _name = 'sodra.darbuotojai'

    def paimam_context(self):
        employees_whose_contracts_changed = self._context.get('pasikeitimai', [])
        voluntary_internships = self._context.get('voluntary_internships', [])
        educational_internships = self._context.get('educational_internships', [])
        if 'pradedantys' in self._context.keys():
            darbuotojai = self._context['pradedantys']
            employee_ids = self.env['hr.employee'].browse(darbuotojai)
            parametrai = []
            for darbuotojas in darbuotojai:
                employee_id = employee_ids.filtered(lambda d: d.id == darbuotojas)
                priezastis = '01'
                if employee_id.id in employees_whose_contracts_changed:
                    priezastis = '96'
                elif employee_id.id in voluntary_internships:
                    priezastis = '17'
                elif employee_id.id in educational_internships:
                    priezastis = '11'
                values = {
                    'employee_id': darbuotojas,
                    'priezastis': priezastis,
                    'kodas1': employee_id.job_id.kodas1.id,
                    'kodas2': employee_id.job_id.kodas2.id,
                    'kodas3': employee_id.job_id.kodas3.id,
                    'kodas4': employee_id.job_id.kodas4.id,
                }
                if employee_id.job_id.kodas1:
                    domain1 = employee_id.job_id.kodas1.kodas + '_'
                    values.update({'domenas1': domain1})
                if employee_id.job_id.kodas2:
                    domain2 = employee_id.job_id.kodas2.kodas + '_'
                    values.update({'domenas2': domain2})
                if employee_id.job_id.kodas3:
                    domain3 = employee_id.job_id.kodas3.kodas + '_'
                    values.update({'domenas3': domain3})
                parametrai.append((0, 0, values))
            return parametrai
        else:
            return None

    parametrai = fields.One2many('sodra.parametrai', 'sodra_id', default=paimam_context)

    def get_company_code(self, company):
        company_code = company.company_registry or ''
        if company_code and len(company_code) > 9:
            company_code = ''
        elif company_code and company_code != ''.join(re.findall(r'\d+', company_code)):
            company_code = ''
        return self._context.get('force_imones_kodas', company_code) or ''

    def get_company_name(self, company):
        max_company_name_size = 68
        company_name = company.name[:max_company_name_size]
        company_name = self._context.get('force_company_name', company_name) or ''
        return company.get_sanitized_sodra_name(company_name)

    def get_address(self, company):
        street = self._context.get('force_gatve', company.street) or ''
        address_number = self._context.get('force_namas', company.street2) or ''
        city = self._context.get('force_miestas', company.city) or ''
        return '{} {}, {}'.format(street, address_number, city)[:68]

    def get_company_data(self, company):
        company_data = company.get_sodra_data()
        company_code = self.get_company_code(company)
        company_name = self.get_company_name(company)
        insurer_code = self._context.get('force_draudejo_kodas', company.draudejo_kodas) or ''
        if not company_name or not insurer_code or not company_code:
            raise exceptions.UserError(_('Nenurodyta kompanijos informacija'))

        return {
            'insurer_name': company_name,
            'company_code': company_code,
            'phone': self._context.get('force_telefonas', company_data.get('phone_number')) or '',
            'address': self.get_address(company),
            'accountant_name': (company_data.get('findir_name') or '')[:68],
            'preparator_details': (company_data.get('findir_data') or '')[:68],
        }

    @api.multi
    def get_data_for_each_employee(self):
        fields_by_employee = list()
        for employee_data in self.parametrai:
            employee_values = {}
            fields_by_employee.append(employee_values)

            employee = employee_data['employee_id']

            contracts = self.env['hr.contract'].search([('employee_id', '=', employee.id)], order='date_start desc')
            if not contracts:
                raise exceptions.UserError(_('Darbuotojas %s neturi susijusių kontraktų') % employee.name)
            contract = contracts[0]

            employee_names = employee.get_split_name()

            # Determine reason text
            if employee_data.priezastis and employee_data.priezastis != '99':
                reason_text = PranesimoPriezastys[employee_data.priezastis]
            else:
                reason_text = employee_data.pranesimoPriezastisKiti

            # Determine reason detalization code
            reason_detalization_code = {
                '05': employee_data.patikslinimoKodas5,
                '06': employee_data.patikslinimoKodas6,
                '10': employee_data.patikslinimoKodas10_11,
                '11': employee_data.patikslinimoKodas10_11,
                '01': sutarciu_tipai_map.get(contract.rusis, ''),
            }.get(employee_data.priezastis, '')

            # Determine reason detalization text
            reason_detalization_text = ''
            if employee_data.priezastis == '05' and employee_data.patikslinimoKodas5:
                reason_detalization_text = valstybesEU[employee_data.patikslinimoKodas5]
            elif employee_data.priezastis == '06' and employee_data.patikslinimoKodas6:
                reason_detalization_text = valstybesKitos[employee_data.patikslinimoKodas6]
            elif employee_data.priezastis in ['10', '11']:
                reason_detalization_text = employee_data.patikslinimoPaaiskinimas
            elif employee_data.priezastis == '01':
                reason_detalization_text = sutarciu_tipai.get(sutarciu_tipai_map.get(contract.rusis, ''))

            is_non_resident = employee.is_non_resident
            show_birth_date = is_non_resident

            # Update employee values
            employee_values.update({
                'person_code': employee.identification_id.strip() if employee.identification_id else '',
                'birth_date': (employee.birthday if show_birth_date else '') or '',
                'insurance_series': employee.sodra_id[:2] if employee.sodra_id else '',
                'insurance_number': employee.sodra_id[2:] if employee.sodra_id else '',
                'insurance_start_date': contract.date_start,
                'first_name': employee_names['first_name'],
                'last_name': employee_names['last_name'],
                'u1_group': '2' if is_non_resident else '1',
                'person_foreign_code': '',  # TODO should set some sort of an "ILTU" code
                'profession_1': employee_data.kodas1.kodas and employee_data.kodas1.kodas[-1] or '',
                'profession_2': employee_data.kodas2.kodas and employee_data.kodas2.kodas[-1] or '',
                'profession_3': employee_data.kodas3.kodas and employee_data.kodas3.kodas[-1] or '',
                'profession_4': employee_data.kodas4.kodas and employee_data.kodas4.kodas[-1] or '',
                'reason_code': employee_data.priezastis,
                'reason_text': reason_text,
                'reason_det_code': reason_detalization_code,
                'reason_det_text': reason_detalization_text,
                'reason_det_type_code': '',
                'reason_det_type_text': '',
            })
        return fields_by_employee

    @api.multi
    def generuoti(self):
        employees_per_page = 2
        number_of_employees_to_declare = len(self.parametrai)

        company = self.env.user.company_id
        company_data = self.get_company_data(company)

        # Build page info data (used to generate fields that should appear on each page)
        number_of_pages_required = (number_of_employees_to_declare+2*employees_per_page-2)/employees_per_page
        today = datetime.today().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        page_info_data = {
            'total_number_of_pages': number_of_pages_required,
            'insurer_code': self._context.get('force_draudejo_kodas', company.draudejo_kodas) or '',
            'document_date': self._context.get('dokumento_data', today),
            'document_number': ''
        }

        # Generate the extension form string to list in the DocumentPages
        number_of_extensions_required = (number_of_employees_to_declare + employees_per_page-2)/employees_per_page
        form_extension_groups = SD1_PAGE_EXTENSION_GROUP_DECLARATION * number_of_extensions_required

        generated_pages = []

        data_for_employees = self.get_data_for_each_employee()

        # Generate first page. It can only hold the data of a single employee
        page_number = 1
        row_number = 1
        page_info_data['page_number'] = page_number
        page_info_data['form_version'] = 11
        # Generate first page form fields (fields that contain company data)
        first_page_form_data = company_data
        first_page_form_data.update({
            'person_count': number_of_employees_to_declare,
        })
        first_page_form_fields = SD1_FORM_FIELDS.format(**first_page_form_data)
        first_page_fields = first_page_form_fields
        first_page_fields += SD1_PAGE_INFO_FIELDS.format(**page_info_data)
        if data_for_employees:
            first_employee_data = data_for_employees[row_number-1]
            first_employee_data['row_number'] = row_number
            first_page_fields += SD1_PAGE_EMPLOYEE_FIELDS.format(**first_employee_data)
        generated_pages.append(SD1_PAGE.format(
            page_def_name='1-SD',
            page_number=page_number,
            page_field_count=34,  # 20 Employee fields + 7 page info fields + 7 company info fields
            page_fields=first_page_fields,
        ))

        # Generate rest of the pages
        page_number = 2
        employee_index = 1
        employees_to_add = data_for_employees[employee_index:]
        while employees_to_add:
            # Start off with page info fields
            page_info_data['page_number'] = page_number
            page_fields = SD1_PAGE_INFO_FIELDS.format(**page_info_data)

            # Add as many employees as it fits
            row_number = 0  # Reset row number for each page
            for employee_data in employees_to_add:
                row_number += 1
                if row_number > employees_per_page:
                    # Don't add any more employees to the page
                    break
                # Add employee fields to page
                employee_index += 1
                employee_data['row_number'] = row_number
                page_fields += SD1_PAGE_EMPLOYEE_FIELDS.format(**employee_data)

            # Add blank fields to fill the page
            blank_employee_fields_to_add = employees_per_page - row_number
            for x in range(0, blank_employee_fields_to_add):
                row_number += 1
                page_fields += SD1_PAGE_BLANK_FIELDS.format(row_number=row_number)

            # Add page to generated pages list
            generated_pages.append(SD1_PAGE.format(
                page_def_name='1-SD-T',  # Second and any further pages are extensions (Tęsinys)
                page_number=page_number,
                page_fields=page_fields,
                page_field_count=47  # Two employees (20*2) + 7 info fields
            ))
            page_number += 1
            employees_to_add = data_for_employees[employee_index:]

        final_xml = SD1_FORM.format(
            created_on=today,
            form_id='{BE195D7B-114A-408B-9BCD-61DE0E41D8CE}',
            form_extension_groups=form_extension_groups,
            total_number_of_pages=number_of_pages_required,
            pages=''.join(generated_pages)
        )

        return final_xml.encode('utf8').encode('base64')

    @api.multi
    def generuokviska(self):
        if not self.parametrai:
            raise exceptions.UserError(_('Nepasirinkti darbuotojai'))

        company_id = self._context.get('company_id') or self.env.user.company_id.id
        ctx = {}
        if self._context.get('sodra', False):
            client = self.env.user.get_sodra_api()
            ctx['sodra'] = True
        else:
            client = False

        generated_file = self.generuoti()
        if generated_file:
            attach_vals = {'res_model': 'res.company',
                           'name': '1-SD' + '.xml',
                           'datas_fname': '1-SD' + '.xml',
                           'res_id': company_id,
                           'type': 'binary',
                           'datas': generated_file}
            self.env['ir.attachment'].sudo().create(attach_vals)
            ctx['failas1'] = generated_file
            if client:
                upload = client.service.uploadEdasDraft(
                    '1-SD-' + datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT) + '.ffdata', generated_file)
                if upload and type(upload) == tuple:
                    try:
                        data = dict(upload[1])
                    except Exception as exc:
                        _logger.info('SODRA SD1 ERROR: %s' % str(exc.args))
                        try:
                            error_msg = '{} {}'.format(str(upload[0]), str(upload[1]))
                        except Exception as exc:
                            _logger.info('SODRA SD1 ERROR: %s' % str(exc.args))
                            raise exceptions.UserError(_('Nenumatyta klaida, bandykite dar kartą.'))
                        raise exceptions.UserError(_('Klaida iš SODRA centrinio serverio: %s' % error_msg))
                    ext_id = data.get('docUID', False)
                    if ext_id:
                        state = 'sent' if upload[0] in [500, 403] else 'confirmed'
                        vals = {
                            'doc_name': '1SD',
                            'signing_url': data.get('signingURL', False),
                            'ext_id': ext_id,
                            'upload_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                            'last_update_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                            'state': state
                        }
                        self.env['sodra.document.export'].create(vals)
                if upload and type(upload) == tuple and upload[0] == 500:
                    client = self.sudo().env.user.get_sodra_api()
                    upload = client.service.uploadEdasDraft(
                        '1-SD-' + datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT) + '.ffdata', generated_file)
                if upload and type(upload) == tuple and upload[0] == 500:
                    _logger.info(str(upload))
                    try:
                        error_msg = '%s' % (upload[1]['detail']['dataServiceFault']['errorMsg'])
                    except:
                        error_msg = _('Įvyko klaida')
                    raise exceptions.UserError(error_msg)
                elif upload and type(upload) == tuple and upload[0] == 200:
                    ctx['url1'] = upload[1]['signingURL']

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sd1.download',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'view_id': self.env.ref('sodra.sodra_sd1_download').id,
            'context': ctx
        }


DarbuotojuParametrai()


class FailoGeneravimas(models.TransientModel):

    _name = 'sd1.download'

    def failo_pavadinimas(self):
        return '1-SD.ffdata'

    def default_download_line_ids(self):
        lines = []
        keys = filter(lambda r: isinstance(r, (unicode, str)) and r[:6] == 'failas', self._context.keys())
        for key in keys:
            val = {'file': self._context[key],
                   'file_name': self.failo_pavadinimas(),
                   }
            no = key[6:]
            key2 = 'url' + no
            if self._context.get(key2, False):
                val['url'] = self._context.get(key2, False)
            lines.append((0, 0, val))
        return lines

    download_line_ids = fields.One2many('sd1.download.line', 'download_id', default=default_download_line_ids, readonly=True)


FailoGeneravimas()


class FailoGeneravimasLine(models.TransientModel):

    _name = 'sd1.download.line'

    download_id = fields.Many2one('sd1.download', required=True, ondelete='cascade')
    file = fields.Binary(string='Ataskaitos dokumentas', readonly=True)
    file_name = fields.Char(string='Failo pavadinimas')
    url = fields.Char(string='URL', readonly=True)

    @api.multi
    def open(self):
        self.ensure_one()
        if self.url:
            return {
                'type': 'ir.actions.act_url',
                'url': self.url,
                'target': 'new',
            }


FailoGeneravimasLine()
