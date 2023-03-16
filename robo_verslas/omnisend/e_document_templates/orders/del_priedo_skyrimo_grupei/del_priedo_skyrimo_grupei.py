# -*- coding: utf-8 -*-
import logging
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, api, tools, fields, _, exceptions

_logger = logging.getLogger(__name__)


class EDocument(models.Model):

    _inherit = 'e.document'

    omnisend_bonus_line_ids = fields.One2many('omnisend.e.document.line', 'e_document_id')

    employees_table_text = fields.Text(compute='_compute_employees_table_text', store=True, readonly=True,
                                 states={'draft': [('readonly', False)]})

    @api.multi
    def omnisend_isakymas_del_priedo_skyrimo_grupei_workflow(self):
        self.ensure_one()

        lines = self.omnisend_bonus_line_ids
        date_from_dt = datetime.strptime(self.date_3, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_from = (date_from_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = (date_from_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        ids = self.env['hr.employee.bonus']

        for line in lines:
            bonus_rec = self.env['hr.employee.bonus'].create({
                'employee_id': line.employee_id.id,
                'for_date_from': self.date_1,
                'for_date_to': self.date_2,
                'payment_date_from': date_from,
                'payment_date_to': date_to,
                'bonus_type': self.bonus_type_selection,
                'amount': line.adjusted_bruto,
                'amount_type': self.bonus_input_type
            })
            bonus_rec.confirm()
            ids += bonus_rec

        self.write({
            'record_model': 'hr.employee.bonus',
            'record_id': bonus_rec.id,
        })
        ids.write({'related_document': self.id})

    @api.multi
    @api.constrains('date_1', 'date_2')
    def constrain_omnisend_dates(self):
        template = self.env.ref('omnisend.isakymas_del_priedo_skyrimo_grupei_template')
        for rec in self:
            if rec.template_id != template or rec.bonus_type_selection == 'ne_vdu':
                continue
            date_from_dt = datetime.strptime(rec.date_1, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = datetime.strptime(rec.date_2, tools.DEFAULT_SERVER_DATE_FORMAT)
            if date_from_dt.day != 1 or date_to_dt + relativedelta(day=31) != date_to_dt:
                raise exceptions.ValidationError(
                    _('Periodo pradžia ir pabaiga turi sutapti su mėnesio pradžios ir pabaigos datomis'))

    @api.multi
    @api.depends('document_type', 'employee_id1', 'employee_id2', 'template_id', 'e_document_line_ids.employee_id2',
                 'business_trip_employee_line_ids.employee_id', 'qualification_order_employee_lines',
                 'omnisend_bonus_line_ids.employee_id')
    def _compute_related_employee_ids(self):
        omnisend_group_bonus_template = self.env.ref('omnisend.isakymas_del_priedo_skyrimo_grupei_template',
                                                     raise_if_not_found=False)
        related_documents = self.filtered(lambda r: r.template_id == omnisend_group_bonus_template)
        unrelated_documents = self.filtered(lambda r: r.template_id != omnisend_group_bonus_template)
        for rec in related_documents:
            rec.related_employee_ids = rec.omnisend_bonus_line_ids.mapped('employee_id')
        return super(EDocument, unrelated_documents)._compute_related_employee_ids()

    @api.multi
    @api.constrains('bonus_input_type', 'bonus_type_selection', 'template_id')
    def _check_bonus_input_type_for_specific_bonus_types(self):
        template = self.env.ref('omnisend.isakymas_del_priedo_skyrimo_grupei_template')
        for rec in self:
            if rec.template_id != template:
                return super(EDocument, rec)._check_bonus_input_type_for_specific_bonus_types()
            if rec.bonus_input_type == 'neto' and rec.bonus_type_selection not in ['1men', 'ne_vdu']:
                raise exceptions.ValidationError(_(
                    'Negalima skirti priedo pagal NETO sumą už ilgesnį nei vieno mėnesio laikotarpį, dėl galimų netikslingų paskaičiavimų'))

    @api.onchange('bonus_input_type', 'bonus_type_selection', 'template_id')
    def _onchange_bonus_input_type_for_specific_bonus_types(self):
        if self.template_id != self.env.ref('omnisend.isakymas_del_priedo_skyrimo_grupei_template'):
            return super(EDocument, self)._onchange_bonus_input_type_for_specific_bonus_types()

        if self.bonus_type_selection not in ['1men', 'ne_vdu']:
            self.bonus_input_type = 'bruto'

    @api.onchange('date_1', 'bonus_type_selection', 'template_id')
    def onch_set_premijos_datos(self):
        res = super(EDocument, self).onch_set_premijos_datos()

        if self.template_id != self.env.ref('omnisend.isakymas_del_priedo_skyrimo_grupei_template'):
            return res

        if self.date_1 and self.bonus_type_selection:
            date_1_dt = datetime.strptime(self.date_1, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_1_rel_delta = relativedelta(day=1)

            if self.bonus_type_selection == '1men':
                date_2_rel_delta = relativedelta(day=31)
                date_3_rel_delta = relativedelta(day=1)
            elif self.bonus_type_selection == '3men':
                date_2_rel_delta = relativedelta(months=2, day=31)
                date_3_rel_delta = relativedelta(months=2, day=1)
            else:
                return

            self.date_1 = (date_1_dt + date_1_rel_delta).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            self.date_2 = (date_1_dt + date_2_rel_delta).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            self.date_3 = (date_1_dt + date_3_rel_delta).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        return res

    @api.one
    @api.depends('omnisend_bonus_line_ids', 'bonus_input_type')
    def _compute_employees_table_text(self):
        if self.template_id != self.env.ref('omnisend.isakymas_del_priedo_skyrimo_grupei_template', raise_if_not_found=False):
            return

        employees_table_text = '''<br>Priedas skiriamas šiems darbuotojams:
                                             <table width="80%" style="border:1px solid black; border-collapse: collapse; text-align: center;">
                                             <tr style="border:1px solid black;">
                                             <td style="border:1px solid black;"><b>Vardas pavardė</b></td>
                                             <td style="border:1px solid black;"><b>Priedo dydis ({0}), EUR</b></td>
                                             <td style="border:1px solid black;"><b>Darbo dienų skaičius</b></td>
                                             <td style="border:1px solid black;"><b>Išdirbtų darbo dienų skaičius</b></td>
                                             <td style="border:1px solid black;"><b>Perskaičiuotas priedo dydis ({0}), EUR</b></td>
                                             </td></tr>'''.format(self.bonus_input_type)

        for line in self.omnisend_bonus_line_ids:
            full_amount = '%.2f' % line.full_bruto
            full_amount = full_amount.replace('.', ',')

            adj_amount = '%.2f' % line.adjusted_bruto
            adj_amount = adj_amount.replace('.', ',')

            w_norm = '%.2f' % line.work_norm
            w_norm = w_norm.replace('.', ',')

            w_days = '%.2f' % line.worked_time
            w_days = w_days.replace('.', ',')

            employees_table_text += '''
                          <tr style="border:1px solid black;">
                          <td style="border:1px solid black;">%(name)s</td>
                          <td style="border:1px solid black;">%(full_amount)s</td>
                          <td style="border:1px solid black;">%(w_norm)s</td>
                          <td style="border:1px solid black;">%(w_days)s</td>
                          <td style="border:1px solid black;">%(adj_amount)s</td>''' % {
                'name': line.employee_id.name,
                'full_amount': full_amount,
                'w_norm': w_norm,
                'w_days': w_days,
                'adj_amount': adj_amount,
            }

        employees_table_text += """</table><br>"""
        self.employees_table_text = employees_table_text

    @api.multi
    def execute_confirm_workflow_update_values(self):
        def set_first_day_of_month(date):
            if date:
                date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
                if date_dt.day != 1:
                    date = (date_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            return date

        res = super(EDocument, self).execute_confirm_workflow_update_values()

        for rec in self:

            if rec.template_id != self.env.ref('omnisend.isakymas_del_priedo_skyrimo_grupei_template'):
                continue

            rec.date_3 = set_first_day_of_month(rec.date_3)

        return res

    @api.multi
    def execute_confirm_workflow_check_values(self):
        res = super(EDocument, self).execute_confirm_workflow_check_values()

        docs_to_check = self.filtered(lambda d: not d.sudo().skip_constraints_confirm and
                                      d.template_id == self.env.ref('omnisend.isakymas_del_priedo_skyrimo_grupei_template'))

        for rec in docs_to_check:

            rec.check_omnisend_bonus_line_ids()

            for line in rec.omnisend_bonus_line_ids:
                if tools.float_is_zero(line.full_bruto, precision_digits=2):  # todo: or currency precision ?
                    raise exceptions.Warning(_('Priedo dydis negali būti nulinis!'))
                if tools.float_is_zero(line.adjusted_bruto, precision_digits=2):  # todo: or currency precision ?
                    raise exceptions.Warning(_('Perskaičiuotas priedo dydis negali būti nulinis!'))

        return res

    @api.multi
    def check_workflow_constraints(self):
        self.ensure_one()

        res = super(EDocument, self).check_workflow_constraints()

        if self.template_id != self.env.ref('omnisend.isakymas_del_priedo_skyrimo_grupei_template', raise_if_not_found=False):
            return res

        employee_ids = self.omnisend_bonus_line_ids.mapped('employee_id.id')

        has_closed_slip = bool(self.env['hr.payslip'].search_count([
            ('employee_id', 'in', employee_ids),
            ('date_from', '=', self.date_3),
            ('state', '=', 'done')
        ]))

        if has_closed_slip:
            raise exceptions.ValidationError(_(
                'Negalite pasirašyti šio dokumento, nes periode egzistuoja patvirtintas darbuotojo algalapis'))

        return res

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        if not self.cancel_id or self.cancel_id.template_id != self.env.ref('omnisend.isakymas_del_priedo_skyrimo_grupei_template'):
            return super(EDocument, self).execute_cancel_workflow()

        cancel_doc = self.cancel_id
        err_msgs = []
        period_from = cancel_doc.date_1
        period_to = cancel_doc.date_2
        period_pay = cancel_doc.date_3
        period_pay_dt = datetime.strptime(period_pay, tools.DEFAULT_SERVER_DATE_FORMAT)
        pay_from = (period_pay_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        pay_to = (period_pay_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        employee_ids = cancel_doc.mapped('omnisend_bonus_line_ids.employee_id')

        bonus_recs = self.env['hr.employee.bonus'].search([
            ('employee_id', 'in', employee_ids.mapped('id')),
            ('for_date_from', '=', period_from),
            ('for_date_to', '=', period_to),
            ('payment_date_from', '=', pay_from),
            ('payment_date_from', '=', pay_from),
            ('payment_date_to', '=', pay_to),
            ('payment_date_from', '=', pay_from),
            ('bonus_type', '=', cancel_doc.bonus_type_selection)
        ])

        slips = self.env['hr.payslip'].search([
            ('employee_id', 'in', employee_ids.mapped('id')),
            ('date_from', '=', pay_from),
            ('date_to', '=', pay_to)
        ])

        for empl_line in cancel_doc.omnisend_bonus_line_ids:
            empl_id = empl_line.employee_id.id
            empl_bonus_recs = bonus_recs.filtered(lambda b: tools.float_compare(b.amount, empl_line.adjusted_bruto,
                                                                                precision_digits=2) == 0 and b.employee_id.id == empl_id)
            if not empl_bonus_recs:
                err_msgs.append((empl_id, 'no_bonus_rec'))
                continue

            empl_slips = slips.filtered(lambda s: s.employee_id.id == empl_id)

            if any(slip.state != 'draft' for slip in empl_slips):
                err_msgs.append((empl_id, 'some_slips_not_draft'))
                continue

            try:
                for empl_bonus_rec in empl_bonus_recs:
                    empl_bonus_rec.action_cancel()
                    bonus_recs = bonus_recs.filtered(lambda b: b.id != empl_bonus_rec.id)
                    empl_bonus_rec.unlink()
            except:
                err_msgs.append((empl_id, 'failed_to_cancel'))

        if err_msgs:
            msg_body = ''
            err_cats = [err_tuple[1] for err_tuple in err_msgs]
            err_cat_name_id_mapping = {
                'no_bonus_rec': _('Nerasti priedų įrašai šiem darbuotojam:'),
                'some_slips_not_draft': _('Šių darbuotojų algalapiai nėra juodraščio būsenos:'),
                'failed_to_cancel': _('Nepavyko atšaukti priedo įrašo dėl nežinomų priežaščių šiem darbuotojam:'),
            }

            for err_cat in set(err_cats):
                err_cat_employee_ids = [err_tuple[0] for err_tuple in err_msgs if err_tuple[1] == err_cat]
                err_cat_employee_names = self.env['hr.employee'].browse(err_cat_employee_ids).mapped('name')

                if msg_body != '':
                    msg_body += '\n'

                err_cat_name = err_cat_name_id_mapping.get(err_cat, 'Nenumatytos problemos:')
                msg_body += err_cat_name + '\n'

                for empl_name in err_cat_employee_names:
                    msg_body += empl_name + '\n'

            is_document_for_group = True if len(cancel_doc.omnisend_bonus_line_ids) > 1 else False
            if is_document_for_group:
                intro = _('Ne visiems darbuotojams pavyko atšaukti įsakymą dėl priedo skyrimo grupei (įmonė {}). '
                          'Priedus reikės pasikoreguoti rankiniu būdu. '
                          'Klaidos pranešimai:').format(str(self.env.user.company_id.name))
            else:
                intro = _('Darbuotojui nepavyko atšaukti įsakymo dėl priedo skyrimo (Įmonė {}).'
                          'Klaidos pranešimai:').format(str(self.env.user.company_id.name))
            msg_body = intro + '\n\n' + msg_body
            raise exceptions.UserError(msg_body)

    @api.multi
    def _date_from_display(self):
        other_documents = self.env['e.document']
        for rec in self:
            if rec.template_id != self.env.ref('omnisend.isakymas_del_priedo_skyrimo_grupei_template'):
                other_documents |= rec
                continue

            date_from = False

            if rec.date_3:
                date_from_dt = datetime.strptime(rec.date_3, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_from = (date_from_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

            rec.date_from_display = date_from
        super(EDocument, other_documents)._date_from_display()

    @api.multi
    def _date_to_display(self):
        other_documents = self.env['e.document']
        for rec in self:
            if rec.template_id != self.env.ref('omnisend.isakymas_del_priedo_skyrimo_grupei_template'):
                other_documents |= rec
                continue

            date_to = False

            if rec.date_3:
                date_from_dt = datetime.strptime(rec.date_3, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_to = (date_from_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

            rec.date_to_display = date_to
        super(EDocument, other_documents)._date_to_display()

    @api.one
    def check_omnisend_bonus_line_ids(self):
        if not self.omnisend_bonus_line_ids:
            raise exceptions.Warning(_('Įveskite bent vieną darbuotoją.'))
        elif self.omnisend_bonus_line_ids:
            employee_ids = self.omnisend_bonus_line_ids.mapped('employee_id')

            if len(employee_ids) != len(self.omnisend_bonus_line_ids):
                raise exceptions.Warning(_('Įvesti darbuotojai kartojasi'))

    @api.onchange('date_1', 'date_2')
    def _check_ziniarastis_exists_by_dates(self):
        employees = self.mapped('omnisend_bonus_line_ids.employee_id')
        if not self.date_1 or not self.date_2 or not employees:
            return

        ziniarastis_lines = self.env['ziniarastis.period.line'].search([
            ('employee_id', 'in', employees.ids),
            ('date_from', '<=', self.date_2),
            ('date_to', '>=', self.date_1),
            ('state', '=', 'done')])

        for employee_id in employees:
            employee_ziniarastis_lines = ziniarastis_lines.filtered(lambda l: l.employee_id.id == employee_id.id)

            if not employee_ziniarastis_lines:
                raise exceptions.UserError(
                    _('Darbuotojas %s neturi patvirtinto apskaitos žiniaraščio') % (employee_id.name))


EDocument()


class EDocumentLine(models.Model):

    _name = 'omnisend.e.document.line'

    e_document_id = fields.Many2one('e.document', required=True)
    employee_id = fields.Many2one('hr.employee', string='Darbuotojo Vardas')
    full_bruto = fields.Float()
    work_norm = fields.Float(compute='_compute_adjusted_bruto', store=True)
    worked_time = fields.Float(compute='_compute_adjusted_bruto', store=True)
    adjusted_bruto = fields.Float(compute='_compute_adjusted_bruto', store=True)

    @api.one
    @api.depends('employee_id', 'full_bruto')
    def _compute_adjusted_bruto(self):
        if not self.employee_id or not self.e_document_id.date_1 or not self.e_document_id.date_2 or not self.full_bruto:
            return

        ziniarastis_lines = self.env['ziniarastis.period.line'].search([
            ('employee_id', '=', self.employee_id.id),
            ('date_from', '<=', self.e_document_id.date_2),
            ('date_to', '>=', self.e_document_id.date_1),
            ('state', '=', 'done')])

        self.worked_time = sum(ziniarastis_lines.mapped('days_total'))

        work_norm = self.env['hr.employee'].employee_work_norm(
            employee=self.employee_id,
            calc_date_from=self.e_document_id.date_1,
            calc_date_to=self.e_document_id.date_2)

        self.work_norm = work_norm['days']

        try:
            self.adjusted_bruto = self.full_bruto / self.work_norm * self.worked_time
        except ZeroDivisionError:
            self.adjusted_bruto = 0

    @api.onchange('employee_id')
    def _check_ziniarastis_exists_by_employee(self):
        if not self.employee_id or not self.e_document_id.date_1 or not self.e_document_id.date_2:
            return

        ziniarastis_lines = self.env['ziniarastis.period.line'].search([
            ('employee_id', '=', self.employee_id.id),
            ('date_from', '<=', self.e_document_id.date_2),
            ('date_to', '>=', self.e_document_id.date_1),
            ('state', '=', 'done')])

        if not ziniarastis_lines:
            raise exceptions.UserError(
                ('Darbuotojas %s neturi patvirtinto apskaitos žiniaraščio') % (self.employee_id.name))


EDocumentLine()

