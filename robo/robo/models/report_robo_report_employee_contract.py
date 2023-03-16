# -*- coding: utf-8 -*-


import re
from datetime import datetime

from odoo.addons.robo.models.linksnis import kas_to_ko

from odoo import api, exceptions, models, tools, _
from odoo.tools.misc import formatLang


class ReportRoboReportEmployeeContract(models.AbstractModel):
    _name = 'report.robo.report_employee_contract'

    @api.multi
    def should_sudo(self, employee):
        return False

    @api.multi
    def render_html(self, doc_ids, data=None):
        if data.get('force_lang'):
            self = self.with_context(lang=data.get('force_lang'))
        report_obj = self.env['report']
        report = report_obj.with_context(force_lang=data.get('force_lang'))._get_report_from_name(
            'robo.report_employee_contract')
        employee = self.env['hr.employee'].browse(data['emp_id'])
        if not employee:
            raise exceptions.ValidationError(_('Related record was not found.\nContact the system administrator.'))

        if self.should_sudo(employee):
            employee = employee.sudo()
            report_obj = self.env['report'].sudo()
            self = self.sudo()

        mapper = {1: _('sausio'), 2: _('vasario'), 3: _('kovo'), 4: _('balandžio'), 5: _('gegužės'), 6: _('birželio'),
                  7: _('liepos'), 8: _('rugpjūčio'), 9: _('rugsėjo'), 10: _('spalio'), 11: _('lapkričio'),
                  12: _('gruodžio'), }
        contract = employee.contract_ids.filtered(lambda s: s.id == data['contract_id'])
        appointment = employee.contract_ids.mapped('appointment_ids').filtered(lambda s: s.id == data['appointment_id'])
        previous_appointment = self.env['hr.contract.appointment'].search(
            [('employee_id', '=', appointment.employee_id.id), ('date_end', '<', appointment.date_start),
             ('contract_id', '=', contract.id)], order='date_end desc', limit=1)

        changelist = []
        if previous_appointment:

            if appointment.job_id != previous_appointment.job_id:
                changelist.append(_('1.2. Pareigos: %s. Darbuotojas vykdys darbo funkcijas, numatytas pareigybės '
                                    'aprašyme. Vykdydamas darbo funkcijas, Darbuotojas privalo laikytis Lietuvos '
                                    'Respublikos įstatymų, Darbdavio įstatų, vidaus reglamentų ir Darbdavio valdymo '
                                    'organo sprendimų.') % appointment.job_id.name)

            if appointment.wage != previous_appointment.wage:
                string_text = _('mėnesinį darbo užmokestį') if \
                    appointment.struct_id.code == 'MEN' else _('valandinį darbo užmokestį')
                if appointment.freeze_net_wage and appointment.struct_id.code == 'MEN':
                    string_text += _(', atskaičius mokesčius')
                    wage = appointment.neto_monthly
                else:
                    string_text += _(', neatskaičius mokesčių')
                    wage = appointment.wage
                changelist.append(_('1.3.1. Darbdavys įsipareigoja darbuotojui mokėti – %s EUR %s.')
                                  % (formatLang(self.env, wage, digits=2), string_text))

            if appointment.avansu_politika != previous_appointment.avansu_politika \
                    or appointment.avansu_politika_suma != previous_appointment.avansu_politika_suma:
                if appointment.avansu_politika == 'fixed_sum':
                    changelist.append(
                        _('1.3.3. Darbo užmokestis mokamas į Darbuotojo sąskaitą banke. '
                          'Darbo užmokestis mokamas du kartus per mėnesį: %s EUR avansas iki einamojo mėnesio %s '
                          'dienos, likusi suma - iki kito mėnesio %s dienos.')
                        % (formatLang(self.env, appointment.avansu_politika_suma, digits=2),
                           appointment.advance_payment_day, data['salary_payment_day']))
                else:
                    changelist.append(
                        _('1.3.3. Darbo užmokestis mokamas į Darbuotojo sąskaitą banke. '
                          'Darbo užmokestis mokamas vieną kartą per mėnesį iki kito mėnesio %s dienos.'
                          ) % data['salary_payment_day']
                    )

            if appointment.department_id and appointment.department_id != previous_appointment.department_id:
                changelist.append(
                    _('1.3.4. Darbuotojas skiriamas dirbti padalinyje „{}“.').format(appointment.department_id.name)
                )

            trial_changes = False
            if appointment.trial_date_end and previous_appointment.trial_date_end:
                prev_date_dt = datetime.strptime(previous_appointment.trial_date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_dt = datetime.strptime(appointment.trial_date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
                if prev_date_dt != date_dt:
                    trial_changes = True
            if not trial_changes:
                if appointment.trial_date_end and not previous_appointment.trial_date_end:
                    trial_changes = True

            if trial_changes:
                date_delta = (datetime.strptime(appointment.trial_date_end, tools.DEFAULT_SERVER_DATE_FORMAT) -
                              datetime.strptime(appointment.trial_date_start, tools.DEFAULT_SERVER_DATE_FORMAT)).days
                if date_delta % 10 == 1:
                    changelist.append(_('3. Nustatomas {0} dienos išbandymo laikotarpis nuo šios'
                                        ' darbo sutarties įsigaliojimo dienos.').format(date_delta))
                else:
                    changelist.append(_('3. Nustatomas {0} dienų išbandymo laikotarpis '
                                        'nuo šios darbo sutarties įsigaliojimo dienos.').format(date_delta))

            if appointment.schedule_template_id.name != previous_appointment.schedule_template_id.name:
                if appointment.schedule_template_id.name == 'Įprasta darbo diena':
                    string_text = _('08-17 40val. savaitė.')
                else:
                    string_text = appointment.schedule_template_id.name if \
                        bool(re.search(r'\d', appointment.schedule_template_id.name)) else \
                        _('{0} etato darbo grafikas').format(int(appointment.schedule_template_id.etatas))
                changelist.append(_('4. Nustatoma darbo dienos (pamainos, darbo savaitės) trukmė: %s.') % string_text)
            if appointment.schedule_template_id.work_norm != previous_appointment.schedule_template_id.work_norm:
                changelist.append(
                    _('5. Nustatomas ne visas darbo laikas: %s.') % appointment.schedule_template_id.work_norm)

            if appointment.schedule_template_id.template_type == 'sumine' != previous_appointment.schedule_template_id.template_type == 'sumine':
                changelist.append(_('Darbuotojas dirba pagal suminę darbo laiko apskaitą.'))

            if previous_appointment.contract_terms_date_end and appointment.contract_terms_date_end and \
                    previous_appointment.contract_terms_date_end != appointment.contract_terms_date_end:
                terms_date_end_dt = datetime.strptime(appointment.contract_terms_date_end,
                                                      tools.DEFAULT_SERVER_DATE_FORMAT)
                changelist.append(_(
                    '12. Darbo sutartis nutraukiama {0} m. {1} mėn. {2} d.').format(terms_date_end_dt.year,
                                                                                    mapper.get(terms_date_end_dt.month),
                                                                                    terms_date_end_dt.day))

            vals = {
                'update': True,
                'changelist': changelist,
            }

        else:

            if appointment.trial_date_end and appointment.trial_date_start <= appointment.trial_date_end:
                date_delta = (datetime.strptime(appointment.trial_date_end, tools.DEFAULT_SERVER_DATE_FORMAT) -
                              datetime.strptime(appointment.trial_date_start,
                                                tools.DEFAULT_SERVER_DATE_FORMAT)).days + 1
                if date_delta % 10 == 1:
                    trial_text = _(
                        'Nustatomas {0} dienos išbandymo laikotarpis nuo '
                        'šios darbo sutarties įsigaliojimo dienos').format(date_delta)
                else:
                    trial_text = _('Nustatomas {0} dienų išbandymo laikotarpis nuo '
                                   'šios darbo sutarties įsigaliojimo dienos').format(date_delta)
            else:
                trial_text = _('Nenustatomas bandomasis laikotarpis')
            if appointment.struct_id.code == 'MEN':
                du_text = _('mėnesinį darbo užmokestį')
                if appointment.freeze_net_wage:
                    du_text += _(', atskaičius mokesčius.')
                else:
                    du_text += _(', neatskaičius mokesčių.')
            else:
                du_text = _('valandinį darbo užmokestį.')
            if appointment.schedule_template_id.work_norm == 1:
                work_level_text = _('Nenustatomas')
            else:
                percentage = appointment.schedule_template_id.work_norm * 100
                work_level_text = _('Nustatomas - {0} %').format(percentage)

            vals = {
                'update': False,
                'trial_text': trial_text,
                'du_text': du_text,
                'work_level_text': work_level_text,
                'department_name': contract.appointment_id.department_id.name,
            }

        ceo_name_ad = kas_to_ko(employee.company_id.vadovas.name)
        ceo_job_ad = kas_to_ko(employee.company_id.vadovas.job_id.name)
        date_dt = datetime.strptime(appointment.date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
        order_date = contract.order_date or appointment.date_start
        order_date_dt = datetime.strptime(order_date, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_display = datetime.strptime(data['contract_date'], tools.DEFAULT_SERVER_DATE_FORMAT)

        # Update the values to pass to Q-web
        vals.update({
            'date_display': _('{0} m. {1} mėn. {2} d.').format(
                date_display.year, mapper.get(date_display.month), date_display.day),
            'appointment_date': _('{0} m. {1} mėn. {2} d.').format(
                date_dt.year, mapper.get(date_dt.month),  date_dt.day),
            'order_date': _('{0} m. {1} mėn. {2} d.').format(
                order_date_dt.year, mapper.get(order_date_dt.month), order_date_dt.day),
            'contract_conditions': data['contract_conditions'] if data['contract_conditions'] else False,
            'contract_liabilities': data['contract_liabilities'] if data['contract_liabilities'] else False,
            'lang': data['force_lang'],
            'representative': data['representative'],
            'salary_payment_day': data['salary_payment_day'],
        })

        if contract.date_end:
            date_end_dt = datetime.strptime(contract.date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
            vals['c_date_end'] = _('{0} m. {1} mėn. {2} d.').format(date_end_dt.year,
                                                                    mapper.get(date_end_dt.month),
                                                                    date_end_dt.day)
        else:
            vals['c_date_end'] = False
        if appointment.job_id:
            job_id = appointment.job_id
        elif contract.job_id:
            job_id = contract.job_id
        else:
            job_id = employee.job_id

        docargs = {
            'doc_ids': doc_ids,
            'doc_model': report.model,
            'docs': employee,
            'contract': contract,
            'appointment': appointment,
            'job_id': job_id,
            'vals': vals,
            'ceo_name_ad': ceo_name_ad,
            'ceo_job_ad': ceo_job_ad
        }
        return report_obj.with_context(lang=vals['lang']).render('robo.report_employee_contract', docargs)
