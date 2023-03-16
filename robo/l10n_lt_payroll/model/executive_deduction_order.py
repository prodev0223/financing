# coding=utf-8
from __future__ import division
from odoo import fields, models, _, api, tools, exceptions
from datetime import datetime
from dateutil.relativedelta import relativedelta


class ExecutiveDeductionOrder(models.Model):
    _name = 'executive.deduction.order'
    _inherit = 'mail.thread'

    def default_journal_id(self):
        return self.env.user.company_id.salary_journal_id

    def default_account_id(self):
        return self.env['account.account'].search([('code', '=', '4484')])

    _sql_constraints = [('employee_id_unique', 'unique(employee_id)',
                         _('Galimas tik vienos išskaitos orderis vienam darbuotojui'))]

    active = fields.Boolean(string="Active", default=True, track_visibility='onchange')
    state = fields.Selection([('draft', 'Juodraštis'), ('confirm', 'Patvirtinta')], string='Būsena', readonly=True,
                             default='draft', required=True, copy=False, track_visibility='onchange')
    name = fields.Char('Pavadinimas', required=True, copy=False, readonly=True,
                       states={'draft': [('readonly', False)]}, track_visibility='onchange')
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', required=True, readonly=True,
                                  states={'draft': [('readonly', False)]}, track_visibility='onchange')
    deduction_order_deduction_ids = fields.One2many('executive.deduction.order.deduction', 'deduction_order_id',
                                                    string='Išskaitos', readonly=True,
                                                    states={'draft': [('readonly', False)]})
    currency_id = fields.Many2one('res.currency', string='Valiuta', required=True, readonly=True,
                                  default=lambda self: self.env.user.company_id.currency_id)

    percentage_under_mma = fields.Float('Iš pajamų neviršijančių MMA (%)', required=True, default=20, readonly=True,
                                        states={'draft': [('readonly', False)]}, track_visibility='onchange')
    percentage_over_mma = fields.Float('Iš pajamų viršijančių MMA (%)', required=True, default=50, readonly=True,
                                       states={'draft': [('readonly', False)]}, track_visibility='onchange')

    deduction_entry_ids = fields.One2many('hr.employee.isskaitos', 'deduction_order_id',
                                          compute='_compute_deduction_entry_ids')
    account_id = fields.Many2one('account.account', string='Išmokėjimo sąskaita',
                                 states={'confirm': [('readonly', True)]}, required=True, default=default_account_id)
    journal_id = fields.Many2one('account.journal', string='Žurnalas', required=True,
                                 states={'confirm': [('readonly', True)]}, default=default_journal_id,
                                 track_visibility='onchange')

    ongoing_deduction_amount = fields.Float(string='Ongoing deduction amount',
                                            compute='_compute_ongoing_deduction_amount')
    ongoing_deduction_amount_left = fields.Float(string='Ongoing deduction amount left',
                                                 compute='_compute_ongoing_deduction_amount_left')
    message_last_post = fields.Datetime(readonly=True)

    @api.one
    @api.depends('deduction_order_deduction_ids.deduction_entry_ids')
    def _compute_deduction_entry_ids(self):
        self.deduction_entry_ids = [(6, 0, self.deduction_order_deduction_ids.mapped('deduction_entry_ids.id'))]

    @api.multi
    def confirm(self):
        self.write({'state': 'confirm'})

    @api.multi
    def action_draft(self):
        self.write({'state': 'draft'})

    @api.multi
    @api.constrains('percentage_under_mma', 'percentage_over_mma')
    def _check_mma_amounts(self):
        for rec in self:
            if tools.float_compare(rec.percentage_over_mma, 100, precision_digits=2) > 0 or tools.float_compare(
                    rec.percentage_over_mma, 0, precision_digits=2) < 0:
                raise exceptions.UserError(_('Procentas virš MMA turi būti tarp 0% ir 100%'))
            if tools.float_compare(rec.percentage_under_mma, 100, precision_digits=2) > 0 or tools.float_compare(
                    rec.percentage_under_mma, 0, precision_digits=2) < 0:
                raise exceptions.UserError(_('Procentas žemiau MMA turi būti tarp 0% ir 100%'))

    @api.multi
    def action_open_deduction_entry_ids(self):
        self.ensure_one()
        return {
            'view_type': 'form',
            'view_mode': 'tree, form',
            'views': [(self.env.ref('l10n_lt_payroll.isskaitos_tree_view').id, 'tree'), (self.env.ref('l10n_lt_payroll.isskaitos_form_view').id, 'form')],
            'res_model': 'hr.employee.isskaitos',
            'domain': [('id', 'in', self.deduction_entry_ids.ids)],
            'view_id': self.env.ref('l10n_lt_payroll.isskaitos_tree_view').id,
            'type': 'ir.actions.act_window',
            'name': _('Orderio - %s (%s) išskaitų įrašai') % (self.name, self.employee_id.display_name),
            'target': 'current',
        }

    @api.multi
    def unlink(self):
        if any(rec.state == 'confirm' for rec in self):
            raise exceptions.UserError(_('Negalima trinti patvirtinto įrašo. Pirmiau atšaukite.'))
        return super(ExecutiveDeductionOrder, self).unlink()

    @api.multi
    @api.depends('deduction_order_deduction_ids', 'deduction_order_deduction_ids.amount',
                 'deduction_order_deduction_ids.ongoing')
    def _compute_ongoing_deduction_amount(self):
        for rec in self:
            deductions = rec.deduction_order_deduction_ids.filtered(lambda deduction: deduction.ongoing)
            rec.ongoing_deduction_amount = sum(deductions.mapped('amount'))

    @api.multi
    @api.depends('deduction_order_deduction_ids', 'deduction_order_deduction_ids.amount',
                 'deduction_order_deduction_ids.ongoing')
    def _compute_ongoing_deduction_amount_left(self):
        for rec in self:
            deductions = rec.deduction_order_deduction_ids.filtered(lambda deduction: deduction.ongoing)
            rec.ongoing_deduction_amount_left = sum(deductions.mapped('amount_left'))


