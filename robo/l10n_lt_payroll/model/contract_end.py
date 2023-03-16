# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions, tools
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


class HrContract(models.Model):

    _inherit = 'hr.contract'

    priezasties_kodas = fields.Char(string='Priežasties kodas')
    priezastis = fields.Char(string='Priežastis')
    priezasties_patikslinimo_kodas = fields.Char(string='Priežasties patikslinimo kodas')
    priezasties_patikslinimas = fields.Char(string='Priežasties patikslinimas')
    teises_akto_straipsnis = fields.Char(string='Teisės akto straipsnis')
    teises_akto_straipsnio_dalis = fields.Char(string='Teisės akto straipsnio dalis')
    teises_akto_straipsnio_dalies_punktas = fields.Char(string='Teisės akto straipsnio dalies punktas')
    num_men_iseitine = fields.Float(string='Už kiek mėnesių išeitinė')

    @api.one
    def create_sd2(self):
        if not self.date_end:
            raise exceptions.Warning(_('Kontraktas nesibaigia'))
        sd_darbuotojai_2_record = self.env['sodra.darbuotojai.sd2'].create({})
        sd_2_paramter_record = self.env['sodra.parametrai.sd2'].create({
            'sodra_id': sd_darbuotojai_2_record.id,
            'employee_id': self.employee_id.id,
            'contract_id': self.id,
            'priezastis': self.priezasties_kodas,
            'patikslinimo_kodas': self.priezasties_patikslinimo_kodas,
            'patikslinimo_paaiskinimas': self.priezasties_patikslinimas,
            'straipsnis': self.teises_akto_straipsnis,
            'straipsnio_dalis': self.teises_akto_straipsnio_dalis,
            'dalies_punktas': self.teises_akto_straipsnio_dalies_punktas,
            'men_sk': self.num_men_iseitine,
        })
        gen_data = sd_darbuotojai_2_record.with_context(company_id=self.env.user.company_id.id,
                                                        dokumento_data=datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)).generuokviska()['context']
        failas = False
        for k in gen_data:
            if 'failas' in k:
                failas = gen_data[k]
                break
        if failas:
            attach_vals = {'res_model': 'hr.contract', 'name': '2-SD' + '.ffdata',
                           'datas_fname': '2-SD' + '.ffdata', 'res_id': self.id,
                           'type': 'binary', 'db_datas': failas}#.decode('base64')}
            self.env['ir.attachment'].sudo().create(attach_vals)

    #
    # @api.model
    # def cron_check_ending_trial_contracts(self, check_ending_today=False, check_ending_tomorrow=True, days_to_check_in_the_future=5):
    #     def send_trial_end_messages(contracts):
    #         for contract in contracts:
    #             now = datetime.utcnow()
    #             ends_in_days = (datetime.strptime(contract.trial_date_end, tools.DEFAULT_SERVER_DATE_FORMAT) - now).days
    #             if contract.trial_date_end == now.strftime(tools.DEFAULT_SERVER_DATE_FORMAT):
    #                 end_string = _('šiandien')
    #             elif contract.trial_date_end == (now+relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT):
    #                 end_string = _('rytoj')
    #             else:
    #                 end_string = _('už %s dienų') % str(ends_in_days+1)
    #             priority = 'medium' if ends_in_days > 1 else 'high'
    #             employee_name = contract.employee_id.name
    #             trial_period_end = contract.trial_date_end
    #             msg = {
    #                 'body': _('Informuojame, kad darbuotojui %s %s (%s) baigiasi bandomasis laikotarpis') % (employee_name, end_string, trial_period_end),
    #                 'subject': _('Bandomojo periodo pabaiga'),
    #                 'priority': priority,
    #                 'front_message': True,
    #                 'rec_model': 'hr.employee',
    #                 'rec_id': contract.employee_id.id,
    #                 'view_id': False,
    #                 'partner_ids': [self.env.user.sudo().company_id.vadovas.user_id.partner_id.id or
    #                                 self.env.user.sudo().company_id.vadovas.address_home_id.id],
    #             }
    #             contract.robo_message_post(**msg)
    #
    #     now = datetime.utcnow()
    #
    #     trial_ending_contracts = self.search([
    #         ('trial_date_end', '!=', False),
    #         ('trial_date_end', '>=', now.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
    #     ])
    #
    #     dates_end = list()
    #     if check_ending_today:
    #         dates_end.append(now.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
    #     if check_ending_tomorrow:
    #         dates_end.append((now + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
    #     dates_end.append((now + relativedelta(days=days_to_check_in_the_future)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
    #
    #     contracts_trial_end = trial_ending_contracts.filtered(lambda c: c.trial_date_end in dates_end).sorted(key='trial_date_end')
    #     send_trial_end_messages(contracts_trial_end)


HrContract()
