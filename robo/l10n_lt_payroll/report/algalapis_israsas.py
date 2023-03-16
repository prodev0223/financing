# -*- coding: utf-8 -*-
from odoo import models, api
from odoo.tools.misc import formatLang
from .suvestine import DEFAULT_PAYSLIP_RELATED_DOCARGS


class AtsiskaitymoLapelis(models.AbstractModel):

    _name = 'report.l10n_lt_payroll.report_algalapis_israsas_sl'


    @api.multi
    def render_html(self, doc_ids, data=None):
        payslip_docs = self.env['hr.payslip'].browse(doc_ids)
        if not doc_ids and data:
            doc_ids = data.get('doc_ids', [])
        payslip_sudo = self.env['hr.payslip'].sudo().browse(doc_ids)
        if self.env.user.is_hr_manager() or self.env.user.is_manager()\
                or all(p.employee_id.user_id.id == self._uid for p in payslip_sudo):
            payslip_docs = self.env['hr.payslip'].sudo().browse(doc_ids)

        docargs = {
            'doc_ids': doc_ids,
            'doc_model': 'hr.payslip',
            'docs': payslip_docs,
            'formatLang': lambda *a, **kw: formatLang(self.env, *a, **kw),
        }
        docargs.update(DEFAULT_PAYSLIP_RELATED_DOCARGS)
        return self.env['report'].render('l10n_lt_payroll.report_algalapis_israsas_sl', docargs)


class AtsiskaitymoLapelisV2(models.AbstractModel):

    _name = 'report.l10n_lt_payroll.report_algalapis_israsas_v2_sl'

    @api.multi
    def render_html(self, doc_ids, data=None):
        payslip_docs = self.env['hr.payslip'].browse(doc_ids)
        if not doc_ids and data:
            doc_ids = data.get('doc_ids', [])
        payslip_sudo = self.env['hr.payslip'].sudo().browse(doc_ids)
        if all(p.payslip_data_is_accessible() for p in payslip_sudo):
            payslip_docs = self.env['hr.payslip'].sudo().browse(doc_ids)

        force_lang = data.get('context', {}).get('force_lang', False) if data else self._context.get('lang') or 'lt_LT'
        docargs = {
            'doc_ids': doc_ids,
            'doc_model': 'hr.payslip',
            'docs': payslip_docs,
            'formatLang': lambda *a, **kw: formatLang(self.env, *a, **kw),
            'force_lang': force_lang
        }
        docargs.update(DEFAULT_PAYSLIP_RELATED_DOCARGS)
        return self.env['report'].render('l10n_lt_payroll.report_algalapis_israsas_v2_sl', docargs)
