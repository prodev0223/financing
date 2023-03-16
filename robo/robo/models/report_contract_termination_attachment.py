# -*- coding: utf-8 -*-


import re
from datetime import datetime

from odoo.addons.robo.models.linksnis import kas_to_ko

from odoo import api, exceptions, models, tools, _
from odoo.tools.misc import formatLang

class ReportContractTerminationAttachment(models.AbstractModel):
    _name = 'report.robo.report_contract_termination_attachment'

    @api.multi
    def render_html(self, doc_ids, data=None):
        if data.get('force_lang'):
            self = self.with_context(lang=data.get('force_lang'))
        report_obj = self.env['report']
        report = report_obj.with_context(force_lang=data.get('force_lang'))._get_report_from_name(
            'robo.report_contract_termination_attachment')
        employee = self.env['hr.employee'].browse(data['emp_id']).exists()
        if not employee:
            raise exceptions.ValidationError(_('Related record was not found.\nContact the system administrator.'))
        contract = employee.contract_ids.filtered(lambda s: s.id == data['contract_id'])
        appointment = employee.contract_ids.mapped('appointment_ids').filtered(lambda s: s.id == data['appointment_id'])

        vals = {}
        ceo_name_ad = kas_to_ko(employee.company_id.vadovas.name)
        ceo_job_ad = kas_to_ko(employee.company_id.vadovas.job_id.name)
        mapper = {1: _('sausio'), 2: _('vasario'), 3: _('kovo'), 4: _('balandžio'), 5: _('gegužės'), 6: _('birželio'),
                  7: _('liepos'), 8: _('rugpjūčio'), 9: _('rugsėjo'), 10: _('spalio'), 11: _('lapkričio'),
                  12: _('gruodžio'), }

        vals['contract_number'] = contract.name
        contract_start_date = datetime.strptime(contract.date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
        vals['contract_start_date'] = _('{0} m. {1} mėn. {2} d.').format(
            contract_start_date.year,
            mapper.get(contract_start_date.month),
            contract_start_date.day,
        )
        contract_termination_date = datetime.strptime(contract.date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
        vals['contract_termination_date'] = _('{0} m. {1} mėn. {2} d.').format(
            contract_termination_date.year,
            mapper.get(contract_termination_date.month),
            contract_termination_date.day,
        )
        dk_article = self.env['dk.nutraukimo.straipsniai'].search([
            ('straipsnis', '=', contract.teises_akto_straipsnis),
            ('dalis', '=', contract.teises_akto_straipsnio_dalis),
            ('punktas', '=', contract.teises_akto_straipsnio_dalies_punktas),
        ], limit=1)

        vals['dk_article'] = dk_article.text_in_document
        vals['dk_article_name'] = dk_article.straipsnio_pav
        vals['lang'] = data['force_lang']
        vals['representative'] = data['representative']

        if appointment.job_id:
            job_id = appointment.job_id
        elif contract.job_id:
            job_id = contract.job_id
        else:
            job_id = employee.job_id

        docargs = {
            'doc_ids': doc_ids,
            'doc_model': report.model,
            'docs': employee,
            'contract': contract,
            'appointment': appointment,
            'job_id': job_id,
            'vals': vals,
            'ceo_name_ad': ceo_name_ad,
            'ceo_job_ad': ceo_job_ad
        }
        return report_obj.render('robo.report_contract_termination_attachment', docargs)
