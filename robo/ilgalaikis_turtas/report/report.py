# -*- coding: utf-8 -*-
from odoo import api, models, tools
from datetime import datetime, timedelta


class suvestine(models.AbstractModel):

    _name = 'report.ilgalaikis_turtas.robo_report_ilgalaikio_turto_sarasas'

    @api.multi
    def render_html(self, doc_ids, data=None):

        def _format(value):
            return tools.formatLang(self.env, value, digits=2, monetary=True, currency_obj=self.env.user.company_id.currency_id)

        def _value_residual_start(asset):
            date_from = asset._context.get('date_from')
            if isinstance(date_from, basestring) and len(date_from) == 10:
                date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_from = (date_from_dt - timedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            return asset.with_context(date=date_from).value_at_date

        def _value_residual_end(asset):
            return asset.with_context(date=asset._context.get('date_to')).value_at_date

        def _perkainavimai(asset):
            date_from = asset._context.get('date_from')
            if isinstance(date_from, basestring) and len(date_from) == 10:
                date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_from = (date_from_dt - timedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            return asset.with_context(date_from=date_from).change_between_dates

        def _nurasymai(asset):
            return asset.write_off_between_dates  # we get date_to from context?

        def _residual(asset):
            total_amount = 0.0
            for line in asset.depreciation_line_ids.filtered(lambda r: r.move_check):
                depreciation_date = line.depreciation_date
                if date_to >= depreciation_date >= date_from:  # used to be an line.move_check  global variable
                    total_amount += line.amount
            value = total_amount
            return value

        current_user = self.env.user
        report_obj = self.env['report']
        if data:
            date_from = data['form']['date_from']
            date_to = data['form']['date_to']
        else:
            now = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_from = now
            date_to = now
        doc_ids = doc_ids or data['ids']
        report = report_obj._get_report_from_name('ilgalaikis_turtas.robo_report_ilgalaikio_turto_sarasas')
        docs = self.env[report.model].browse(doc_ids)
        if current_user.is_manager():
            docs = docs.sudo()
        sorted_docs = []
        category_ids = docs.mapped('category_id').sorted(key=lambda r: r.name)
        for category_id in category_ids:
            sorted_docs.append(docs.filtered(lambda r: r.category_id.id == category_id.id).sorted(key=lambda r: r.code))
        current_user_is_accountant = current_user and current_user.is_accountant() and \
                                     not current_user.has_group('base.group_system')
        accountant = current_user.display_name.upper() if current_user_is_accountant else \
            current_user.company_id.findir.display_name

        docargs = {
            'doc_ids': doc_ids,
            'doc_model': report.model,
            'docs': sorted_docs,
            'residual_start': _value_residual_start,
            'residual_end': _value_residual_end,
            'residual': _residual,
            'company_id': current_user.company_id,
            'format': _format,
            'perkainavimai_f': _perkainavimai,
            'nurasymai_f': _nurasymai,
            'date_from': date_from,
            'date_to': date_to,
            'accountant': accountant,
        }

        return report_obj.render('ilgalaikis_turtas.robo_report_ilgalaikio_turto_sarasas', docargs)
