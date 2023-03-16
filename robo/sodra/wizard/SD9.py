# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions, _
from datetime import datetime
from dateutil.relativedelta import relativedelta
import re
import logging
from ... e_document.model import e_document_tools

# from SAM import SKYRIAI_VALUES
# from SD12 import SKYRIAI

_logger = logging.getLogger(__name__)
reasons_selection = [
    ('01', 'TĖVYSTĖS ATOSTOGOS'),
    ('02', 'ATOSTOGOS VAIKUI PRIŽIŪRĖTI'),
    ('03', 'ATOSTOGOS VAIKUI PRIŽIŪRĖTI PAGAL LR DK 180 STR. 2 D.'),
]

reasons_values = {'01': 'TĖVYSTĖS ATOSTOGOS',
                  '02': 'ATOSTOGOS VAIKUI PRIŽIŪRĖTI',
                  '03': 'ATOSTOGOS VAIKUI PRIŽIŪRĖTI PAGAL LR DK 180 STR. 2 D.'}


class HrHolidays(models.Model):

    _inherit = 'hr.holidays'

    child_birthdate = fields.Date(string='Child Birth')
    child_person_code = fields.Char(string='Vaiko asmens kodas')


HrHolidays()


class Sd9WizardLine(models.TransientModel):

    _name = 'sd9.wizard.line'

    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=1)
    holiday_start = fields.Date(string='Holiday start', readonly=1)
    holiday_end = fields.Date(string='Holiday end', readonly=1)
    child_birthdate = fields.Date(string='Child Birth')
    child_person_code = fields.Char(string='Vaiko asmens kodas')
    leave_id = fields.Many2one('hr.holidays', string='Holiday', readonly=1)
    file = fields.Binary(string='Report', readonly=True, compute='file_compute')
    file_name = fields.Char(string='File name', readonly=1)
    wizard_id = fields.Many2one('e.sodra.sd9', required=True, string="Wizard", ondelete='cascade')
    url = fields.Char(string='URL', readonly=True)

    @api.multi
    @api.depends('child_birthdate', 'child_person_code')
    def file_compute(self):
        for rec in self:
            generated_xml = rec.wizard_id.sd9_generate(rec.leave_id, rec.child_birthdate, rec.child_person_code)
            xml_file = generated_xml.encode('utf8').encode('base64')
            rec.file = xml_file

    @api.multi
    def open(self):
        self.ensure_one()
        if self.url:
            return {
                'type': 'ir.actions.act_url',
                'url': self.url,
                'target': 'new',
            }

    @api.multi
    def sd9_upload_single_line(self):
        # TODO: Extend in the future so single line can be uploaded. Change needs to be done in front-end
        # TODO: So that the method can be called without triggering the line edit
        self.ensure_one()
        self.wizard_id.with_context(single_file_upload=self.ids).sd9_upload()


Sd9WizardLine()


