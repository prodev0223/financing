# -*- coding: utf-8 -*-

from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import _, api, exceptions, fields, models, tools


class EDocument(models.Model):
    _inherit = 'e.document'

    show_inform_of_possible_subsidy_banner = fields.Boolean(compute='_compute_show_inform_of_possible_subsidy_banner')

    @api.multi
    @api.depends('employee_id2', 'template_id')
    def _compute_show_inform_of_possible_subsidy_banner(self):
        date_today = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        template = self.env.ref('e_document.isakymas_del_prastovos_nutraukimo_template')
        for rec in self.filtered(lambda t: t.template_id == template):
            rec.show_inform_of_possible_subsidy_banner = date_today <= '2021-08-31'

    @api.multi
    def _check_main_downtime_cancellation_constraints(self):
        self.ensure_one()
        if not self.is_prastovos_nutraukimo_doc():
            return
        if not self._context.get('force_check_constraints') and \
                (self.sudo().skip_constraints_confirm or self.sudo().skip_constraints):
            return
        cancel_date = self.date_2
        if not cancel_date:
            raise exceptions.UserError(_('Nenustatyta, kada nutraukima prastova'))
        downtime = self.env['hr.holidays'].search([
            ('date_from_date_format', '<=', cancel_date),
            ('date_to_date_format', '>=', cancel_date),
            ('employee_id', '=', self.employee_id2.id),
            ('holiday_status_id', '=', self.env.ref('hr_holidays.holiday_status_PN').id),
            ('type', '=', 'remove'),
        ], limit=1)

        # When cancelling downtime for the start date the date from will match date to and the record will not be
        # confirmed to keep data and to restore the record just in case. So here we can include non validated leaves as
        # long as their end date does not match start date.
        if downtime.state != 'validate':
            if downtime.date_from != downtime.date_to:
                downtime = None

        if not downtime:
            raise exceptions.UserError(_('Nurodytai datai nurodytam darbuotojui prastova nepaskelbta'))

        ziniarastis_is_confirmed = self.env['ziniarastis.period.line'].search_count([
            ('contract_id', '=', self.employee_id2.with_context(date=cancel_date).contract_id.id),
            ('date_from', '<=', downtime.date_to_date_format),
            ('date_to', '>=', cancel_date),
            ('state', '=', 'done')
        ])
        if ziniarastis_is_confirmed:
            if self.env.user.is_accountant():
                err_msg = _('Norint patvirtinti šį įsakymą pirmiausia reikia atšaukti darbo laiko žiniaraštį.')
            else:
                err_msg = _('Nurodytai datai šiam darbuotojui jau pradėtas skaičiuoti ar net paskaičiuotas darbo '
                            'užmokestis.')
            raise exceptions.ValidationError(err_msg)

    @api.multi
    def execute_confirm_workflow_check_values(self):
        res = super(EDocument, self).execute_confirm_workflow_check_values()
        for doc in self:
            doc._check_main_downtime_cancellation_constraints()
        return res

    @api.multi
    def is_prastovos_nutraukimo_doc(self):
        self.ensure_one()
        doc_to_check = self.env.ref('e_document.isakymas_del_prastovos_nutraukimo_template', raise_if_not_found=False)
        is_doc = doc_to_check and self.sudo().template_id.id == doc_to_check.id
        if not is_doc:
            try:
                is_doc = doc_to_check and self.template_id.id == doc_to_check.id
            except:
                pass
        return is_doc

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        # Find the original document
        original_document = self.sudo().cancel_id

        if original_document and original_document.is_prastovos_nutraukimo_doc():
            if not self.sudo().skip_constraints:
                original_document.with_context(force_check_constraints=True)._check_main_downtime_cancellation_constraints()
            downtime = None
            if original_document.record_id and original_document.record_model == 'hr.holidays':
                downtime = self.env['hr.holidays'].search([('id', '=', original_document.record_id)], limit=1)
            cancel_date = original_document.date_2
            if not downtime:
                downtime = self.env['hr.holidays'].search([
                    ('date_from_date_format', '<=', cancel_date),
                    ('date_to_date_format', '>=', cancel_date),
                    ('employee_id', '=', original_document.employee_id2.id),
                    ('holiday_status_id', '=', self.env.ref('hr_holidays.holiday_status_PN').id),
                    ('type', '=', 'remove'),
                ], limit=1)
            if not downtime:
                raise exceptions.ValidationError(_('Prastovos neatvykimas nerastas. Susisiekite su savo buhalteriu.'))

            if downtime.state == 'validate':
                downtime.action_refuse()
                downtime.action_draft()
            downtime.write({'date_to': self.calc_date_to(original_document.date_1)})  # Restore original date
            downtime.action_confirm()
            downtime.sudo().action_approve()
        else:
            return super(EDocument, self).execute_cancel_workflow()

    @api.multi
    def isakymas_del_prastovos_nutraukimo_workflow(self):
        self.ensure_one()
        if not self.is_prastovos_nutraukimo_doc():
            return
        self._check_main_downtime_cancellation_constraints()

        cancel_date = self.date_2
        cancel_date_dt = datetime.strptime(cancel_date, tools.DEFAULT_SERVER_DATE_FORMAT)
        day_before_cancel_date = (cancel_date_dt - relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        downtime = self.env['hr.holidays'].search([
            ('date_from_date_format', '<=', cancel_date),
            ('date_to_date_format', '>=', cancel_date),
            ('employee_id', '=', self.employee_id2.id),
            ('holiday_status_id', '=', self.env.ref('hr_holidays.holiday_status_PN').id),
            ('type', '=', 'remove'),
            ('state', '=', 'validate')
        ], limit=1)

        downtime.action_refuse()
        downtime.action_draft()
        self.write({'date_1': downtime.date_to_date_format})
        # Day before might be before the holiday starts
        date_to = max(downtime.date_from, self.calc_date_to(day_before_cancel_date))
        downtime.write({'date_to': date_to})
        # If the entire downtime is cancelled - don't confirm the record
        if date_to != downtime.date_from:
            downtime.action_confirm()
            downtime.sudo().action_approve()
        self.write({
            'record_model': 'hr.holidays',
            'record_id': downtime.id,
        })


EDocument()
