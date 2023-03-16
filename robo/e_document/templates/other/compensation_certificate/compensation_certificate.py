# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import _, api, exceptions, fields, models, tools

TEMPLATE_REF = 'e_document.compensation_certificate_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    compensation_table = fields.Html(compute='_compute_compensation_table', store=True)

    @api.multi
    @api.depends('template_id', 'e_document_line_ids', 'e_document_line_ids.employee_id2',
                 'e_document_line_ids.float_1', 'e_document_line_ids.selection_1', 'e_document_line_ids.int_2',
                 'e_document_line_ids.int_3', 'e_document_line_ids.char_1')
    def _compute_compensation_table(self):
        template = self.env.ref(TEMPLATE_REF, raise_if_not_found=False)
        if template:
            for rec in self.filtered(lambda doc: doc.sudo().template_id == template):
                td_style = th_style = '''border: 1px solid black; padding: 4px;'''
                th_style += ''' font-weight: bold;'''

                table_lines = '\n'.join([
                    '''
                    <tr>
                        <td style="{0}">{1}</td>\n
                        <td style="{0}">{2}</td>\n
                        <td style="{0}">{3}</td>\n
                        <td style="{0}">{4}</td>\n
                        <td style="{0}">{5}</td>\n
                    </tr>
                    '''.format(
                        td_style,
                        line.employee_id2.name,
                        line.float_1,
                        'Darbuotojas' if line.selection_1 == 'no' else 'Darbdavys',
                        '{}-{}'.format(line.int_2, line.int_3),
                        line.char_1 or '',
                    ) for line in rec.e_document_line_ids
                ])

                table_base = '''
                <table style='border: 1px solid black; border-collapse: collapse'>
                    <tr>
                        <th style="{0}">Darbuotojas</th>
                        <th style="{0}">Suma</th>
                        <th style="{0}">Mokesčius moka</th>
                        <th style="{0}">Išmokėjimo periodas</th>
                        <th style="{0}">Komentaras</th>
                    </tr>
                    {1}
                </table>
                '''.format(
                    th_style,
                    table_lines
                )

                rec.compensation_table = table_base.format(table_lines)

    @api.multi
    def compensation_certificate_workflow(self):
        self.ensure_one()

        natura_records = self.env['hr.employee.natura']
        for employee_line in self.e_document_line_ids:
            payout_month = employee_line.int_3
            payout_year = employee_line.int_2
            payout_date_dt = datetime(payout_year, payout_month, 1)
            date_from = payout_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = payout_date_dt + relativedelta(day=31)
            date_to = date_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

            natura_record = self.env['hr.employee.natura'].create({
                'employee_id': employee_line.employee_id2.id,
                'date_from': date_from,
                'date_to': date_to,
                'amount': employee_line.float_1,
                'comment': employee_line.char_1,
                'taxes_paid_by': 'employee' if employee_line.selection_1 == 'no' else 'employer',
                'e_document_id': self.id,
            })
            natura_record.confirm()
            natura_records |= natura_record
        self.write({
            'record_model': 'hr.employee.natura',
            'record_ids': self.format_record_ids(natura_records.ids),
        })

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        template = self.env.ref(TEMPLATE_REF, raise_if_not_found=False)
        if self.cancel_id and self.cancel_id.template_id.id == template.id:
            natura_records = self.env['hr.employee.natura'].browse(self.cancel_id.parse_record_ids())
            for natura_record in natura_records:
                natura_record.action_cancel()
                natura_record.unlink()
        return super(EDocument, self).execute_cancel_workflow()

    @api.multi
    def execute_confirm_workflow_check_values(self):
        super(EDocument, self).execute_confirm_workflow_check_values()
        template = self.env.ref(TEMPLATE_REF, raise_if_not_found=False)
        for rec in self.filtered(lambda d: d.template_id == template):
            if not rec.e_document_line_ids:
                raise exceptions.UserError(_('Nurodykite darbuotojus, kuriems skiriama kompensacija'))
            if any(line.int_3 < 1 or line.int_3 > 12 for line in rec.e_document_line_ids):
                raise exceptions.UserError(_('Mėnuo, su kuriuo išmokama kompensacija privalo būti tarp 1-12 '
                                             '(Sausis-Gruodis)'))
            now = datetime.utcnow()
            current_year = now.year
            min_year = current_year - 2
            max_year = current_year + 5
            if any(line.int_2 < min_year or line.int_2 > max_year for line in rec.e_document_line_ids):
                raise exceptions.UserError(_('Metai, su kuriais išmokama privalo būti ne anksčiau nei {} ir ne vėliau '
                                             'nei {}').format(min_year, max_year))

            dates = [
                datetime(line.int_2, line.int_3, 1) for line in rec.e_document_line_ids
            ]
            if dates:
                min_date_dt = min(dates)
                max_date_dt = max(dates)
                min_date_from = min_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                max_date_from = max_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                payslips = self.env['hr.payslip'].search([
                    ('date_from', '>=', min_date_from),
                    ('date_from', '<=', max_date_from),
                    ('state', '=', 'done'),
                    ('employee_id', 'in', rec.e_document_line_ids.mapped('employee_id2').ids)
                ])
                for line in rec.e_document_line_ids:
                    line_date_from = datetime(line.int_2, line.int_3, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    payslip = payslips.filtered(
                        lambda slip: slip.date_from == line_date_from and slip.employee_id.id == line.employee_id2.id
                    )
                    if payslip:
                        raise exceptions.UserError(
                            _('Negalima patvirtinti kompensacijos, nes periode {}-{} egzistuoja patvirtintas darbuotojo '
                              '{} algalapis').format(line.int_2, line.int_3, line.employee_id2.name))

    @api.multi
    def _set_document_number(self):
        self.ensure_one()
        template = self.env.ref(TEMPLATE_REF, raise_if_not_found=False)
        if template and self.sudo().template_id == template:
            self.sudo().write({'document_number': self.env['ir.sequence'].next_by_code('employee_compensation')})
        else:
            return super(EDocument, self)._set_document_number()

    @api.multi
    def execute_confirm_workflow_update_values(self):
        template = self.env.ref(TEMPLATE_REF, raise_if_not_found=False)
        if template:
            for rec in self.filtered(lambda doc: doc.sudo().template_id == template):
                min_date = max_date = False
                for line in rec.e_document_line_ids:
                    date_dt = datetime(line.int_2, line.int_3, 1)
                    if not min_date or date_dt < min_date:
                        min_date = date_dt
                    if not max_date or date_dt > max_date:
                        max_date = date_dt
                max_date += relativedelta(day=31)
                rec.date_from = min_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                rec.date_to = max_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        return super(EDocument, self).execute_confirm_workflow_update_values()

    @api.multi
    def check_user_can_sign(self, raise_if_false=True):
        template = self.env.ref(TEMPLATE_REF, raise_if_not_found=False)
        if template and self.sudo().template_id == template:
            user = self.env.user
            company = user.sudo().company_id
            company_manager = company.vadovas.user_id
            is_manager = user == company_manager
            user_employees = user.employee_ids
            if not is_manager:
                is_signable_by_delegate = self.is_signable_by_delegate()
                if not is_signable_by_delegate:
                    if raise_if_false:
                        raise exceptions.UserError(_('Tik įmonės vadovas gali pasirašyti šio tipo '
                                                     'dokumentus.'))
                    return False
                is_delegate = False
                if self.reikia_pasirasyti_iki and user_employees:
                    is_delegate = user_employees[0].is_delegate_at_date(self.reikia_pasirasyti_iki)
                if not is_delegate:
                    if raise_if_false:
                        raise exceptions.UserError(_('Tik įmonės vadovas ir įgalioti asmenys gali pasirašyti šio tipo '
                                                     'dokumentus.'))
                    return False
            return True
        return super(EDocument, self).check_user_can_sign(raise_if_false)


EDocument()
