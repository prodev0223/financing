# -*- coding: utf-8 -*-
import math
from datetime import datetime

from odoo import models, fields, api, tools
from six import iteritems, iterkeys, itervalues


def convert_to_str(num_float):
    return ('%.2f' % num_float).replace('.', ',')

partner_code_type_map = {'mmak': '1',
                         'vlm': '2',
                         'PVMmk': '3',
                         'ivvpn': '4',
                         'atpdsin': '5'}


class FR0471Report(models.Model):
    _name = 'fr.0471.report'

    partner_id = fields.Many2one('res.partner', string='Partneris')
    date = fields.Date(string='Date')
    b_klase_kodas_id = fields.Many2one('b.klase.kodas')
    amount = fields.Float(string='Suma')

    def quick_create(self, vals):
        updates = [
            ('id', "nextval('%s')" % self._sequence),
        ]
        for k, v in iteritems(vals):
            field = self._fields[k]
            if field.store and field.column_type:
                updates.append((k, field.column_format, field.convert_to_column(v, self)))
            # updates.append((k, v))
        query = """INSERT INTO "%s" (%s) VALUES(%s) RETURNING id""" % (
            self._table,
            ', '.join('"%s"' % u[0] for u in updates),
            ', '.join(u[1] for u in updates),
        )
        self._cr.execute(query, tuple(u[2] for u in updates if len(u) > 2))

    def refresh_report(self, date_from, date_to):
        self._cr.execute('DELETE FROM fr_0471_report')
        self._cr.execute('''
        SELECT 
            transaction.date,
            transaction.partner_id,
            main_aml.b_klase_kodas_id,
            apr.amount as amount_paid
        FROM account_move_line transaction
            INNER JOIN account_partial_reconcile apr on apr.debit_move_id = transaction.id
            INNER JOIN account_move_line main_aml on apr.credit_move_id = main_aml.id
        WHERE transaction.date >= %s and transaction.date <= %s 
            AND main_aml.b_klase_kodas_id IS NOT NULL
        ''', (date_from, date_to))
        for el in self._cr.dictfetchall():
            vals = {'partner_id': el['partner_id'],
                    'date': el['date'],
                    'b_klase_kodas_id': el['b_klase_kodas_id'],
                    'amount': el['amount_paid'],
                    }
            self.quick_create(vals)


FR0471Report()


