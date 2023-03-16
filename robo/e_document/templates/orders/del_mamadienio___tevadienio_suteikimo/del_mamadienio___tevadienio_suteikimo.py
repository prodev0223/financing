# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, api, exceptions, _, tools, fields

ORDER_TEMPLATE = 'e_document.isakymas_del_mamadienio_/_tevadienio_suteikimo_template'
REQUEST_TEMPLATE = 'e_document.prasymas_del_mamadienio_/_tevadienio_suteikimo_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    find_children_automatically = fields.Boolean(compute='_compute_find_children_automatically')
    processed_num_children = fields.Selection([('0', 'The employee has no children'),
                                               ('1', '1 (Disabled under 18 years old)'),
                                               ('1_under_12', '1 (under 12 years old)'),
                                               ('2', '2 (Under 12 years old)'),
                                               ('3', '3 and over (Under 12 years old)')],
                                              compute='_compute_processed_num_children')

    @api.multi
    @api.depends('num_children')
    def _compute_find_children_automatically(self):
        """Checking or 'Use children's records for monthly parental leave documents' field is on or off."""
        order_template = self.env.ref(ORDER_TEMPLATE, raise_if_not_found=False)
        request_template = self.env.ref(REQUEST_TEMPLATE, raise_if_not_found=False)
        for rec in self.filtered(lambda t: t.template_id in [order_template, request_template]):
            config_parameter = rec.env.user.company_id.use_children_records_for_parental_leave_documents
            if config_parameter:
                rec.find_children_automatically = config_parameter

    @api.multi
    @api.depends('num_children', 'date_3', 'employee_id2', 'employee_id1')
    def _compute_processed_num_children(self):
        """
        If 'Use children's records for monthly parental leave documents' field is on,
        used 'processed_num_children' field, if off 'processed_num_children' turns 'num_children' field.
        """
        order_template = self.env.ref(ORDER_TEMPLATE, raise_if_not_found=False)
        request_template = self.env.ref(REQUEST_TEMPLATE, raise_if_not_found=False)
        for rec in self.filtered(lambda t: t.template_id in [order_template, request_template]):
            if not rec.find_children_automatically:
                rec.processed_num_children = rec.num_children
                continue
            employee = rec.employee_id2 if rec.document_type == 'isakymas' else rec.employee_id1
            date = rec.date_3
            if not employee or not date:
                continue
            children_list = employee.sudo().get_list_of_children_by_age_and_disability(date)
            if children_list['under_twelve'] >= 3:
                rec.processed_num_children = '3'
            elif children_list['under_twelve'] == 2:
                rec.processed_num_children = '2'
            elif children_list['under_twelve'] == 1:
                rec.processed_num_children = '1_under_12'
            elif children_list['with_disability'] >= 1:
                rec.processed_num_children = '1'
            else:
                rec.processed_num_children = '0'

    @api.multi
    @api.constrains('num_extra_days')
    def constrains_children(self):
        order_template = self.env.ref(ORDER_TEMPLATE, raise_if_not_found=False)
        request_template = self.env.ref(REQUEST_TEMPLATE, raise_if_not_found=False)
        for rec in self.filtered(lambda t: t.template_id in [order_template, request_template]):
            if not rec.find_children_automatically:
                # Only check constraints when use children records is disabled
                return super(EDocument, rec).constrains_children()

    @api.multi
    @api.constrains('date_3', 'date_4')
    def _check_dates_do_not_match(self):
        """
        Check whether date_3 and date_4 are different dates
        """
        order_template = self.env.ref(ORDER_TEMPLATE, raise_if_not_found=False)
        request_template = self.env.ref(REQUEST_TEMPLATE, raise_if_not_found=False)
        for rec in self.filtered(lambda t: t.template_id in [order_template, request_template]):
            if rec.num_extra_days == '1':
                if rec.date_4:
                    rec.date_4 = False
                continue
            if rec.date_3 == rec.date_4:
                raise exceptions.ValidationError(_('The first extra day cannot be the same as the second extra day'))

    @api.multi
    def _date_from_display(self):
        order_template = self.env.ref(ORDER_TEMPLATE, raise_if_not_found=False)
        request_template = self.env.ref(REQUEST_TEMPLATE, raise_if_not_found=False)
        other_documents = self.env['e.document']
        for rec in self:
            if rec.template_id not in [order_template, request_template]:
                other_documents |= rec
                continue

            if rec.num_extra_days == '1':
                date_from = rec.date_3
            else:
                date_from_min = min(rec.date_3, rec.date_4)
                date_from = date_from_min

            rec.date_from_display = date_from
        super(EDocument, other_documents)._date_from_display()

    @api.multi
    def _date_to_display(self):
        order_template = self.env.ref(ORDER_TEMPLATE, raise_if_not_found=False)
        request_template = self.env.ref(REQUEST_TEMPLATE, raise_if_not_found=False)
        other_documents = self.env['e.document']
        for rec in self:
            if rec.template_id not in [order_template, request_template]:
                other_documents |= rec
                continue

            date_to = False

            if rec.num_extra_days == '1':
                date_to = rec.date_3
            else:
                date_from_str = min(rec.date_3, rec.date_4)
                date_to_str = max(rec.date_3, rec.date_4)
                date_from_dt = datetime.strptime(date_from_str, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_from_next_day = (date_from_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                if date_to_str == date_from_next_day:
                    date_to = date_to_str

            rec.date_to_display = date_to
        super(EDocument, other_documents)._date_to_display()

    @api.multi
    def isakymas_del_mamadienio_tevadienio_suteikimo_workflow(self):
        self.ensure_one()
        isakymo_nr = self.document_number
        holiday_name = 'Papildomas poilsio laikas darbuotojams, auginantiems neįgalų vaiką iki 18 metų arba du ir ' \
                       'daugiau vaikų iki 12 metų'
        vals = {
            'name': holiday_name,
            'data': self.date_document,
            'employee_id': self.employee_id2.id,
            'holiday_status_id': self.env.ref('hr_holidays.holiday_status_M').id,
            'date_from': self.calc_date_from(self.date_3),
            'date_to': self.calc_date_to(self.date_3),
            'type': 'remove',
            'numeris': isakymo_nr,
        }
        hol_id = self.env['hr.holidays'].create(vals)
        hol_id.action_approve()
        self.inform_about_creation(hol_id)
        if self.num_extra_days == '2':
            vals.update({
                'date_from': self.calc_date_from(self.date_4),
                'date_to': self.calc_date_to(self.date_4)
            })
            hol2_id = self.env['hr.holidays'].create(vals)
            hol2_id.action_approve()
            self.inform_about_creation(hol2_id)
        self.write({
            'record_model': 'hr.holidays',
            'record_id': hol_id.id,
        })

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        template = self.env.ref(ORDER_TEMPLATE, raise_if_not_found=False)
        order = self.cancel_id
        if order and order.template_id == template:
            record_model = order.record_model
            record_id = order.record_id
            holidays_to_remove = self.env['hr.holidays']
            if record_model and record_id:
                holidays_to_remove |= self.env[record_model].browse(record_id)
            if order.num_extra_days == '2':
                holidays_to_remove |= self.env['hr.holidays'].search([
                    ('employee_id', '=', order.employee_id2.id),
                    ('date_from', '=', self.calc_date_from(order.date_4)),
                    ('date_to', '=', self.calc_date_to(order.date_4)),
                    ('holiday_status_id', '=', self.env.ref('hr_holidays.holiday_status_M').id),
                    ('type', '=', 'remove'),
                    ('numeris', '=', order.document_number)
                ], limit=1)
            holidays_to_remove = holidays_to_remove.filtered(lambda h: h.date_from)
            for holiday in holidays_to_remove:
                validated_timesheets = self.env['ziniarastis.period.line'].search_count([
                    ('employee_id', '=', holiday.employee_id.id),
                    ('date_from', '<=', holiday.date_from_date_format),
                    ('date_to', '>=', holiday.date_from_date_format),
                    ('ziniarastis_period_id.state', '=', 'done')
                ])
                if validated_timesheets:
                    raise exceptions.Warning(_('Įsakymo patvirtinti negalima, nes atlyginimai jau buvo '
                                               'paskaičiuoti. Informuokite buhalterį '
                                               'parašydami žinutę dokumento apačioje.'))
            holidays_to_remove.filtered(lambda h: h.state == 'validate').action_refuse()
            holidays_to_remove.action_draft()
            holidays_to_remove.unlink()
        else:
            super(EDocument, self).execute_cancel_workflow()

    @api.multi
    def get_requested_free_day_periods(self):
        """
        Get free days requested per period based on the requested days.
        @return: list() - a list of periods and days requested for each period ([[year, month, days_requested], []])
        """
        self.ensure_one()
        date_3_dt = datetime.strptime(self.date_3, tools.DEFAULT_SERVER_DATE_FORMAT)
        first_period = [date_3_dt.year, date_3_dt.month, 1]
        second_period = None
        if self.num_extra_days == '2':
            date_4_dt = datetime.strptime(self.date_4, tools.DEFAULT_SERVER_DATE_FORMAT)
            second_period = [date_4_dt.year, date_4_dt.month, 1]
            if first_period == second_period:
                first_period[2] += 1
                second_period = None
        periods = [first_period]
        if second_period:
            periods.append(second_period)
        return periods

    @api.multi
    def execute_confirm_workflow_check_values(self):
        """ Checks value before allowing to confirm an edoc """
        res = super(EDocument, self).execute_confirm_workflow_check_values()

        order_template_id = self.env.ref(ORDER_TEMPLATE, raise_if_not_found=False).id
        request_template_id = self.env.ref(REQUEST_TEMPLATE, raise_if_not_found=False).id
        parental_leave_documents = self.filtered(
            lambda document: document.template_id.id in [order_template_id, request_template_id]
        )
        company_id = self.env.user.company_id
        if not company_id.use_children_records_for_parental_leave_documents:
            parental_leave_documents.perform_parental_leave_checks()
            return res

        for rec in parental_leave_documents:
            if rec.processed_num_children == '0':
                raise exceptions.ValidationError(
                    _('You cannot choose days off. The employee has no children.')
                )
            elif rec.processed_num_children in ['1', '2'] and rec.num_extra_days == '2':
                raise exceptions.ValidationError(
                    _('You cannot choose two days off, if you have less than three children.')
                )
            elif rec.processed_num_children == '1_under_12' and rec.num_extra_days != '1':
                raise exceptions.ValidationError(
                    _('You cannot ask for more than one day off every three months if you have only one child who\'s '
                      'under twelve years old.')
                )

            employee = rec.employee_id2 if rec.document_type == 'isakymas' else rec.employee_id1

            if rec.processed_num_children != '1_under_12':
                requested_periods = rec.get_requested_free_day_periods()
                for requested_period in requested_periods:
                    days_left = employee.child_support_free_days_left(year=requested_period[0],
                                                                      month=requested_period[1])
                    days_requested = requested_period[2]
                    if days_left < days_requested:
                        raise exceptions.ValidationError(_('Insufficient days'))
            else:
                rec.perform_parental_leave_checks()

        return res

    @api.multi
    def perform_parental_leave_checks(self):
        # Make sure document template is checked before calling this method
        for rec in self:
            if rec.processed_num_children != '1_under_12':
                continue  # TODO no checks exist yet
            employee = rec.employee_id2 if rec.document_type == 'isakymas' else rec.employee_id1
            date = datetime.strptime(rec.date_3, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_from_dt = (date - relativedelta(months=3)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = (date + relativedelta(months=3)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            parental_leave_dates_taken = self.env['hr.holidays'].sudo().search([
                ('employee_id', '=', employee.id),
                ('date_from_date_format', '<=', date_to_dt),
                ('date_to_date_format', '>=', date_from_dt),
                ('state', '=', 'validate'),
                ('type', '=', 'remove'),
                ('holiday_status_id', '=', self.env.ref('hr_holidays.holiday_status_M').id)
            ]).mapped('date_to_date_format')
            if parental_leave_dates_taken:
                raise exceptions.ValidationError(
                    _('You can not request for another parental leave date due to the parental leaves taken for '
                      'the following dates: {}').format(', '.join(parental_leave_dates_taken))
                )


EDocument()
