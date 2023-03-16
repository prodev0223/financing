# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions, _
from datetime import datetime
from dateutil.relativedelta import relativedelta
import calendar
import re
import logging

_logger = logging.getLogger(__name__)


dokumentuKodai = [
    ('K01', 'Darbo kodeksas'),
    ('K02', 'Tarnybos kalėjimų dep. prie lr teisingumo minist. statutas'),
    ('K03', 'TARNYBOS LR MUITINĖJE STATUTAS'),
    ('K04', 'VALSTYBĖS SAUGUMO DEPARTAMENTO STATUTAS'),
    ('K05', 'SPECIALIŲJŲ TYRIMŲ TARNYBOS STATUTAS'),
    ('K06', 'VIDAUS TARNYBOS STATUTAS'),
    ('K07', 'CIVILINĖS KRAŠTO APSAUGOS TARNYBOS STATUTAS'),
    ('K08', '2-OJO OPERATYVINIŲ TARNYBŲ DEPARTAMENTO PRIE KAM STATUTAS'),
    ('K09', 'SEIMO STATUTAS'),
    ('K10', 'LR VALSTYBĖS TARNYBOS ĮSTATYMAS'),
    ('K11', 'LR DIPLOMATINĖS TARNYBOS ĮSTATYMAS'),
    ('K12', 'LR TEISMŲ ĮSTATYMAS'),
    ('K13', 'LR PROKURATŪROS ISTATYMAS'),
    ('K14', 'LR KONSTITUCINIO TEISMO ĮSTATYMAS'),
    ('K15', 'LR VYRIAUSYBĖS ĮSTATYMAS'),
    ('K16', 'LR KRAŠTO APSAUGOS SISTEMOS ORGANIZAVIMO IR KT ĮSTATYMAS'),
    ('K17', 'LR SEIMO KONTROLIERIŲ ĮSTATYMAS'),
    ('K18', 'LR VALSTYBĖS KONTROLĖS ĮSTATYMAS'),
    ('K19', 'LR MOTERŲ IR VYRŲ LYGIŲ GALIMYBIŲ ĮSTATYMAS'),
    ('K20', 'LR VAIKO TEISIŲ APSAUGOS KONTROLIERIAUS ĮSTATYMAS'),
    ('K21', 'LR VISUOMENĖS INFORMAVIMO ĮSTATYMAS'),
    ('K22', 'LR VYRIAUSIOSIOS RINKIMŲ KOMISIJOS ĮSTATYMAS'),
    ('K23', 'LR VYRIAUSIOSIOS TARNYBINĖS ETIKOS KOMISIJOS ĮSTATYMAS'),
    ('K24', 'LR LIETUVOS BANKO ĮSTATYMAS'),
    ('K25', 'LR FINANSINIŲ PRIEMONIŲ RINKŲ ĮSTATYMAS'),
    ('K26', 'LR AZARTINIŲ LOŠIMŲ ĮSTATYMAS'),
    ('K27', 'LR ENERGETIKOS ĮSTATYMAS'),
    ('K28', 'LR KONKURENCIJOS ĮSTATYMAS'),
    ('K29', 'LR DRAUDIMO ĮSTATYMAS'),
    ('K30', 'LR MOKESČIŲ ADMINISTRAVIMO ĮSTATYMAS'),
    ('K31', 'LR ADMINISTRACINIŲ GINČŲ KOMISIJŲ ĮSTATYMAS'),
    ('K32', 'LR VIETOS SAVIVALDOS ĮSTATYMAS'),
    ('K33', 'LR SAVIVALDYBIŲ TARYBŲ RINKIMŲ ĮSTATYMAS'),
    ('K34', 'LR KONSTITUCIJA'),
    ('K35', 'AKCINIŲ BENDROVIŲ ĮSTATYMAS'),
    ('K36', 'LR VADOVYBĖS APSAUGOS ĮSTATYMAS'),
    ('K37', 'LR ŽVALGYBOS ĮSTATYMAS'),
    ('K99', 'KITAS TEISĖS AKTAS'),
]