class SD9(models.TransientModel):

    _name = 'e.sodra.sd9'

    def _date_from(self):
        date_from = (datetime.utcnow() - relativedelta(months=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        return date_from

    def _date_to(self):
        date_to = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        return date_to

    registration_date = fields.Date(string='Date of registration', default=fields.Date.today, required=True)
    date_from = fields.Date(string='Date from', default=_date_from, required=True)
    date_to = fields.Date(string='Date to', default=_date_to, required=True)
    employee_ids = fields.One2many('sd9.wizard.line', 'wizard_id')
    is_sent = fields.Boolean(string='9-SD successfully sent to SoDra')

    @api.onchange('date_from', 'date_to')
    def _onchange_dates(self):
        holiday_codes = ['TA', 'VP']
        leaves = self.env['hr.holidays'].search([('holiday_status_id.kodas', 'in', holiday_codes),
                                                 ('date_to', '>=', self.date_from),
                                                 ('date_from', '<=', self.date_to)])
        lines = []
        for leave in leaves:
            child_person_code = leave.child_person_code if e_document_tools.assert_correct_identification_id(
                leave.child_person_code) else str()
            vals = {'employee_id': leave.employee_id.id,
                    'holiday_start': leave.date_from,
                    'holiday_end': leave.date_to,
                    'file_name': 'SD_9.ffdata',
                    'leave_id': leave.id,
                    'child_birthdate': leave.child_birthdate,
                    'child_person_code': child_person_code
                    }
            lines.append((0, 0, vals))
        self.employee_ids = [(5,)] + lines

    @api.model
    def action_create_wizard(self):
        """
        Action to create self record before opening the wizard, so the on-changes behave correctly
        :return: wizard action
        """
        res = self.env[self._name].create({})
        res._onchange_dates()
        return {
            'name': _('SD9'),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': self.env.ref('sodra.sodra_sd9').id,
            'res_id': res.id,
            'res_model': self._name,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.multi
    def sd9_generate(self, leave, child_birthdate, child_person_code):
        reason_code = '01' if leave.holiday_status_id.kodas == 'TA' else '02'  # todo nepalaikome 03 (iš karto po įvaikinimo)
        # is_parent_holiday = 1 if leave.holiday_status_id.kodas == 'TA' else 0
        company_id = self.env.user.company_id
        company_data = company_id.get_sodra_data()
        # user_employee = self.env['hr.employee'].search([('user_id', '=', self.env.user.id)])
        # manager = company_id.vadovas
        # manager = company_id.findir
        # preparator_detail = ''
        # preparator_detail += user_employee.name
        # preparator_detail += ' ' + user_employee.work_phone if user_employee.work_phone else ''
        # preparator_detail += ' ' + user_employee.work_email if user_employee.work_email else ''
        date_from = datetime.strptime(leave.date_from, tools.DEFAULT_SERVER_DATETIME_FORMAT)
        date_to = datetime.strptime(leave.date_to, tools.DEFAULT_SERVER_DATETIME_FORMAT)
        imones_kodas = company_id.partner_id.kodas or ''
        if imones_kodas and len(imones_kodas) > 9:
            imones_kodas = ''
        elif imones_kodas and imones_kodas != ''.join(re.findall(r'\d+', imones_kodas)):
            imones_kodas = ''
        elpastas = company_id.findir.partner_id.email
        if len(elpastas) > 68:
            elpastas = elpastas[:68]
        company_name = self._context.get('force_company_name', company_id.name) or ''
        company_name = company_id.get_sanitized_sodra_name(company_name)
        draudejo_kodas = self._context.get('force_draudejo_kodas', company_data.get('draudejo_kodas')) or ''
        imones_kodas = self._context.get('force_imones_kodas', imones_kodas) or ''
        telefonas = self._context.get('force_telefonas', company_data.get('phone_number')) or ''
        if not company_name or not draudejo_kodas or not imones_kodas:
            raise exceptions.UserError(_('Nenurodyta kompanijos informacija'))

        XML = '''<?xml version="1.0" encoding="UTF-8"?>
                <FFData Version="1" CreatedByApp="Robolabs" CreatedByLogin="%(created_by)s" CreatedOn="%(created_on)s">
                    <Form FormDefId="{07699928-F4D7-4577-A6A7-7727F0944B38}">
                        <DocumentPages>
                            <Group Name="Forma">
                                <ListPages>
                                    <ListPage>9-SD</ListPage>
                                </ListPages>
                            </Group>
                        </DocumentPages>
                        <Pages Count="1">
                            <Page PageDefName="9-SD" PageNumber="1">
                                <Fields Count="23">
                                    <Field Name="FormCode">9-SD</Field>
                                    <Field Name="FormVersion">06</Field>
                                    <Field Name="InsurerName">%(company_name)s</Field>
                                    <Field Name="InsurerCode">%(draudejo_kodas)s</Field>
                                    <Field Name="JuridicalPersonCode">%(company_code)s</Field>
                                    <Field Name="InsurerPhone">%(company_phone)s</Field>
                                    <Field Name="InsurerAddress">%(company_email)s</Field>
                                    <Field Name="DocDate">%(reg_date)s</Field>
                                    <Field Name="DocNumber"></Field>
                                    ''' % \
              {
                  'created_by': self.env.user.name,
                  'created_on': datetime.now().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                  'company_name': company_name,
                  'company_code': imones_kodas,
                  'company_phone': telefonas,
                  'company_email': elpastas,
                  # 'department': SKYRIAI_VALUES[self.sodra_department] if self.sodra_department else '',
                  'reg_date': self.registration_date,
                  'draudejo_kodas': draudejo_kodas,
              }

        if leave.employee_id.sodra_id:
            insurer_series = leave.employee_id.sodra_id[:2]
            insurer_code = leave.employee_id.sodra_id[2:]
        else:
            insurer_series = ''
            insurer_code = ''

        employee_name = leave.employee_id.get_split_name()
        child_person_code_snt = child_person_code or ''
        XML += '''<Field Name="PersonCode">%(person_code)s</Field>
                                    <Field Name="InsuranceSeries">%(insurer_series)s</Field>
                                    <Field Name="InsuranceNumber">%(insurer_code)s</Field>
                                    <Field Name="PersonFirstName">%(employee_first_name)s</Field>
                                    <Field Name="PersonLastName">%(employee_last_name)s</Field>
                                    <Field Name="HolidayStartDate">%(holiday_start)s</Field>
                                    <Field Name="HolidayEndDate">%(holiday_end)s</Field>
                                    <Field Name="HolidayCancelDate"></Field>
                                    <Field Name="ChildBirthDate">%(child_birth)s</Field>
                                    <Field Name="ChildPersonCode">%(child_person_code_snt)s</Field>
                                    <Field Name="ManagerFullName">%(manager_name)s</Field>
                                    <Field Name="PreparatorDetails">%(preparator_detail)s</Field>
                                    <Field Name="ReasonText_1">%(reason_text)s</Field>
                                    <Field Name="ReasonCode_1">%(reason_code)s</Field>
                                </Fields>
                            </Page>
                        </Pages>
                        </Form>
                        </FFData>''' % \
               {
                   'person_code': leave.employee_id.identification_id,
                   'insurer_series': insurer_series,
                   'insurer_code': insurer_code,
                   'employee_first_name': employee_name['first_name'],
                   'employee_last_name': employee_name['last_name'],
                   'holiday_start': date_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                   'holiday_end': date_to.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                   # 'manager_job_title': manager.job_id.name,
                   # 'manager_job_title': company_data.get('job_title') or '',
                   'manager_name': company_data.get('findir_name'),
                   'preparator_detail': company_data.get('findir_data'),
                   # 'parent_holiday': is_parent_holiday,
                   # 'child_holiday':  0 if is_parent_holiday else 1,
                   'child_birth': child_birthdate or '',
                   'reason_code': reason_code,
                   'reason_text': reasons_values[reason_code],
                   'child_person_code_snt': child_person_code_snt
               }
        return XML

    @api.multi
    def sd9_upload(self):
        self.ensure_one()
        client = self.env.user.get_sodra_api()
        single_id = self._context.get('single_file_upload')
        iterable = self.employee_ids.filtered(lambda x: x.id in single_id) \
            if single_id else self.employee_ids
        if client:
            for line in iterable:
                upload = client.service.uploadEdasDraft(
                    '9-SD-' + datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT) + '.ffdata', line.file)
                if upload and type(upload) == tuple:
                    try:
                        data = dict(upload[1])
                    except Exception as exc:
                        _logger.info('SODRA SD9 ERROR: %s' % str(exc.args))
                        try:
                            error_msg = '{} {}'.format(str(upload[0]), str(upload[1]))
                        except Exception as exc:
                            _logger.info('SODRA SD12 ERROR: %s' % str(exc.args))
                            raise exceptions.UserError(_('Nenumatyta klaida, bandykite dar kartą.'))
                        raise exceptions.UserError(_('Klaida iš SODRA centrinio serverio: %s' % error_msg))
                    ext_id = data.get('docUID', False)
                    if ext_id:
                        state = 'sent' if upload[0] in [500, 403] else 'confirmed'
                        vals = {
                            'doc_name': '9-SD',
                            'signing_url': data.get('signingURL', False),
                            'ext_id': ext_id,
                            'upload_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                            'last_update_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                            'state': state
                        }
                        self.env['sodra.document.export'].create(vals)
                if upload and type(upload) == tuple and upload[0] == 500:
                    client = self.sudo().env.user.get_sodra_api()
                    upload = client.service.uploadEdasDraft(
                        '9-SD-' + datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT) + '.ffdata', line.file)
                if upload and type(upload) == tuple and upload[0] == 500:
                    try:
                        detail_obj = upload[1]['detail'] if 'detail' in upload[1] else upload[1]
                        err_msg = detail_obj['dataServiceFault']['errorMsg']
                    except AttributeError:
                        err_msg = 'Nenumatyta klaida'
                    err_msg += '\nBandant pateikti darbuotojo %s neatvykimą periodu %s - %s' % \
                               (line.employee_id.display_name, line.holiday_start, line.holiday_end)
                    raise exceptions.UserError('%s' % err_msg)
                elif upload and type(upload) == tuple and upload[0] == 200:
                    line.url = upload[1]['signingURL']
            self.is_sent = True
        return {
            'type': 'ir.actions.do_nothing',
        }


SD9()
