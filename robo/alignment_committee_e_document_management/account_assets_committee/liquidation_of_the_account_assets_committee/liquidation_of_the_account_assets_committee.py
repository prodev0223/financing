# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import _, models, api, fields, exceptions, tools

TEMPLATE = 'e_document.liquidation_of_the_account_assets_committee_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    def _get_alignment_committee_id_domain(self):
        date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        domain = ['&', ('type', '=', 'asset'), '|', ('date_to', '=', False), ('date_to', '>=', date)]
        return domain

    alignment_committee_id = fields.Many2one('alignment.committee', string='Alignment Committee',
                                             domain=lambda self: self._get_alignment_committee_id_domain(),
                                             readonly=True, states={'draft': [('readonly', False)]})

    @api.onchange('alignment_committee_id')
    def _onchange_committee_liquidation_date(self):
        for rec in self.filtered(lambda t: t.template_id == self.env.ref(TEMPLATE, raise_if_not_found=False)):
            if not rec.alignment_committee_id:
                continue
            rec.date_to = rec.alignment_committee_id.date_to

    @api.multi
    @api.constrains('date_to')
    def _check_dates_liquidation_document(self):
        """
        Checks whether date_to is not lower than account asset committee date_from
        """
        for rec in self.filtered(lambda t: t.template_id == self.env.ref(TEMPLATE, raise_if_not_found=False)):
            date_from_dt = datetime.strptime(rec.alignment_committee_id.date, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            if date_to_dt <= date_from_dt:
                raise exceptions.ValidationError(
                    _('Date of expiry of Commission can\'t be earlier than Date of entry into force of the '
                      'Commission: {}').format(date_from_dt))

    @api.multi
    def liquidation_of_the_account_assets_committee_workflow(self):
        for rec in self.filtered(lambda t: t.template_id == self.env.ref(TEMPLATE, raise_if_not_found=False)):
            date_to_dt = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            rec.alignment_committee_id.write({
                'date_to': date_to_dt,
            })