dokumentai = {
    'K01': 'DARBO KODEKSAS',
    'K02': 'TARNYBOS KALĖJIMŲ DEP. PRIE LR TEISINGUMO MINIST. STATUTAS',
    'K03': 'TARNYBOS LR MUITINĖJE STATUTAS',
    'K04': 'VALSTYBĖS SAUGUMO DEPARTAMENTO STATUTAS',
    'K05': 'SPECIALIŲJŲ TYRIMŲ TARNYBOS STATUTAS',
    'K06': 'VIDAUS TARNYBOS STATUTAS',
    'K07': 'CIVILINĖS KRAŠTO APSAUGOS TARNYBOS STATUTAS',
    'K08': '2-OJO OPERATYVINIŲ TARNYBŲ DEPARTAMENTO PRIE KAM STATUTAS',
    'K09': 'SEIMO STATUTAS',
    'K10': 'LR VALSTYBĖS TARNYBOS ĮSTATYMAS',
    'K11': 'LR DIPLOMATINĖS TARNYBOS ĮSTATYMAS',
    'K12': 'LR TEISMŲ ĮSTATYMAS',
    'K13': 'LR PROKURATŪROS ISTATYMAS',
    'K14': 'LR KONSTITUCINIO TEISMO ĮSTATYMAS',
    'K15': 'LR VYRIAUSYBĖS ĮSTATYMAS',
    'K16': 'LR KRAŠTO APSAUGOS SISTEMOS ORGANIZAVIMO IR KT ĮSTATYMAS',
    'K17': 'LR SEIMO KONTROLIERIŲ ĮSTATYMAS',
    'K18': 'LR VALSTYBĖS KONTROLĖS ĮSTATYMAS',
    'K19': 'LR MOTERŲ IR VYRŲ LYGIŲ GALIMYBIŲ ĮSTATYMAS',
    'K20': 'LR VAIKO TEISIŲ APSAUGOS KONTROLIERIAUS ĮSTATYMAS',
    'K21': 'LR VISUOMENĖS INFORMAVIMO ĮSTATYMAS',
    'K22': 'LR VYRIAUSIOSIOS RINKIMŲ KOMISIJOS ĮSTATYMAS',
    'K23': 'LR VYRIAUSIOSIOS TARNYBINĖS ETIKOS KOMISIJOS ĮSTATYMAS',
    'K24': 'LR LIETUVOS BANKO ĮSTATYMAS',
    'K25': 'LR FINANSINIŲ PRIEMONIŲ RINKŲ ĮSTATYMAS',
    'K26': 'LR AZARTINIŲ LOŠIMŲ ĮSTATYMAS',
    'K27': 'LR ENERGETIKOS ĮSTATYMAS',
    'K28': 'LR KONKURENCIJOS ĮSTATYMAS',
    'K29': 'LR DRAUDIMO ĮSTATYMAS',
    'K30': 'LR MOKESČIŲ ADMINISTRAVIMO ĮSTATYMAS',
    'K31': 'LR ADMINISTRACINIŲ GINČŲ KOMISIJŲ ĮSTATYMAS',
    'K32': 'LR VIETOS SAVIVALDOS ĮSTATYMAS',
    'K33': 'LR SAVIVALDYBIŲ TARYBŲ RINKIMŲ ĮSTATYMAS',
    'K34': 'LR KONSTITUCIJA',
    'K35': 'AKCINIŲ BENDROVIŲ ĮSTATYMAS',
    'K36': 'LR VADOVYBĖS APSAUGOS ĮSTATYMAS',
    'K37': 'LR ŽVALGYBOS ĮSTATYMAS',
    'K99': 'KITAS TEISĖS AKTAS',
    }

k01straipsniai = [
    ('107', '107'),
    ('124', '124'),
    ('125', '125'),
    ('126', '126'),
    ('127', '127'),
    ('128', '128'),
    ('129', '129'),
    ('136', '136'),
    ('137', '137'),
    ('139', '139'),
    ('297', '297'),
    ('300', '300'),
]

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
    ('02', 'atleidimas iš darbo (pagal darbo sutartį)'),
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
    ('16', 'atleidimas iš pareigų valstybės tarnyboje'),
    ('17', 'savanoriška praktika'),
    ('18', 'kursantas'),
    ('19', 'užsienietis su viza'),
    ('20', 'kariūnas'),
    ('96', 'darbo sutarties rūšies priskyrimas/pakeitimas'),
    ('99', 'kiti atvejai'),
]

PranesimoPriezastys = {
    '02': 'atleidimas iš darbo (pagal darbo sutartį)',
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
    '16': 'atleidimas iš pareigų valstybės tarnyboje',
    '17': 'savanoriška praktika',
    '18': 'kursantas',
    '19': 'užsienietis su viza',
    '20': 'kariūnas',
    '96': 'darbo sutarties rūšies priskyrimas/pakeitimas',
    '99': 'kiti atvejai',

}

#
# SKYRIAI_VALUES = {
#     '1': 'ALYTAUS SKYRIUI',
#     '2': 'KARINIŲ IR JOMS PRILYGINTŲ STRUKTŪRŲ SKYRIUI',
#     '3': 'KAUNO SKYRIUI',
#     '4': 'KLAIPĖDOS SKYRIUI',
#     '5': 'MARIJAMPOLĖS SKYRIUI',
#     '6': 'MAŽEIKIŲ SKYRIUI',
#     '7': 'PANEVĖŽIO SKYRIUI',
#     '8': 'ŠIAULIŲ SKYRIUI',
#     '9': 'ŠILALĖS SKYRIUI',
#     '10': 'UTENOS SKYRIUI',
#     '11': 'VILNIAUS SKYRIUI'
# }


