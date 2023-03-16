# -*- coding: utf-8 -*-

from odoo import _, api, exceptions, fields, models, tools


class InvoiceApprovalCondition(models.Model):
    _name = 'invoice.approval.condition'

    @api.model
    def _get_default_step_from_context(self):
        return self._context.get('active_approval_step_id') or False

    @api.model
    def _get_default_approver_from_context(self):
        return self._context.get('active_approver_id') or False

    step_id = fields.Many2one('invoice.approval.step', string='Approval step', default=_get_default_step_from_context)
    approver_id = fields.Many2one('invoice.approver', string='Approver', ondelete='cascade', copy=False,
                                  default=_get_default_approver_from_context)
    approver_type = fields.Selection([('approver', 'Approver'), ('auditor', 'Auditor')], string='Approver type',
                                     related='approver_id.type', readonly=True)

    # Filters
    account_analytic_ids = fields.Many2many('account.analytic.account', string='Analytic account')
    account_ids = fields.Many2many('account.account', string='Accounts')
    supplier_filter = fields.Selection(
        [('any', 'Any'), ('matches', 'Matches'), ('does_not_match', 'Does not match')],
        string='Suppliers',
        default='any',
        required=True
    )
    supplier_ids = fields.Many2many('res.partner', string='Suppliers')
    supplier_identifiers = fields.Text(string='Additional supplier identifiers')
    requester_filter = fields.Selection(
        [('any', 'Any'), ('matches', 'Matches'), ('does_not_match', 'Does not match')],
        string='Requesters',
        default='any',
        required=True
    )  # Submitter filters
    requester_ids = fields.Many2many('hr.employee', string='Requesters')
    requester_identifiers = fields.Text(string='Additional requester identifiers')

    amount_filter = fields.Selection(
        [('any', 'Any'), ('over_or_equal_to', 'Over or equal to'), ('under', 'Under'), ('within', 'Within')],
        string='Amount',
        required=True,
        default='any'
    )
    amount_under = fields.Float()
    amount_over = fields.Float()

    analytic_account_display = fields.Html(string='Analytic account', compute='_compute_human_readable_condition_text',
                                           sanitize=False)
    account_display = fields.Html(string='Account', compute='_compute_human_readable_condition_text', sanitize=False)
    supplier_display = fields.Html(string='Supplier', compute='_compute_human_readable_condition_text', sanitize=False)
    requester_display = fields.Html(string='Submitter', compute='_compute_human_readable_condition_text',
                                    sanitize=False)
    amount_display = fields.Html(string='Amount', compute='_compute_human_readable_condition_text', sanitize=False)

    @api.multi
    @api.constrains('amount_filter', 'amount_under', 'amount_over')
    def _check_amounts(self):
        for condition in self.filtered(lambda c: c.amount_filter == 'within'):
            if tools.float_compare(condition.amount_under, condition.amount_over, precision_digits=2) > 0:
                raise exceptions.ValidationError(_('Amount to has to be more than amount from'))

    @api.multi
    def _invoice_matches_condition(self, invoice):
        """
        Checks the invoice if it matches all of the options for this condition

        Returns:
            object: Boolean - does the invoice match the condition
        """
        self.ensure_one()

        # Perform analytic account checks
        if self.account_analytic_ids:
            analytic_account_ids = self.account_analytic_ids.ids
            invoice_analytic_account_ids = invoice.mapped('invoice_line_ids.account_analytic_id').ids
            if not any(analytic_acc_id in invoice_analytic_account_ids for analytic_acc_id in analytic_account_ids):
                return False

        # Perform account checks
        if self.account_ids:
            account_ids = self.account_ids.ids
            invoice_account_id = invoice.account_id.id
            if invoice_account_id not in account_ids:
                return False

        # Check supplier filters
        if self.supplier_filter in ['matches', 'does_not_match']:
            supplier_ids = self.supplier_ids.ids
            supplier_identifiers = []
            if self.supplier_identifiers:
                # Try to get the identifiers by splitting by comma
                try:
                    supplier_identifiers = self.supplier_identifiers.lower().split(',')
                except:
                    pass

            invoice_supplier = invoice.partner_id

            # Check if the supplier matches
            supplier_matches = invoice_supplier.id in supplier_ids
            if not supplier_matches:
                supplier_name = invoice_supplier.name.lower()
                for supplier_identifier in supplier_identifiers:
                    if supplier_identifier in supplier_name or supplier_identifier.replace(' ', '') in supplier_name:
                        supplier_matches = True
                        break

            # Return False based on the required condition
            if self.supplier_filter == 'matches':
                if not supplier_matches:
                    return False
            elif self.supplier_filter == 'does_not_match':
                if supplier_matches:
                    return False

        # Check requester filters
        if self.requester_filter in ['matches', 'does_not_match']:
            requester_ids = self.requester_ids.ids
            requester_identifiers = []
            if self.requester_identifiers:
                # Try to get the identifiers by splitting by comma
                try:
                    requester_identifiers = self.requester_identifiers.lower().split(',')
                except:
                    pass

            requester_matches = False
            submitted_employee = invoice.submitted_employee_id
            invoice_requester = invoice.submitted.lower()

            # Check if the requester matches
            if submitted_employee:
                if submitted_employee.id in requester_ids:
                    requester_matches = True

            if not requester_matches:
                for requester_identifier in requester_identifiers:
                    if requester_identifier in invoice_requester or \
                            requester_identifier.replace(' ', '') in invoice_requester:
                        requester_matches = True
                        break

            # Return False based on the required condition
            if self.requester_filter == 'matches':
                if not requester_matches:
                    return False
            elif self.requester_filter == 'does_not_match':
                if requester_matches:
                    return False

        # Check amount filters
        if self.amount_filter != 'any':
            amount_total_company_signed = abs(invoice.amount_total_company_signed)
            if self.amount_filter == 'over_or_equal_to':
                if tools.float_compare(amount_total_company_signed, self.amount_over, precision_digits=2) < 0:
                    return False
            elif self.amount_filter == 'under':
                if tools.float_compare(amount_total_company_signed, self.amount_under, precision_digits=2) >= 0:
                    return False
            elif self.amount_filter == 'within':
                if tools.float_compare(amount_total_company_signed, self.amount_under, precision_digits=2) < 0 or \
                        tools.float_compare(amount_total_company_signed, self.amount_over, precision_digits=2) > 0:
                    return False

        return True

    @api.model
    def _strings_as_html_tags(self, strings):
        number_of_strings_to_show = 5
        html_tags_text = ', '.join(strings[:number_of_strings_to_show])
        number_of_other_strings = max(len(strings) - number_of_strings_to_show, 0)
        if number_of_other_strings > 0:
            html_tags_text += _(' +{} others').format(number_of_other_strings)
        return html_tags_text

    @api.multi
    def _compute_human_readable_condition_text(self):
        supplier_selection = dict(self._fields.get('supplier_filter', False)._description_selection(self.env))
        requester_selection = dict(self._fields.get('requester_filter', False)._description_selection(self.env))
        amount_selection = dict(self._fields.get('amount_filter', False)._description_selection(self.env))
        for rec in self:
            # Analytic account display
            if not rec.account_analytic_ids:
                rec.analytic_account_display = _('Any')
            else:
                rec.analytic_account_display = self._strings_as_html_tags(rec.account_analytic_ids.mapped('name'))

            # Account display
            if not rec.account_ids:
                rec.account_display = _('Any')
            else:
                rec.account_display = self._strings_as_html_tags(rec.account_ids.mapped('name'))

            # Supplier display
            supplier_display = supplier_selection.get(rec.supplier_filter) or ''
            if rec.supplier_filter != 'any':
                supplier_names = rec.supplier_ids.mapped('name')
                if rec.supplier_identifiers:
                    try:
                        supplier_names += self.supplier_identifiers.lower().split(',')
                    except:
                        pass
                supplier_display += ' ' + self._strings_as_html_tags(supplier_names)
            rec.supplier_display = supplier_display

            requester_display = requester_selection.get(rec.requester_filter) or ''
            if rec.requester_filter != 'any':
                requester_names = rec.requester_ids.mapped('name')
                if rec.requester_identifiers:
                    try:
                        requester_names += self.requester_identifiers.lower().split(',')
                    except:
                        pass
                requester_display += ' ' + self._strings_as_html_tags(requester_names)
            rec.requester_display = requester_display

            # Amount display
            selection_string = amount_selection.get(rec.amount_filter) or ''
            if rec.amount_filter == 'any':
                amount_display = selection_string
            elif rec.amount_filter == 'over_or_equal_to':
                amount_display = selection_string + ' ' + str(rec.amount_over)
            elif rec.amount_filter == 'under':
                amount_display = selection_string + ' ' + str(rec.amount_under)
            else:
                amount_display = str(rec.amount_under)
                if tools.float_compare(rec.amount_under, rec.amount_over, precision_digits=2) != 0:
                    amount_display += '-' + str(rec.amount_over)
            rec.amount_display = amount_display


InvoiceApprovalCondition()
