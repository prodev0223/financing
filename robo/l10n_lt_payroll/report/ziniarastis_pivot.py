# -*- coding: utf-8 -*-
from odoo import models, fields, tools, api, _


class ZniarastisLineReport(models.Model):

    _name = 'ziniarastis.line.report'
    _auto = False

    employee_id = fields.Many2one('hr.employee', string='Darbuotojas',)
    contract_id = fields.Many2one('hr.contract', string='Kontraktas')
    date = fields.Date(string='Data')
    worked_time = fields.Float(string='Darbo valandos')
    code = fields.Char(string='Kodas')

    @api.model_cr
    def init(self):
        tools.drop_view_if_exists(self._cr, 'ziniarastis_line_report')
        self._cr.execute('''
                CREATE OR REPLACE VIEW ziniarastis_line_report AS (
                SELECT
                    ziniarastis_day_line.id as id,
                    ziniarastis_day.contract_id as contract_id,
                    ziniarastis_day.employee_id as employee_id,
                    ziniarastis_day.date as date,
                    tabelio_zymejimas.code as code,
                    ziniarastis_day_line.worked_time_hours + ziniarastis_day_line.worked_time_minutes/60.0 as worked_time
                FROM ziniarastis_day_line
                    JOIN ziniarastis_day ON ziniarastis_day_line.ziniarastis_id = ziniarastis_day.id
                    JOIN tabelio_zymejimas ON ziniarastis_day_line.tabelio_zymejimas_id = tabelio_zymejimas.id
                )
                ''')


ZniarastisLineReport()
