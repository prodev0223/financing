# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import api, models, tools
from odoo.addons.queue_job.job import job, identity_exact


class DynamicReportXLSXExport(models.AbstractModel):
    _name = 'dynamic.report.xlsx.export'

    @api.model
    def get_xlsx_report_options(self):
        return {}

    @api.multi
    def action_background_xlsx(self):
        self.ensure_one()
        user_id = self.env.user.id
        report_name = self.display_name
        now = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

        report_job = self.env['robo.report.job'].create({
            'report_name': report_name,
            'execution_start_date': now,
            'state': 'in_progress',
            'user_id': user_id,
            'job_type': 'export'
        })

        context = self._context.copy()

        # Start export job
        self.with_delay(eta=5, channel='root', identity_key=identity_exact).perform_xlsx_export_job(
            report_job.id, additional_context=context
        )

        # Return the action which displays information on where to find the report
        action = self.env.ref('robo.action_open_robo_report_job').read()[0]
        action.update({
            'view_mode': 'form', 'res_id': report_job.id,
            'view_id': self.env.ref('robo.form_robo_report_job').id
        })  # Force form view of the created import job
        return action

    @job
    @api.multi
    def perform_xlsx_export_job(self, import_job_id, additional_context=None):
        self.ensure_one()

        context = self._context.copy()
        if additional_context:
            context.update(additional_context)

        # Re-browse import object
        report_job = self.env['robo.report.job'].browse(import_job_id)
        if not report_job.exists():
            return

        try:
            if not context.get('active_ids'):
                context['active_ids'] = [self.id]
            action = self.with_context(context)._action_xlsx()
            action['data'] = action['datas']
            data = report_job.with_context(context).render_report(action)
            base64_file = data.get('base64_file')
            exported_file_name = data.get('exported_file_name')
            exported_file_type = data.get('exported_file_type')
        except Exception as exc:
            report_job.write({
                'state': 'failed',
                'fail_message': str(exc.args[0]),
                'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            })
        else:
            report_job.write({
                'state': 'succeeded',
                'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                'exported_file': base64_file,
                'exported_file_name': exported_file_name,
                'exported_file_type': exported_file_type
            })

        report_job.post_message()

    @api.model
    def prepare_xlsx_data(self):
        return {}

    @api.multi
    def _action_xlsx(self):
        self.ensure_one()

        xlsx_data = self.prepare_xlsx_data()
        report_name = xlsx_data['report_name']
        columns = xlsx_data['columns']
        report_data = xlsx_data['report_data']
        filters = xlsx_data['filters']

        return {
            'type': 'ir.actions.report.xml',
            'title': report_name,
            'name': report_name,
            'report_name': 'account_dynamic_reports.dynamic_xlsx_report',
            # 'report_name': report_identifier,
            'datas':  {
                'columns': columns,
                'report_data': report_data,
                'report_name': report_name,
                'filters': filters,
                'report_options': self.get_xlsx_report_options()
            },
            'context': {}
        }
