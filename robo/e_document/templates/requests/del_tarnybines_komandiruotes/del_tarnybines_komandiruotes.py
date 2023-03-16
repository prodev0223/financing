# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, api, exceptions, _


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_del_tarnybines_komandiruotes_workflow(self):
        self.ensure_one()
        amount_allowance = self.country_allowance_id.get_amount(self.date_from, self.date_to)
        allowance_percentage = self._get_business_trip_request_allowance_percentage()
        amount_allowance = amount_allowance * allowance_percentage / 100.0  # P3:DivOK
        employee_line_vals = {
            'employee_id': self.employee_id1.id,
            'allowance_amount': amount_allowance,
            'allowance_percentage': allowance_percentage,
            'overtime_compensation': self.business_trip_request_overtime_compensation,
            'journey_compensation': self.business_trip_request_journey_compensation,
            'extra_worked_day_ids': [(0, 0, {
                'date': line.date,
                'worked': line.worked if self.business_trip_request_wish_to_work_extra_days else False
            }) for line in self.business_trip_request_extra_worked_day_ids]
        }

        generated_id = self.env['e.document'].create({
            'template_id': self.env.ref('e_document.isakymas_del_tarnybines_komandiruotes_template').id,
            'document_type': 'isakymas',
            'user_id': self.user_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'text_6': self.text_8,
            'country_allowance_id': self.country_allowance_id.id,
            'business_trip_employee_line_ids': [(0, 0, employee_line_vals)]
        })

        self.write({'record_model': 'e.document', 'record_id': generated_id.id})

    @api.multi
    def _get_business_trip_request_allowance_percentage(self):
        # Overridden in "iprojektavimas" module
        self.ensure_one()
        return 100

    @api.model
    def check_intersecting_holidays(self, employee_id, date_from, date_to, holidays_template_ids):

        if self.template_id != self.env.ref('e_document.prasymas_del_tarnybines_komandiruotes_template',
                                            raise_if_not_found=False):
            return super(EDocument, self).check_intersecting_holidays(employee_id, date_from, date_to,
                                                                      holidays_template_ids)

        if date_from > date_to:
            raise exceptions.UserError(_('Neteisingas periodas.'))

        intersecting_documents = self.env['e.document'].search([('id', '!=', self.id),
                                                                ('employee_id1', '=', employee_id),
                                                                ('state', '=', 'e_signed'),
                                                                ('template_id', 'in', holidays_template_ids),
                                                                ('rejected', '=', False),
                                                                '|',
                                                                '&',
                                                                ('date_from', '<=', date_from),
                                                                ('date_to', '>=', date_from),
                                                                '&',
                                                                ('date_from', '<=', date_to),
                                                                ('date_from', '>=', date_from),
                                                                ])

        intersecting_requests = intersecting_documents.filtered(lambda d: d.record_id != '' and
                                                                d.susijes_isakymas_pasirasytas is True
                                                                and d.document_type == 'prasymas')

        intersecting_documents = intersecting_documents.filtered(lambda d: d.id not in intersecting_requests.mapped('id'))

        if intersecting_documents:
            return False  # Intersecting documents excluding requests with related signed order are found

        for request in intersecting_requests:

            rel_order = self.env['e.document'].browse(request.record_id)

            if not rel_order:
                return False  # Related order not found, checking request dates

            if rel_order.document_type == 'isakymas' and ((rel_order.date_from <= date_from <= rel_order.date_to) or
                                                          (date_to >= rel_order.date_from >= date_from)):
                return False  # Related order is intersecting

        intersecting_holidays = self.env['hr.holidays'].search([('employee_id', '=', employee_id),
                                                                ('date_from', '<=', date_to),
                                                                ('date_to', '>=', date_from),
                                                                ('state', '=', 'validate')], count=True)

        if intersecting_holidays:
            return False  # Intersecting holidays are found

        return True


EDocument()
