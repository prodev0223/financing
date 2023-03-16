# -*- coding: utf-8 -*-
from __future__ import division
from six import iteritems
from odoo import _, api, exceptions, fields, models, tools


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    state = fields.Selection([('draft', 'Juodraštis'),
                              ('proforma', 'Išankstinė'),
                              ('proforma2', 'Išankstinė'),
                              ('open', 'Laukiama mokėjimo'),
                              ('paid', 'Apmokėta'),
                              ('cancel', 'Atšaukta')], compute='get_state')
    product_uom_categ_id = fields.Many2one('product.uom.categ', related='product_id.uom_id.category_id', readonly=True)

    # Analytic change (single invoice line) wizard action -------------------------------------------------------------
    @api.multi
    def action_line_change_analytics(self):
        self.ensure_one()
        aml = self.get_corresponding_aml()
        wizard_lines_obj = self.env['invoice.analytic.wizard.line']
        vals = {
            'invoice_line_id': self.id,
            'old_analytic_id': self.account_analytic_id.id,
            'analytic_id': self.account_analytic_id.id,
            'name': self.name,
            'qty': self.quantity,
            'amount': self.price_subtotal,
            'currency_id': self.currency_id.id,
            'sequence': self.sequence,
            'analytic_line_ids': [(4, rec.id) for rec in aml.mapped('analytic_line_ids')]
        }
        wiz_id = wizard_lines_obj.create(vals)
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'invoice.analytic.wizard.line',
            'res_id': wiz_id.id,
            'view_id': self.env.ref('robo.line_analytic_wizard_line_form').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.multi
    def get_corresponding_aml(self):
        self.ensure_one()
        company_curr_id = self.sudo().env.user.company_id.currency_id
        invoice = self.invoice_id
        lines_to_change = self.env['account.move.line']
        if invoice.check_access_rights('write'):
            invoice.check_access_rule('write')
            account_move_lines = invoice.sudo().move_id.line_ids
            if invoice.expense_split:
                account_move_lines += self.invoice_id.sudo().mapped('gpm_move.line_ids')
        else:
            return lines_to_change
        line_amount = abs(self.price_subtotal_signed)
        line_amount_curr = abs(self.price_subtotal)
        filtered_template = account_move_lines.filtered(
            lambda r: r.account_id.id == self.account_id.id
                      and r.product_id.id == self.product_id.id
                      and r.quantity == self.quantity)

        if invoice.state in ['open', 'paid'] and not invoice.expense_split:
            # 1st Check / Analytics and amounts
            lines_to_change = filtered_template.filtered(
                lambda r: r.analytic_account_id.id == self.account_analytic_id.id
                          and (not tools.float_compare(r.credit, line_amount, precision_digits=2)
                               or not tools.float_compare(r.debit, line_amount, precision_digits=2)))

            # 2nd Check / Only amounts
            if not lines_to_change:
                lines_to_change = filtered_template.filtered(
                    lambda r: (not tools.float_compare(r.credit, line_amount, precision_digits=2)
                               or not tools.float_compare(r.debit, line_amount, precision_digits=2)))

            # 3rd Check / Check via amount currency
            if not lines_to_change and self.currency_id != company_curr_id:
                lines_to_change = filtered_template.filtered(
                    lambda r: not tools.float_compare(abs(r.amount_currency), abs(line_amount_curr),
                                                      precision_digits=2))

        if invoice.state in ['open', 'paid'] and invoice.expense_split:
            # P3:DivOK
            gpm_proc = invoice.company_id.with_context(date=invoice.date_invoice).gpm_du_unrelated / 100
            lines_to_change = filtered_template.filtered(
                lambda r: r.analytic_account_id.id == self.account_analytic_id.id
                          and (not tools.float_compare(r.credit, line_amount * gpm_proc, precision_digits=2)
                               or not tools.float_compare(r.debit, line_amount * gpm_proc, precision_digits=2)
                               or not tools.float_compare(r.credit, line_amount * (1 - gpm_proc), precision_digits=2)
                               or not tools.float_compare(r.debit, line_amount * (1 - gpm_proc), precision_digits=2))
            )
            if not lines_to_change:
                lines_to_change = filtered_template.filtered(
                    lambda r: not tools.float_compare(r.credit, line_amount * gpm_proc, precision_digits=2)
                              or not tools.float_compare(r.debit, line_amount * gpm_proc, precision_digits=2)
                              or not tools.float_compare(r.credit, line_amount * (1 - gpm_proc), precision_digits=2)
                              or not tools.float_compare(r.debit, line_amount * (1 - gpm_proc), precision_digits=2)
                )
        return lines_to_change

    @api.one
    @api.depends('invoice_id')
    def get_state(self):
        if self.invoice_id:
            self.state = self.invoice_id.state

    @api.multi
    def action_change_line_vals(self):
        self.ensure_one()

        change_lines_obj = self.env['invoice.change.line.wizard']
        vals = {
            'invoice_line_id': self.id,
            'product_id': self.product_id.id,
            'name': self.name,
            'account_id': self.account_id.id,
            'quantity': self.quantity,
            'uom_id': self.uom_id.id,
            'invoice_line_tax_ids': [(6, 0, self.invoice_line_tax_ids.ids)],
            'price_unit': self.price_unit,
            'deferred': self.deferred,
            'currency_id': self.currency_id.id,
            'discount': self.discount,
            'price_subtotal_make_force_step': True,
            'price_subtotal_save_force_value': self.amount_depends  # Force original amount depends
        }
        wiz_id = change_lines_obj.create(vals).id

        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'invoice.change.line.wizard',
            'res_id': wiz_id,
            'view_id': self.env.ref('robo.wizard_change_line_vals_form').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': {'inv_type': 'out' if self.invoice_id.type in ['out_invoice', 'out_refund'] else 'in'}
        }

    @api.multi
    @api.constrains('account_analytic_id')
    def constraint_analytic_type(self):
        for rec in self.filtered('account_analytic_id'):
            inv_type = rec.invoice_id.type
            analytic_type = rec.account_analytic_id.account_type
            if analytic_type == 'expense' and inv_type in ['out_invoice', 'out_refund']:
                raise exceptions.ValidationError(
                    _('Analitinė sąskaita %s yra pažymėta kaip kaštų centras, '
                      'negalite naudoti šios analitinės sąskaitos kliento sąskaitoje faktūroje.' %
                      rec.account_analytic_id.display_name))
            elif analytic_type == 'income' and inv_type in ['in_invoice', 'in_refund']:
                raise exceptions.ValidationError(
                    _('Analitinė sąskaita %s yra pažymėta kaip pajamų centras, '
                      'negalite naudoti šios analitinės sąskaitos tiekėjo sąskaitoje faktūroje.' %
                      rec.account_analytic_id.display_name))

    @api.onchange('account_analytic_id')
    def onchange_analytic_id(self):
        if self.account_analytic_id:
            inv_type = self.invoice_id.type
            analytic_type = self.account_analytic_id.account_type
            if analytic_type == 'expense' and inv_type in ['out_invoice', 'out_refund']:
                return {'warning': {'title': _('Įspėjimas'),
                                    'message': _('Analitinė sąskaita %s yra pažymėta kaip kaštų centras, '
                                                 'negalite naudoti šios analitinės sąskaitos '
                                                 'kliento sąskaitoje faktūroje.' %
                                                 self.account_analytic_id.display_name)}}
            elif analytic_type == 'income' and inv_type in ['in_invoice', 'in_refund']:
                return {'warning': {'title': _('Įspėjimas'),
                                    'message': _('Analitinė sąskaita %s yra pažymėta kaip pajamų centras, '
                                                 'negalite naudoti šios analitinės sąskaitos '
                                                 'tiekėjo sąskaitoje faktūroje.' %
                                                 self.account_analytic_id.display_name)}}

    @api.onchange('product_id')
    def _onchange_product_id(self):
        res = super(AccountInvoiceLine, self)._onchange_product_id()
        # Call the default get two times, one with sudo and one w/o.
        # Only set the account if both sudo and simple call fetch the same result
        sudo_analytic_default = self.get_default_analytic_account(with_sudo=True)
        analytic_default = self.get_default_analytic_account()
        self.account_analytic_id = analytic_default.analytic_id.id \
            if sudo_analytic_default == analytic_default else False

        if self.env.user.company_id.use_latest_product_price and self.invoice_id.type in ('out_invoice', 'out_refund'):
            if self.partner_id and self.product_id:
                recent_prices = self.env['product.price.history'].search([
                    ('product_id', '=', self.product_id.id)
                ]).sorted(lambda d: d.datetime, reverse=True)
                self.price_unit = recent_prices[0].cost if recent_prices else self.product_id.list_price
        return res

    @api.multi
    def get_default_analytic_account(self, with_sudo=False):
        """Return default analytic account for current invoice line"""
        self.ensure_one()
        # Sudo has to be applied from the inside of
        # the method, does not work with on-changes
        analytic_default = self.env['account.analytic.default']
        if with_sudo:
            analytic_default = analytic_default.sudo()

        analytic_default = analytic_default.account_get(
            product_id=self.product_id.id,
            partner_id=self.invoice_id.partner_id.id,
            date=self.invoice_id.date_invoice,
            user_id=self.invoice_id.user_id.id,
            account_id=self.account_id.id,
            journal_id=self.invoice_id.journal_id.id,
            invoice_type=self.invoice_id.type,
        )
        return analytic_default

    @api.multi
    def apply_default_analytics(self):
        """Applies default analytic account to invoice line if any"""
        # Do not apply analytics if base analytic group is not set on the user
        if not self.env.user.has_group('analytic.group_analytic_accounting'):
            return
        default_analytic_errors = str()
        for rec in self.filtered(lambda x: not x.account_analytic_id):
            # Get default analytic account with sudo
            sudo_analytic_default = rec.get_default_analytic_account(with_sudo=True)
            if sudo_analytic_default:
                # If default account exists for current line, fetch the same account without sudo and check
                # the access rules for the current user. If it crashes - append it to the error string
                analytic_account = self.env['account.analytic.account'].browse(sudo_analytic_default.analytic_id.id)
                try:
                    analytic_account.check_access_rule('read')
                except (exceptions.AccessError, exceptions.UserError):
                    default_analytic_errors += _('Line - "{}"\n').format(rec.name)
                else:
                    # Otherwise account is assigned to the line
                    rec.account_analytic_id = analytic_account.id

        # Check if there's any default analytic errors
        if default_analytic_errors:
            error_msg = _(
                'Failed to confirm the invoice - lines listed below have default analytic accounts that '
                'are set by the rules, however, your user does not have sufficient rights to access '
                'these accounts. Contact your manager in regards to user rights configuration or fill '
                'in all of the analytic account fields in the invoice lines. \n\n'
                ) + default_analytic_errors
            raise exceptions.ValidationError(error_msg)

    @api.multi
    def get_line_vals_to_post(self):
        res = {}
        for line in self:
            res[line.id] = {'account_analytic_id': line.account_analytic_id.id}
        return res

    @api.multi
    def write(self, vals):
        if 'account_analytic_id' in vals:
            prev_line_values = dict((m.id, m.get_line_vals_to_post()) for m in self)
        else:
            prev_line_values = {}
        res = super(AccountInvoiceLine, self).write(vals)
        if 'account_analytic_id' in vals:
            post_message = False
            message = '''<strong>Buvusios reikšmės:\n</strong>
                            <table border="2" width=100%%>
                                <tr>
                                    <td><b>Eilutė</b></td>
                                    <td><b>Analitinė Sąskaita</b></td>
                                </tr>'''
            for rec in self:
                if not prev_line_values.get(rec.id, {}).get(rec.id, {}).get('account_analytic_id', False):
                    continue
                post_message = True
                for prev_line_id, prev_line_vals in iteritems(prev_line_values.get(rec.id, {})):
                    new_line = rec.filtered(lambda r: r.id == prev_line_id)
                    if len(new_line) > 1:
                        continue
                    new_line = '''<tr>'''
                    new_line += '<td>%s</td>' % rec.name
                    new_line += '<td>%s</td>' % self.env['account.analytic.account'].browse(
                        prev_line_vals.get('account_analytic_id', False)).display_name
                    new_line += '''</tr>'''
                    message += new_line
            message += '</table>'
            if post_message:
                for rec in self.mapped('invoice_id'):
                    rec.message_post(body=message, subtype='robo.mt_robo_front_message', front_message=True)
        return res

    @api.model
    def invoice_line_to_aml_matcher(self, invoice_line, move_lines, used_lines):
        """
        Completely override the method (original in stock-extend)
        by adding 'forced_analytic_default' in the condition
        """
        return move_lines.filtered(
            lambda x: x.product_id.id == invoice_line.product_id.id
            and x.account_id.code.startswith('6')
            and not x.forced_analytic_default
            and x not in used_lines
        )
