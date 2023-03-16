# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions, _
from datetime import datetime
from dateutil.relativedelta import relativedelta
from math import ceil
import re
import logging

_logger = logging.getLogger(__name__)


class NotInsurablePeriod(models.Model):

    _name = 'noninsurable.period'

    name = fields.Char(string='Number', readonly=1)
    description = fields.Char(string='Description', readonly=1)
    codes = fields.Many2many('hr.holidays.status', string='Codes')


class SAM(models.TransientModel):

    _name = 'e.sodra.sd12'

    def _date_from(self):
        date_from = (datetime.utcnow() - relativedelta(months=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        return date_from

    def _date_to(self):
        date_to = (datetime.utcnow() + relativedelta(days=7)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        return date_to

    registration_date = fields.Date(string='Date of registration', default=fields.Date.today, required=True)
    date_from = fields.Date(string='Date from', default=_date_from)
    date_to = fields.Date(string='Date to', default=_date_to)
    leave_ids = fields.One2many('sd12.wizard.line', 'wizard_id')
    remove_sent_leaves = fields.Boolean(string='Remove leaves that were sent to SoDra', store=False)

    @api.multi
    def sd12_generate(self):
        self.check_form_values()

        company_id = self.env.user.company_id

        company_data = company_id.get_sodra_data()

        line_leave_ids = self.leave_ids.mapped('leave_id').ids
        leaves = self.env['hr.holidays'].search([('id', 'in', line_leave_ids)])

        XML = '''<?xml version="1.0" encoding="UTF-8"?>
                        <FFData Version="1" CreatedByApp="Robolabs" CreatedByLogin="ROBO" CreatedOn="%(created_on)s">
                        <Form FormDefId="{A06213A3-FD5C-40AF-817D-C648AC8FF772}" FormLocation="">
                        '''

        page_lines = [{}]
        page_lines[0]['lines'] = ''
        for idx, leave in enumerate(leaves):
            date_from = datetime.strptime(leave.date_from, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            date_to = datetime.strptime(leave.date_to, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            leave_reason = self.env['noninsurable.period'].search(
                [('codes.kodas', '=', leave.holiday_status_id.kodas)])
            if leave.employee_id.sodra_id:
                insurer_series = leave.employee_id.sodra_id[:2]
                insurer_code = leave.employee_id.sodra_id[2:]
            else:
                insurer_series = ''
                insurer_code = ''
            employee_name = leave.employee_id.get_split_name()
            if idx <= 1:
                page_lines[0]['lines'] += '''<Field Name="RowNumber_%(row_num)d">%(row_num)d</Field>
                                    <Field Name="PersonCode_%(row_num)d">%(person_code)s</Field>
                                    <Field Name="InsuranceSeries_%(row_num)d">%(insurer_series)s</Field>
                                    <Field Name="InsuranceNumber_%(row_num)d">%(insurer_code)s</Field>
                                    <Field Name="InsuranceSuspendStart_%(row_num)d">%(leave_start)s</Field>
                                    <Field Name="InsuranceSuspendEnd_%(row_num)d">%(leave_end)s</Field>
                                    <Field Name="PersonFirstName_%(row_num)d">%(employee_name)s</Field>
                                    <Field Name="PersonLastName_%(row_num)d">%(employee_lastname)s</Field>
                                    <Field Name="ReasonCode_%(row_num)d">%(leave_code)s</Field>
                                    <Field Name="ReasonText_%(row_num)d">%(leave_reason)s</Field>
                                    ''' % {
                    'row_num': idx + 1,
                    'person_code': leave.employee_id.identification_id or '',
                    'leave_start': date_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                    'leave_end': date_to.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                    'employee_name': employee_name['first_name'],
                    'employee_lastname': employee_name['last_name'],
                    'leave_reason': leave_reason.description,
                    'leave_code': leave_reason.name,
                    'insurer_series': insurer_series,
                    'insurer_code': insurer_code
                }
            else:
                page_number = ((idx - 2) // 4) + 1
                row_number = ((idx - 2) - 4 * (page_number - 1)) + 1
                if len(page_lines) - 1 < page_number:
                    page_lines.append({})
                    page_lines[page_number]['lines'] = ''
                page_lines[page_number]['lines'] += '''<Field Name="RowNumber_%(row_num)d">%(row_num)d</Field>
                                    <Field Name="PersonCode_%(row_num)d">%(person_code)s</Field>
                                    <Field Name="InsuranceSeries_%(row_num)d">%(insurer_series)s</Field>
                                    <Field Name="InsuranceNumber_%(row_num)d">%(insurer_code)s</Field>
                                    <Field Name="InsuranceSuspendStart_%(row_num)d">%(leave_start)s</Field>
                                    <Field Name="InsuranceSuspendEnd_%(row_num)d">%(leave_end)s</Field>
                                    <Field Name="PersonFirstName_%(row_num)d">%(employee_name)s</Field>
                                    <Field Name="PersonLastName_%(row_num)d">%(employee_lastname)s</Field>
                                    <Field Name="ReasonCode_%(row_num)d">%(leave_code)s</Field>
                                    <Field Name="ReasonText_%(row_num)d">%(leave_reason)s</Field>
                                    ''' % {
                    'row_num': row_number,
                    'person_code': leave.employee_id.identification_id,
                    'leave_start': date_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                    'leave_end': date_to.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                    'employee_name': employee_name['first_name'],
                    'employee_lastname': employee_name['last_name'],
                    'leave_reason': leave_reason.description,
                    'leave_code': leave_reason.name,
                    'insurer_series': insurer_series,
                    'insurer_code': insurer_code
                }
        if len(leaves) > 2:
            n_leaves = len(leaves)
            if (n_leaves - 2) % 4 != 0:
                for idx in range(n_leaves, int(ceil((n_leaves-2)/4.0))*4 + 2):
                    page_number = ((idx - 2) // 4) + 1
                    row_number = ((idx - 2) - 4 * (page_number - 1)) + 1
                    if len(page_lines) - 1 < page_number:
                        page_lines.append({})
                        page_lines[page_number]['lines'] = ''
                    page_lines[page_number]['lines'] += '''<Field Name="RowNumber_%(row_num)d">%(row_num)d</Field>
                                            <Field Name="PersonCode_%(row_num)d"></Field>
                                            <Field Name="InsuranceSeries_%(row_num)d"></Field>
                                            <Field Name="InsuranceNumber_%(row_num)d"></Field>
                                            <Field Name="InsuranceSuspendStart_%(row_num)d"></Field>
                                            <Field Name="InsuranceSuspendEnd_%(row_num)d"></Field>
                                            <Field Name="PersonFirstName_%(row_num)d"></Field>
                                            <Field Name="PersonLastName_%(row_num)d"></Field>
                                            <Field Name="ReasonCode_%(row_num)d"></Field>
                                            <Field Name="ReasonText_%(row_num)d"></Field>
                                            ''' % {
                        'row_num': row_number,
                    }

        XML += '''<DocumentPages>
                    <Group Name="Forma">
                        <ListPages>
                            <ListPage>12-SD</ListPage>
                        </ListPages>'''

        for idx, page in enumerate(page_lines):
            if idx == 0:
                continue
            XML += '''
                    <Group Name="Tęsinys">
                        <ListPages>
                            <ListPage>12-SD-T</ListPage>
                        </ListPages>
                    </Group>
                        '''
        XML += '''</Group>'''

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
        draudejo_kodas = self._context.get('force_draudejo_kodas', company_id.draudejo_kodas) or ''
        imones_kodas = self._context.get('force_imones_kodas', imones_kodas) or ''
        telefonas = self._context.get('force_telefonas', company_data.get('phone_number', '')) or ''
        if not company_name or not draudejo_kodas or not imones_kodas:
            raise exceptions.UserError(_('Nenurodyta kompanijos informacija'))

        XML += '''
                </DocumentPages>
                <Pages Count="%(page_total)s">
                    <Page PageDefName="12-SD" PageNumber="1">
                        <Fields Count="34">
                            <Field Name="FormCode">12-SD</Field>
                            <Field Name="FormVersion">05</Field>
                            <Field Name="PageNumber">1</Field>
                            <Field Name="PageTotal">%(page_total)d</Field>
                            <Field Name="InsurerName">%(insurer_name)s</Field>
                            <Field Name="InsurerCode">%(insurer_code)s</Field>
                            <Field Name="JuridicalPersonCode">%(insurer_comp_code)s</Field>
                            <Field Name="InsurerPhone">%(insurer_phone)s</Field>
                            <Field Name="InsurerAddress">%(insurer_email)s</Field>
                            <Field Name="DocDate">%(reg_date)s</Field>
                            <Field Name="DocNumber"></Field>
                            <Field Name="PersonCountTotal">%(person_count)s</Field>
                            ''' % {
                                    'insurer_name': company_name,
                                    'insurer_code': draudejo_kodas,
                                    'insurer_comp_code': imones_kodas,
                                    'insurer_email': elpastas,
                                    'page_total': len(page_lines),
                                    'reg_date': self.registration_date,
                                    'person_count': len(leaves),
                                    'insurer_phone': telefonas,
                                }
        if len(leaves) < 2:
            for row_num in range(len(leaves)+1, 3):
                page_lines[0]['lines'] += '''<Field Name="RowNumber_%(row_num)d"></Field>
                    <Field Name="PersonCode_%(row_num)d"></Field>
                    <Field Name="InsuranceSeries_%(row_num)d"></Field>
                    <Field Name="InsuranceNumber_%(row_num)d"></Field>
                    <Field Name="InsuranceSuspendStart_%(row_num)d"></Field>
                    <Field Name="InsuranceSuspendEnd_%(row_num)d"></Field>
                    <Field Name="PersonFirstName_%(row_num)d"></Field>
                    <Field Name="PersonLastName_%(row_num)d"></Field>
                    <Field Name="ReasonCode_%(row_num)d"></Field>
                    <Field Name="ReasonText_%(row_num)d"></Field>
                    ''' % {'row_num': row_num}
        XML += page_lines[0]['lines']

        XML += '''<Field Name="ManagerFullName">%(manager_name)s</Field>
                            <Field Name="PreparatorDetails">%(vyr_buhalt)s</Field>
                        </Fields>
                    </Page>'''
        XML_Add_Pages = ''
        for idx, page in enumerate(page_lines):
            if idx == 0:
                continue
            page_number = idx + 1
            XML_Add_Pages += '''
                    <Page PageDefName="12-SD-T" PageNumber="%(page_number)d">
                        <Fields Count="47">
                            <Field Name="FormCode">12-SD</Field>
                            <Field Name="FormVersion">05</Field>
                            <Field Name="PageNumber">1</Field>
                            <Field Name="PageTotal">%(page_total)d</Field>
                            <Field Name="InsurerCode">%(insurer_code)s</Field>
                            <Field Name="DocDate">%(reg_date)s</Field>
                            <Field Name="DocNumber"></Field>
                        ''' % {
                'page_number': page_number,
                'page_total': len(page_lines),
                'insurer_code': company_id.draudejo_kodas,
                'reg_date': self.registration_date,
            }
            XML_Add_Pages += page['lines']
            XML_Add_Pages += '''</Fields>
                            </Page>'''
        XML += XML_Add_Pages + '''
                </Pages>'''
        XML += '''
           </Form>
       </FFData>'''

        XML = XML % {
            'created_on': datetime.now().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            'page_count': 1,
            'person_count': len(leaves),
            'insurer_name': company_id.name,
            'insurer_code': company_id.partner_id.kodas,
            'insurer_comp_code': company_id.partner_id.kodas,
            'insurer_address': company_id.street,
            'reg_date': self.registration_date,
            'manager_name': company_data.get('findir_name') or '',
            'vyr_buhalt': company_data.get('findir_data') or '',
            'page_total': len(page_lines),
        }
        xml_file = XML.encode('utf8').encode('base64')
        url = False
        client = None
        do_not_send_to_sodra = self._context.get('do_not_send_to_sodra')
        if not do_not_send_to_sodra:
            client = self.env.user.get_sodra_api()
        if client:
            upload = client.service.uploadEdasDraft(
                '12-SD-' + datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT) + '.ffdata', xml_file)
            if upload and type(upload) == tuple:
                try:
                    data = dict(upload[1])
                except Exception as exc:
                    _logger.info('SODRA SD12 ERROR: %s' % str(exc.args))
                    try:
                        error_msg = '{} {}'.format(str(upload[0]), str(upload[1]))
                    except Exception as exc:
                        _logger.info('SODRA SD12 ERROR: %s' % str(exc.args))
                        raise exceptions.UserError(_('Nenumatyta klaida, bandykite dar kartą.'))
                    raise exceptions.UserError(_('Klaida iš SODRA centrinio serverio: %s' % error_msg))
                ext_id = data.get('docUID', False)
                if ext_id:
                    state = 'sent' if upload[0] in [500] else 'confirmed'
                    vals = {
                        'doc_name': '12-SD',
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
                    '12-SD-' + datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT) + '.ffdata', xml_file)
            if upload and type(upload) == tuple and upload[0] == 500:
                _logger.info(_('SODRA API exception: %s') % str(upload))
                try:
                    error_msg = upload[1]['detail']['dataServiceFault']['errorMsg']
                except:
                    error_msg = 'Nepavyko įkelti'
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'sd12.download',
                    'view_mode': 'form',
                    'view_type': 'form',
                    'views': [(False, 'form')],
                    'target': 'new',
                    'view_id': self.env.ref('sodra.sodra_sd12_download').id,
                    'context': {'file': xml_file, 'err': error_msg},
                }
            elif upload and type(upload) == tuple and upload[0] == 200:
                url = upload[1]['signingURL']
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sd12.download',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'view_id': self.env.ref('sodra.sodra_sd12_download').id,
            'context': {
                'file': xml_file,
                'url': url,
                'leave_ids': leaves.ids,
                'was_not_sent_to_sodra': do_not_send_to_sodra,
            },
        }

    @api.multi
    def check_form_values(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise exceptions.ValidationError(_('Date to can not precede date from on the form'))
        if not self.leave_ids:
            raise exceptions.ValidationError(_('At least one line is needed to generate SD12'))

        holiday_codes = ['NA', 'PB', 'ND']  # todo
        period_leave_ids = self.env['hr.holidays'].search([
            ('holiday_status_id.kodas', 'in', holiday_codes),
            ('date_from', '>=', self.date_from),
            ('date_to', '<=', self.date_to),
            ('state', '=', 'validate')
        ]).mapped('id')

        for line in self.leave_ids:
            line_leave_start = line.leave_start
            line_leave_end = line.leave_end
            line_employee_name = line.employee_id.name_related
            line_string = _('Line: {} {} {}').format(line_employee_name, line_leave_start, line_leave_end)

            if line_leave_start < self.date_from or line_leave_end > self.date_to:
                raise exceptions.ValidationError(_('Holiday line dates can not precede/exceed dates on the form.\n'
                                                   '{}').format(line_string))
            if line_leave_start > line_leave_end:
                raise exceptions.ValidationError(_('End date precedes the start date.\n{}').format(line_string))
            if line.leave_id.id not in period_leave_ids:
                raise exceptions.ValidationError(_('Holiday record does not exist.\n{}.').format(line_string))

    @api.onchange('date_from', 'date_to', 'remove_sent_leaves')
    def _onchange_values(self):
        holiday_codes = ['NA', 'PB', 'ND']
        date_from = self.date_from or self._date_from()
        date_to = self.date_to or self._date_to()

        domain = [
            ('holiday_status_id.kodas', 'in', holiday_codes),
            ('date_from', '>=', date_from),
            ('date_to', '<=', date_to),
            ('state', '=', 'validate')
        ]
        if self.remove_sent_leaves:
            domain.append(('is_sent_to_sodra', '!=', True))
        leaves = self.env['hr.holidays'].search(domain)

        lines = []
        for leave in leaves:
            vals = {
                'employee_id': leave.employee_id.id,
                'leave_id': leave.id,
                'leave_start': leave.date_from_date_format,
                'leave_end': leave.date_to_date_format,
            }
            lines.append((0, 0, vals))
        self.leave_ids = [(5, )] + lines

    @api.model
    def action_create_wizard(self):
        """
        Action to create self record before opening the wizard, so the on-changes behave correctly
        :return: wizard action
        """
        res = self.env[self._name].create({})
        res._onchange_values()
        return {
            'name': _('SD12'),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': self.env.ref('sodra.sodra_sd12').id,
            'res_id': res.id,
            'res_model': self._name,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }


class FailoGeneravimas(models.TransientModel):

    _name = 'sd12.download'

    @api.multi
    def auto_load_file(self):
        if 'file' in self._context.keys():
            return self._context['file']
        else:
            return ''

    def file_name(self):
            return '12-SD.ffdata'

    def default_url(self):
        return self._context.get('url', False)

    file = fields.Binary(string='Report document', readonly=True, default=auto_load_file)
    file_name = fields.Char(string='File Name', default=file_name)
    url = fields.Char(string='URL', default=default_url)

    @api.onchange('file')
    def _compute_failed(self):
        err = self._context.get('err', False)
        if err:
            raise exceptions.UserError(_('Nepavyko pateikti į SODRA, todėl negalėsite pasirašyti\nKlaidos pranešimas: %s') % err)

    @api.multi
    def open(self):
        self.ensure_one()
        leave_ids = self._context.get('leave_ids')
        was_not_sent_to_sodra = self._context.get('was_not_sent_to_sodra')
        if leave_ids and not was_not_sent_to_sodra:
            self.env['hr.holidays'].browse(leave_ids).write({'is_sent_to_sodra': True})
        if self.url:
            return {
                'type': 'ir.actions.act_url',
                'url': self.url,
                'target': 'new',
            }


FailoGeneravimas()


class Sd12WizardLine(models.TransientModel):

    _name = 'sd12.wizard.line'

    employee_id = fields.Many2one('hr.employee', string='Employee')
    leave_id = fields.Many2one('hr.holidays', string='Leave')
    is_leave_sent_to_sodra = fields.Boolean(related='leave_id.is_sent_to_sodra')
    wizard_id = fields.Many2one('e.sodra.sd12', string="Wizard", ondelete='cascade')
    leave_start = fields.Date(string='Leave start')
    leave_end = fields.Date(string='Leave end')