class FR0471(models.TransientModel):
    _name = 'e.vmi.fr0471'

    def _kompanija(self):
        return self.env.user.company_id.id

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
        return 'FR0471.ffdata'

    kompanija = fields.Many2one('res.company', string='Kompanija', default=_kompanija, required=True)
    data_nuo = fields.Date(string='Periodas nuo', default=_pradzia, required=True)
    data_iki = fields.Date(string='Periodas iki', default=_pabaiga, required=True)
    failas = fields.Binary(string='Ataskaitos dokumentas', readonly=True, default=auto_load)
    failo_pavadinimas = fields.Char(string='Failo pavadinimas', default=failo_pavadinimas)

    @api.multi
    def open_report(self):
        self.env['fr.0471.report'].refresh_report(self.data_nuo, self.data_iki)
        action = self.env.ref('e_ataskaitos.action_vmi_fr_0471_report')
        return action.read()[0]

    def get_additional_data(self, partner_id):
        partner = self.env['res.partner'].browse(partner_id)
        country_code = partner.country_id.code
        if not country_code or country_code == 'LT':
            country_code = ''

        return {'partner_code': partner.kodas or '',
                'id_kodo_kategorija': partner_code_type_map.get(partner.partner_code_type, '1'),
                'country_code': country_code,
                'name': partner.name,
                }

    def get_data(self):
        all_data = {}
        rep_els = self.env['fr.0471.report'].search([])
        for rec in rep_els:
            key = (rec.partner_id.id, rec.b_klase_kodas_id.id)
            if key not in all_data:
                all_data[key] = {'amount': 0.0,
                                 'amount_gpm': 0.0}
            # amount_gpm = tools.float_round(rec.amount * rec.b_klase_kodas_id.gpm_proc / 100.0, precision_digits=2)
            all_data[key]['amount'] += rec.amount
            # all_data[key]['amount_gpm'] += amount_gpm
        partner_obj = self.env['res.partner']
        all_data_keys = sorted(iterkeys(all_data), key=lambda x: partner_obj.browse(x[0]).name)  # P3:Ok
        resident_data = {}
        non_resident_data = {}
        for key in all_data_keys:
            partner_id = key[0]
            if partner_obj.browse(partner_id).rezidentas == 'rezidentas':
                resident_data[key] = all_data[key]
            else:
                non_resident_data[key] = all_data[key]
        return resident_data, non_resident_data

    def get_page_info(self, num_residents_pages, num_nonresidents_pages):

        res = '''<DocumentPages>
<Group Name="Visa forma">
<ListPages>
<ListPage>FR0471</ListPage>
</ListPages>
'''
        if num_residents_pages > 0:
            res += '''<Group Name="Priedas_FR0471P">
<ListPages>
'''
            res += '''<ListPage>FR0471P</ListPage>
''' * num_residents_pages
            res += '''</ListPages>
</Group>
'''
        if num_nonresidents_pages > 0:
            res += '''<Group Name="Priedas_FR0471P">
<ListPages>
'''
            res += '''<ListPage>FR0471P</ListPage>
''' * num_nonresidents_pages
            res += '''</Group>
</ListPages>
'''
        res += '''</Group>
</DocumentPages>
<Pages Count="%d">
''' % (1 + num_residents_pages + num_nonresidents_pages)
        return res

    @api.multi
    def fr0471(self):

        def get_line_resident(line_num, abs_num, data, set_empty=False, first_page=False):
            if first_page:
                letter = 'E'
            else:
                letter = 'P'
            if set_empty is False:
                values = {'num': str(line_num),
                          'abs_num': str(abs_num),
                          'person_id': data.get('partner_code', ''),
                          'id_kodo_kategorija': data.get('id_kodo_kategorija', ''),
                          'country_code': data.get('country_code', ''),
                          'name': data.get('name', ''),
                          'pajamu_kodas': data.get('pajamu_kodas', ''),
                          'amount': convert_to_str(data.get('amount', 0.0)),
                          'paid_by_employer': '0',
                          'returned_to_employee': '0',
                          'amount_gpm': '',
                          'letter': letter,
                          }
            else:
                values = {'num': str(line_num),
                          'abs_num': '',
                          'person_id': '',
                          'id_kodo_kategorija': '',
                          'country_code': data.get('country_code', ''),
                          'name': '',
                          'pajamu_kodas': '',
                          'amount': '',
                          'paid_by_employer': '',
                          'returned_to_employee': '',
                          'amount_gpm': '',
                          'letter': letter,
                          }

            return '''<Field Name="%(letter)s11-%(num)s">%(abs_num)s</Field>
<Field Name="%(letter)s12-%(num)s">%(person_id)s</Field>
<Field Name="%(letter)s12_1-%(num)s">%(id_kodo_kategorija)s</Field>
<Field Name="%(letter)s30-%(num)s">%(country_code)s</Field>
<Field Name="%(letter)s13-%(num)s">%(name)s</Field>
<Field Name="%(letter)s14-%(num)s">%(pajamu_kodas)s</Field>
<Field Name="%(letter)s15-%(num)s">%(amount)s</Field>
<Field Name="%(letter)s16-%(num)s">%(paid_by_employer)s</Field>
<Field Name="%(letter)s25-%(num)s">%(returned_to_employee)s</Field>
<Field Name="%(letter)s26-%(num)s">%(amount_gpm)s</Field>
''' % values

        self.env['fr.0471.report'].refresh_report(self.data_nuo, self.data_iki)
        num_first_page = 2
        num_residents_per_page = 5
        num_non_residents_per_page = 5
        resident_data, non_resident_data = self.get_data()
        num_residents = len(resident_data)
        num_non_residents = len(non_resident_data)
        num_residents_pages = int(round(math.ceil((num_residents - num_first_page) / float(num_residents_per_page))))
        num_nonresidents_pages = int(round(math.ceil(num_non_residents / float(num_non_residents_per_page))))
        page_info = self.get_page_info(num_residents_pages, num_nonresidents_pages)

        company_data = self.kompanija.get_report_company_data()
        pildymo_data = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        periodo_metai = str(datetime.strptime(self.data_nuo, tools.DEFAULT_SERVER_DATE_FORMAT).year)
        resident_keys = resident_data.keys()
        # non_resident_keys = non_resident_data.keys()
        header = '''<?xml version="1.0" encoding="UTF-8"?>
<FFData Version="1" CreatedByLogin="ROBO" CreatedOn="%(create_date)s">
<Form FormDefId="{40F5E678-5C8A-455B-BC15-035BA2DCC5B8}">
''' + page_info
        first_page = '''<Page PageDefName="FR0471" PageNumber="1">
<Fields Count="32">
<Field Name="B_MM_ID">%(kompanijos_kodas)s</Field>
<Field Name="B_MM_Pavad">%(pavadinimas)s</Field>
<Field Name="B_MM_Adresas">%(adresas)s</Field>
<Field Name="B_MM_Epastas">%(email)s</Field>
<Field Name="B_MM_Tel">%(phone)s</Field>
<Field Name="B_ML_Metai">%(year)s</Field>
''' % {'kompanijos_kodas': company_data['code'],
       'pavadinimas': company_data['name'].upper()[:45],
       'adresas': company_data['full_address'],
       'email': company_data['email'].upper(),
       'phone': company_data['phone'],
       'year': periodo_metai,
       'periodo_metai': periodo_metai,
       'create_date': pildymo_data,
       }
        amount_page = 0
        amount_total = sum(el['amount'] for el in itervalues(resident_data))
        abs_num = 0
        for i in range(num_first_page):
            if resident_keys:
                abs_num += 1
                key = resident_keys.pop(0)
                data = resident_data[key].copy()
                add_data = self.get_additional_data(key[0])
                b_klase_kodas = self.env['b.klase.kodas'].browse(key[1]).code
                data.update(add_data, pajamu_kodas=b_klase_kodas)
                amount_page += data['amount']
                line = get_line_resident(i + 1, abs_num, data, set_empty=False, first_page=True)
            else:
                line = get_line_resident(i + 1, 0, {}, set_empty=True, first_page=True)
            first_page += line
        first_page += '''<Field Name="E17">%(num_residents_pages)s</Field>
<Field Name="E19">%(amount_page)s</Field>
<Field Name="E20">%(amount_total)s</Field>
<Field Name="E18">%(num_nonresidents_pages)s</Field>
<Field Name="B_FormNr"></Field>
<Field Name="B_FormVerNr"></Field>
</Fields>
</Page>
''' % {'amount_page': convert_to_str(amount_page),
       'amount_total': convert_to_str(amount_total),
       'num_residents_pages': num_residents_pages and str(num_residents_pages) or '',
       'num_nonresidents_pages': num_nonresidents_pages and str(num_nonresidents_pages) or '', }
        result = header + first_page
        num_next_line = 1
        page_num = 0
        next_page = ''
        amount_page = 0
        while resident_keys:
            if num_next_line == 1:
                page_num += 1
                next_page = '''<Page PageDefName="FR0471P" PageNumber="%(page_num)d">
<Fields Count="56">
''' % {'page_num': page_num}
                amount_page = 0
            key = resident_keys.pop(0)
            abs_num += 1
            data = resident_data[key].copy()
            amount_page += data['amount']
            add_data = self.get_additional_data(key[0])
            b_klase_kodas = self.env['b.klase.kodas'].browse(key[1]).code
            data.update(add_data, pajamu_kodas=b_klase_kodas)
            line = get_line_resident(num_next_line, abs_num, data, set_empty=False, first_page=False)
            next_page += line
            num_next_line = num_next_line % num_residents_per_page + 1

            if num_next_line == 1:
                next_page += '''<Field Name="P19">%(amount_page)s</Field>
<Field Name="B_MM_ID">%(kompanijos_kodas)s</Field>
<Field Name="B_FormNr"></Field>
<Field Name="B_FormVerNr"></Field>
<Field Name="LapoNr">%(page_num)d</Field>
<Field Name="B_ML_Metai">%(year)s</Field>
</Fields>
</Page>
''' % {
                    'page_num': page_num,
                    'amount_page': convert_to_str(amount_page),
                    'kompanijos_kodas': company_data['code'],
                    'year': periodo_metai
                }
                result += next_page
                next_page = ''
        while num_next_line != 1:
            line = get_line_resident(num_next_line, 0, {}, set_empty=True, first_page=False)
            next_page += line
            num_next_line = num_next_line % num_residents_per_page + 1
            if num_next_line == 1:
                next_page += '''<Field Name="P19">%(amount_page)s</Field>
<Field Name="B_MM_ID">%(kompanijos_kodas)s</Field>
<Field Name="B_FormNr"></Field>
<Field Name="B_FormVerNr"></Field>
<Field Name="LapoNr">%(page_num)d</Field>
<Field Name="B_ML_Metai">%(year)s</Field>
</Fields>
</Page>
''' % {
                    'page_num': page_num,
                    'amount_page': convert_to_str(amount_page),
                    'kompanijos_kodas': company_data['code'],
                    'year': periodo_metai,
                }
                result += next_page
                next_page = ''
        result += '''</Pages>
</Form>
</FFData>'''
        FAILAS = result

        if self._context.get('eds'):
            self.env.user.upload_eds_file(
                FAILAS.encode('utf8').encode('base64'), 'FR0471.ffdata',
                self.data_nuo, registry_num=company_data['code']
            )

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'e.vmi.fr0471',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'view_id': self.env.ref('e_ataskaitos.vmi_fr0471_download').id,
            'context': {'failas': FAILAS.encode('utf8').encode('base64')},
        }


FR0471()
