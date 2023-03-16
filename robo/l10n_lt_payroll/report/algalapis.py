# -*- coding: utf-8 -*-
from odoo import models, api
from odoo.report import report_sxw
from .suvestine import DEFAULT_PAYSLIP_RELATED_DOCARGS


class algalapis(report_sxw.rml_parse):

    def __init__(self, cr, uid, name, context=None):
        super(algalapis, self).__init__(cr, uid, name, context=context)
        self.localcontext.update(DEFAULT_PAYSLIP_RELATED_DOCARGS)

class report_payslip(models.AbstractModel):
    _name = 'report.l10n_lt_payroll.report_algalapis_sl'
    # _inherit = 'report.hr_payroll.report_payslipdetails'
    _inherit = 'report.abstract_report'
    _template = 'l10n_lt_payroll.report_algalapis_sl'
    _wrapped_report_class = algalapis

    @api.model
    def render_html(self, docids, data=None):
        context = dict(self.env.context or {})
        if not docids and data:
            docids = data.get('doc_ids', [])

        # If the key 'landscape' is present in data['form'], passing it into the context
        if data and data.get('form', {}).get('landscape'):
            context['landscape'] = True

        if context and context.get('active_ids'):
            # Browse the selected objects via their reference in context
            model = context.get('active_model') or context.get('model')
            objects_model = self.env[model]
            objects = objects_model.with_context(context).browse(context['active_ids'])
        else:
            # If no context is set (for instance, during test execution), build one
            model = self.env['report']._get_report_from_name(self._template).model
            objects_model = self.env[model]
            objects = objects_model.with_context(context).browse(docids)
            context['active_model'] = model
            context['active_ids'] = docids

        # Generate the old style report
        wrapped_report = self.with_context(context)._wrapped_report_class(self.env.cr, self.env.uid, '',
                                                                          context=self.env.context)
        wrapped_report.set_context(objects, data, context['active_ids'])

        # Rendering self._template with the wrapped report instance localcontext as
        # rendering environment
        docargs = dict(wrapped_report.localcontext)
        if not docargs.get('lang'):
            docargs.pop('lang', False)

        # ROBO:
        doc_ids = context['active_ids']
        payslip_docs = self.env[model].browse(doc_ids)

        payslip_sudo = self.env[model].sudo().browse(doc_ids)
        if self.env.user.is_manager() \
                or all(p.employee_id.user_id.id == self._uid for p in payslip_sudo):
            payslip_docs = self.env[model].sudo().browse(doc_ids)

        current_user = self.env.user
        accountant = current_user if current_user.is_accountant() and not current_user.has_group('base.group_system') \
            else False

        docargs_additional = {
            'accountant': accountant,
            'current_user_timestamp': self.env.user.get_current_timestamp(),
            'docs': payslip_docs,
            'doc_ids': doc_ids,  # Used in template translation (see translate_doc method from report model)
            'doc_model': model,
        }
        docargs.update(docargs_additional)

        return self.env['report'].with_context(context).render(self._template, docargs)
