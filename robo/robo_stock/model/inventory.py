# -*- coding: utf-8 -*-
from __future__ import division

import copy
import logging
from datetime import datetime

from dateutil.relativedelta import relativedelta
from psycopg2 import OperationalError, errorcodes

import odoo.addons.decimal_precision as dp
from odoo import models, fields, api, _, exceptions, tools
from odoo.addons.queue_job.job import job, identity_exact

_logger = logging.getLogger(__name__)


class StockInventory(models.Model):
    _name = 'stock.inventory'
    _inherit = ['stock.inventory', 'ir.attachment.drop']
    #TODO Override ir.attachment.drop _compute_attachment_drop_lock to lock file uploads with some condition

    accounting_date = fields.Date(track_visibility='onchange')
    total_value = fields.Monetary(track_visibility='onchange')
    currency_id = fields.Many2one(track_visibility='onchange')
    account_id = fields.Many2one(track_visibility='onchange')
    filter = fields.Selection(track_visibility='onchange')
    date = fields.Datetime(track_visibility='onchange')
    location_id = fields.Many2one(track_visibility='onchange')

    representation_inventory = fields.Boolean(compute='_representation_inventory')
    reason_line = fields.Many2one('stock.reason.line', string='Nurašymo priežastis', track_visibility='onchange')
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analitinė sąskaita',
                                          inverse='_set_analytic_inventory_line', track_visibility='onchange')
    accountant_validated = fields.Boolean(string='Validated by accountant', readonly=True, copy=False,
                                          track_visibility='onchange')
    accountant_validated_text = fields.Text(compute='_compute_accountant_validated_text')
    surplus = fields.Boolean(compute='_compute_surplus')

    # Consumption of goods for private needs fields
    invoice_id = fields.Many2one('account.invoice', string='Related invoice', copy=False)
    job_status = fields.Selection(
        selection=[
            ('none', 'None'),
            ('in_queue', 'Job in Queue'),
            ('progress', 'Job in Progress'),
            ('fail', 'Failed'),
        ],
        copy=False, readonly=True,
        default='none'
    )
    job_message = fields.Char(string='Job message')

    @api.one
    @api.depends('reason_line.representation_split')
    def _representation_inventory(self):
        self.representation_inventory = True if self.reason_line.representation_split else False

    def _compute_accountant_validated_text(self):
        accountant_validated_text = _('Patvirtinta buhalterio')
        for rec in self:
            rec.accountant_validated_text = accountant_validated_text

    @api.depends('reason_line')
    def _compute_surplus(self):
        reason_stock_surplus = self.env.ref('robo_stock.reason_line_9', False)
        if reason_stock_surplus:
            for rec in self:
                rec.surplus = rec.reason_line and rec.reason_line == reason_stock_surplus

    @api.multi
    def unlink(self):
        if self.env['stock.move'].sudo().search_count([('inventory_line_id', 'in', self.mapped('line_ids.id'))]):
            raise exceptions.UserError(
                _('You cannot delete an inventory act that as been previously confirmed'))
        return super(StockInventory, self).unlink()

    @api.multi
    def check_job_status(self, states):
        return any(rec.job_status in states for rec in self)

    @api.multi
    def check_job_in_queue(self):
        self.ensure_one()
        if self.job_status != 'in_queue':
            raise exceptions.UserError(_('%s: The job is not in queue ') % self.name)

    @api.multi
    def create_invoices(self):
        """
        Creates invoice for current stock.inventory record based
        on the related reason line setting.
        :return: None
        """
        # Get invoice defaults
        default_account = self.env.ref('l10n_lt.1_account_229')
        default_line_tax = self.env.ref('l10n_lt.1_account_tax_pvm29')
        default_partner = self.sudo().env.user.company_id.partner_id
        default_journal = self.env.ref('robo_stock.private_product_consumption_journal')

        # Get needed precisions
        price_precision = self.env['decimal.precision'].precision_get('Product Price')
        qty_precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        for rec in self.filtered(lambda x: x.reason_line.create_invoice):
            # Check base constraints
            if not rec.reason_line.create_invoice:
                raise exceptions.ValidationError(
                    _('You cannot create the invoice for stock inventory with selected reason line')
                )
            if not rec.state == 'done':
                raise exceptions.ValidationError(
                    _('You can only create invoice for done inventory records')
                )
            if rec.invoice_id:
                raise exceptions.ValidationError(_('Related stock inventory already has an invoice'))

            # Create the invoice based on the lines
            invoice_lines = []
            invoice_values = {
                'force_dates': True,
                'private_product_consumption': True,
                'price_include_selection': 'exc',
                'account_id': default_account.id,
                'journal_id': default_journal.id,
                'partner_id': default_partner.id,
                'invoice_line_ids': invoice_lines,
                'type': 'out_invoice',
                'date_invoice': rec.accounting_date,
            }
            for line in rec.line_ids:
                # Ensure that consumed quantity is less than zero
                if tools.float_compare(0.0, line.consumed_qty, precision_digits=2) < 1:
                    raise exceptions.ValidationError(_('Consumed quantity cannot be more than zero'))
                # Get account for the product
                product_account = line.product_id.get_product_income_account(return_default=True)

                # Round total price, quantity and calculate price unit
                total_price = tools.float_round(line.total_value, precision_digits=price_precision)
                # Skip the line if line value is zero
                if tools.float_is_zero(total_price, precision_digits=price_precision):
                    continue

                quantity = tools.float_round(abs(line.consumed_qty), precision_digits=qty_precision)
                # Quantity is already validated for non-zero
                price_unit = total_price / quantity  # P3:DivOK

                # Prepare values for the line
                line_vals = {
                    'name': line.product_id.name,
                    'product_id': line.product_id.id,
                    'quantity': abs(line.consumed_qty),
                    'price_unit': price_unit,
                    'account_id': product_account.id,
                    'invoice_line_tax_ids': [(6, 0, default_line_tax.ids)],
                }
                invoice_lines.append((0, 0, line_vals))

            # Do not create the invoice if there's no lines
            # (if all the lines have zero value)
            if not invoice_lines:
                continue

            # Create the invoice
            invoice = self.env['account.invoice'].create(invoice_values)
            # Assign created invoice to current record
            rec.write({'invoice_id': invoice.id})
            invoice.partner_data_force()
            # Confirm the invoice
            invoice.action_invoice_open()
            invoice.accountant_validated = True

    @api.multi
    def action_copy(self):
        self.ensure_one()
        res = self.copy()
        res.message_post(_('Copied from inventory act %s') % self.id)
        return {
            'name': _('Atsargų nurašymas'),
            'view_mode': 'form',
            'view_id': self.env.ref('robo_stock.robo_stock_inventory_form').id,
            'view_type': 'form',
            'res_model': 'stock.inventory',
            'res_id': res.id,
            'type': 'ir.actions.act_window',
            'context': dict(self._context),
            'flags': {'initial_mode': 'edit'},
        }

    @api.multi
    def _set_analytic_inventory_line(self):
        for inv in self:
            inv.line_ids.write({'account_analytic_id': inv.account_analytic_id.id})

    @api.onchange('reason_line')
    def _onchange_reason_line(self):
        self.exhausted = self.surplus
        self.account_id = self.reason_line.account_id

    @api.model
    def _selection_filter(self):
        """ Get the list of filter allowed according to the options checked
        in 'Settings\Warehouse'. """
        res_filter = [
            ('none', _('All products')),
            ('category', _('One product category')),
            ('product', _('One product only')),
            ('partial', _('Select products manually'))]

        if self.user_has_groups('stock.group_tracking_owner'):
            res_filter += [('owner', _('One owner only')), ('product_owner', _('One product for a specific owner'))]
        if self.user_has_groups('stock.group_production_lot'):
            res_filter.append(('lot', _('One Lot/Serial Number')))
        if self.user_has_groups('stock.group_tracking_lot'):
            res_filter.append(('pack', _('A Pack')))
        return res_filter

    @api.multi
    def reset_accounting_qty(self):
        if not self.env.user.has_group('robo_stock.group_show_accounting_qty'):
            raise exceptions.UserError(_('You do not have sufficient rights'))
        for line in self.mapped('line_ids'):
            line.accounting_product_qty = 0
            line.consumed_qty = -line.accounting_qty

    # @inventory_exceptions
    @api.multi
    def prepare_inventory(self):
        if self.env.user.is_accountant():
            super(StockInventory, self).prepare_inventory()
        else:
            try:
                super(StockInventory, self).prepare_inventory()
            except exceptions.UserError:
                raise exceptions.UserError(_(
                    'Atsiprašome, negalime paruošti koregavimo. Įsitikinkite, kad šiai lokacijai nėra vykdomi kiti koregavimai.'))
        self.check_existing_inventory_lines()

    @api.multi
    def btn_prepare_inventory(self):
        """ Create jobs for preparing stock, inventory """
        self.ensure_one()
        if self.state != 'draft':
            raise exceptions.UserError(_('The inventory is not in the right state for preparation'))
        if self.job_status not in ['none', 'fail']:
            raise exceptions.UserError(_('The job can not be enqueued'))
        self.with_delay(eta=5, channel='root.inventory', identity_key=identity_exact).prepare_inventory_job()
        self.write({'job_status': 'in_queue'})

    @job
    @api.multi
    def prepare_inventory_job(self):
        """ Prepare inventory """
        self.ensure_one()
        if self.check_job_status(['progress']):
            raise exceptions.UserError(_('%s: There is already a job in progress on this inventory act') % self.name)
        self.check_job_in_queue()
        try:
            self.write({'job_status': 'progress'})
            self.env.cr.commit()
            self.prepare_inventory()
        except Exception as e:
            serialization_issue = isinstance(e, OperationalError) and e.pgcode == errorcodes.SERIALIZATION_FAILURE
            if serialization_issue:
                # Handle serialization issue - rollback and reset job status
                self.env.cr.rollback()
                self.write({'job_status': 'none'})
                try:
                    self.btn_prepare_inventory()
                except Exception as e:
                    self.handle_inventory_prepare_exception(e)
            else:
                self.handle_inventory_prepare_exception(e)
        else:
            self.write({'job_status': 'none'})

    @api.multi
    def handle_inventory_prepare_exception(self, exception):
        is_odoo_exception = isinstance(exception, (
            exceptions.UserError, exceptions.ValidationError, exceptions.Warning
        ))
        if is_odoo_exception:
            err_msg = str(exception.args[0])
        else:
            _logger.info('Failed inventory act job: %s', tools.ustr(exception))
            err_msg = _('Inventory could not be prepared')
        self.env.cr.rollback()
        self.write({'job_status': 'fail', 'job_message': err_msg})

    @api.multi
    def btn_recalculate_theoretical_qty(self):
        """ Create a job to cancel stock, inventory adjustments that is in draft """
        self.ensure_one()
        if self.state == 'done':
            raise exceptions.UserError(_('You cannot recalculate theoretical quantity on a validated act'))
        if self.job_status not in ['none', 'fail']:
            raise exceptions.UserError(_('The job can not be enqueued'))
        self.with_delay(eta=5, channel='root.inventory', identity_key=identity_exact).recalculate_theoretical_qty_job()
        self.write({'job_status': 'in_queue'})

    @job
    @api.multi
    def recalculate_theoretical_qty_job(self):
        self.ensure_one()
        if self.check_job_status(['progress']):
            raise exceptions.UserError(_('%s: There is already a job in progress on this inventory act') % self.name)
        self.check_job_in_queue()
        try:
            self.write({'job_status': 'progress'})
            self.env.cr.commit()
            self.recalculate_theoretical_qty()
        except Exception as e:
            is_odoo_exception = isinstance(e, (
                exceptions.UserError, exceptions.ValidationError, exceptions.Warning
            ))
            if is_odoo_exception:
                err_msg = str(e.args[0])
            else:
                _logger.info('Failed inventory act job: %s', tools.ustr(e))
                err_msg = _('Theoretical quantity could not be recomputed')
            self.env.cr.rollback()
            self.write({'job_status': 'fail', 'job_message': err_msg})
        else:
            self.write({'job_status': 'none'})

    @api.multi
    def action_done(self):
        error_message = []
        if self.state != 'confirm':
            message = '{}:'.format(self.name)
            message += _('You cannot apply adjustments if the act is not confirmed yet')
            error_message.append(message)
            
        if self.env.user.company_id.sudo().stock_inventory_require_committee:
            for rec in self:
                if not rec.komisija:
                    message = '{}:'.format(rec.name)
                    message += _('You need to select a committee.')
                    error_message.append(message)

        if self.env.user.company_id.sudo().stock_inventory_require_reason_line:
            for rec in self:
                if not rec.reason_line:
                    message = '{}: '.format(rec.name)
                    message += _('You need to provide the reason for write-off.')
                    error_message.append(message)

        if error_message:
            raise exceptions.UserError('\n'.join(error_message))

        res = super(StockInventory, self).action_done()
        #Create invoices for the write-offs based on the reason line after base action_done
        self.create_invoices()
        return res

    @api.multi
    def button_action_done(self):
        """ Create a job to apply stock, inventory adjustments """
        self.ensure_one()

        if self.state != 'confirm':
            raise exceptions.UserError(_('You cannot validate an inventory act in the current state'))
        date = datetime.strptime(self.date, tools.DEFAULT_SERVER_DATETIME_FORMAT).\
            strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        view = self.env.ref('robo_stock.stock_inventory_adjustment_confirmation_view', raise_if_not_found=False)
        if not self.env.user.is_accountant() and self.accounting_date and date != self.accounting_date and view:
            message = _('The accounting date does not match inventory adjustment date.\n'
                        'Inventory adjustment records will be created for the specified accounting date - {}.\n')\
                .format(self.accounting_date)
            wiz = self.env['stock.inventory.adjustment.confirmation'].create({'inventory_id': self.id,
                                                                              'warning_message': message})
            return {
                'name': _('Apply adjustments?'),
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'stock.inventory.adjustment.confirmation',
                'views': [(view.id, 'form')],
                'view_id': view.id,
                'target': 'new',
                'res_id': wiz.id,
                'context': self.env.context,
            }
        if self.job_status not in ['none', 'fail']:
            raise exceptions.UserError(_('The job can not be enqueued'))
        self.with_delay(eta=5, channel='root.inventory', identity_key=identity_exact).action_done_job()
        self.write({'job_status': 'in_queue'})

    @job
    @api.multi
    def action_done_job(self):
        self.ensure_one()
        if self.check_job_status(['progress']):
            raise exceptions.UserError(_('%s: There is already a job in progress on this inventory act') % self.name)
        self.check_job_in_queue()
        try:
            self.write({'job_status': 'progress'})
            self.env.cr.commit()
            self.action_done()
        except Exception as e:
            is_odoo_exception = isinstance(e, (
                exceptions.UserError, exceptions.ValidationError, exceptions.Warning
            ))
            if is_odoo_exception:
                err_msg = str(e.args[0])
            else:
                _logger.info('Failed inventory act job: %s', tools.ustr(e))
                err_msg = _('An error occurred during validation of the inventory act')
            self.env.cr.rollback()
            self.write({'job_status': 'fail', 'job_message': err_msg})
        else:
            self.write({'job_status': 'none'})
        
    @api.multi
    def action_cancel_draft(self):
        if self.env.user.is_accountant():
            super(StockInventory, self).action_cancel_draft()
        else:
            try:
                super(StockInventory, self).action_cancel_draft()
            except exceptions.UserError:
                raise exceptions.UserError(_('Atsiprašome, negalime atstatyti šio koregavimo į juodraščio būseną.'))

    @api.multi
    def btn_cancel_draft_inventory(self):
        """ Create a job to cancel stock, inventory adjustments that is in draft """
        self.ensure_one()
        if self.state != 'confirm':
            raise exceptions.UserError(_('You cannot cancel the inventory in the current state'),)
        if self.job_status not in ['none', 'fail']:
            raise exceptions.UserError(_('The job can not be enqueued'))
        self.with_delay(eta=5, channel='root.inventory', identity_key=identity_exact).cancel_draft_inventory_job()
        self.write({'job_status': 'in_queue'})

    @job
    @api.multi
    def cancel_draft_inventory_job(self):
        self.ensure_one()
        if self.check_job_status(['progress']):
            raise exceptions.UserError(_('%s: There is already a job in progress on this inventory act') % self.name)
        self.check_job_in_queue()
        try:
            self.write({'job_status': 'progress'})
            self.env.cr.commit()
            self.action_cancel_draft()
        except Exception as e:
            is_odoo_exception = isinstance(e, (
                exceptions.UserError, exceptions.ValidationError, exceptions.Warning
            ))
            if is_odoo_exception:
                err_msg = str(e.args[0])
            else:
                _logger.info('Failed inventory act job: %s', tools.ustr(e))
                err_msg = _('An error occurred when cancelling the inventory')
            self.env.cr.rollback()
            self.write({'job_status': 'fail', 'job_message': err_msg})
        else:
            self.write({'job_status': 'none'})

    @api.multi
    def cancel_state_done(self):
        self.ensure_one()
        if not self.env.user.is_accountant() and self.accountant_validated:
            raise exceptions.UserError(_('Negalima atšaukti atsargų nurašymo, kurį patvirtino buhalteris!'))
        if self.env.user.is_accountant():
            super(StockInventory, self).cancel_state_done()
        else:
            try:
                super(StockInventory, self).cancel_state_done()
            except exceptions.UserError:
                raise exceptions.UserError(_('Atsiprašome, negalime atšaukti šio koregavimo.'))

        # If inventory has private consumption invoice,
        # make sure that it's canceled as well
        invoice = self.invoice_id
        if invoice:
            invoice.remove_outstanding_payments()
            invoice.action_invoice_cancel()
        self.unlink_vat_restore_account_move()

    @api.multi
    def btn_cancel_state_done(self):
        """ Create a job to cancel stock, inventory adjustments that has been done """
        self.ensure_one()
        if self.state != 'done':
            raise exceptions.UserError(_('You can only cancel a validated inventory act with this action'))
        if self.job_status not in ['none', 'fail']:
            raise exceptions.UserError(_('The job can not be enqueued'))
        self.with_delay(eta=5, channel='root.inventory', identity_key=identity_exact).cancel_state_done_job()
        self.write({'job_status': 'in_queue'})

    @job
    @api.multi
    def cancel_state_done_job(self):
        self.ensure_one()
        if self.check_job_status(['progress']):
            raise exceptions.UserError(_('%s: There is already a job in progress on this inventory act') % self.name)
        self.check_job_in_queue()
        try:
            self.write({'job_status': 'progress'})
            self.env.cr.commit()
            self.cancel_state_done()
        except Exception as e:
            is_odoo_exception = isinstance(e, (
                exceptions.UserError, exceptions.ValidationError, exceptions.Warning
            ))
            if is_odoo_exception:
                err_msg = str(e.args[0])
            else:
                _logger.info('Failed inventory act job: %s', tools.ustr(e))
                err_msg = _('An error occurred when cancelling the validated inventory act')
            self.env.cr.rollback()
            self.write({'job_status': 'fail', 'job_message': err_msg})
        else:
            self.write({'job_status': 'none'})

    @api.multi
    def action_check_for_duplicate_lines(self):
        self.ensure_one()
        StockInventoryLine = self.env['stock.inventory.line']
        duplicates = []
        warnings = str()
        for line in self.line_ids:
            product = line.product_id
            existing = StockInventoryLine.search([
                ('id', '!=', line.id),
                ('inventory_id', '=', line.inventory_id.id),
                ('product_id', '=', product.id),
                ('location_id', '=', line.location_id.id),
                ('partner_id', '=', line.partner_id.id),
                ('package_id', '=', line.package_id.id),
                ('prod_lot_id', '=', line.prod_lot_id.id),
                ('consumed_qty', '<>', 0.0),
            ])
            if existing and product.id not in duplicates:
                duplicates.append(product.id)
                warnings += _('[%s] %s\n') % (product.default_code or str(), product.name)

        if warnings:
            warning_msg = _('Kai kurių produktų informacija dubliuojasi:\n') + warnings
            raise exceptions.UserError(warning_msg)
        raise exceptions.UserError(_('Dublikatų nerasta.'))

    @api.multi
    def action_split_lack_surplus(self):
        self.ensure_one()
        if not self.env.user.has_group('robo_stock.group_show_accounting_qty'):
            raise exceptions.UserError(_('You do not have sufficient rights'))
        StockInventory = self.env['stock.inventory']
        StockInventoryLine = self.env['stock.inventory.line']

        reason = self.env.ref('robo_stock.reason_line_9', False)

        lines = StockInventoryLine.search([('inventory_id', '=', self.id)])
        lines_to_split = lines.filtered(lambda x: tools.float_compare(x.consumed_qty, 0.0, precision_digits=2) > 0 or
                                                  tools.float_compare(x.accounting_qty, abs(x.consumed_qty),
                                                                      precision_digits=2) < 0)
        if not lines_to_split:
            raise exceptions.UserError(_('No lines to split'))

        inventory = StockInventory.create({
            'location_id': self.location_id.id,
            'filter': 'partial',
            'name': self.name + ' - ' + _('Surplus'),
            'accounting_date': self.accounting_date,
            'reason_line': reason.id,
            'account_analytic_id': self.account_analytic_id.id if self.account_analytic_id else False
        })
        inventory._onchange_reason_line()

        for line in lines_to_split:
            split_surplus = tools.float_compare(line.consumed_qty, 0.0, precision_digits=2) > 0
            qty_to_split = line.consumed_qty if split_surplus else abs(line.accounting_qty + line.consumed_qty)
            line.with_context(skip_existing_check=True).copy(default={'inventory_id': inventory.id,
                                                                      'consumed_qty': qty_to_split})
            consumed_qty = line.consumed_qty
            consumed_qty += -qty_to_split if split_surplus else qty_to_split
            if tools.float_is_zero(consumed_qty, precision_digits=2):
                line.unlink()
            else:
                line.write({
                    'consumed_qty': consumed_qty
                })

        return {
            'name': _('Inventory adjustment'),
            'view_mode': 'form',
            'view_id': self.env.ref('robo_stock.robo_stock_inventory_form').id,
            'view_type': 'form',
            'res_model': 'stock.inventory',
            'res_id': inventory.id,
            'type': 'ir.actions.act_window',
            'context': dict(self._context),
            'flags': {'initial_mode': 'edit'},
        }

    @api.multi
    def action_recalculate_accounting_qty(self):
        """
        Manually recompute accounting qty for each line.
        :return: None
        """
        if self.state not in ['draft', 'confirm']:
            raise exceptions.UserError(_('You cannot recalculate the accounting quantity in the current state'))
        if not self.env.user.has_group('robo_stock.group_show_accounting_qty'):
            raise exceptions.UserError(_('You do not have sufficient rights'))
        self.mapped('line_ids')._compute_accounting_qty()

    @api.multi
    def btn_action_recalculate_accounting_qty(self):
        """ Create a job to recalculate accounting Qty """
        self.ensure_one()
        if self.state not in ['draft', 'confirm']:
            raise exceptions.UserError(_('You cannot recalculate the accounting quantity in the current state'))
        if self.job_status not in ['none', 'fail']:
            raise exceptions.UserError(_('The job can not be enqueued'))
        self.with_delay(eta=5, channel='root.inventory', identity_key=identity_exact).action_recalculate_accounting_qty_job()
        self.write({'job_status': 'in_queue'})

    @job
    @api.multi
    def action_recalculate_accounting_qty_job(self):
        self.ensure_one()
        if self.check_job_status(['progress']):
            raise exceptions.UserError(_('%s: There is already a job in progress on this inventory act'))
        self.check_job_in_queue()
        try:
            self.write({'job_status': 'progress'})
            self.env.cr.commit()
            self.action_recalculate_accounting_qty()
        except Exception as e:
            is_odoo_exception = isinstance(e, (
                exceptions.UserError, exceptions.ValidationError, exceptions.Warning
            ))
            if is_odoo_exception:
                err_msg = str(e.args[0])
            else:
                _logger.info('Failed inventory act job: %s', tools.ustr(e))
                err_msg = _('An error occurred when recalculating accounting quantity')
            self.env.cr.rollback()
            self.write({'job_status': 'fail', 'job_message': err_msg})
        else:
            self.write({'job_status': 'none'})

    @api.multi
    def action_open_inventory_import_wizard(self):
        self.ensure_one()
        if not self.env.user.has_group('robo_stock.group_show_accounting_qty'):
            raise exceptions.UserError(_('You do not have sufficient rights'))
        if self.check_job_status(['in_queue', 'progress']):
            raise exceptions.UserError(_('There is already a job in progress on this inventory act'))
        if self.state not in ['draft', 'confirm']:
            raise exceptions.UserError(_('You cannot import in the current state'))
        wizard = self.env['stock.inventory.import'].create({
            'inventory_id': self.id
        })

        return {
            'name': _('Stock inventory import'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.inventory.import',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
            'res_id': wizard.id,
            'view_id': self.env.ref('robo_stock.stock_inventory_import_wizard').id,
        }

    @api.multi
    def print_report(self):
        return self.env['report'].get_action(self, 'nurasymo_aktas.report_nurasymo_aktas_templ')

    @api.multi
    def post_inventory(self):
        res = super(StockInventory, self).post_inventory()
        if self.env.user.sudo().company_id.restore_vat_in_inventory_write_off:
            self.create_vat_restore_account_move()
        return res

    @api.multi
    def mark_validated(self):
        if self.env.user.is_accountant():
            self.write({
                'accountant_validated': True
            })

    @api.multi
    def mark_invalidated(self):
        if self.env.user.is_accountant():
            self.write({
                'accountant_validated': False
            })

    @api.model
    def create_stock_inventory_validation_actions(self):
        action = self.env.ref('robo_stock.stock_inventory_mark_validated_server_action', raise_if_not_found=False)
        if action:
            action.create_action()
        action = self.env.ref('robo_stock.stock_inventory_mark_invalidated_server_action', raise_if_not_found=False)
        if action:
            action.create_action()

    @api.multi
    def create_vat_restore_account_move(self):
        AccountMove = self.env['account.move']
        AccountMoveLine = self.env['account.move.line']
        journal_id = self.env.user.sudo().company_id.vat_journal_id.id
        tax = self.env['account.tax'].search([('code', '=', 'PVM1'), ('nondeductible', '=', False),
                                              ('type_tax_use', '=', 'purchase'),
                                              ('price_include', '=', False)], limit=1)
        vmi_partner_id = self.env['res.partner'].search([('kodas', '=', '188659752')], limit=1).id
        default_non_deductible_acc_id = self.env['account.account'].search([('code', '=', '652')], limit=1).id

        for rec in self.filtered(lambda x: x.reason_line.deductible_vat):
            if rec.reason_line.representation_split:
                representation_move_lines = AccountMoveLine.sudo().search([
                    ('inventory_id', '=', rec.id),
                    ('account_id', '=', rec.reason_line.representation_non_deductible_account_id.id)])
                total_value = abs(sum(x.debit - x.credit for x in representation_move_lines))
            else:
                total_value = abs(rec.total_value)

            vat_amount = total_value * tax.amount / 100.0
            move_line_base = {
                'name': _('INV:') + (rec.name or ''),
                'ref': rec.number,
                'journal_id': journal_id,
                'date': rec.accounting_date,
                'inventory_id': rec.id,
            }

            move_line_1 = move_line_base.copy()
            move_line_1.update({
                'account_id': rec.account_id.id or default_non_deductible_acc_id,
                'debit': vat_amount,
                'credit': 0.0,
                'analytic_account_id': rec.account_analytic_id.id or False,
            })

            move_line_2 = move_line_base.copy()
            move_line_2.update({
                'account_id': tax.account_id.id,
                'partner_id': vmi_partner_id,
                'debit': 0.0,
                'credit': vat_amount,
            })

            # Create the move and post
            move = AccountMove.sudo().create({
                'ref': rec.number,
                'date': rec.accounting_date,
                'journal_id': journal_id,
                'line_ids': [(0, 0, move_line_1), (0, 0, move_line_2)],
            })
            move.post()

    @api.multi
    def unlink_vat_restore_account_move(self):
        AccountMoveLine = self.env['account.move.line'].sudo()
        vat_journal_id = self.env.user.sudo().company_id.vat_journal_id.id
        vmi_partner_id = self.env['res.partner'].search([('kodas', '=', '188659752')], limit=1).id

        for rec in self.filtered(lambda x: x.reason_line.deductible_vat):
            move_line = AccountMoveLine.sudo().search([('journal_id', '=', vat_journal_id),
                                                       ('inventory_id', '=', rec.id),
                                                       ('partner_id', '=', vmi_partner_id)], limit=1)
            if move_line:
                move = move_line.move_id
                move.button_cancel()
                move.unlink()

    @api.multi
    def check_existing_inventory_lines(self):
        StockInventoryLine = self.env['stock.inventory.line']
        for rec in self:
            for line in rec.line_ids:
                existing = StockInventoryLine.search([
                    ('inventory_id', '!=', line.inventory_id.id),
                    ('product_id', '=', line.product_id.id),
                    ('inventory_id.state', '=', 'confirm'),
                    ('location_id', '=', line.location_id.id),
                    ('partner_id', '=', line.partner_id.id),
                    ('package_id', '=', line.package_id.id),
                    ('prod_lot_id', '=', line.prod_lot_id.id)])
                if existing:
                    raise exceptions.UserError(
                        _('Negali būti kelių vykdomų atsargų nurašymų su tuo pačiu produktu (%s), '
                          'lokacija (%s), pakuote, savininku ir partija. Patvirtinkite sutampantį atsargų nurašymo '
                          'aktą prieš ruošdami naująjį.') % (line.product_id.name, line.location_id.display_name))

    @api.multi
    def button_journal_entries(self):
        return {
            'name': _('Žurnalo elementai'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move.line',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': ['|', ('inventory_id', 'in', self.ids), ('ref', '=', self.number)],
        }

    @api.multi
    def write(self, vals):
        res = super(StockInventory, self).write(vals)
        if 'accounting_date' in vals:
            self.mapped('line_ids')._compute_accounting_qty()
        return res


StockInventory()


class AlignmentCommittee(models.Model):
    _inherit = 'alignment.committee'

    type = fields.Selection([('asset', 'Turto'), ('inventory', 'Atsargų')])
    state = fields.Selection([('valid', 'Patvirtinta'), ('invalid', 'Nepatvirtinta')])


AlignmentCommittee()


class AccountMoveLine(models.Model):

    _inherit = 'account.move.line'

    inventory_id = fields.Many2one('stock.inventory', string='Atsargų nurašymas', copy=False)


AccountMoveLine()


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _prepare_account_move_line(self, qty, cost, credit_account_id, debit_account_id):
        res = super(StockMove, self)._prepare_account_move_line(qty, cost, credit_account_id, debit_account_id)
        if not res:
            return []
        if self.inventory_id:
            for line in res:
                if len(line) == 3:
                    line[2]['inventory_id'] = self.inventory_id.id
        if self.inventory_line_id and self.inventory_line_id.account_analytic_id \
                and (not self.inventory_line_id.account_id or (self.inventory_line_id.account_id.code.startswith('6')
                     or self.inventory_line_id.account_id.code.startswith('5'))):
            for line in res:
                if len(line) == 3:
                    line[2]['analytic_account_id'] = self.inventory_line_id.account_analytic_id.id
        if self.inventory_id.representation_inventory:
            account_to_filter = self.inventory_id.reason_line.representation_deductible_account_id
            line_to_split = filter(lambda x: x[2]['account_id'] == account_to_filter.id, res)
            key = 'credit' if not tools.float_is_zero(line_to_split[0][2]['credit'], precision_digits=2) else 'debit'

            full_amount = line_to_split[0][2][key]
            amount_to_force = tools.float_round(full_amount / 2, precision_digits=2)
            # Overcome odd number division
            amt_first = amount_to_force
            amt_second = amount_to_force
            while tools.float_compare(full_amount, amt_first + amt_second, precision_digits=2) < 0:
                amt_first -= 0.01
            while tools.float_compare(full_amount, amt_first + amt_second, precision_digits=2) > 0:
                amt_first += 0.01

            line_to_split[0][2][key] = amt_first
            representation_line_non_deductible = copy.deepcopy(line_to_split)
            representation_line_non_deductible[0][2]['account_id'] = \
                self.inventory_id.reason_line.representation_non_deductible_account_id.id
            representation_line_non_deductible[0][2][key] = amt_second
            res.append(representation_line_non_deductible[0])
        return res

    @api.multi
    def _get_accounting_data_for_valuation(self):

        journal_id, acc_src, acc_dest, acc_valuation = super(StockMove, self)._get_accounting_data_for_valuation()

        if self.inventory_id.representation_inventory and not self.origin_returned_move_id:
            acc_dest = self.inventory_id.reason_line.representation_deductible_account_id.id
            # Force dummy account.account so we can filter and split the line afterwards
        elif self.inventory_id.representation_inventory and self.origin_returned_move_id:
            acc_src = self.inventory_id.reason_line.representation_deductible_account_id.id
            # Force dummy account.account so we can filter and split the line afterwards

        if self.inventory_id.surplus:
            surplus_account = self.product_id.stock_surplus_account_id
            if not surplus_account:
                category = self.product_id.categ_id
                while category.parent_id and not category.stock_surplus_account_categ_id:
                    category = category.parent_id
                surplus_account = category.stock_surplus_account_categ_id or \
                                  self.env.user.sudo().company_id.default_stock_surplus_account_id
            if not surplus_account:
                raise exceptions.UserError(
                    _('Nenustatyta atsargų pertekliaus sąskaita produktui %s') % self.product_id.name)
            acc_src = surplus_account.id

        return journal_id, acc_src, acc_dest, acc_valuation


StockMove()


class StockInventoryLine(models.Model):

    _inherit = 'stock.inventory.line'

    account_analytic_id = fields.Many2one('account.analytic.account', string='Analitinė sąskaita')
    accounting_qty = fields.Float('Accounting quantity', digits=dp.get_precision('Product Unit of Measure'),
                                  readonly=True)
    accounting_product_qty = fields.Float('Real accounting quantity', compute='_compute_accounting_product_qty',
                                          inverse='_set_accounting_product_qty',
                                          digits=dp.get_precision('Product Unit of Measure'))

    @api.model
    def create(self, values):
        res = super(StockInventoryLine, self).create(values)
        inventory = self.env['stock.inventory'].search([('id', '=', values['inventory_id'])], limit=1)
        if inventory.account_analytic_id:
            res['account_analytic_id'] = inventory.account_analytic_id
        res._compute_accounting_qty()
        return res

    @api.multi
    def write(self, vals):
        res = super(StockInventoryLine, self).write(vals)
        # Recompute the value of accounting quantity separately for each line according to values changed
        # The usual approach of a stored compute field recomputes all lines at once and slows it down
        accounting_quantity_related_values = ['location_id', 'product_id', 'product_name', 'package_id',
                                              'product_uom_id', 'prod_lot_id', 'partner_id']
        if any(v in vals for v in accounting_quantity_related_values):
            self._compute_accounting_qty()
        return res

    @api.multi
    def unlink(self):
        if self.env['stock.move'].sudo().search_count([('inventory_line_id', 'in', self.ids)]):
            raise exceptions.UserError(_('You cannot delete an inventory act that as been previously confirmed'))
        return super(StockInventoryLine, self).unlink()

    # Full override of the method from stock_extend
    # Calling super() passes empty record
    @api.onchange('consumed_qty')
    def onchange_consumed_qty(self):
        if self.consumed_qty and self.consumed_qty > 0 and not self.changed and not self.inventory_id.surplus:
            self.consumed_qty = -self.consumed_qty
            self.changed = True

    def _compute_accounting_qty(self):
        for rec in self:
            if not rec.product_id:
                rec.accounting_qty = 0
                continue
            stock_date_dt = datetime.strptime(rec.inventory_id.accounting_date,
                                              tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(hour=21)
            params = (rec.location_id.id, rec.product_id.id, stock_date_dt)
            self._cr.execute('''
                SELECT SUM(quantity) 
                FROM stock_history 
                WHERE location_id = %s AND product_id = %s AND date < %s
                ''', params)
            accounting_qty = self._cr.fetchone()[0] or 0.0
            if accounting_qty and rec.product_uom_id and rec.product_id.uom_id != rec.product_uom_id:
                accounting_qty = rec.product_id.uom_id._compute_quantity(accounting_qty, rec.product_uom_id)
            rec.accounting_qty = accounting_qty

    @api.depends('accounting_qty', 'consumed_qty')
    def _compute_accounting_product_qty(self):
        for rec in self:
            rec.accounting_product_qty = rec.accounting_qty + rec.consumed_qty

    def _set_accounting_product_qty(self):
        for rec in self:
            if tools.float_compare(rec.accounting_product_qty, 0.0, precision_digits=2) >= 0:
                rec.consumed_qty = rec.accounting_product_qty - rec.accounting_qty


StockInventoryLine()
