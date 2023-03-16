# -*- coding: utf-8 -*-
from odoo.addons.work_schedule.report.export_xls import WorkScheduleMonthlyExcel
from odoo import models, api


class WorkScheduleMonthlyExcelExtended(WorkScheduleMonthlyExcel):
    def create_top(self, user_name=False, user_job_name=False):
        WorkScheduleMonthlyExcel.create_top(self, user_name, user_job_name)
        extra_text = False
        if user_job_name or user_name:
            extra_text = 'Darbo grafiką sudarė '
            if user_job_name:
                extra_text += user_job_name.lower()
                if user_name:
                    extra_text += ' - '
            if user_name:
                extra_text += user_name
        if extra_text:
            self.merge_cells(self.max_employee_rows_per_page + 2, self.max_employee_rows_per_page + 3, 31, 37, borders=False, header_company_info=True)
            self.write_schedule_cell(self.max_employee_rows_per_page + 2, 31, unicode(extra_text), company_info=True, header_company_info=True, small=True)

        self.merge_cells(self.max_employee_rows_per_page + 6, self.max_employee_rows_per_page + 6, 0, self.num_days + 7,
                         borders=False, header_company_info=True)
        self.merge_cells(self.max_employee_rows_per_page + 7, self.max_employee_rows_per_page + 7, 0, self.num_days + 7,
                         borders=False, header_company_info=True)
        self.write_schedule_cell(self.max_employee_rows_per_page + 6, 0, unicode(
            '''Pirma pietų pertrauka darbuotojams suteikiama praėjus ne mažiau kaip 4 valandoms nuo darbo pradžios. Dirbant 12 ar 14 valandų pamainą pagal darbo grafiką, yra suteikiamos dvi poilsio pertraukos po 30 minučių'''),
                                 company_info=True, header_company_info=True, small=True)
        self.write_schedule_cell(self.max_employee_rows_per_page + 7, 0, unicode(
            '''Dirbant 24 valandų pamainą pagal darbo grafiką, yra suteikiamos 3 poilsio pertraukos po 30 minučių. Poilsio pertraukomis darbuotojas pasinaudoja savo nuožiūra bei atsižvelgdamas į darbo krūvį. Pietų pertraukų laikas yra įskaičiuotas į nurodytą darbo valandų laiką'''),
                                 company_info=True, header_company_info=True, small=True)


class HrScheduleDay(models.Model):
    _inherit = "work.schedule.day"

    @api.model
    def get_export_class(self):
        return WorkScheduleMonthlyExcelExtended()