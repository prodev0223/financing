# -*- coding: utf-8 -*-
from odoo import models, api, fields, _

UNPAID_FREE_TIME_REQUEST_TEMPLATE = 'e_document.unpaid_free_time_request_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    is_unpaid_free_time_request = fields.Boolean(compute='_compute_is_unpaid_free_time_request')
    unpaid_free_time_table = fields.Html(compute='_compute_unpaid_free_time_table')

    @api.multi
    def _compute_is_unpaid_free_time_request(self):
        unpaid_free_time_request_template = self.env.ref(UNPAID_FREE_TIME_REQUEST_TEMPLATE, False)
        for rec in self:
            rec.is_unpaid_free_time_request = rec.template_id and rec.template_id == unpaid_free_time_request_template

    @api.multi
    @api.depends('e_document_time_line_ids')
    def _compute_unpaid_free_time_table(self):
        table = '''<table>{}</table>'''
        row = '''<tr>{}</tr>'''
        cell_style = '''border: 1px solid black; border-collapse: collapse; padding: 2px; text-align: center;'''
        cell = '''<td style="{}">'''.format(cell_style) + '''{}</td>'''
        header_cell = '''<th style="{}">'''.format(cell_style) + '''{}</th>'''

        header_row = row.format(''.join([
            header_cell.format(_('Date')),
            header_cell.format(_('From')),
            header_cell.format(_('To')),
            header_cell.format(_('Duration')),
        ]))

        for rec in self:
            rows = [header_row]
            for line in rec.e_document_time_line_ids:
                rows.append(row.format(''.join([
                    cell.format(line.date),
                    cell.format(self.format_float_to_hours(line.time_from)),
                    cell.format(self.format_float_to_hours(line.time_to)),
                    cell.format(self.format_float_to_hours(line.duration)),
                ])))
            rec.unpaid_free_time_table = table.format(''.join(rows))

    @api.multi
    @api.depends(lambda self: self._min_max_date_dependencies())
    def _compute_min_max_dates(self):
        unpaid_free_time_documents = self.filtered(lambda document: document.is_unpaid_free_time_request)
        other_documents = self.filtered(lambda document: not document.is_unpaid_free_time_request)
        for rec in unpaid_free_time_documents:
            dates = rec.mapped('e_document_time_line_ids').mapped('date')
            if not dates:
                rec.min_date_from = rec.max_date_to = False
            else:
                rec.min_date_from, rec.max_date_to = min(dates), max(dates)
        return super(EDocument, other_documents)._compute_min_max_dates()

    @api.multi
    def _min_max_date_dependencies(self):
        current_dependencies = super(EDocument, self)._min_max_date_dependencies()
        additional_dependencies = ['e_document_time_line_ids.date']
        return list(set(current_dependencies + additional_dependencies))

    @api.multi
    def execute_confirm_workflow_check_values(self):
        super(EDocument, self).execute_confirm_workflow_check_values()
        for rec in self.filtered(lambda d: d.is_unpaid_free_time_request):
            if rec.sudo().skip_constraints_confirm:
                continue
            rec.check_free_time_document_constraints(rec.employee_id1)

    @api.multi
    def unpaid_free_time_request_workflow(self):
        self.ensure_one()
        order = self.sudo().create({
            'template_id': self.env.ref('e_document.unpaid_free_time_order_template').id,
            'document_type': 'isakymas',
            'employee_id2': self.employee_id1.id,
            'date_2': self.date_document,
            'user_id': self.user_id.id,
            'bool_1': True,  # Used in the unpaid free time order to determine if the document comes from a request
            'e_document_time_line_ids': [(0, 0, line.read()[0]) for line in self.e_document_time_line_ids],
        })
        self.write({'record_model': 'e.document', 'record_id': order.id})
