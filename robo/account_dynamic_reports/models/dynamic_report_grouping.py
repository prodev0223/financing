# -*- coding: utf-8 -*-

import json

from odoo import api, fields, models


class DynamicReportGrouping(models.AbstractModel):
    _name = 'dynamic.report.grouping'

    @api.model
    def get_report_model(self):
        return self.env['ir.model'].sudo().search([('model', '=', self._name)], limit=1)

    @api.model
    def _default_group_by_fields(self):
        report_model = self.get_report_model()
        if not report_model:
            return
        return self.env['dr.group.by.field'].search([
            ('report_model_id', '=', report_model.id),
            ('applied_by_default', '=', True)
        ])

    def _get_group_by_field_domain(self):
        report_model = self.get_report_model()
        if not report_model:
            return [True, '=', False]
        return [('report_model_id', '=', report_model.id)]

    group_by_field_ids = fields.Many2many('dr.group.by.field', string='Group by', domain=_get_group_by_field_domain,
                                          default=_default_group_by_fields, inverse='_inverse_group_by_field_ids')

    group_by_field_identifiers = fields.Text(string='Stored ordered group_by identifiers',
                                             help='Used to determine group by sequence')

    show_group_by_selection = fields.Boolean(compute='_compute_show_group_by_selection', store=False)

    @api.multi
    @api.depends('group_by_field_ids')
    def _compute_show_group_by_selection(self):
        report_models = self.env['ir.model'].sudo().search([('model', 'in', [x._name for x in self])])
        models_with_filter_fields_by_name = self.env['dr.group.by.field'].sudo().search([
            ('report_model_id', 'in', report_models.ids),
        ]).mapped('report_model_id.name')
        for rec in self:
            rec.show_group_by_selection = rec._name in models_with_filter_fields_by_name

    @api.multi
    def _inverse_group_by_field_ids(self):
        for rec in self:
            group_by_field_identifiers = rec.group_by_field_ids.mapped('identifier')
            try:
                rec.write({'group_by_field_identifiers': json.dumps(group_by_field_identifiers)})
            except Exception as e:
                pass

    @api.model
    def process_selected_group_by_identifiers(self, group_by_identifiers):
        report_model = self.env['ir.model'].sudo().search([('model', '=', self._name)], limit=1)
        return [
            identifier for identifier in group_by_identifiers if
            identifier in self.env['dr.group.by.field'].sudo().search([
                ('report_model_id', '=', report_model.id)
            ]).mapped('identifier')
        ]

    @api.multi
    def store_group_by_identifiers(self, group_by_identifiers):
        group_by_fields = self.env['dr.group.by.field'].search([
            '|',
            ('identifier', 'in', group_by_identifiers),
            ('forced', '=', True)
        ])
        self.write({'group_by_field_ids': [(6, 0, group_by_fields.ids)]})
        self.write({'group_by_field_identifiers': json.dumps(group_by_identifiers)})

    @api.multi
    def get_forced_group_by_identifiers(self):
        self.ensure_one()
        enabled_group_by_data = self.get_enabled_group_by_data(skip_stored_sorting=True)
        forced_group_by_identifiers = [
            x['id'] for x in enabled_group_by_data if x.get('forced') and x.get('id')
        ]
        return forced_group_by_identifiers

    @api.multi
    def get_enabled_group_by_data(self, skip_stored_sorting=False):
        self.ensure_one()
        context = self._context.copy()
        if 'lang' not in context:
            context['lang'] = self.determine_language_code()
        model_group_by_fields = self.env['dr.group.by.field'].with_context(context).search([
            ('report_model_id.model', '=', self._name)
        ])
        group_by_data = [
            {
                'id': group_by_field.identifier,
                'name': group_by_field.name,
                'selected': group_by_field.forced or group_by_field in self.group_by_field_ids,
                'forced': group_by_field.forced
            }
            for group_by_field in model_group_by_fields
        ]
        if not skip_stored_sorting:
            # Sort group by data by the stored identifier index
            sorted_identifiers = self.get_stored_group_by_identifiers()
            group_by_data.sort(key=lambda identifier: not identifier['selected'] or sorted_identifiers.index(identifier['id']))
        return group_by_data

    @api.multi
    def get_stored_group_by_identifiers(self):
        self.ensure_one()
        # Find stored group by fields
        stored_group_by_identifiers = self.get_forced_group_by_identifiers()
        try:
            stored_group_by_identifiers += json.loads(self.group_by_field_identifiers)
            if not isinstance(stored_group_by_identifiers, list):
                stored_group_by_identifiers = list()
        except TypeError:
            pass
        ordered_group_by_identifiers = list(stored_group_by_identifiers)
        stored_group_by_identifiers = list(set(stored_group_by_identifiers))
        stored_group_by_identifiers.sort(key=lambda identifier: ordered_group_by_identifiers.index(identifier))
        return stored_group_by_identifiers

    @api.multi
    def update_group_by_selection(self, group_by):
        """
        Updates report selected group by fields
        """
        self.ensure_one()
        if not isinstance(group_by, list):
            return
        group_by = self.process_selected_group_by_identifiers(group_by)
        self.store_group_by_identifiers(group_by)