ExecutiveDeductionOrder()


class ExecutiveDeductionOrderDeduction(models.Model):
    _name = 'executive.deduction.order.deduction'

    def default_date_start(self):
        now = datetime.utcnow()
        first_of_month = now + relativedelta(months=1, day=1)
        return first_of_month.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    deduction_order_id = fields.Many2one('executive.deduction.order', required=True)
    partner_id = fields.Many2one('res.partner', string='Partneris', required=True)
    amount = fields.Monetary(string='Išskaitos dydis', currency_field='currency_id', required=True)
    amount_left = fields.Monetary(string='Likutis', currency_field='currency_id', required=True, compute="_compute_amount_left")
    currency_id = fields.Many2one('res.currency', compute='_compute_curency_id')
    line_of_satisfaction = fields.Selection([
        ('first', 'Pirmoji'),
        ('second', 'Antroji'),
        ('third', 'Trečioji')
    ], string='Reikalavimų patenkinimo eilė', required=True, default='second')

    ongoing = fields.Boolean('Vykdomas', default=True)

    deduction_entry_ids = fields.One2many('hr.employee.isskaitos', 'deduction_order_deduction_id', string='Partnerio išskaitų įrašai', readonly=True)
    date_start = fields.Date('Vykdyti nuo', required=True, default=default_date_start)
    comment = fields.Text(string='Mokėjimo paskirtis', copy=False)

    @api.one
    @api.depends('deduction_order_id')
    def _compute_curency_id(self):
        self.currency_id = self.deduction_order_id.currency_id

    @api.multi
    @api.constrains('date_start')
    def _check_date_start(self):
        for rec in self:
            date_start = rec.date_start
            date_start_dt = datetime.strptime(date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
            first_of_month = (date_start_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if date_start != first_of_month:
                raise exceptions.ValidationError(
                    _('Pradžios data, nuo kada vykdyti išskaitą - privalo būti mėnesio pirma diena')
                )

    @api.constrains('amount')
    def _check_amounts_positive(self):
        if any(tools.float_compare(rec.amount, 0.0, precision_digits=2) < 0 for rec in self):
            raise exceptions.ValidationError(_('Išieškojimo suma privalo būti teigiamas skaičius'))

    @api.one
    @api.depends('amount', 'deduction_entry_ids')
    def _compute_amount_left(self):
        self.amount_left = self.amount - sum(self.deduction_entry_ids.mapped('amount'))

    @api.multi
    def unlink(self):
        if any(rec.deduction_order_id and rec.deduction_order_id.state == 'confirm' for rec in self):
            raise exceptions.UserError(_('Negalima trinti patvirtinto įrašo. Pirmiau atšaukite.'))
        return super(ExecutiveDeductionOrderDeduction, self).unlink()


ExecutiveDeductionOrderDeduction()


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    @api.multi
    def refresh_and_recompute(self):
        def deduct_from_lines(lines, max_deductible, other_class_lines_exist=False):
            lines_amount_left = sum(lines.mapped('amount_left'))

            deducted_amnt = 0.0
            isskaitos = []
            percentages = {}
            if not lines:
                return {'isskaitos_vals': isskaitos, 'deducted_amount': deducted_amnt}
            use_proportion = tools.float_compare(lines_amount_left, max_deductible, precision_digits=2) > 0
            if use_proportion:  # No need otherwise
                for line in lines:
                    percentages[str(line.id)] = line.amount_left / lines_amount_left * 100  # P3:DivOK

            deductible_amount_left = max_deductible
            number_of_lines = len(lines)
            index = 0
            for line in lines:
                index += 1
                if use_proportion:
                    line_percentage = percentages.get(str(line.id), 0.0)
                    to_deduct = max_deductible * line_percentage / 100.0  # P3:DivOK
                else:
                    to_deduct = line.amount_left

                # Deduct the maximum possible amount from the last line if the maximum possible amount to be deducted is
                # no more than two cents higher than the amount that was going to be deducted. Precision issues occur
                # when calculating ratios for multiple lines.
                if index == number_of_lines and not other_class_lines_exist:
                    difference_with_deductible_amount_left = abs(to_deduct - deductible_amount_left)
                    if tools.float_compare(difference_with_deductible_amount_left, 0.02, precision_digits=2) <= 0:
                        to_deduct = deductible_amount_left

                to_deduct = tools.float_round(to_deduct, precision_digits=2)
                deductible_amount_left -= to_deduct
                deducted_amnt += to_deduct

                isskaitos.append({
                    'employee_id': line.deduction_order_id.employee_id.id,
                    'deduction_order_deduction_id': line.id,
                    'journal_id': line.deduction_order_id.journal_id.id,
                    'reason': 'vykd_r',
                    'account_id': line.deduction_order_id.account_id.id,
                    'partner_id': line.partner_id.id,
                    'currency_id': line.deduction_order_id.currency_id.id,
                    'date': min(rec.date_to, rec.contract_id.date_end or rec.date_to),
                    'amount': to_deduct,
                    'date_maturity': (datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(months=1, day=15)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                    'comment': line.comment
                })

            return {'isskaitos_vals': isskaitos, 'deducted_amount': deducted_amnt}

        res = super(HrPayslip, self).refresh_and_recompute()
        for rec in self:
            deduction_order = self.env['executive.deduction.order'].search([
                ('employee_id', '=', rec.employee_id.id),
                ('state', '!=', 'draft')
            ], limit=1)
            if not deduction_order:
                continue

            deduction_date = min(rec.date_to, rec.contract_id.date_end or rec.date_to)
            start_date = max(rec.date_from, rec.contract_id.date_start)
            created_entries = deduction_order.deduction_entry_ids.filtered(
                lambda e: start_date <= e.date <= deduction_date
            )
            created_entries.action_cancel()
            created_entries.unlink()

            deduction_ids = deduction_order.mapped('deduction_order_deduction_ids').filtered(
                lambda d: d.ongoing and not
                          tools.float_is_zero(d.amount_left, precision_digits=2) and
                          d.date_start <= rec.date_from)

            if not deduction_ids:
                continue

            already_deducted = sum(rec.line_ids.filtered(lambda r: r.code in ['IŠSK']).mapped('total'))
            amount_neto = sum(rec.line_ids.filtered(lambda r: r.code in ['BENDM']).mapped('total'))
            advance_amount = sum(rec.line_ids.filtered(lambda r: r.code in ['AVN']).mapped('total'))
            # If the advance is more than what should be left after deductions - then the advance should be lowered.
            total_amount_neto = amount_neto + advance_amount + already_deducted
            # Should not deduct from specific compensations
            other_addition = sum(rec.line_ids.filtered(lambda r: r.code in ['KKPD']).mapped('total'))
            # In this case KKPD is a dynamic workplace compensation that's in the M rule (used in BENDM rule). This
            # compensation is not taxed. Should not be deducted from.
            total_amount_neto -= other_addition
            total_amount_neto = max(total_amount_neto, 0.0)
            percentage_over = deduction_order.percentage_over_mma
            percentage_under = deduction_order.percentage_under_mma
            neto_mma = rec.get_neto_mma()

            under_mma_amount_to_calc_from = min(total_amount_neto, neto_mma)
            under_mma_amount_deductible = under_mma_amount_to_calc_from * percentage_under / 100.0  # P3:DivOK
            over_mma_amount_deductible = 0.0
            if tools.float_compare(neto_mma, total_amount_neto, precision_digits=2) < 0:
                over_mma_amount = total_amount_neto - neto_mma
                over_mma_amount_deductible = over_mma_amount * percentage_over / 100.0  # P3:DivOK

            max_deductible_amount = under_mma_amount_deductible + over_mma_amount_deductible
            max_deductible_amount = tools.float_round(max_deductible_amount, precision_digits=2)

            first_priority_lines = deduction_ids.filtered(lambda d: d.line_of_satisfaction == 'first')
            second_priority_lines = deduction_ids.filtered(lambda d: d.line_of_satisfaction == 'second')
            third_priority_lines = deduction_ids.filtered(lambda d: d.line_of_satisfaction == 'third')

            all_isskaitos_vals = []
            data = deduct_from_lines(first_priority_lines, max_deductible_amount, bool(second_priority_lines))
            all_isskaitos_vals += data['isskaitos_vals']
            max_deductible_amount -= data['deducted_amount']
            data = deduct_from_lines(second_priority_lines, max_deductible_amount, bool(third_priority_lines))
            all_isskaitos_vals += data['isskaitos_vals']
            max_deductible_amount -= data['deducted_amount']
            data = deduct_from_lines(third_priority_lines, max_deductible_amount)
            all_isskaitos_vals += data['isskaitos_vals']
            max_deductible_amount -= data['deducted_amount']
            ISSKAITOS_OBJ = self.env['hr.employee.isskaitos']
            isskaitos_recs = ISSKAITOS_OBJ
            for isskaitos_vals in all_isskaitos_vals:
                if not tools.float_is_zero(isskaitos_vals.get('amount'), precision_digits=2):
                    isskaitos_recs |= ISSKAITOS_OBJ.create(isskaitos_vals)
            isskaitos_recs.confirm()  # This refreshes and recomputes the slip.
        return res

    @api.multi
    def get_neto_mma(self):
        self.ensure_one()
        employee = self.employee_id

        date_get = self.date_from or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        appointments = self.contract_id.mapped('appointment_ids').filtered(
            lambda a: a.date_start <= self.date_to and
                      (not a.date_end or a.date_end >= self.date_from)
        ).sorted(key=lambda a: a.date_start)
        appointment = appointments[0] if appointments else None

        if appointment:
            force_npd = None if appointment.use_npd else 0.0
            voluntary_pension = appointment.sodra_papildomai and appointment.sodra_papildomai_type
            disability = appointment.darbingumas.name if appointment.invalidumas else False
            is_fixed_term = appointment.contract_id.is_fixed_term
        else:
            force_npd = None
            voluntary_pension = disability = is_fixed_term = False

        minimum_wage = self.with_context(date=date_get).contract_id.get_payroll_tax_rates(['mma'])['mma']

        npd_date = self.get_npd_values()['npd_date']

        payroll_values = self.env['hr.payroll'].sudo().get_payroll_values(
            date=date_get,
            npd_date=npd_date,
            bruto=minimum_wage,
            force_npd=force_npd,
            voluntary_pension=voluntary_pension,
            disability=disability,
            is_foreign_resident=employee.is_non_resident,
            is_fixed_term=is_fixed_term,
        )
        return payroll_values.get('neto', 0.0)


HrPayslip()


class HrEmployeeIsskaitos(models.Model):
    _inherit = 'hr.employee.isskaitos'

    deduction_order_deduction_id = fields.Many2one('executive.deduction.order.deduction', readonly=True)
    deduction_order_id = fields.Many2one('executive.deduction.order', compute='_compute_deduction_order_id')

    @api.one
    @api.depends('deduction_order_deduction_id')
    def _compute_deduction_order_id(self):
        self.deduction_order_id = self.deduction_order_deduction_id.deduction_order_id


HrEmployeeIsskaitos()
