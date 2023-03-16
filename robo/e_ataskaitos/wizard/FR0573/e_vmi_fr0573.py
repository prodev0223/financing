# -*- coding: utf-8 -*-
import math
from collections import OrderedDict
from datetime import datetime

from odoo import models, fields, api, tools
from ...e_vmi_tools import SKYRIAI, round_to_int, convert_to_str, convert_to_int_str


partner_code_type_map = {'mmak': '1',
                         'PVMmk': '2',
                         'atpdsin': '3'}


class FR0573(models.TransientModel):
    _name = 'e.vmi.fr0573'

    def _kompanija(self):
        return self.env.user.company_id.id

    # def _gpm_saskaita(self):
    #     return self.env['account.account'].search([('code', '=', '4481')])

    def _pradzia(self):
        date = datetime.utcnow()
        if date.month > 5:
            year = date.year
        else:
            year = date.year - 1
        return datetime(year, 1, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _pabaiga(self):
        date = datetime.utcnow()
        if date.month > 5:
            year = date.year
        else:
            year = date.year - 1
        return datetime(year, 12, 31).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    def auto_load(self):
        if 'failas' in self._context.keys():
            return self._context['failas']
        else:
            return ''

    def failo_pavadinimas(self):
        return 'FR0573.ffdata'

    kompanija = fields.Many2one('res.company', string='Kompanija', default=_kompanija, required=True)
    data_nuo = fields.Date(string='Periodas nuo', default=_pradzia, required=True)
    data_iki = fields.Date(string='Periodas iki', default=_pabaiga, required=True)
    failas = fields.Binary(string='Ataskaitos dokumentas', readonly=True, default=auto_load)
    failo_pavadinimas = fields.Char(string='Failo pavadinimas', default=failo_pavadinimas)
    skyrius = fields.Selection(SKYRIAI, string='Padalinys', default='13', required=True)

    # gpm_saskaita = fields.Many2one('account.account', string='GPM sąskaita', default=_gpm_saskaita, required=True)

    def open_report(self):
        if not self.data_nuo or not self.data_iki:
            return
        force = True
        if self.env['fr.0573.report'].search([('date', '>=', self.data_nuo), ('date', '<=', self.data_iki),
                                              ('correction', '=', True)], limit=1, count=True):
            force = False
        self.env['fr.0573.report'].refresh_report(self.data_nuo, self.data_iki, force)
        action = self.env.ref('e_ataskaitos.action_vmi_fr_0573_report')
        action = action.read()[0]
        action['domain'] = [('date', '>=', self.data_nuo), ('date', '<=', self.data_iki)]
        return action

    @api.onchange('kompanija')
    def onchange_kompanija(self):
        if self.kompanija:
            self.skyrius = self.kompanija.savivaldybe
        # return amount_with_tax, amount_to_pay, total_tax_amount  # du atveju amount_with_tax != amount_to_pay + total_tax_amount

    @api.multi
    def fr0573(self):
        self.env['fr.0573.report'].refresh_report(self.data_nuo, self.data_iki)
        company_data = self.kompanija.get_report_company_data()
        company_name = company_data['name'].upper()[:45]
        pildymo_data = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        periodo_metai = str(datetime.strptime(self.data_iki, tools.DEFAULT_SERVER_DATE_FORMAT).year)
        num_emp_per_page = 5
        XML = '''<?xml version="1.0" encoding="UTF-8"?>
<FFData Version="1" CreatedByApp="Odoo" CreatedByLogin="Robo" CreatedOn="%(pildymo_data)s">
<Form FormDefId="{F6ACA101-4103-4538-AB33-E598C539EB9B}">
<DocumentPages>
<Group Name="Visa forma">
<ListPages>
<ListPage>FR0573</ListPage>
</ListPages>
%(page_list)s</Group>
</DocumentPages>
<Pages Count="%(MaxPageNumber)s">
<Page PageDefName="FR0573" PageNumber="1">
<Fields Count="20">
<Field Name="B_MM_ID">%(imones_kodas)s</Field>
<Field Name="B_MM_SavKodas">%(sav_kodas)s</Field>
<Field Name="B_MM_Pavad">%(pavad)s</Field>
<Field Name="B_MM_Adresas">%(adresas)s</Field>
<Field Name="B_MM_Tel">%(telefonas)s</Field>
<Field Name="B_MM_Epastas">%(epastas)s</Field>
<Field Name="B_UzpildData">%(pildymo_data)s</Field>
<Field Name="B_ML_Metai">%(periodo_metai)s</Field>
<Field Name="E12">%(priedoA_lapu_skaicius)s</Field>
<Field Name="E13">%(priedoA_eiluciu_skaicius)s</Field>
<Field Name="E14">%(priedoU_lapu_skaicius)s</Field>
<Field Name="E15">%(priedoU_eiluciu_skaicius)s</Field>
<Field Name="E16">%(A_ismoketu_ismoku_neatemus_mokesciu)s</Field>
<Field Name="E17">%(A_pajamu_mokestis_priskaiciuotas)s</Field>
<Field Name="E18">%(A_pajamu_mokestis_ismoketas)s</Field>
<Field Name="E19">%(U_ismoketu_ismoku_neatemus_mokesciu)s</Field>
<Field Name="E20">%(U_pajamu_mokestis_priskaiciuotas)s</Field>
<Field Name="E21">%(U_pajamu_mokestis_ismoketas)s</Field>
<Field Name="B_FormNr"></Field>
<Field Name="B_FormVerNr"></Field>
</Fields>
</Page>
''' % {
            'MaxPageNumber': '%(MaxPageNumber)d',
            'imones_kodas': company_data['code'],
            'sav_kodas': self.skyrius or '',
            'pavad': company_name,
            'adresas': company_data['full_address'],
            'epastas': company_data['email'].upper(),
            'telefonas': company_data['phone'],
            'pildymo_data': pildymo_data,
            'periodo_metai': periodo_metai,
            'priedoA_lapu_skaicius': '%(priedoA_lapu_skaicius)d',
            'priedoA_eiluciu_skaicius': '%(priedoA_eiluciu_skaicius)d',
            'priedoU_lapu_skaicius': '%(priedoU_lapu_skaicius)d',
            'priedoU_eiluciu_skaicius': '%(priedoU_eiluciu_skaicius)d',
            'A_ismoketu_ismoku_neatemus_mokesciu': '%(A_ismoketu_ismoku_neatemus_mokesciu)s',
            'A_pajamu_mokestis_priskaiciuotas': '%(A_pajamu_mokestis_priskaiciuotas)s',
            'A_pajamu_mokestis_ismoketas': '%(A_pajamu_mokestis_ismoketas)s',
            'U_ismoketu_ismoku_neatemus_mokesciu': '%(U_ismoketu_ismoku_neatemus_mokesciu)s',
            'U_pajamu_mokestis_priskaiciuotas': '%(U_pajamu_mokestis_priskaiciuotas)s',
            'U_pajamu_mokestis_ismoketas': '%(U_pajamu_mokestis_ismoketas)s',
            'page_list': '%(page_list)s',
        }

        eil_nr = 1
        A_ismoketu_ismoku_neatemus_mokesciu = 0
        A_pajamu_mokestis_priskaiciuotas = 0
        A_pajamu_mokestis_ismoketas = 0
        sum_pageA_gyv_ismokos_neatemus_mokesciu = 0
        sum_pageA_pajamu_mokestis_priskaiciuotas = 0
        sum_pageA_pajamu_mokestis_ismoketas = 0
        # reconciled_with_a_klase = self.env['account.move.line'].search([('date', '>=', self.data_nuo),
        #                                                                 ('date', '<=', self.data_iki),
        #                                                                 ('reconciled_with_a_klase', '=', True),
        #                                                                 ('company_id', '=', self.kompanija.id)])
        rezidentai_data = OrderedDict()
        ne_rezidentai_data = OrderedDict()
        # gpm_account_ids = self.env['account.account'].search([('code', 'in', ['4481', '4487'])]).ids
        for rep_val in self.env['fr.0573.report'].search([]):
            update_values = {'npd': rep_val.amount_npd,
                             'pnpd': rep_val.amount_pnpd,
                             'pajamu_mokestis_is_imones_lesu': 0.0,
                             'grazinta_suma': 0.0,
                             'amount_paid_taxes_included': rep_val.amount_bruto,
                             'amount_gpm': rep_val.amount_tax,
                             'amount_gpm_paid': rep_val.amount_tax_paid,
                             }
            partner = rep_val.partner_id
            data_key = (partner.id, rep_val.a_klase_kodas_id.id)
            rezidentas = partner.rezidentas == 'rezidentas'
            if rezidentas:
                existing_values = rezidentai_data.get(data_key, {})
                for k in update_values.keys():
                    existing_values[k] = existing_values.get(k, 0.0) + update_values[k]
                rezidentai_data[data_key] = existing_values
            else:
                existing_values = ne_rezidentai_data.get(data_key, {})
                for k in update_values.keys():
                    existing_values[k] = existing_values.get(k, 0.0) + update_values[k]
                ne_rezidentai_data[data_key] = existing_values
        PageNumber = 1
        if rezidentai_data:
            PageNumber += 1
            XML += '''<Page PageDefName="FR0573A" PageNumber="2">
<Fields Count="84">
'''
        nr = 0
        for (partner_id, a_klase_kodas_id), values in rezidentai_data.items():
            partner = self.env['res.partner'].browse(partner_id).with_context(active_test=False)
            id_kodo_kategorija = partner_code_type_map.get(partner.partner_code_type, '1')
            a_klase_record = self.env['a.klase.kodas'].browse(a_klase_kodas_id)
            a_klase_kodas = a_klase_record.code
            employee = partner.employee_ids and partner.employee_ids[0]
            if a_klase_kodas in ['26', '62']:
                country_code = partner.country_id.code or ''
            else:
                country_code = ''
            if country_code == 'LT':
                country_code = ''
            # if 'employee_id' in v.keys() and v['employee_id'].address_home_id:
            #     id_kodo_kategorija = 2 if not v['employee_id'].address_home_id.kodas and v['employee_id'].address_home_id.vat else 1
            # else:
            #     id_kodo_kategorija = 1
            partner_code = partner.kodas or ''
            if partner.employee_ids:
                employee = partner.employee_ids[0]
                if employee.identification_id:
                    partner_code = employee.identification_id
            tarifas_float = a_klase_record.gpm_proc
            if tools.float_is_zero(tarifas_float - 15, precision_digits=2):
                tarifas = '15'
            elif tools.float_is_zero(tarifas_float - 5, precision_digits=2):
                tarifas = '5'
            else:
                tarifas = '0'
            amount_gpm = round_to_int(values['amount_gpm'])
            amount_gpm_paid = round_to_int(values['amount_gpm_paid'])
            nr += 1
            XML += '''<Field Name="A3-%(eil_nr)d">%(RowNumberA)s</Field>
<Field Name="A4-%(eil_nr)d">%(ID_kodas)s</Field>
<Field Name="A4_1-%(eil_nr)d">%(id_kodo_kategorija)s</Field>
<Field Name="A5-%(eil_nr)d">%(vardas)s</Field>
<Field Name="A6-%(eil_nr)d">%(sav_kodas)s</Field>
<Field Name="A7-%(eil_nr)d">%(pajamu_kodas)s</Field>
<Field Name="A8-%(eil_nr)d">%(mnpd)s</Field>
<Field Name="A9-%(eil_nr)d">%(mpnpd)s</Field>
<Field Name="A17-%(eil_nr)d">%(pajamu_mokestis_is_imones_lesu)s</Field>
<Field Name="A18-%(eil_nr)d">%(grazinta_suma)s</Field>
<Field Name="A19-%(eil_nr)d">%(valstybes_kodas)s</Field>
<Field Name="A10-%(eil_nr)d">%(gyv_ismokos_neatemus_mokesciu)s</Field>
<Field Name="A11-%(eil_nr)d">%(tarifas)s</Field>
<Field Name="A12-%(eil_nr)d">%(pajamu_mokestis_priskaiciuotas)d</Field>
<Field Name="A13-%(eil_nr)d">%(pajamu_mokestis_ismoketas)d</Field>
''' % {
                'RowNumberA': nr,
                'eil_nr': eil_nr,
                'ID_kodas': partner_code,
                'id_kodo_kategorija': id_kodo_kategorija,
                'vardas': (employee.name or partner.name or '').upper()[:26],
                'sav_kodas': employee.savivaldybe or self.skyrius or '',
                'pajamu_kodas': a_klase_kodas,
                'mnpd': convert_to_str(values['npd']),
                'mpnpd': convert_to_str(values['pnpd']),
                'pajamu_mokestis_is_imones_lesu': convert_to_int_str(values['pajamu_mokestis_is_imones_lesu']),
                'grazinta_suma': convert_to_int_str(values['grazinta_suma']),
                'valstybes_kodas': country_code,
                'gyv_ismokos_neatemus_mokesciu': convert_to_str(values['amount_paid_taxes_included']),
                'tarifas': tarifas,
                'pajamu_mokestis_priskaiciuotas': amount_gpm,
                'pajamu_mokestis_ismoketas': amount_gpm_paid,
            }

            sum_pageA_gyv_ismokos_neatemus_mokesciu += values['amount_paid_taxes_included'] or 0
            sum_pageA_pajamu_mokestis_priskaiciuotas += amount_gpm
            sum_pageA_pajamu_mokestis_ismoketas += amount_gpm_paid
            A_ismoketu_ismoku_neatemus_mokesciu += values['amount_paid_taxes_included'] or 0
            A_pajamu_mokestis_priskaiciuotas += amount_gpm
            A_pajamu_mokestis_ismoketas += amount_gpm_paid

            if eil_nr >= num_emp_per_page:
                XML += '''<Field Name="A14">%(sum_pageA_gyv_ismokos_neatemus_mokesciu)s</Field>
<Field Name="A15">%(sum_pageA_pajamu_mokestis_priskaiciuotas)s</Field>
<Field Name="A16">%(sum_pageA_pajamu_mokestis_ismoketas)s</Field>
<Field Name="B_MM_ID">%(imones_kodas)s</Field>
<Field Name="LapoNr">%(LapoNrA)s</Field>
<Field Name="B_FormNr"></Field>
<Field Name="B_FormVerNr"></Field>
<Field Name="B_ML_Metai">%(periodo_metai)s</Field>
<Field Name="B_UzpildData">%(pildymo_data)s</Field>
</Fields>
</Page>
''' % {
                    'sum_pageA_gyv_ismokos_neatemus_mokesciu': convert_to_str(sum_pageA_gyv_ismokos_neatemus_mokesciu),
                    'sum_pageA_pajamu_mokestis_priskaiciuotas': convert_to_int_str(
                        sum_pageA_pajamu_mokestis_priskaiciuotas),
                    'sum_pageA_pajamu_mokestis_ismoketas': convert_to_int_str(sum_pageA_pajamu_mokestis_ismoketas),
                    'imones_kodas': company_data['code'].upper(),
                    'LapoNrA': PageNumber - 1 or '',
                    'pildymo_data': pildymo_data,
                    'periodo_metai': periodo_metai,
                }
                sum_pageA_gyv_ismokos_neatemus_mokesciu = 0
                sum_pageA_pajamu_mokestis_priskaiciuotas = 0
                sum_pageA_pajamu_mokestis_ismoketas = 0
                eil_nr = 0
                if nr != len(rezidentai_data):
                    PageNumber += 1
                    XML += '''<Page PageDefName="FR0573A" PageNumber="%s">
<Fields Count="84">
''' % PageNumber

            eil_nr += 1

        if eil_nr != 1:
            for m in range(eil_nr, num_emp_per_page + 1):
                XML += '''<Field Name="A3-%(m)d"></Field>
<Field Name="A4-%(m)d"></Field>
<Field Name="A4_1-%(m)d"></Field>
<Field Name="A5-%(m)d"></Field>
<Field Name="A6-%(m)d"></Field>
<Field Name="A7-%(m)d"></Field>
<Field Name="A8-%(m)d"></Field>
<Field Name="A9-%(m)d"></Field>
<Field Name="A17-%(m)d"></Field>
<Field Name="A18-%(m)d"></Field>
<Field Name="A19-%(m)d"></Field>
<Field Name="A10-%(m)d"></Field>
<Field Name="A11-%(m)d"></Field>
<Field Name="A12-%(m)d"></Field>
<Field Name="A13-%(m)d"></Field>
''' % {'m': m}

            XML += '''<Field Name="A14">%(sum_pageA_gyv_ismokos_neatemus_mokesciu)s</Field>
<Field Name="A15">%(sum_pageA_pajamu_mokestis_priskaiciuotas)s</Field>
<Field Name="A16">%(sum_pageA_pajamu_mokestis_ismoketas)s</Field>
<Field Name="B_MM_ID">%(imones_kodas)s</Field>
<Field Name="LapoNr">%(LapoNrA)s</Field>
<Field Name="B_FormNr"></Field>
<Field Name="B_FormVerNr"></Field>
<Field Name="B_ML_Metai">%(periodo_metai)s</Field>
<Field Name="B_UzpildData">%(pildymo_data)s</Field>
</Fields>
</Page>
''' % {
                'sum_pageA_gyv_ismokos_neatemus_mokesciu': convert_to_str(sum_pageA_gyv_ismokos_neatemus_mokesciu),
                'sum_pageA_pajamu_mokestis_priskaiciuotas': convert_to_int_str(
                    sum_pageA_pajamu_mokestis_priskaiciuotas),
                'sum_pageA_pajamu_mokestis_ismoketas': convert_to_int_str(sum_pageA_pajamu_mokestis_ismoketas),
                'imones_kodas': company_data['code'],
                'LapoNrA': PageNumber or '',
                'pildymo_data': pildymo_data,
                'periodo_metai': periodo_metai,
            }

        del sum_pageA_gyv_ismokos_neatemus_mokesciu
        del sum_pageA_pajamu_mokestis_priskaiciuotas
        del sum_pageA_pajamu_mokestis_ismoketas

        U_ismoketu_ismoku_neatemus_mokesciu = 0
        U_pajamu_mokestis_priskaiciuotas = 0
        U_pajamu_mokestis_ismoketas = 0
        # #########  # todo do not delete! page U
        # PageNumber += 1
        # sum_pageU_gyv_ismokos_neatemus_mokesciu = 0
        # sum_pageU_pajamu_mokestis_priskaiciuotas = 0
        # sum_pageU_pajamu_mokestis_ismoketas = 0
        # XML += '''<Page PageDefName="FR0573U" PageNumber="%s">
        # <Fields Count="57">''' % PageNumber
        # for (partner_id, a_klase_kodas_id), values in rezidentai_data.items():
        #     partner = self.env['res.partner'].browse(partner_id)
        #     if partner.kodas:
        #         id_kodo_kategorija = 2
        #     else:
        #         id_kodo_kategorija = 1
        #     a_klase_kodas = self.env['a.klase.kodas'].browse(a_klase_kodas_id).code
        #     employee = partner.employee_ids and partner.employee_ids[0]
        #     country_code = partner.country_id.code or ''
        #
        #     XML += '''<Field Name="U3-%(eil_nr)d">%(RowNumberA)s</Field>
        # <Field Name="U4-%(eil_nr)d">%(ID_kodas)s</Field>
        # <Field Name="U4_1-%(eil_nr)d">%(id_kodo_kategorija)s</Field>
        # <Field Name="U5-%(eil_nr)d">%(vardas)s</Field>
        # <Field Name="U8-%(eil_nr)d">%(mnpd)s</Field>
        # <Field Name="U9-%(eil_nr)d">%(mpnpd)s</Field>
        # <Field Name="U6-%(eil_nr)d">%(sav_kodas)s</Field>
        # <Field Name="U7-%(eil_nr)d">%(pajamu_kodas)s</Field>
        # <Field Name="U10-%(eil_nr)d">%(gyv_ismokos_neatemus_mokesciu)s</Field>
        # <Field Name="U12-%(eil_nr)d">%(pajamu_mokestis_priskaiciuotas)s</Field>
        # <Field Name="U13-%(eil_nr)d">%(pajamu_mokestis_ismoketas)s</Field>
        # <Field Name="U14-%(eil_nr)d"></Field>
        # <Field Name="U15-%(eil_nr)d"></Field>
        # <Field Name="U19-%(eil_nr)d">%(valstybes_kodas)s</Field>
        # <Field Name="U20-%(eil_nr)d"></Field>
        # <Field Name="U21-%(eil_nr)d"></Field>''' % {
        #         'RowNumberA': eil_nr,
        #         'eil_nr': eil_nr,
        #         'ID_kodas': partner.kodas or '',
        #         'id_kodo_kategorija': id_kodo_kategorija,
        #         'vardas': employee.name or partner.name or '',
        #         'sav_kodas': employee.savivaldybe or self.skyrius or '13',
        #         'pajamu_kodas': a_klase_kodas,
        #         'mnpd': str(values['npd']).replace('.', ',') or 0,
        #         'mpnpd': str(values['pnpd']).replace('.', ',') or 0,
        #         'pajamu_mokestis_is_imones_lesu': values['pajamu_mokestis_is_imones_lesu'],
        #         'grazinta_suma': values['grazinta_suma'],
        #         'valstybes_kodas': country_code,
        #         'gyv_ismokos_neatemus_mokesciu': str(values['amount_paid_taxes_included']).replace('.', ',') or 0,
        #         'tarifas_0_ar_15': '15',  # todo
        #         'pajamu_mokestis_priskaiciuotas': str(values['amount_gpm']).replace('.', ',') or 0,
        #         'pajamu_mokestis_ismoketas': str(values['amount_gpm_paid']).replace('.', ',') or 0,
        #     }
        #
        #     sum_pageU_gyv_ismokos_neatemus_mokesciu += values['amount_paid_taxes_included'] or 0
        #     sum_pageU_pajamu_mokestis_priskaiciuotas += values['amount_gpm'] or 0
        #     sum_pageU_pajamu_mokestis_ismoketas += values['amount_gpm_paid'] or 0
        #
        #     if eil_nr >= 3:  #todo
        #         XML += '''<Field Name="U16">%(sum_pageU_gyv_ismokos_neatemus_mokesciu)s</Field>
        # <Field Name="U17">%(sum_pageU_pajamu_mokestis_priskaiciuotas)s</Field>
        # <Field Name="U18">%(sum_pageU_pajamu_mokestis_ismoketas)s</Field>
        # <Field Name="B_MM_ID">%(imones_kodas)s</Field>
        # <Field Name="LapoNr">%(LapoNrU)s</Field>
        # <Field Name="B_FormNr"></Field>
        # <Field Name="B_FormVerNr"></Field>
        # <Field Name="B_UzpildData">%(pildymo_data)s</Field>
        # <Field Name="B_ML_Metai">%(periodo_metai)s</Field>
        # </Fields>
        # </Page>''' % {
        #             'sum_pageU_gyv_ismokos_neatemus_mokesciu': str(sum_pageU_gyv_ismokos_neatemus_mokesciu).replace('.',
        #                                                                                                             ',') or '',
        #             'sum_pageU_pajamu_mokestis_priskaiciuotas': str(sum_pageU_pajamu_mokestis_priskaiciuotas).replace(
        #                 '.', ',') or '',
        #             'sum_pageU_pajamu_mokestis_ismoketas': str(sum_pageU_pajamu_mokestis_ismoketas).replace('.',
        #                                                                                                     ',') or '',
        #             'imones_kodas': self.kompanija.company_registry or '',
        #             'LapoNrU': PageNumber or '',
        #             'pildymo_data': pildymo_data,
        #             'periodo_metai': periodo_metai,
        #         }
        #         sum_pageU_gyv_ismokos_neatemus_mokesciu = 0
        #         sum_pageU_pajamu_mokestis_priskaiciuotas = 0
        #         sum_pageU_pajamu_mokestis_ismoketas = 0
        #         eil_nr = 0
        #         PageNumber += 1
        #
        #         XML += '''<Page PageDefName="FR0573U" PageNumber="%s">
        # <Fields Count="84">''' % PageNumber
        #
        #     eil_nr += 1
        #
        # if 1 <= eil_nr <= 4:
        #     for m in range(eil_nr, 4):
        #         XML += '''<Field Name="U3-%(m)d"></Field>
        # <Field Name="U4-%(m)d"></Field>
        # <Field Name="U4_1-%(m)d"></Field>
        # <Field Name="U5-%(m)d"></Field>
        # <Field Name="U8-%(m)d"></Field>
        # <Field Name="U9-%(m)d"></Field>
        # <Field Name="U6-%(m)d"></Field>
        # <Field Name="U7-%(m)d"></Field>
        # <Field Name="U10-%(m)d"></Field>
        # <Field Name="U12-%(m)d"></Field>
        # <Field Name="U13-%(m)d"></Field>
        # <Field Name="U14-%(m)d"></Field>
        # <Field Name="U15-%(m)d"></Field>
        # <Field Name="U19-%(m)d"></Field>
        # <Field Name="U20-%(m)d"></Field>
        # <Field Name="U21-%(m)d"></Field>''' % {'m': m}
        #
        #     XML += '''<Field Name="U16">%(sum_pageU_gyv_ismokos_neatemus_mokesciu)s</Field>
        # <Field Name="U17">%(sum_pageU_pajamu_mokestis_priskaiciuotas)s</Field>
        # <Field Name="U18">%(sum_pageU_pajamu_mokestis_ismoketas)s</Field>
        # <Field Name="B_MM_ID">%(imones_kodas)s</Field>
        # <Field Name="LapoNr">%(LapoNrU)s</Field>
        # <Field Name="B_FormNr"></Field>
        # <Field Name="B_FormVerNr"></Field>
        # <Field Name="B_ML_Metai">%(periodo_metai)s</Field>
        # <Field Name="B_UzpildData">%(pildymo_data)s</Field>
        # </Fields>
        # </Page>''' % {
        #         'sum_pageU_gyv_ismokos_neatemus_mokesciu': str(sum_pageU_gyv_ismokos_neatemus_mokesciu).replace('.',
        #                                                                                                         ',') or '',
        #         'sum_pageU_pajamu_mokestis_priskaiciuotas': str(sum_pageU_pajamu_mokestis_priskaiciuotas).replace('.',
        #                                                                                                           ',') or '',
        #         'sum_pageU_pajamu_mokestis_ismoketas': str(sum_pageU_pajamu_mokestis_ismoketas).replace('.', ',') or '',
        #         'imones_kodas': self.kompanija.company_registry or '',
        #         'LapoNrU': PageNumber or '',
        #         'pildymo_data': pildymo_data,
        #         'periodo_metai': periodo_metai,
        #     }
        # #########

        XML += '''</Pages>
</Form>
</FFData>'''
        page_list = '''<Group Name="Priedas_FR0573A">
<ListPages>
<ListPage>FR0573A</ListPage>
</ListPages>
</Group>
''' * max(PageNumber - 1, 0)
        FAILAS = XML % {
            'MaxPageNumber': PageNumber,
            'U_ismoketu_ismoku_neatemus_mokesciu': convert_to_int_str(U_ismoketu_ismoku_neatemus_mokesciu),
            'U_pajamu_mokestis_priskaiciuotas': convert_to_int_str(U_pajamu_mokestis_priskaiciuotas),
            'U_pajamu_mokestis_ismoketas': convert_to_int_str(U_pajamu_mokestis_ismoketas),
            'A_ismoketu_ismoku_neatemus_mokesciu': convert_to_str(A_ismoketu_ismoku_neatemus_mokesciu),
            'A_pajamu_mokestis_priskaiciuotas': convert_to_int_str(A_pajamu_mokestis_priskaiciuotas),
            'A_pajamu_mokestis_ismoketas': convert_to_int_str(A_pajamu_mokestis_ismoketas),
            'priedoA_lapu_skaicius': int(math.ceil(len(rezidentai_data) / float(num_emp_per_page))),
            'priedoA_eiluciu_skaicius': len(rezidentai_data),
            # 'priedoU_lapu_skaicius': PageNumber - 1,
            # 'priedoU_eiluciu_skaicius': int(round(len(ne_rezidentai_data)/3.0)),
            'priedoU_lapu_skaicius': 0,
            'priedoU_eiluciu_skaicius': 0,
            'page_list': page_list,
        }

        if self._context.get('eds'):
            try:
                self.env.user.upload_eds_file(
                    FAILAS.encode('utf8').encode('base64'),
                    'FR0573.ffdata', self.data_nuo,
                    registry_num=company_data['code']
                )
            except:
                self.sudo().env.user.upload_eds_file(
                    FAILAS.encode('utf8').encode('base64'), 'FR0573.ffdata',
                    self.data_nuo, registry_num=company_data['code']
                )

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'e.vmi.fr0573',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'view_id': self.env.ref('e_ataskaitos.vmi_fr0573_download').id,
            'context': {'failas': FAILAS.encode('utf8').encode('base64')},
        }


FR0573()
