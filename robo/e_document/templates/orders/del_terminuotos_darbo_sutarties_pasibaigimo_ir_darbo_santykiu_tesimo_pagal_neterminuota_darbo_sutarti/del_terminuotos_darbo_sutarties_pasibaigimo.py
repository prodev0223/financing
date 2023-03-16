# -*- coding: utf-8 -*-

from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import _, api, exceptions, models, tools


TEMPLATE = 'e_document.isakymas_del_terminuotos_darbo_sutarties_pasibaigimo_ir_darbo_santykiu_tesimo_pagal_neterminuota_darbo_sutarti_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_terminuotos_darbo_sutarties_pasibaigimo_ir_darbo_santykiu_tesimo_pagal_neterminuota_darbo_sutarti_workflow(
            self):
        self.ensure_one()
        if self.employee_id2 and self.date_1_computed:
            employee_contracts = self.env['hr.contract'].search([
                ('employee_id', '=', self.employee_id2.id)
            ])
            if not self.employee_id2.active:
                self.employee_id2.toggle_active()
            employee_contracts = employee_contracts.sorted(key='date_start', reverse=True)
            last_contract = employee_contracts[0]
            last_contract_end = last_contract.date_end
            new_contract_start = (
                    datetime.strptime(last_contract_end, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(
                days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            last_contract_latest_appointment = last_contract.with_context(date=last_contract_end).appointment_id

            new_contract = self.env['hr.contract.create'].create({
                'name': last_contract.name,
                'employee_id': last_contract.employee_id.id,
                'job_id': last_contract.job_id.id,
                'department_id': last_contract.department_id.id or False,
                'struct_id': last_contract.struct_id.id,
                'date_start': new_contract_start,
                'date_end': False,
                'wage': last_contract_latest_appointment.wage,
                'rusis': 'neterminuota',
                'sodra_papildomai': last_contract_latest_appointment.sodra_papildomai,
                'sodra_papildomai_type': last_contract_latest_appointment.sodra_papildomai_type,
                'trial_date_end': False,
                'use_npd': last_contract_latest_appointment.use_npd,
                'invalidumas': last_contract_latest_appointment.invalidumas,
                'darbingumas': last_contract_latest_appointment.darbingumas,
                'schedule_template_id': last_contract_latest_appointment.schedule_template_id.copy({
                    'appointment_id': False
                }).id,
                'order_date': self.date_document,
            }).with_context(no_action=True).create_contract()

            last_contract.write({
                'priezasties_kodas': '96',
            })

            self.inform_about_creation(new_contract)

            if datetime.strptime(new_contract_start, tools.DEFAULT_SERVER_DATE_FORMAT).day != 1:
                try:
                    subject = _('''
                    [{}] Dokumentas dėl darbo santykių tęsimo pagal neterminuotą darbo sutartį buvo pasirašytas
                    ''').format(self._cr.dbname)
                    body = _('''
                    Ne mėnesio pradžioje buvo pasirašytas dokumentas dėl terminuotos darbo sutarties pasibaigimo ir 
                    santykių tęsimo pagal neterminuotą darbo sutartį. Primename, kad šiam mėnesiui yra sukurti du 
                    algalapiai ir gali prireikti rankinių taisymų susijusių su NPD.
                    ''')
                    self.create_internal_ticket(subject, body)
                except Exception:
                    message = _('''
                    [{}] Failed to create a ticket informing about potential need for manual fixes
                    ''').format(self._cr.dbname)
                    self.env['robo.bug'].sudo().create({'user_id': self.env.user.id, 'error_message': message, })

            self.write({
                'record_model': 'hr.contract',
                'record_id': new_contract.id
            })

    @api.multi
    @api.depends('employee_id2')
    def _compute_date_1_computed(self):
        for rec in self.filtered(lambda doc: doc.template_id == self.env.ref(TEMPLATE) and doc.employee_id2):
            month_prev_dt = (datetime.utcnow() - relativedelta(months=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            employee_contracts = self.env['hr.contract'].search([
                ('employee_id', '=', rec.employee_id2.id),
                ('date_end', '>', month_prev_dt),
                ('state', '!=', 'cancel'),
            ])
            employee_contracts = employee_contracts.sorted(key='date_start', reverse=True)
            if employee_contracts and employee_contracts[0].date_end:
                rec.date_1_computed = employee_contracts[0].date_end

    @api.multi
    @api.constrains('employee_id2')
    def _check_employee_id2_is_correct(self):
        template = self.env.ref(TEMPLATE, raise_if_not_found=False)
        for rec in self:
            if rec.template_id == template and rec.employee_id2 and not rec.date_1_computed:
                raise exceptions.UserError(_(
                    'Pasirinktas darbuotojas neturi darbo sutarties, arba paskutinė darbuotojo darbo sutartis nėra terminuota'))

    @api.multi
    def check_date_1_constraints(self):
        self.ensure_one()
        if self.date_1_computed < datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT):
            if not self.sudo().skip_constraints_confirm:
                return _('Negalima pasirašyti dokumento, nes sena darbo sutartis jau baigė galioti, reikia išjungti dokumento apribojimų tikrinimą.\n')
        return ''

    @api.multi
    def check_workflow_constraints(self):
        res = super(EDocument, self).check_workflow_constraints()
        template = self.env.ref(TEMPLATE)
        for rec in self.filtered(lambda doc: doc.template_id == template):
            res += rec.check_date_1_constraints()
        return res

    @api.model
    def cron_cancel_expired_work_continuation_contracts(self):
        template = self.env.ref(TEMPLATE)
        finished_states = ('e_signed', 'cancel')

        max_end_date = datetime.utcnow()
        days_to_substract = 3
        while days_to_substract:
            max_end_date = (max_end_date - relativedelta(days=1))
            if max_end_date.weekday() in (5, 6):
                continue
            if self.env['sistema.iseigines'].search_count([('date', '=', max_end_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))]):
                continue
            days_to_substract -= 1
        max_date = max_end_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        recs = self.search([('template_id', '=', template.id),
                            ('state', 'not in', finished_states)])
        recs.filtered(lambda d: d.date_1_computed <= max_date).write({'state': 'cancel', 'cancel_uid': self.env.uid})