class sd2(models.TransientModel):

    _name = 'e.sodra.sd2'

    def _company_id(self):
        return self.env.user.company_id

    def _pradzia(self):
        return (datetime.utcnow() + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

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
        return '2-SD.ffdata'

    company_id = fields.Many2one('res.company', string='Kompanija', default=_company_id, required=True)
    data_nuo = fields.Date(string='Periodas nuo', default=_pradzia, required=True)
    data_iki = fields.Date(string='Periodas iki', default=_pabaiga, required=True)
    failas = fields.Binary(string='Ataskaitos dokumentas', readonly=True, default=auto_load)
    failo_pavadinimas = fields.Char(string='Failo pavadinimas', default=failo_pavadinimas)
    dokumento_data = fields.Date(string='Dokumento Data', default=_siandiena, required=True)

    @api.multi
    def sd2(self):
        ending_contracts = self.env['hr.contract'].search([('date_end', '>=', self.data_nuo),
                                                           ('date_end', '<=', self.data_iki)])
        bad_ids = []
        for ending_contract in ending_contracts:
            next_potential_date = (datetime.strptime(ending_contract.date_end, tools.DEFAULT_SERVER_DATE_FORMAT)+relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            next_contract = self.env['hr.contract'].search([
                ('employee_id', '=', ending_contract.employee_id.id),
                ('date_start', '=', next_potential_date)
            ])
            if next_contract and next_contract.rusis == ending_contract.rusis:
                bad_ids.append(ending_contract.id)
        ending_contract_ids = ending_contracts.filtered(lambda c: c.id not in bad_ids)

        ctx = {}
        if ending_contract_ids:
            ctx = self._context.copy()
            ctx['baigiantys'] = ending_contract_ids.ids
        ctx['company_id'] = self.company_id.id
        ctx['dokumento_data'] = self.dokumento_data
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sodra.darbuotojai.sd2',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'view_id': self.env.ref('sodra.sodra_sd2_kitas_meniu').id,
            'context': ctx,
            }


sd2()


class DarbuotojoParametrai(models.TransientModel):

    _name = 'sodra.parametrai.sd2'

    sodra_id = fields.Many2one('sodra.darbuotojai.sd2', string='Sodros parametrai', required=True, ondelete='cascade')

    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', required=True, ondelete='cascade')
    contract_id = fields.Many2one('hr.contract', string='Kontraktas', required=True, ondelete='cascade')
    priezastis = fields.Selection(PranesimoPriezasciuKodai, string='Priežastis', inverse='change1')

    patikslinimo_kodas = fields.Char(string='Pranešimo pateikimo priežasties patikslinimo kodas', default='')
    patikslinimo_paaiskinimas = fields.Char(string='Pranešimo pateikimo priežasties patikslinimas', default='')
    straipsnis = fields.Char(string='Teisės akto straipsnis', default='')
    straipsnio_dalis = fields.Char(string='Teisės akto straipsnio dalis', default='')
    dalies_punktas = fields.Char(string='Teisės akto dalies punktas', default='')
    men_sk = fields.Float(string='Kompensuojamų mėnesių skaičius')
    pajamos_neatsk_mokes = fields.Float(string='Pajamų, nuo kurių skaičiuojami mokesčiai, suma', compute='_pajamos_neatsk')
    imoku_suma = fields.Float(string='Įmokų suma', compute='_imokos')
    patikslinimo_kodas_02 = fields.Selection(dokumentuKodai, string='Pranešimo pateikimo priežasties patikslinimo kodas')
    patikslinimo_kodas_05 = fields.Selection(valstybiuKodaiEU, string='Pranešimo pateikimo priežasties patikslinimo kodas')
    patikslinimo_kodas_06 = fields.Selection(valstybiuKodaiKitos, string='Pranešimo pateikimo priežasties patikslinimo kodas')
    patikslinimo_kodas_11 = fields.Char(string='Pranešimo pateikimo priežasties patikslinimo kodas')
    patikslinimo_kodas_16 = fields.Selection(dokumentuKodai, string='Pranešimo pateikimo priežasties patikslinimo kodas')

    @api.onchange('priezastis', 'patikslinimo_kodas_02', 'patikslinimo_kodas_05', 'patikslinimo_kodas_06',
                  'patikslinimo_kodas_11', 'patikslinimo_kodas_16', 'patikslinimo_kodas')
    def change1(self):
        if self.priezastis == '02' and self.patikslinimo_kodas_02:
            self.patikslinimo_paaiskinimas = dokumentai[self.patikslinimo_kodas_02]
            self.patikslinimo_kodas = self.patikslinimo_kodas_02
        elif self.priezastis == '05' and self.patikslinimo_kodas_05:
            self.patikslinimo_paaiskinimas = valstybesEU[self.patikslinimo_kodas_05]
            self.patikslinimo_kodas = self.patikslinimo_kodas_05
        elif self.priezastis == '06' and self.patikslinimo_kodas_06:
            self.patikslinimo_paaiskinimas = valstybesKitos[self.patikslinimo_kodas_06]
            self.patikslinimo_kodas = self.patikslinimo_kodas_06
        elif self.priezastis == '16' and self.patikslinimo_kodas_16:
            self.patikslinimo_paaiskinimas = valstybesKitos[self.patikslinimo_kodas_16]
            self.patikslinimo_kodas = self.patikslinimo_kodas_16
        elif self.priezastis == '11' and self.patikslinimo_kodas_11:
            self.patikslinimo_paaiskinimas = ''
            self.patikslinimo_kodas = self.contract_id.educational_institution_code
        else:
            self.patikslinimo_paaiskinimas = ''
            self.patikslinimo_kodas = ''

    @api.multi
    @api.depends('employee_id', 'contract_id')
    def _pajamos_neatsk(self):
        for rec in self:
            pab_contract = rec.contract_id
            if not pab_contract or tools.float_is_zero(pab_contract.wage, precision_digits=2):
                continue
            if pab_contract and not pab_contract.date_end:
                raise exceptions.UserError(_('Darbuotojo %s kontraktas nesibaigia') % rec.employee_id.name)

            pab_data = datetime.strptime(pab_contract.date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
            metai = pab_data.year
            menuo = pab_data.month
            pab_data = datetime(pab_data.year, pab_data.month, calendar.monthrange(metai, menuo)[1]).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            payslips = self.env['hr.payslip.line'].search([('employee_id.id', '=', rec.employee_id.id),
                                                           ('code', 'in', ['MEN', 'VAL']),
                                                           ('slip_id.date_from', '<=', pab_data),
                                                           ('slip_id.state', '=', 'done'),
                                                           ('slip_id.date_to', '>=', pab_data)])
            liga = sum(self.env['hr.payslip.line'].search(
                [('employee_id.id', '=', rec.employee_id.id), ('code', 'in', ['L']),
                 ('slip_id.date_from', '<=', pab_data), ('slip_id.state', '=', 'done'),
                 ('slip_id.date_to', '>=', pab_data)]).mapped('total'))
            if not payslips:
                raise exceptions.UserError(_('Nėra darbuotojo %s paskutinio algalapio') % rec.employee_id.name)
            neatsk_paj = sum(payslips.mapped('amount')) - liga
            rec.pajamos_neatsk_mokes = neatsk_paj

    @api.multi
    @api.depends('employee_id', 'contract_id')
    def _imokos(self):
        for rec in self:
            pab_contract = rec.contract_id
            if not pab_contract or tools.float_is_zero(pab_contract.wage, precision_digits=2):
                continue
            if pab_contract and not pab_contract.date_end:
                raise exceptions.UserError(_('Darbuotojo %s kontraktas nesibaigia') % rec.employee_id.name)
            pab_data = datetime.strptime(pab_contract.date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
            sodra_codes = ['SDP', 'SDB', 'EMPLRSDB', 'EMPLRSDP', 'EMPLRSDDMAIN']
            if pab_contract.date_end <= '2018-06-17':
                sodra_codes.append('SDD')
            else:
                sodra_codes.append('SDDMAIN')
            payslips = self.env['hr.payslip.line'].search(
                [('employee_id.id', '=', rec.employee_id.id), ('code', 'in', sodra_codes),
                 ('slip_id.date_from', '<=', pab_data), ('slip_id.state', '=', 'done'),
                 ('slip_id.date_to', '>=', pab_data)])
            liga = sum(self.env['hr.payslip.line'].search(
                [('employee_id.id', '=', rec.employee_id.id), ('code', 'in', ['L']),
                 ('slip_id.date_from', '<=', pab_data), ('slip_id.state', '=', 'done'),
                 ('slip_id.date_to', '>=', pab_data)]).mapped('total'))
            if not (payslips and payslips[0]):
                raise exceptions.UserError(_('Nėra darbuotojo %s paskutinio algalapio') % rec.employee_id.name)
            # imoku_suma = sum(payslips.mapped('amount')) - liga
            imoku_suma = sum(payslips.mapped('amount'))
            rec.imoku_suma = imoku_suma

    @api.multi
    @api.constrains('employee_id', 'contract_id')
    def constrain_employee(self):
        for rec in self:
            if rec.contract_id.employee_id != rec.employee_id:
                raise exceptions.ValidationError(
                    _('Darbuotojas %s neatitinka kontrakto %s darbuotojo') % (
                        rec.employee_id.name, rec.contract_id.name)
                )
            if not rec.contract_id.date_end:
                raise exceptions.ValidationError(_('Kontraktas %s nesibaigia') % rec.contract_id.name)


DarbuotojoParametrai()


class DarbuotojuParametrai(models.TransientModel):

    _name = 'sodra.darbuotojai.sd2'

    def paimam_context(self):

        if 'baigiantys' in self._context.keys():
            contract_ids = self._context['baigiantys']
            contracts = self.env['hr.contract'].browse(contract_ids)
            parametrai = []
            for contract in contracts:
                patikslinimo_kodas_02 = contract.priezasties_patikslinimo_kodas if dokumentai.get(contract.priezasties_patikslinimo_kodas, False) else False
                straipsnis = contract.teises_akto_straipsnis or False
                straipsnio_dalis = contract.teises_akto_straipsnio_dalis or False
                dalies_punktas = contract.teises_akto_straipsnio_dalies_punktas or False
                men_sk = contract.num_men_iseitine or 0.0
                contract_pk = contract.priezasties_kodas
                if contract.rusis == 'educational_internship':
                    priezastis = '11'
                elif contract_pk and contract_pk in [code for code, desc in PranesimoPriezasciuKodai]:
                    priezastis = contract_pk
                else:
                    priezastis = '02'
                parametrai.append((0, 0,  {
                    'employee_id': contract.employee_id.id,
                    'contract_id': contract.id,
                    'priezastis': priezastis,
                    'patikslinimo_kodas_02': patikslinimo_kodas_02,
                    'straipsnis': straipsnis,
                    'straipsnio_dalis': straipsnio_dalis,
                    'dalies_punktas': dalies_punktas,
                    'men_sk': men_sk,
                }))
            return parametrai
        else:
            return None

    parametrai = fields.One2many('sodra.parametrai.sd2', 'sodra_id', default=paimam_context)

    def generuoti(self):
        num_employees = len(self.parametrai)
        n_emp_per_page = 3
        company = self.env['res.company'].search([('id', '=', self._context.get('company_id', False))], limit=1)
        if not company:
            raise exceptions.UserError(_('Kompanija nerasta'))

        company_data = company.get_sodra_data()
        imones_kodas = company.company_registry or ''
        if imones_kodas and len(imones_kodas) > 9:
            imones_kodas = ''
        elif imones_kodas and imones_kodas != ''.join(re.findall(r'\d+', imones_kodas)):
            imones_kodas = ''
        company_name = self._context.get('force_company_name', '') or company.name[:68]
        company_name = company.get_sanitized_sodra_name(company_name)
        draudejo_kodas = self._context.get('force_draudejo_kodas', '') or company.draudejo_kodas
        imones_kodas = self._context.get('force_imones_kodas', '') or imones_kodas
        telefonas = self._context.get('force_telefonas', '') or company_data.get('phone_number')
        if not company_name or not draudejo_kodas or not imones_kodas:
            raise exceptions.UserError(_('Nenurodyta kompanijos informacija'))

        DATA1 = {
            'draudejo_elpastas': company.findir.partner_id.email,
            'data': datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'puslapiuSkaicius': (num_employees+2*n_emp_per_page -2 )/n_emp_per_page,
            'pavadinimas': company_name,
            'draudejo_kodas': draudejo_kodas,
            'juridinio_asmens_kodas': imones_kodas,
            'draudejo_tel_numeris': telefonas,
            'dokumento_data': self._context.get('dokumento_data', ''),
            'dokumento_numeris': '',
            'zmoniu_skaicius': num_employees,
            'vadovo_pareigos': company_data.get('job_title') or '',
            'vadovo_vardas': company_data.get('findir_name') or '',
            'pranesima_pildziusio_duomenys': company_data.get('findir_data') or '',
            'income_total': '{0:.2f}'.format(sum(darbuotojas['pajamos_neatsk_mokes'] for darbuotojas in self.parametrai)).replace('.',','),
            'payment_total': '{0:.2f}'.format(sum(darbuotojas['imoku_suma'] for darbuotojas in self.parametrai)).replace('.',','),
        }

        if len(DATA1['draudejo_elpastas']) > 68:
            DATA1['draudejo_elpastas'] = DATA1['draudejo_elpastas'][:68]
        if len(DATA1['vadovo_pareigos']) > 30:
            DATA1['vadovo_pareigos'] = DATA1['vadovo_pareigos'][:30]
        if len(DATA1['vadovo_vardas']) > 68:
            DATA1['vadovo_vardas'] = DATA1['vadovo_vardas'][:68]
        if len(DATA1['pranesima_pildziusio_duomenys']) > 68:
            DATA1['pranesima_pildziusio_duomenys'] = DATA1['pranesima_pildziusio_duomenys'][:68]

        FullData = []
        for darbuotojas in self.parametrai:
            end_date = darbuotojas.contract_id.date_end
            if not end_date:
                raise exceptions.UserError(_('Darbuotojo %s kontraktas nesibaigia') % darbuotojas['employee_id'].name)
            employee_rate = darbuotojas.contract_id.with_context(date=end_date).effective_employee_tax_rate_proc_sodra
            employer_rate = darbuotojas.contract_id.with_context(date=end_date).effective_employer_tax_rate_proc
            sum_rate = employee_rate + employer_rate
            priezastis = darbuotojas.priezastis
            patikslinimo_kodas = darbuotojas.patikslinimo_kodas
            if priezastis == '02':
                patikslinimo_kodas = darbuotojas.patikslinimo_kodas_02
            elif priezastis == '05':
                patikslinimo_kodas = darbuotojas.patikslinimo_kodas_05
            if priezastis == '06':
                patikslinimo_kodas = darbuotojas.patikslinimo_kodas_06
            elif priezastis == '11':
                patikslinimo_kodas = darbuotojas.patikslinimo_kodas_11
            elif priezastis == '16':
                patikslinimo_kodas = darbuotojas.patikslinimo_kodas_16
            employee_name = darbuotojas['employee_id'].get_split_name()
            FullData.append({
                'nr': 0,
                'asmens_kodas': darbuotojas['employee_id'].identification_id.strip() if darbuotojas['employee_id'].identification_id else '',
                'sodros_kodas1': darbuotojas['employee_id'].sodra_id[:2] if darbuotojas['employee_id'].sodra_id else '',
                'sodros_kodas2': darbuotojas['employee_id'].sodra_id[2:] if darbuotojas['employee_id'].sodra_id else '',
                'pabaiga': end_date,
                'vardas': employee_name['first_name'],
                'pavarde': employee_name['last_name'],
                'priezasties_kodas': darbuotojas.priezastis or '',
                'priezasties_tekstas': PranesimoPriezastys.get(darbuotojas.priezastis, '')[:65],
                'patikslinimo_kodas': patikslinimo_kodas or '',
                'patikslinimo_tekstas': (darbuotojas.patikslinimo_paaiskinimas or '')[:58],
                'straipsnis': darbuotojas.straipsnis,
                'dalis': darbuotojas.straipsnio_dalis or '-',
                'punktai': darbuotojas.dalies_punktas or '',
                'kompens_menes': '{0:.2f}'.format(darbuotojas.men_sk).replace('.', ','),
                'income_sum': '{0:.2f}'.format(darbuotojas.pajamos_neatsk_mokes).replace('.', ','),
                'payment_sum': '{0:.2f}'.format(darbuotojas.imoku_suma).replace('.', ','),
                'income_sum_float': darbuotojas.pajamos_neatsk_mokes,
                'payment_sum_float': darbuotojas.imoku_suma,
                'tax_rate_1': '{0:.2f}'.format(sum_rate).replace('.', ','),
            })

        Final_XML = '''<FFData Version="1" CreatedByApp="ROBO" CreatedByLogin="ROBO" CreatedOn="%(data)s">
<Form FormDefId="{BE53CB69-1964-4A09-97F4-406B16C010A8}">
<DocumentPages>
<Group Name="Forma">
<ListPages>
<ListPage>2-SD</ListPage>
</ListPages>
''' % DATA1
        Final_XML += '''<Group Name="Tęsinys">
<ListPages>
<ListPage>2-SD-T</ListPage>
</ListPages>
</Group>
''' * ((num_employees + n_emp_per_page - 2)/n_emp_per_page)
        Final_XML += '''</Group>
</DocumentPages>
<Pages Count="%(puslapiuSkaicius)s">
<Page PageDefName="2-SD" PageNumber="1">
<Fields Count="34">
<Field Name="FormCode">2-SD</Field>
<Field Name="FormVersion">09</Field>
<Field Name="PageNumber">1</Field>
<Field Name="PageTotal">%(puslapiuSkaicius)s</Field>
<Field Name="InsurerName">%(pavadinimas)s</Field>
<Field Name="InsurerCode">%(draudejo_kodas)s</Field>
<Field Name="JuridicalPersonCode">%(juridinio_asmens_kodas)s</Field>
<Field Name="InsurerPhone">%(draudejo_tel_numeris)s</Field>
<Field Name="InsurerAddress">%(draudejo_elpastas)s</Field>
<Field Name="DocDate">%(dokumento_data)s</Field>
<Field Name="DocNumber">%(dokumento_numeris)s</Field>
<Field Name="PersonCountTotal">%(zmoniu_skaicius)s</Field>
<Field Name="InsIncomeTotal">%(income_total)s</Field>
<Field Name="PaymentTotal">%(payment_total)s</Field>
'''            % DATA1

        Final_XML += '''<Field Name="RowNumber_1">1</Field>
<Field Name="PersonCode_1">%(asmens_kodas)s</Field>
<Field Name="InsuranceSeries_1">%(sodros_kodas1)s</Field>
<Field Name="InsuranceNumber_1">%(sodros_kodas2)s</Field>
<Field Name="InsuranceEndDate_1">%(pabaiga)s</Field>
<Field Name="PersonFirstName_1">%(vardas)s</Field>
<Field Name="PersonLastName_1">%(pavarde)s</Field>
<Field Name="InsIncomeSum_1">%(income_sum)s</Field>
<Field Name="TaxRate_1">%(tax_rate_1)s</Field>
<Field Name="PaymentSum_1">%(payment_sum)s</Field>
<Field Name="ReasonCode_1">%(priezasties_kodas)s</Field>
<Field Name="ReasonText_1">%(priezasties_tekstas)s</Field>
<Field Name="ReasonDetCode_1">%(patikslinimo_kodas)s</Field>
<Field Name="ReasonDetText_1">%(patikslinimo_tekstas)s</Field>
<Field Name="LawActArticle_1">%(straipsnis)s</Field>
<Field Name="LawActPart_1">%(dalis)s</Field>
<Field Name="LawActSubsection_1">%(punktai)s</Field>
<Field Name="CompensatedMonthsCount_1">%(kompens_menes)s</Field>
''' % FullData[0]

        Final_XML += '''
<Field Name="ManagerFullName">%(vadovo_vardas)s</Field>
<Field Name="PreparatorDetails">%(pranesima_pildziusio_duomenys)s</Field>
</Fields>
</Page>
''' % DATA1
        if num_employees == 1:
            Final_XML += '''</Pages>
</Form>
</FFData>'''
        else:
            for i in range(2, 1+(num_employees+2*n_emp_per_page -2)/n_emp_per_page):
                income_sum_float = 0
                payment_sum_float = 0
                DATA1['temp'] = i
                Final_XML += '''<Page PageDefName="2-SD-T" PageNumber="%(temp)s">
<Fields Count="63">
<Field Name="FormCode">2-SD-T</Field>
<Field Name="FormVersion">09</Field>
<Field Name="PageNumber">%(temp)s</Field>
<Field Name="PageTotal">%(puslapiuSkaicius)s</Field>
<Field Name="InsurerCode">%(draudejo_kodas)s</Field>
<Field Name="DocDate">%(dokumento_data)s</Field>
<Field Name="DocNumber">%(dokumento_numeris)s</Field>
''' % DATA1

                for j in range(1, min(n_emp_per_page+1, num_employees-n_emp_per_page*i+2*n_emp_per_page)):
                    payment_sum_float += FullData[n_emp_per_page*i+j-2*n_emp_per_page]['payment_sum_float']
                    income_sum_float += FullData[n_emp_per_page*i+j-2*n_emp_per_page]['income_sum_float']
                    FullData[n_emp_per_page*i+j-2*n_emp_per_page]['nr'] = j
                    FullData[n_emp_per_page*i+j-2*n_emp_per_page]['eiles_nr'] = n_emp_per_page*i+j-2*n_emp_per_page+1
                    Final_XML += '''<Field Name="RowNumber_%(nr)s"></Field>
<Field Name="PersonCode_%(nr)s">%(asmens_kodas)s</Field>
<Field Name="InsuranceSeries_%(nr)s">%(sodros_kodas1)s</Field>
<Field Name="InsuranceNumber_%(nr)s">%(sodros_kodas2)s</Field>
<Field Name="InsuranceEndDate_%(nr)s">%(pabaiga)s</Field>
<Field Name="PersonFirstName_%(nr)s">%(vardas)s</Field>
<Field Name="PersonLastName_%(nr)s">%(pavarde)s</Field>
<Field Name="ReasonCode_%(nr)s">%(priezasties_kodas)s</Field>
<Field Name="ReasonText_%(nr)s">%(priezasties_tekstas)s</Field>
<Field Name="ReasonDetCode_%(nr)s">%(patikslinimo_kodas)s</Field>
<Field Name="ReasonDetText_%(nr)s">%(patikslinimo_tekstas)s</Field>
<Field Name="LawActArticle_%(nr)s">%(straipsnis)s</Field>
<Field Name="LawActPart_%(nr)s">%(dalis)s</Field>
<Field Name="LawActSubsection_%(nr)s">%(punktai)s</Field>
<Field Name="CompensatedMonthsCount_%(nr)s">%(kompens_menes)s</Field>
<Field Name="InsIncomeSum_%(nr)s">%(income_sum)s</Field>
<Field Name="TaxRate_%(nr)s">%(tax_rate_1)s</Field>
<Field Name="PaymentSum_%(nr)s">%(payment_sum)s</Field>
''' % FullData[n_emp_per_page*i+j-2*n_emp_per_page]
                if num_employees-n_emp_per_page*i+2*n_emp_per_page-1 < n_emp_per_page:
                    for j in range(num_employees-n_emp_per_page*i+2*n_emp_per_page, n_emp_per_page+1):
                        Final_XML += '''<Field Name="RowNumber_%(nr)s"></Field>
<Field Name="PersonCode_%(nr)s"></Field>
<Field Name="InsuranceSeries_%(nr)s"></Field>
<Field Name="InsuranceNumber_%(nr)s"></Field>
<Field Name="InsuranceEndDate_%(nr)s"></Field>
<Field Name="PersonFirstName_%(nr)s"></Field>
<Field Name="PersonLastName_%(nr)s"></Field>
<Field Name="ReasonCode_%(nr)s"></Field>
<Field Name="ReasonText_%(nr)s"></Field>
<Field Name="ReasonDetCode_%(nr)s"></Field>
<Field Name="ReasonDetText_%(nr)s"></Field>
<Field Name="LawActArticle_%(nr)s"></Field>
<Field Name="LawActPart_%(nr)s"></Field>
<Field Name="LawActSubsection_%(nr)s"></Field>
<Field Name="CompensatedMonthsCount_%(nr)s"></Field>
<Field Name="InsIncomeSum_%(nr)s"></Field>
<Field Name="TaxRate_%(nr)s"></Field>
<Field Name="PaymentSum_%(nr)s"></Field>
''' % {'nr': j
       }

                Final_XML += '''<Field Name="InsIncomePage">%(income_sum_float)s</Field>
<Field Name="PaymentPage">%(payment_sum_float)s</Field></Fields>
</Page>
''' % {'income_sum_float': '{0:.2f}'.format(income_sum_float).replace('.', ','),
       'payment_sum_float': '{0:.2f}'.format(payment_sum_float).replace('.', ',')}

            Final_XML += '''
</Pages>
</Form>
</FFData>'''

        return Final_XML.encode('utf8').encode('base64')

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
                           'name': '2-SD' + '.xml',
                           'datas_fname': '2-SD' + '.xml',
                           'res_id': company_id,
                           'type': 'binary',
                           'datas': generated_file}
            self.env['ir.attachment'].sudo().create(attach_vals)
            ctx['failas1'] = generated_file
            if client:
                upload = client.service.uploadEdasDraft(
                    '2-SD-' + datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT) + '.ffdata', generated_file)
                if upload and type(upload) == tuple:
                    try:
                        data = dict(upload[1])
                    except Exception as exc:
                        _logger.info('SODRA SD2 ERROR: %s' % str(exc.args))
                        try:
                            error_msg = '{} {}'.format(str(upload[0]), str(upload[1]))
                        except Exception as exc:
                            _logger.info('SODRA SD12 ERROR: %s' % str(exc.args))
                            raise exceptions.UserError(_('Nenumatyta klaida, bandykite dar kartą.'))
                        raise exceptions.UserError(_('Klaida iš SODRA centrinio serverio: %s' % error_msg))
                    ext_id = data.get('docUID', False)
                    if ext_id:
                        state = 'sent' if upload[0] in [500, 403] else 'confirmed'
                        vals = {
                            'doc_name': '2-SD',
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
                        '2-SD-' + datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT) + '.ffdata', generated_file)
                if upload and type(upload) == tuple and upload[0] == 500:
                    _logger.info(str(upload))
                    try:
                        error_msg = '%s' % (upload[1]['detail']['dataServiceFault']['errorMsg'])
                    except:
                        error_msg = _('Įvyko klaida')
                    raise exceptions.UserError(error_msg)
                elif upload and type(upload) == tuple and upload[0] == 200:
                    ctx['url1'] = upload[1]['signingURL']

        return{
            'type': 'ir.actions.act_window',
            'res_model': 'sd2.download',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
            'view_id': self.env.ref('sodra.sodra_sd2_download').id,
            'context': ctx
        }


DarbuotojuParametrai()


class FailoGeneravimas(models.TransientModel):

    _name = 'sd2.download'

    def failo_pavadinimas(self):
        return '2-SD.ffdata'

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

    download_line_ids = fields.One2many('sd2.download.line', 'download_id', default=default_download_line_ids, readonly=True)


FailoGeneravimas()


class FailoGeneravimasLine(models.TransientModel):

    _name = 'sd2.download.line'

    download_id = fields.Many2one('sd2.download', required=True, ondelete='cascade')
    file = fields.Binary(string='Dokumentas', readonly=True)
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
