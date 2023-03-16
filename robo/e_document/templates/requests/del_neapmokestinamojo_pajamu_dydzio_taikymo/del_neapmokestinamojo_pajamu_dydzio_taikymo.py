# -*- coding: utf-8 -*-
from odoo import models, api, exceptions, _


TEMPLATE = 'e_document.prasymas_del_neapmokestinamojo_pajamu_dydzio_taikymo_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_del_neapmokestinamojo_pajamu_dydzio_taikymo_workflow(self):
        self.ensure_one()
        contract = self.env['hr.contract'].search(
            [('employee_id', '=', self.employee_id1.id), ('date_start', '<=', self.date_1), '|',
             ('date_end', '=', False), ('date_end', '>=', self.date_1)], limit=1)

        date_to_use = self.date_1

        if not contract:
            first_contract = self.env['hr.contract'].search(
                [('employee_id', '=', self.employee_id1.id), ('date_start', '>', self.date_1)], order='date_start asc',
                limit=1)
            if first_contract and first_contract.date_start > self.date_1:
                e_docs_in_between = self.env['e.document'].search([
                    ('employee_id1', '=', self.employee_id1.id),
                    ('template_id', '=', self.template_id.id),
                    ('date_1', '<=', first_contract.date_start),
                    ('date_1', '>', self.date_1),
                    ('state', 'in', ['signed', 'e_signed']),
                    ('id', '!=', self.id)
                ])
                if not e_docs_in_between:
                    contract = first_contract
                    date_to_use = contract.date_start
        if contract:
            new_record = contract.update_terms(date_from=date_to_use, use_npd=self.selection_bool_1 == 'true')
            if new_record:
                self.inform_about_creation(new_record)
                self.set_link_to_record(new_record)

        self.update_npd_selection_in_upcoming_salary_change_documents()

    @api.multi
    def update_npd_selection_in_upcoming_salary_change_documents(self):
        """
        Updates the non-taxable income type selection in salary change documents when the employee issues a new request
        for the non-taxable income choice.
        """
        self.ensure_one()
        use_npd = self.selection_bool_1 == 'true'
        npd_type_that_should_be_set = 'auto' if use_npd else 'manual'
        change_date = self.date_1
        salary_change_orders = self.sudo().search([
            ('state', 'in', ['draft', 'confirm']),
            ('template_id', '=', self.env.ref('e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template').id),
            ('employee_id2', '=', self.employee_id1.id),
            ('date_3', '>=', change_date),
            ('npd_type', '!=', npd_type_that_should_be_set)
        ])
        orders_to_inform_about = self.env['e.document']
        for salary_change_order in salary_change_orders:
            if salary_change_order.running or salary_change_order.state == 'confirm':
                # Inform about documents that can't be changed at the moment
                orders_to_inform_about |= salary_change_order
                continue
            salary_change_order.write({'npd_type': npd_type_that_should_be_set})

        if orders_to_inform_about:
            try:
                employee_name = self.employee_id1.name or self.employee_id1.address_home_id.name
                order_list = '\n'.join(
                    '- {} {}'.format(order.template_id.name, order.date_3) for order in orders_to_inform_about
                )
                subject = _('[{}] Pasirašytas prašymas dėl neapmokestinamojo pajamų dydžio taikymo').format(self._cr.dbname)
                body = _("""Pasirašytas darbuotojo {} prašymas ({}) dėl neapmokestinamojo pajamų dydžio taikymo. 
                Sistema rado jau paruoštus sutarties sąlygų pakeitimo įsakymus, kuriuose nustatytas NPD pasirinkimas 
                prieštarauja naujai pasirašytam prašymui. Pasirinkimo šiuose įsakymuose nepavyko pakeisti automatiškai, 
                todėl reikėtų susisiekti su klientu, arba rankiniu būdu pakeisti NPD taikymo pasirinkimą šiuose darbo 
                sutarties sąlygų pakeitimo įsaykmuose:\n{}""").format(employee_name, self.id, order_list)
                self.create_internal_ticket(subject, body)
            except Exception as exc:
                message = _("""[{}] Failed to create a ticket notifying about waiting salary change documents after 
                signing a non-taxable income request ({}): Affected order ids: {}. \nError: {}
                """).format(
                    self._cr.dbname, self.id, ', '.join(str(order_id) for order_id in orders_to_inform_about.ids),
                    str(exc.args)
                )
                self.env['robo.bug'].sudo().create({
                    'user_id': self.env.user.id,
                    'error_message': message,
                })

    @api.multi
    def execute_confirm_workflow_check_values(self):
        res = super(EDocument, self).execute_confirm_workflow_check_values()
        for rec in self.filtered(
                lambda r: r.template_id == self.env.ref(TEMPLATE) and not r.sudo().skip_constraints_confirm):
            errors = rec.check_request_for_application_of_non_taxable_income_amount_constraints()
            if errors:
                raise exceptions.ValidationError(errors)
        return res

    @api.multi
    def check_workflow_constraints(self):
        res = super(EDocument, self).check_workflow_constraints()
        for rec in self.filtered(lambda r: r.template_id == self.env.ref(TEMPLATE)):
            res += rec.check_request_for_application_of_non_taxable_income_amount_constraints()
        return res

    @api.multi
    def check_request_for_application_of_non_taxable_income_amount_constraints(self):
        """
        Method to check constraints for 'prasymas_del_neapmokestinamojo_pajamu_dydzio_taikymo_template' EDoc template
        :return: if a constraint was violated return an error message in string, otherwise an empty string
        """
        self.ensure_one()
        country_lithuania = self.env['res.country'].search([('code', '=', 'LT'), ])
        employee = self.employee_id1.sudo()
        nationality = employee.nationality_id
        is_foreigner = (nationality and nationality != country_lithuania) or employee.is_non_resident
        if self.selection_bool_1 == 'true' and is_foreigner:
            return _('Pursuant to article 20 part 4 of the law on Personal Income Tax of the Republic of Lithuania, '
                     'NPD applies only to permanent residents of Lithuania. If You have supporting documents, '
                     'contact the accountant responsible for Your company.')
        return str()


EDocument()
