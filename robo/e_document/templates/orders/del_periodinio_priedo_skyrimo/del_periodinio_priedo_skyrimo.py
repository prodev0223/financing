# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, api, tools, fields, exceptions, _

TEMPLATE = 'e_document.isakymas_del_periodinio_priedo_skyrimo_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    show_existing_periodic_bonus_warning = fields.Boolean(compute='_compute_show_existing_periodic_bonus_warning')

    @api.model
    def _get_accumulative_work_time_accounting_net_bonus_warning_dependencies(self):
        dependencies = super(EDocument, self)._get_accumulative_work_time_accounting_net_bonus_warning_dependencies()
        dependencies += ['employee_id2', 'date_1']
        return dependencies

    @api.multi
    def _get_employees_for_bonuses(self):
        self.ensure_one()
        template = self.env.ref(TEMPLATE)
        if self.template_id != template:
            return super(EDocument, self)._get_employees_for_bonuses()
        return self.employee_id2

    @api.multi
    def _get_bonus_payment_dates(self):
        self.ensure_one()
        template = self.env.ref(TEMPLATE)
        if self.template_id != template:
            return super(EDocument, self)._get_bonus_payment_dates()
        if not self.date_1:
            return False, False
        date_from_dt = datetime.strptime(self.date_1, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_from = (date_from_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = (date_from_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        return date_from, date_to

    @api.multi
    def check_workflow_constraints(self):
        res = super(EDocument, self).check_workflow_constraints()
        for rec in self.filtered(lambda d: d.template_id == self.env.ref(TEMPLATE)):
            res += rec.check_bonus_type_accumulative_accounting_constraints()
        return res

    @api.multi
    def isakymas_del_periodinio_priedo_skyrimo_workflow(self):
        self.ensure_one()
        date_from, date_to = self._get_bonus_payment_dates()
        bonus_rec = self.env['hr.employee.bonus'].create({
            'employee_id': self.employee_id2.id,
            'for_date_from': date_from,
            'for_date_to': date_to,
            'payment_date_from': date_from,
            'payment_date_to': date_to,
            'bonus_type': self.bonus_type_selection or '1men',
            'amount': self.float_1,
            'amount_type': self.bonus_input_type,
        })
        bonus_rec.confirm()
        bonus_rec.with_context(skip_past_date_check=True).make_periodic()
        periodic_bonus = bonus_rec.periodic_id
        periodic_bonus.write({'date_stop': self.date_2,
                              'action': 'open'})
        date_stop = min(datetime.utcnow(), datetime.strptime(self.date_2, tools.DEFAULT_SERVER_DATE_FORMAT)) \
            if self.date_2 else datetime.utcnow()
        while periodic_bonus.date and periodic_bonus.date <= date_stop.strftime(tools.DEFAULT_SERVER_DATE_FORMAT):
            periodic_bonus.with_context(skip_past_date_check=True).run()
        self.write({
            'record_model': 'hr.employee.bonus.periodic',
            'record_id': bonus_rec.periodic_id.id,
        })
        bonus_rec.write({'related_document': self.id})

    @api.model
    def default_get(self, fields_list):
        res = super(EDocument, self).default_get(fields_list)
        template = self.env.ref(TEMPLATE, raise_if_not_found=False)
        if res.get('template_id') == template.id:
            res['bonus_type_selection'] = '1men'
        return res

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        original_document = self.sudo().cancel_id
        template = self.env.ref(TEMPLATE, raise_if_not_found=False)
        if original_document and original_document.sudo().template_id == template:
            now = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if original_document.record_id:
                periodic_id = self.env['hr.employee.bonus.periodic'].browse(original_document.record_id)
            else:
                periodic_id = self.env['hr.employee.bonus.periodic'].search([
                    ('employee_id', '=', original_document.employee_id2.id),
                    '|', ('date_stop', '=', False), ('date_stop', '>=', now)
                ])
            if periodic_id:
                periodic_id.write({'date_stop': now})
                for bonus in periodic_id.mapped('bonus_ids').filtered(lambda b: b.state == 'confirm'):
                    confirmed_slip = self.env['hr.payslip'].sudo().search_count([
                        ('date_from', '=', bonus.for_date_from),
                        ('date_to', '=', bonus.for_date_to),
                        ('employee_id', '=', bonus.employee_id.id),
                        ('state', 'not in', ['draft', 'verify'])
                    ])
                    if not confirmed_slip:
                        bonus.action_cancel()
        else:
            return super(EDocument, self).execute_cancel_workflow()

    @api.multi
    @api.depends('employee_id2', 'date_1')
    def _compute_show_existing_periodic_bonus_warning(self):
        HrEmployeeBonusPeriodic = self.env['hr.employee.bonus.periodic']
        for rec in self:
            if rec.template_id == self.env.ref(TEMPLATE, False) and rec.employee_id2 and rec.date_1:
                bonus_count = HrEmployeeBonusPeriodic.search_count([
                    ('employee_id', '=', rec.employee_id2.id),
                    '|',
                    ('date_stop', '=', False),
                    ('date_stop', '>=', rec.date_1)])

                if bonus_count:
                    rec.show_existing_periodic_bonus_warning = True

    @api.constrains('bonus_type_selection')
    def _check_bonus_type_selection(self):
        template = self.env.ref(TEMPLATE, raise_if_not_found=False)
        for rec in self:
            if rec.template_id != template:
                continue
            if rec.bonus_type_selection not in ['1men', 'ne_vdu']:
                raise exceptions.ValidationError(
                    _('Skiriant periodinį priedą premijos rūšis privalo būti mėnesinė arba nepatenkanti į VDU.'))


EDocument()
