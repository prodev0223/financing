# -*- coding: utf-8 -*-
from __future__ import division
from six import iteritems
from odoo import models, fields, _, api, tools, exceptions
from datetime import datetime
from dateutil.relativedelta import relativedelta


class InvoiceAnalyticWizardLine(models.TransientModel):
    """
    Analytic change wizard for single account.invoice.line
    Possible actions:
        - Change analytic accounts
        - Split invoice line into several lines (so multiple analytic accounts can be applied)
        - Split analytic lines by dates
        - Force specific dates to related analytic lines
    """
    _name = 'invoice.analytic.wizard.line'
    _order = 'sequence'

    def analytic_actions(self):
        """
        Determine what analytic actions should be shown to the user
        :return: list of possible actions
        """
        actions = [('change_accounts', 'Keisti analitines sąskaitas'),
                   ('split_invoice_line', 'Skaidyti sąskaitos eilutę')]
        if self.env.user.company_id.additional_analytic_actions:
            actions += [('split_analytic_lines', 'Skaidyti analitines eilutes'),
                        ('force_dates', 'Keisti analitines datas')]
        return actions

    def analytic_account_domain(self):
        """
        :return: Return domain for analytic accounts based on the invoice type
        """
        ail = self._context.get('active_id', False)
        invoice_id = self.env['account.invoice.line'].browse(ail).invoice_id if ail else self.env['account.invoice']
        if invoice_id:
            if invoice_id.type in ['in_invoice', 'in_refund']:
                return [('account_type', 'in', ['profit', 'expense'])]
            else:
                return [('account_type', 'in', ['profit', 'income'])]
        else:
            return []

    invoice_line_id = fields.Many2one('account.invoice.line', readonly=True)
    old_analytic_id = fields.Many2one('account.analytic.account', string='Keisti iš', readonly=True)
    analytic_id = fields.Many2one('account.analytic.account', string='Keisti į', readonly=False,
                                  domain=lambda self: self.analytic_account_domain())
    name = fields.Char(string='Aprašymas', readonly=True)
    qty = fields.Float(string='Kiekis', readonly=True)
    amount = fields.Monetary(string='Suma be PVM', currency_field='currency_id', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    sequence = fields.Integer(readonly=True)

    default_action = fields.Selection('analytic_actions', string='Veiksmas', default='change_accounts')
    analytic_line_ids = fields.Many2many(
        'account.analytic.line', string='Analitinės eilutės', inverse='_set_analytic_line_ids')
    deferred_period = fields.Selection([('1', '1 mėnuo'),
                                        ('2', '2 mėnesiai'),
                                        ('3', '3 mėnesiai'),
                                        ('4', '4 mėnesiai'),
                                        ('5', '5 mėnesiai'),
                                        ('6', '6 mėnesiai'),
                                        ('7', '7 mėnesiai'),
                                        ('8', '8 mėnesiai'),
                                        ('9', '9 mėnesiai'),
                                        ('10', '10 mėnesių'),
                                        ('11', '11 mėnesių'),
                                        ('12', '12 mėnesių'),
                                        ('13', '13 mėnesių'),
                                        ('14', '14 mėnesių'),
                                        ('15', '15 mėnesių'),
                                        ('16', '16 mėnesių'),
                                        ('17', '17 mėnesių'),
                                        ('18', '18 mėnesių'),
                                        ('19', '19 mėnesių'),
                                        ('20', '20 mėnesių'),
                                        ('21', '21 mėnuo'),
                                        ('22', '22 mėnesiai'),
                                        ('23', '23 mėnesiai'),
                                        ('24', '24 mėnesiai'),
                                        ], string='Išskaidymo periodas')

    line_amount = fields.Float(string='Eilutės suma', compute='_line_amount')
    left_line_amount = fields.Float(string='Likusi eilutės suma', compute='_left_line_amount')
    line_split_ids = fields.Many2many('invoice.line.split.parts', string='Išskaidytos eilutės dalys')
    wizard_analytic_line_ids = fields.One2many(
        'invoice.analytic.wizard.line.account.analytic.line', 'wizard_id')

    split_part_amount = fields.Float(string='Suma')
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analitinė sąskaita',
                                          ondelete='cascade', domain=lambda self: self.analytic_account_domain())
    split_line_quantity_warning = fields.Boolean(compute='_split_line_quantity_warning')
    save_analytic_rule = fields.Selection([('true', 'Taip'),
                                           ('false', 'Ne')], string='Įsiminti analitinę taisyklę',
                                          default='false', required=True)
    analytic_rule_save_type = fields.Selection([('everyone', 'Visiems'), ('user_only', 'Tik man')],
                                               string='Analitinė taisyklė įsimenama', default='everyone')

    locked_analytic_period = fields.Boolean(compute='_compute_locked_analytic_period')
    locked_analytic_period_message = fields.Text(compute='_compute_locked_analytic_period')
    has_picking = fields.Boolean(compute='_compute_has_picking')

    @api.multi
    @api.depends('invoice_line_id.invoice_id')
    def _compute_has_picking(self):
        """Checks whether related invoice has pickings"""
        for rec in self.filtered(lambda i: i.invoice_line_id.invoice_id):
            pickings = rec.invoice_line_id.invoice_id.get_related_pickings()
            if pickings:
                rec.has_picking = True

    @api.multi
    def _set_analytic_line_ids(self):
        """
        Inverse //
        Create analytic wizard lines based
        on account invoice line analytic lines.
        :return: None
        """
        for rec in self:
            for line in self.analytic_line_ids:
                self.env['invoice.analytic.wizard.line.account.analytic.line'].create({
                    'wizard_id': rec.id,
                    'analytic_line_id': line.id,
                    'account_id': line.general_account_id.id,
                    'date': line.date,
                    # TODO: only users with group_robo_analytic_see_amounts can read the amount. Also move the wizard to robo_analytic module
                    # 'amount': line.amount,
                    'ref': line.ref
                })

    @api.multi
    def _compute_locked_analytic_period(self):
        """
        Compute //
        Check whether message about frozen/blocked analytics should be shown to the user
        :return: None
        """
        lock_type = 'freeze' if self.sudo().env.user.company_id.analytic_lock_type in ['freeze'] else 'block'
        for rec in self:
            invoice_id = rec.invoice_line_id.invoice_id
            if self.env['analytic.lock.dates.wizard'].check_locked_analytic(invoice_id.date_invoice, mode='return'):
                rec.locked_analytic_period = True
                if lock_type in ['freeze']:
                    rec.locked_analytic_period_message = _('Sąskaita faktūra yra periode kurio analitika yra '
                                                           'užšaldyta. Analitinės sąskaitos keitimas yra leidžiamas, '
                                                           'tačiau pakeitimai nepateks į verslo analitiką')
                else:
                    rec.locked_analytic_period_message = _(
                        'Sąskaita faktūra yra periode kurio analitika yra užrakinta. '
                        'Analitinės sąskaitos keitimas nėra leidžiamas')

    @api.one
    @api.depends('invoice_line_id.quantity')
    def _split_line_quantity_warning(self):
        """
        Compute //
        Computes whether to show a warning that line quantity will be lost
        :return: None
        """
        self.split_line_quantity_warning = True \
            if self.invoice_line_id.quantity and self.invoice_line_id.quantity > 1 else False

    @api.onchange('split_part_amount')
    def onchange_split_part_amount(self):
        if tools.float_is_zero(self.left_line_amount, precision_digits=2):
            raise exceptions.ValidationError(_('Negalite pridėti daugiau eilučių, skaidomos eilutės likutis yra nulis'))
        if self.split_part_amount:
            if tools.float_compare(self.split_part_amount, self.left_line_amount, precision_digits=2) > 0:
                self.split_part_amount = self.left_line_amount
            self.add_split_line()
            self.account_analytic_id = False
            self.split_part_amount = 0

    @api.multi
    def add_split_line(self):
        self.line_split_ids |= self.line_split_ids.new({'account_analytic_id': self.account_analytic_id.id,
                                                        'amount': self.split_part_amount})

    @api.one
    @api.depends('invoice_line_id.amount_depends')
    def _line_amount(self):
        self.line_amount = self.invoice_line_id.amount_depends

    @api.one
    @api.depends('line_amount', 'line_split_ids.amount')
    def _left_line_amount(self):
        used_amt = sum(x.amount for x in self.line_split_ids)
        self.left_line_amount = self.line_amount - used_amt if (self.line_amount - used_amt) > 0 else 0

    @api.multi
    def split_invoice_line(self):
        """
        Splits account.invoice line into multiple lines
        and forces passed analytic accounts.
        All of the newly split lines must contain analytic
        account and the total amount must match initial amount.
        :return: JS action (dict)
        """
        self.ensure_one()
        if not self.env.user.has_group('analytic.group_analytic_accounting'):
            return
        if not all(x.account_analytic_id for x in self.line_split_ids):
            raise exceptions.ValidationError(_('Bent viena iš išskaidytų eilučių neturi analitinės sąskaitos'))

        forced_tax_values = {}
        # Force base context to line and invoice
        invoice_line = self.with_context(skip_accountant_validated_check=True).invoice_line_id
        invoice = invoice_line.invoice_id

        invoice.check_access_rights('write')
        invoice.check_access_rule('write')
        invoice_line = invoice_line.sudo()
        invoice = invoice.sudo()

        if invoice.force_taxes:
            # If invoice has forced taxes, save it's initial values
            # and un-force the taxes until the splitting is done
            for t_line in invoice.tax_line_ids:
                forced_tax_values[t_line.tax_id] = t_line.amount
            invoice.force_taxes = False
            invoice.recompute_taxes_if_neccesary()

        field_to_use = 'amount_untaxed_signed' if invoice.price_include_selection == 'exc' else 'amount_total_signed'
        # Sum the total amount of split lines and current amount of invoice
        all_amt = sum(x.amount for x in self.line_split_ids)
        # Compare these amounts, if they do not match, raise an error
        if tools.float_compare(all_amt, self.line_amount, precision_digits=2):
            raise exceptions.ValidationError(
                _('Išskaidytų eilučių bendra suma %s nesutampa su pradine eilutės suma %s!') % (
                    all_amt, self.line_amount)
            )
        # Prepare message to post
        body = _('''<span>Išskaidyta eilutė "{} / {} {}"\n</span>
                    <table border="2" width=100%%>
                        <tr>
                            <td><b>Suma</b></td>
                            <td><b>Analitinė Sąskaita</b></td>
                        </tr>''').format(self.invoice_line_id.name, self.line_amount, invoice.currency_id.name)

        old_amt = invoice[field_to_use]
        # Loop through split lines, and create corresponding invoice lines
        for line in self.line_split_ids:
            new_line = invoice_line.copy({
                'price_unit': line.amount,
                'account_analytic_id': line.account_analytic_id.id,
                'quantity': 1.0,
                'invoice_id': invoice.id,
                'price_subtotal_make_force_step': False,
                'price_subtotal_save_force_value': 0.0
            })
            new_line._amount_depends()
            body += '''<tr><td>{} {}</td><td>{}</td></tr>'''.format(
                line.amount, invoice.currency_id.name, line.account_analytic_id.display_name)
        body += '</table>'

        # Cancel the invoice and save it's payments
        payments = invoice.action_invoice_cancel_draft_and_remove_outstanding()
        invoice_line.unlink()

        # Check whether there are any forced tax values
        if forced_tax_values:
            for tax, forced_amount in iteritems(forced_tax_values):
                invoice_tax_line = invoice.tax_line_ids.filtered(lambda x: x.tax_id.id == tax.id)
                if invoice_tax_line:
                    invoice_tax_line.write({
                        'amount': forced_amount,
                    })
            invoice.force_taxes = True

        # Reconfirm the invoice
        invoice.with_context(skip_attachments=True, skip_isaf_redeclaration=True).action_invoice_open()
        new_amt = invoice[field_to_use]

        # Check the amounts again, after confirmation
        if tools.float_compare(new_amt, old_amt, precision_digits=2):
            raise exceptions.ValidationError(
                _('Sisteminė klaida, kreipkitės į administraciją. Išskaidytų eilučių bendra suma %s '
                  'nesutampa su sąskaitos suma %s!') % (new_amt, old_amt))

        # Post the message to invoice as an user changing analytics if action was successful
        invoice.message_post(body=body, author_id=self.env.user.partner_id.id)

        # Reassign the payments and return reload action
        invoice.action_re_assign_outstanding(payments, raise_exception=False)
        return {'type': 'ir.actions.act_close_wizard_and_reload_view'}

    @api.multi
    def split_analytic_lines(self):
        self.ensure_one()
        if self.locked_analytic_period:
            raise exceptions.UserError(
                _('Negalite skaidyti analitinės eilutės, sąskaita faktūra yra periode kurio analitika yra užšaldyta.'))
        deferred_lines = self.analytic_line_ids.filtered(lambda c: c.deferred_line)
        orig_lines = self.analytic_line_ids.filtered(lambda c: not c.deferred_line)
        deferred_lines.unlink()
        for line in orig_lines:
            amount = (line.move_id.credit or 0.0) - (line.move_id.debit or 0.0)
            period = int(self.deferred_period)
            # P3:DivOK
            deferred_amount = tools.float_round(amount / period, precision_digits=2)
            relative_amount = period * deferred_amount
            leftovers = 0.0
            if tools.float_compare(relative_amount, amount, precision_digits=2) != 0:
                leftovers = amount - relative_amount
            line.amount = deferred_amount
            deferred_line = self.env['account.analytic.line']
            for x in range(1, period):
                date = (datetime.strptime(line.date, tools.DEFAULT_SERVER_DATE_FORMAT) +
                        relativedelta(months=x)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                deferred_line = line.copy(default={'date': date, 'amount': deferred_amount, 'deferred_line': True})
            if deferred_line:
                deferred_line.amount = deferred_amount + leftovers

        # Post the message to invoice if action was successful
        # State is the description of selection field value
        invoice = self.invoice_line_id.invoice_id
        period = str(dict(self._fields['deferred_period']._description_selection(self.env)).get(self.deferred_period))
        body = _('Išskaidytos eilutės "{} / {} {}" analitinės sumos. Periodas - {}').format(
            self.invoice_line_id.name, self.line_amount, invoice.currency_id.name, period)
        invoice.message_post(body=body)

    @api.multi
    def write_analytic_line_changes(self):
        """
        Write changes to the account.analytic.line object that is
        related to current invoice line. Changes are taken from
        invoice.analytic.wizard.line.account.analytic.line object
        and compared with the actual line. Some of the changes
        are logged to account.invoice chatter
        :return: None
        """
        self.ensure_one()
        invoice = self.invoice_line_id.invoice_id
        # No logging for account_id since simple users cannot change it
        body = _('''<span>Pakeistos eilutės "{} / {} {}" analitinės datos\n</span>
                    <table border="2" width=100%%>
                        <tr>
                            <td><b>Buvusi data</b></td>
                            <td><b>Pakeista data</b></td>
                        </tr>''').format(
            self.invoice_line_id.name, self.line_amount, invoice.currency_id.name)
        # Check whether analytic lines were changed
        change_body = str()

        for line in self.wizard_analytic_line_ids:
            new_values = {}
            # Check differences between wizard line, and actual line
            # collect them and compose table for message logging
            if line.date != line.analytic_line_id.date:
                change_body += '''<tr><td>{}</td><td>{}</td></tr>'''.format(line.analytic_line_id.date, line.date)
                new_values.update({'date': line.date})
            if line.account_id != line.analytic_line_id.general_account_id:
                new_values.update({'general_account_id': line.account_id.id})

            # Write changes to actual analytic line object, if any.
            if new_values:
                line.analytic_line_id.write(new_values)

        # If some values were actually changed,
        # post the message to the invoice
        if change_body:
            body = body + change_body + '''</table>'''
            invoice.message_post(body=body)

    @api.multi
    def change_analytics(self):
        self.ensure_one()
        # Every action that is executed from this method must keep the batch integrity
        self = self.with_context(ensure_analytic_batch_integrity=True)
        if not self.env.user.has_group('analytic.group_analytic_accounting'):
            return
        invoice = self.invoice_line_id.invoice_id
        if invoice.check_access_rights('write'):
            invoice.check_access_rule('write')
            account_move_lines = invoice.sudo().move_id.line_ids
            if invoice.expense_split:
                account_move_lines += invoice.sudo().mapped('gpm_move.line_ids')
        else:
            return

        # Getting corresponding AMLs should be done before writing new analytic account to invoice lines
        lines_to_change = self.invoice_line_id.get_corresponding_aml()

        self.invoice_line_id.write({
            'account_analytic_id': self.analytic_id.id
        })
        if self.sudo().invoice_line_id.deferred_line_id:
            aml = self.invoice_line_id.sudo().deferred_line_id.related_moves.mapped('line_ids')
            aml.write({'analytic_account_id': self.analytic_id.id})
            aml.create_analytic_lines()
        if invoice.fuel_expense_move_id:
            invoice_line_balance = self.invoice_line_id.price_subtotal
            aml = invoice.sudo().fuel_expense_move_id.line_ids.filtered(
                lambda l: l.account_id.code and l.account_id.code[0] in ['5', '6']
                          and tools.float_compare(l.balance, invoice_line_balance, precision_digits=2) == 0
            )
            # If more than one line found with same balance, need to filter the lines out even more
            if len(aml) > 1:
                # There might be no lines left after the second filter, so we save the first record just in case
                aml_first_record = aml[0]
                # Filter out by analytic_account_id
                aml = aml.filtered(lambda l: l.analytic_account_id.id == self.old_analytic_id.id)
                if not aml:
                    # If there are no more aml after the second filter, use the first saved record
                    aml = aml_first_record
                if len(aml) > 1:
                    # Otherwise, use the first out of the filtered lines
                    aml = aml[0]
            aml.write({'analytic_account_id': self.analytic_id.id})
            aml.create_analytic_lines()

        potential_taxes = self.env['account.invoice.tax']
        for tax_id in self.invoice_line_id.invoice_line_tax_ids:
            potential_taxes |= invoice.tax_line_ids.filtered(
                lambda x: tax_id.code == x.tax_id.code and x.tax_id.nondeductible)

        corresponding_taxes = self.env['account.invoice.tax']
        for tax_id in potential_taxes:
            ail = invoice.invoice_line_ids.filtered(
                lambda x: tax_id.tax_id.code in x.invoice_line_tax_ids.mapped('code'))
            if len(set(l.account_analytic_id.id if l.account_analytic_id else None for l in ail)) == 1:
                corresponding_taxes |= tax_id

        corresponding_taxes.write({'account_analytic_id': self.invoice_line_id.account_analytic_id.id})
        for tax_id in corresponding_taxes:
            aml = invoice.move_id.line_ids.filtered(lambda x: x.tax_line_id.id == tax_id.tax_id.id)
            aml.write({'analytic_account_id': self.invoice_line_id.account_analytic_id.id})
            aml.create_analytic_lines()

        if invoice.state in ['open', 'paid']:
            if lines_to_change:
                lines_to_change.mapped('analytic_line_ids').unlink()
                lines_to_change.write({'analytic_account_id': self.analytic_id.id})
                lines_to_change.create_analytic_lines()

                # Force analytics to related pickings move lines
                self.invoice_line_id.force_picking_aml_analytics_prep(check_constraint=True)
            elif not lines_to_change:
                raise exceptions.ValidationError(
                    _('Nepavyko pakeisti analitikos. Kreipkitės į Jus aptarnaujantį buhalterį.'))

        if self.save_analytic_rule == 'true' and self.invoice_line_id and self.analytic_id:
            analytic_id = self.analytic_id.id
            product_id = self.invoice_line_id.product_id.id
            category_id = self.invoice_line_id.product_id.categ_id.id
            partner_id = self.invoice_line_id.partner_id.id
            user_id = self.env.user.id if self.analytic_rule_save_type == 'user_only' else False
            rules = self.env['account.analytic.default'].search([
                ('product_id', '=', product_id),
                ('partner_id', '=', partner_id),
                ('product_category', '=', category_id),
            ])
            if not rules:
                self.env['account.analytic.default'].create({
                    'analytic_id': analytic_id,
                    'product_id': product_id,
                    'partner_id': partner_id,
                    'user_id': user_id,
                    'product_category': category_id,
                })
            else:
                rules[0].write({
                    'analytic_id': analytic_id,
                    'user_id': user_id
                })


InvoiceAnalyticWizardLine()
