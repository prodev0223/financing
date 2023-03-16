# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, api, exceptions, tools, _, fields
from odoo.addons.e_document.model.linksnis import kas_to_ko

TEMPLATE = 'e_document.asset_lease_agreement_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    lease_type = fields.Selection([('auto_rent', 'Auto lease'), ('rent', 'Real estate lease')], string="Lease type",
                                  default='rent', inverse='set_final_document', readonly=True,
                                  states={'draft': [('readonly', False)]})
    lease_gross_amount = fields.Float(string='Lease GROSS amount', compute='_compute_lease_amounts')
    lease_net_amount = fields.Float(string='Lease NET amount', compute='_compute_lease_amounts')
    lease_calculation_table = fields.Html(compute='_compute_lease_amounts')

    @api.multi
    @api.depends('lease_type', 'float_1', 'date_1', 'du_input_type')
    def _compute_lease_amounts(self):
        template = self.env.ref(TEMPLATE, False)
        if not template:
            return
        for rec in self.filtered(lambda doc: doc.template_id == template):
            if not rec.lease_type or not rec.float_1 or not rec.date_1:
                continue

            tax_rates = self.get_asset_lease_tax_rates(rec.date_1)

            if rec.du_input_type == 'bruto':
                gross_amount = rec.float_1
            else:
                gross_amount = self.env['hr.payroll'].sudo().convert_net_income_to_gross(
                    rec.float_1, date=rec.date_1, **tax_rates
                )
            rec.lease_gross_amount = gross_amount

            calculated_values = self.env['hr.payroll'].sudo().get_payroll_values(
                date=rec.date_from, bruto=gross_amount, **tax_rates
            )
            net_amount = calculated_values.get('neto')
            income_tax_amount = calculated_values.get('gpm')

            def preprocess_amount(amount):
                return "{:.2f}".format(tools.float_round(amount, precision_digits=2))

            rec.lease_calculation_table = self.env['ir.qweb'].sudo().render('e_document.LeaseCalculationTable', {
                'currency_symbol': self.env.user.company_id.currency_id.symbol or '€',
                'gross_amount': preprocess_amount(gross_amount),
                'net_amount': preprocess_amount(net_amount),
                'income_tax_amount': preprocess_amount(income_tax_amount),
            })

            rec.lease_net_amount = net_amount

    @api.model
    def get_asset_lease_tax_rates(self, date):
        # Force the tax rates for wage unrelated payments
        du_unrelated_income_tax_percentage = self.env['hr.contract'].sudo().with_context(
            date=date
        ).get_payroll_tax_rates(['gpm_du_unrelated'])['gpm_du_unrelated']
        return {
            'gpm_proc': du_unrelated_income_tax_percentage,
            'sodra_papild_proc': 0.0,
            'sodra_papild_exponential_proc': 0.0,
            'darbuotojo_sveikatos_proc': 0.0,
            'darbdavio_sodra_proc': 0.0,
            'darbuotojo_pensijos_proc': 0.0,
            'force_npd': 0.0,
        }

    @api.multi
    def execute_confirm_workflow_check_values(self):
        res = super(EDocument, self).execute_confirm_workflow_check_values()
        template = self.env.ref(TEMPLATE, False)
        if not template:
            return res
        today = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        allow_historic_signing = self.env.user.company_id.e_documents_allow_historic_signing_spec
        for rec in self.filtered(lambda d: d.template_id == template and not d.sudo().skip_constraints_confirm):
            if rec.date_to and rec.date_from > rec.date_to:
                raise exceptions.ValidationError(_('Lease has to end after it starts'))
            if rec.date_1 < rec.date_from:
                raise exceptions.ValidationError(_('First payment date must be on or after lease start date'))
            if rec.date_to and rec.date_1 > rec.date_to:
                raise exceptions.ValidationError(_('First payment date has to be before the lease ends'))
            if rec.date_from < today and not allow_historic_signing:
                raise exceptions.ValidationError(_('Lease start date can\'t be in the past'))
            if tools.float_compare(rec.float_1, 0.0, precision_digits=2) <= 0:
                raise exceptions.ValidationError(_('Incorrect lease amount'))
        return res

    @api.multi
    def get_asset_payment_base_values(self):
        self.ensure_one()
        lang = self._context.get('lang') or self.env.user.lang or 'lt_LT'
        lease_type_name = dict(self._fields['lease_type'].selection).get(self.lease_type)
        if lang == 'lt_LT':
            lease_type_name = kas_to_ko(lease_type_name, 'Aa')

        if self.lease_type == 'rent':
            a_class_code = self.env.ref('l10n_lt_payroll.a_klase_kodas_14')
        else:
            a_class_code = self.env.ref('l10n_lt_payroll.a_klase_kodas_15')

        return {
            'state': 'ready',
            'description': lease_type_name + _('payment'),
            'partner_id': self.doc_partner_id.id,
            'type': self.lease_type,
            'amount_paid': self.lease_net_amount,
            'amount_bruto': self.lease_gross_amount,
            'a_klase_kodas_id': a_class_code.id,
        }

    @api.multi
    def create_partial_asset_lease_payment(self):
        self.ensure_one()

        start_date = self.date_1

        # Calculate payment amount based on lease duration
        date_from_dt = datetime.strptime(start_date, tools.DEFAULT_SERVER_DATE_FORMAT)
        end_of_month_dt = date_from_dt + relativedelta(day=31)
        if self.date_to:
            end_date_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            end_date_dt = min(end_of_month_dt, end_date_dt)
        else:
            end_date_dt = end_of_month_dt
        duration = 1 if date_from_dt == end_date_dt else (end_date_dt - date_from_dt).days
        days_in_month = end_of_month_dt.day
        amount = duration / float(days_in_month) * self.lease_gross_amount

        # Get tax rates fpr date and calculate the NET amount to pay
        tax_rates = self.get_asset_lease_tax_rates(start_date)
        calculated_values = self.env['hr.payroll'].sudo().get_payroll_values(date=start_date, bruto=amount, **tax_rates)
        net_amount = calculated_values.get('neto', 0.0)
        amount_gpm = calculated_values.get('gpm', 0.0)

        # Create payment
        payment_values = self.get_asset_payment_base_values()
        payment_values.update({
            'date': start_date,
            'date_payment': start_date,
            'date_from': start_date,
            'date_to': end_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'amount_bruto': amount,
            'amount_paid': net_amount,
            'amount_gpm': amount_gpm,
        })
        payment = self.env['hr.employee.payment'].create(payment_values)
        payment.onchange_type()
        payment.atlikti()
        return payment

    @api.multi
    def create_first_full_asset_lease_payment(self):
        self.ensure_one()

        # Date start will be the first day of the next month after the first payment
        start_date = self.date_1
        date_from_dt = datetime.strptime(start_date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(day=1, months=1)
        date_from = date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        # Date to will either be the end of the month of start date or the lease date to described in the document
        date_end = (date_from_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        if self.date_to:
            date_end = min(date_end, self.date_to)

        # Create payment
        payment_values = self.get_asset_payment_base_values()
        payment_values.update({
            'date': date_from,
            'date_payment': date_from,
            'date_from': date_from,
            'date_to': date_end,
            'amount_bruto': self.lease_gross_amount,
            'amount_paid': self.lease_net_amount,
            'amount_gpm': self.lease_gross_amount - self.lease_net_amount,
        })
        payment = self.env['hr.employee.payment'].create(payment_values)
        payment.onchange_type()
        payment.atlikti()
        return payment

    @api.multi
    def create_asset_lease_payments(self):
        self.ensure_one()

        first_payment_dt = datetime.strptime(self.date_1, tools.DEFAULT_SERVER_DATE_FORMAT)

        # Check if the first payment is made on the first day of the month and if not - create a residual payment for
        # the number of days left in the month.
        payments = self.env['hr.employee.payment']
        if first_payment_dt != first_payment_dt + relativedelta(day=1):
            payments |= self.create_partial_asset_lease_payment()

        # Find the date of the first full payment
        first_of_next_month_dt = first_payment_dt + relativedelta(day=1, months=1)
        first_of_next_month = first_of_next_month_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        # Check if the lease ends after the first partial payment and if so - create the first full lease payment
        if not self.date_to or self.date_to >= first_of_next_month:
            full_payment = self.create_first_full_asset_lease_payment()
            payments |= full_payment

            # Check if the lease sometime after the first full payment and if so - make the lease payments periodic
            if not self.date_to or self.date_to > full_payment.date_to:
                # Make the first full payment periodic
                payment_date_to_dt = datetime.strptime(full_payment.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
                next_payment_date_dt = payment_date_to_dt + relativedelta(day=1, months=1)
                next_payment_date = next_payment_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                periodic_payment = self.env['hr.employee.payment.periodic'].create({
                    'payment_id': full_payment.id,
                    'action': 'open_form',
                    'date': next_payment_date,
                    'date_stop': self.date_to,
                    'amount_base': self.lease_net_amount,
                    'split_amount_in_proportion': True,
                })
                full_payment.write({'periodic_id': periodic_payment.id})
        return payments

    @api.multi
    def asset_lease_workflow(self):
        self.ensure_one()
        payments = self.create_asset_lease_payments()
        self.write({
            'record_model': payments and payments[0]._name,
            'record_ids': self.format_record_ids(payments.ids)
        })

    @api.multi
    def end_agreement(self, date_from):
        self.ensure_one()
        super(EDocument, self).end_agreement(date_from)
        template = self.env.ref(TEMPLATE, False)
        if template and self.template_id == template:
            payments = self.env[self.record_model].browse(self.parse_record_ids())
            periodic_payments = payments.mapped('periodic_id')
            if periodic_payments:
                periodic_payments.write({'date_stop': date_from})

            cancelling_before_first_payment = date_from <= self.date_1

            if not cancelling_before_first_payment:
                # Try to cancel and unlink only the payments after the provided date
                payments = payments.filtered(lambda p: p.date >= date_from)
                payments.mapped('periodic_id').sudo().exists().unlink()
            else:
                periodic_payments.sudo().unlink()  # Unlink all periodic payments
            payments.atsaukti()
            payments.sudo().unlink()

    @api.multi
    def create_agreement_end_document(self):
        self.ensure_one()
        if not self.env.user.is_manager():
            raise exceptions.AccessError(_('Only managers can perform this action'))
        template = self.env.ref('e_document.end_agreement_template')
        cancel_id = self.env['e.document'].create({
            'document_type': 'isakymas',
            'template_id': template.id,
            'doc_partner_id': self.doc_partner_id.id,
            'cancel_id': self.id,
            'date_4': datetime.now(),
            'date_from': datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
        })
        ctx = dict(self._context)
        ctx['robo_header'] = {}
        action = self.env.ref('e_document.end_agreement_action').read()[0]
        action.update({'res_id': cancel_id.id, 'context': ctx})
        return action