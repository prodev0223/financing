# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, tools, exceptions
from odoo.tools.translate import _


def convert_to_str(num_float):
    return ('%.2f' % num_float).replace('.', ',')


class GPM313(models.TransientModel):
    _name = 'e.vmi.gpm313'

    def _kompanija(self):
        return self.env.user.company_id.id

    # def _gpm_saskaita(self):
    #     return self.env['account.account'].search([('code', '=', '4481')])

    def _pradzia(self):
        return (datetime.now() + relativedelta(months=-1, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _pabaiga(self):
        return (datetime.now() + relativedelta(months=-1, day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    def auto_load(self):
        if 'failas' in self._context.keys():
            return self._context['failas']
        else:
            return ''

    def failo_pavadinimas(self):
        return 'GPM313.ffdata'

    kompanija = fields.Many2one('res.company', string='Kompanija', default=_kompanija, required=True)
    data_nuo = fields.Date(string='Periodas nuo', default=_pradzia, required=True)
    data_iki = fields.Date(string='Periodas iki', default=_pabaiga, required=True)
    failas = fields.Binary(string='Ataskaitos dokumentas', readonly=True, default=auto_load)
    failo_pavadinimas = fields.Char(string='Failo pavadinimas', default=failo_pavadinimas)
    force = fields.Boolean(string='Priverstinai atnaujinti')
    corrections_exist = fields.Boolean(string='Yra korekcijų', compute='_corrections_exist')
    partner_ids = fields.Many2many('res.partner', string='Filtruoti partnerius')

    @api.onchange('data_nuo')
    def _onchange_data_nuo(self):
        if self.data_nuo:
            date_from = datetime.strptime(self.data_nuo, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to = date_from + relativedelta(day=31)
            self.data_iki = date_to.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.one
    @api.depends('data_nuo', 'data_iki')
    def _corrections_exist(self):
        if self.data_nuo and self.data_iki:
            if self.env['fr.0573.report'].search([('date', '>=', self.data_nuo), ('date', '<=', self.data_iki),
                                                  ('correction', '=', True)], count=True):
                self.corrections_exist = True

    @api.model
    def get_form_values(self, company_id, date_from, date_to, force, partner_ids=[]):
        if not self.env.user.has_group('hr.group_hr_manager'):
            raise exceptions.UserError(_('Jūs neturite pakankamai teisių'))
        self.env['fr.0573.report'].refresh_report(date_from, date_to, force, partner_ids)
        # darbo_a_klase_kodas_id = self.env.ref('l10n_lt_payroll.a_klase_kodas_1').id
        self._cr.execute('''
        SELECT 
            SUM(COALESCE(amount_bruto, 0)) AS amount_bruto, 
            SUM(COALESCE(amount_tax, 0) + COALESCE(gpm_for_responsible_person_amount, 0)) AS amount_gpm, 
            fr_0573_report.iki_15, 
            a_klase_kodas_id
        FROM 
            fr_0573_report 
        LEFT JOIN 
            res_partner AS partner ON fr_0573_report.partner_id = partner.id
        WHERE 
            fr_0573_report.date >= %s AND 
            fr_0573_report.date <= %s AND
            partner.skip_monthly_income_tax_report IS NOT TRUE
        GROUP BY 
            fr_0573_report.iki_15, a_klase_kodas_id
                         ''', (date_from, date_to,))
        empl_bruto = 0
        empl_gpm_iki_15 = 0
        empl_gpm_po_15 = 0
        non_empl_bruto = 0
        non_empl_gpm_iki_15 = 0
        non_empl_gpm_po_15 = 0
        darbo_kodai = ['01', '02', '03', '06', '07']
        excluded_kodai = ['05', '08']
        for row in self._cr.dictfetchall():
            a_klase_kodas_id = row['a_klase_kodas_id']
            if not a_klase_kodas_id:
                continue
            a_klase_kodas_rec = self.env['a.klase.kodas'].browse(a_klase_kodas_id)
            if a_klase_kodas_rec.code in darbo_kodai:
                empl_bruto += row['amount_bruto']
                if row['iki_15']:
                    empl_gpm_iki_15 += row['amount_gpm']
                else:
                    empl_gpm_po_15 += row['amount_gpm']
            elif a_klase_kodas_rec.code not in excluded_kodai:
                non_empl_bruto += row['amount_bruto']
                if row['iki_15']:
                    non_empl_gpm_iki_15 += row['amount_gpm']
                else:
                    non_empl_gpm_po_15 += row['amount_gpm']

        company = self.env['res.company'].browse(company_id)
        date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        return {'pildymo_data': datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                'imones_kodas': company.company_registry,
                'imones_pavadinimas': (company.name or str()).replace('&', '&amp;'),
                'periodo_metai': str(date_from_dt.year),
                'periodo_menuo': str(date_from_dt.month),
                'empl_bruto': convert_to_str(empl_bruto),
                'empl_gpm_iki_15': convert_to_str(empl_gpm_iki_15),
                'empl_gpm_po_15': convert_to_str(empl_gpm_po_15),
                'non_empl_bruto': convert_to_str(non_empl_bruto),
                'non_empl_gpm_iki_15': convert_to_str(non_empl_gpm_iki_15),
                'non_empl_gpm_po_15': convert_to_str(non_empl_gpm_po_15),
                'b_klase_bruto': '',
                'b_klase_gpm': '',
                }

    def open_report(self):
        self.env['fr.0573.report'].refresh_report(self.data_nuo, self.data_iki, self.force,
                                                  self.partner_ids.mapped('id'))
        action = self.env.ref('e_ataskaitos.action_vmi_fr_0573_report')
        res = action.read()[0]
        res['context'] = '''{
            'search_default_not_in_gpm313': True, 
            'search_default_included_in_mothly_income_tax_report': True
        }'''
        res['domain'] = [('date', '>=', self.data_nuo), ('date', '<=', self.data_iki)]
        return res

    @api.multi
    def form_gpm313(self):
        if not self.env.user.has_group('hr.group_hr_manager'):
            raise exceptions.UserError(_('Jūs neturite pakankamai teisių'))
        values = self.env['e.vmi.gpm313'].get_form_values(self.kompanija.id, self.data_nuo, self.data_iki, self.force,
                                                          self.partner_ids.mapped('id'))
        forma_template = '''<?xml version="1.0" encoding="UTF-8"?>
<FFData Version="1" CreatedByApp="robo" CreatedByLogin="robo" CreatedOn="%(pildymo_data)s">
<Form FormDefId="{EB03E9EF-39B0-457F-8264-79E86F053009}">
<DocumentPages>
<Group Name="Visa forma">
<ListPages>
<ListPage>GPM313</ListPage>
</ListPages>
</Group>
</DocumentPages>
<Pages Count="1">
<Page PageDefName="GPM313" PageNumber="1">
<Fields Count="14">
<Field Name="B_MM_ID">%(imones_kodas)s</Field>
<Field Name="B_MM_Pavadinimas">%(imones_pavadinimas)s</Field>
<Field Name="B_ML_Metai">%(periodo_metai)s</Field>
<Field Name="B_ML_Menuo">%(periodo_menuo)s</Field>
<Field Name="G5">%(empl_bruto)s</Field>
<Field Name="G6">%(empl_gpm_iki_15)s</Field>
<Field Name="G7">%(empl_gpm_po_15)s</Field>
<Field Name="G8">%(non_empl_bruto)s</Field>
<Field Name="G9">%(non_empl_gpm_iki_15)s</Field>
<Field Name="G10">%(non_empl_gpm_po_15)s</Field>
<Field Name="G11">%(b_klase_bruto)s</Field>
<Field Name="G12">%(b_klase_gpm)s</Field>
<Field Name="B_FormNr"></Field>
<Field Name="B_FormVerNr"></Field>
</Fields>
</Page>
</Pages>
</Form>
</FFData>
'''
        failas = forma_template % values
        if self._context.get('check_report_matches_payslips'):
            report_action = self.open_report()
            domain = report_action.get('domain')
            if domain:
                report = self.env['fr.0573.report'].search(domain, limit=1)
            else:
                report = self.env['fr.0573.report'].search([
                    ('date', '<=', self.data_iki),
                    ('date', '>=', self.data_nuo)
                ], order='write_date desc', limit=1)
            if not report:
                raise exceptions.UserError(_('Report could not be found'))
            pairs_to_match = [
                ('payslip_amount_bruto', 'amount_bruto'),
                ('payslip_amount_neto', 'amount_neto'),
                ('payslip_amount_tax', 'amount_tax'),
            ]
            report_matches_payslip = all(
                tools.float_compare(report[to_match[0]], report[to_match[1]], precision_digits=2) == 0
                for to_match in pairs_to_match
            )
            if not report_matches_payslip:
                raise exceptions.UserError(_('Report values do not match payslip values'))
        if self._context.get('eds'):
            try:
                self.env.user.upload_eds_file(failas.encode('utf8').encode('base64'), 'GPM313.ffdata', self.data_nuo)
            except:
                self.sudo().env.user.upload_eds_file(failas.encode('utf8').encode('base64'), 'GPM313.ffdata',
                                                     self.data_nuo)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'e.vmi.gpm313',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
            'view_id': self.env.ref('e_ataskaitos.vmi_gpm313_download').id,
            'context': {'failas': failas.encode('utf8').encode('base64')},
        }


GPM313()
