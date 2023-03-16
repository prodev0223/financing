# -*- coding: utf-8 -*-
from odoo import models, fields, tools, api, _, exceptions
from odoo.addons.sepa import api_bank_integrations as abi
from dateutil.relativedelta import relativedelta
from datetime import datetime
from odoo.tools import float_compare


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    sepa_instruction_id = fields.Char(readonly=True, copy=False, string='SEPA InstrID')
    exported_sepa = fields.Boolean(string='Eksportuotas SEPA', default=False, readonly=True, copy=False)
    exported_sepa_date = fields.Date(string='Eksporto į SEPA data', copy=False)

    # HTML alerts (one is used in form view, another one in tree view)
    bank_export_state_alert_html = fields.Html(compute='_compute_bank_export_state_alert_html')
    bank_export_state_html = fields.Text(compute='_compute_bank_export_state_html')

    # Bank export data fields
    bank_export_job_ids = fields.Many2many('bank.export.job', string='Banko eksporto darbai', copy=False)
    has_export_job_ids = fields.Boolean(string='Turi susijusių eksportų', compute='_compute_has_export_job_data')
    bank_exports_to_sign = fields.Boolean(
        string='Turi eksportuotų transakcijų kurias galima pasirašyti', compute='_compute_has_export_job_data')

    bank_export_residual = fields.Float(compute='_compute_bank_export_residual')
    bank_export_state = fields.Selection(
        abi.BANK_EXPORT_STATES, string='Paskutinė eksportavimo būsena',
        store=True, compute='_compute_bank_export_state', copy=False
    )

    @api.multi
    @api.depends('bank_export_job_ids', 'bank_export_job_ids.available_for_signing')
    def _compute_has_export_job_data(self):
        """
        Compute //
        Check whether invoice has any related bank export jobs and
        whether any bank.export.jobs related export jobs are 'available_for_signing'
        (has_export_job_ids used as a separate boolean, so it behaves nicely in form view)
        :return: None
        """
        for rec in self:
            rec.has_export_job_ids = bool(rec.bank_export_job_ids)
            rec.bank_exports_to_sign = any(x.available_for_signing for x in rec.bank_export_job_ids)

    @api.multi
    @api.depends('bank_export_job_ids.export_state')
    def _compute_bank_export_state(self):
        """
        Compute //
        Compute latest bank export state based on
        related bank_export_job_ids records
        :return: None
        """
        for rec in self:
            bank_export_state = 'no_action'
            live_exports = rec.bank_export_job_ids.filtered(lambda x: not x.xml_file_download)
            if live_exports:
                latest_export = live_exports.sorted(key=lambda c: c.id, reverse=True)[0]
                bank_export_state = latest_export.export_state
            rec.bank_export_state = bank_export_state

    @api.multi
    @api.depends('bank_export_job_ids', 'amount_residual', 'amount_residual_currency', 'currency_id')
    def _compute_bank_export_residual(self):
        """
        Compute //
        Compute latest bank export residual and based on
        related bank_export_job_ids records
        :return: None
        """
        for rec in self:
            # Determine which residual value should be used based on whether account move line
            # has res.currency record associated with it or not
            value_to_use = abs(rec.amount_residual_currency if rec.currency_id else rec.amount_residual)
            live_exports = rec.bank_export_job_ids.filtered(lambda x: not x.xml_file_download)
            if live_exports:
                # Get the residual from latest successful export
                latest_successful_exports = live_exports.filtered(
                    lambda x: x.export_state in abi.ACCEPTED_STATES).sorted(key=lambda c: c.id, reverse=True)
                if latest_successful_exports and tools.float_compare(
                        value_to_use, latest_successful_exports[0].post_export_residual, precision_digits=2) > 0:
                    value_to_use = latest_successful_exports[0].post_export_residual
            rec.bank_export_residual = value_to_use

    @api.multi
    @api.depends('bank_export_state', 'exported_sepa', 'exported_sepa_date')
    def _compute_bank_export_state_alert_html(self):
        """
        Compute //
        Compose html for exported bank state alert box
        :return: None
        """
        for rec in self:
            rec.bank_export_state_alert_html = self.env['api.bank.integrations'].get_bank_export_state_alert_html_data(
                state=rec.bank_export_state,
                extra_data={
                    'exported_sepa_date': rec.exported_sepa_date,
                    'exported_sepa': rec.exported_sepa
                }
            )

    @api.multi
    @api.depends('bank_export_state', 'exported_sepa')
    def _compute_bank_export_state_html(self):
        """
        Compute //
        Composes HTML element (button) of the bank export state
        for the specific account.invoice record (displayed in the tree view)
        :return: None
        """
        # Loop through records and compose HTML of the button
        # that is displayed in the tree view (title, color, image)
        for rec in self:
            rec.bank_export_state_html = self.env['api.bank.integrations'].get_bank_export_state_html_data(
                model='account.move.line',
                state=rec.bank_export_state,
                extra_data={
                    'exported_sepa': rec.exported_sepa,
                }
            )

    @api.model
    def call_multiple_invoice_export_wizard(self):
        """
        Action that validates passed account move lines
        and calls the wizard to export them to bank
        :return: JS action (dict)
        """
        ctx = self._context.copy()

        # AMLs that can be paid are either - without currency containing residual amount that is negative,
        # or with currency and containing amount residual currency that is negative
        aml_to_pay = self.filtered(
            lambda l: (not l.currency_id and float_compare(l.amount_residual, 0.0, precision_rounding=0.01) < 0) or
            l.currency_id and float_compare(l.amount_residual_currency, 0.0, precision_rounding=0.01) < 0
        )
        # If there are no AMLs to pay (and forced context does not exit), raise an error
        if not aml_to_pay and not self._context.get('form_gpm_payments_for_holidays', []):
            raise exceptions.UserError(_('Nėra eilučių, kurias būtų galima apmokėti.'))

        # Update the context and create the wizard
        ctx.update({'aml_ids': aml_to_pay.ids, 'download': self._context.get('allow_download', True)})
        wizard = self.env['account.invoice.export.wizard'].with_context(ctx).create({})

        # Return final action
        return {
            'name': _('Apmokėti sąskaitas banke'),
            'context': ctx,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.invoice.export.wizard',
            'res_id': wizard.id,
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.model
    def create_account_move_line_bank_action(self):
        """
        Create tree action for multi record-set
        """
        action = self.env.ref('mokejimu_eksportas.account_move_line_bank_statement_action')
        if action:
            action.create_action()

    # Reconciliation methods ------------------------------------------------------------------------------------------

    @api.multi
    def get_best_matching_lines_by_name(self, name):
        """
        Check if passed name matches exactly one move line,
        if it does, return the specific line
        :param name: name to match against (str)
        :return: record-set/None
        """
        # Param that indicates the length of the split name
        # to be considered valid for matching. Split parts
        # less than 5 characters are ignored
        name_split_len = 5
        move_lines = self.env['account.move.line']
        if self:
            # Try to replace common separators with empty string
            ref_name = name or str()
            for ch in ['*', '_', '.', ';', ':', ',']:
                if ch in ref_name:
                    ref_name = ref_name.replace(ch, ' ')
            # Split the result
            potential_references = [ref for ref in ref_name.split() if ref and len(ref) > name_split_len]
            # Loop through references and gather move lines
            for reference in potential_references:
                # Check against display name and name
                move_line = self.filtered(lambda x: reference in x.display_name)
                if len(move_line) == 1:
                    move_lines |= move_line
                else:
                    move_line = self.filtered(lambda x: reference in x.name)
                    if len(move_line) == 1:
                        move_lines |= move_line
        return move_lines

    @api.multi
    def get_best_matching_lines_by_amount(self, move_lines, amount):
        """
        Filters out best matching account move lines based on passed amount.
        Possibility tree is build with different combinations of
        account move lines that are filtered based on earliest dates
        and least amount of partial reconciliations. Note that
        account move lines that are passed should be already filtered by
        other criteria besides amount (partner, etc..)
        :param move_lines: account.move.line (recordset)
        :param amount: amount (float)
        :return: account.move.line (recordset)
        """
        matched_lines = self.env['account.move.line']
        # 1st naive check - If we get exactly one line that matches
        # the amount, return it without any further checks.
        aml_filtered = move_lines.filtered(
            lambda x: not tools.float_compare(amount, x.amount_residual, precision_digits=2))
        if aml_filtered and len(aml_filtered) == 1:
            return aml_filtered

        if move_lines:
            p_tree = ProbabilityTree(abs(amount))
            # Build tree, condition -> zero amount
            dates = move_lines.mapped('date_maturity')
            dates = sorted(set(dates), key=dates.index)
            level_overflow = found = False
            for date in dates:
                level = []
                corresponding = move_lines.filtered(lambda x: x.date_maturity == date)
                skip_ids = self.env['account.move.line']
                if p_tree.depth_level_overflow():
                    level_overflow = True
                    break
                latest_level = p_tree.get_latest_level()
                # Build leaves on top
                for branch in latest_level:
                    branch_total = branch.get_branch_balance()
                    res, found = self.probability_tree_iterations(branch_total, corresponding, p_tree, parent=branch)
                    level += res
                    if found or len(level) > p_tree.level_threshold:
                        break
                if found:
                    p_tree.add_level(level)
                    aml_ids = p_tree.get_zero_branch().get_branch_aml_ids()
                    return self.env['account.move.line'].browse(aml_ids)
                # Always build new branches
                res, found = self.probability_tree_iterations(0.0, corresponding, p_tree)
                level += res
                p_tree.add_level(level)
                if found:
                    aml_ids = p_tree.get_zero_branch().get_branch_aml_ids()
                    return self.env['account.move.line'].browse(aml_ids)

            if level_overflow:
                # on overflow, start matching from the end of the list
                dates.reverse()
                p_tree = ProbabilityTree(abs(amount))
                for date in dates:
                    level = []
                    corresponding = move_lines.filtered(lambda x: x.date_maturity == date)
                    skip_ids = self.env['account.move.line']
                    if p_tree.depth_level_overflow():
                        break
                    latest_level = p_tree.get_latest_level()
                    # Build leaves on top
                    for branch in latest_level:
                        branch_total = branch.get_branch_balance()
                        res, found = self.probability_tree_iterations(
                            branch_total, corresponding, p_tree, parent=branch)
                        level += res
                        if found or len(level) > p_tree.level_threshold:
                            break
                    if found:
                        p_tree.add_level(level)
                        aml_ids = p_tree.get_zero_branch().get_branch_aml_ids()
                        return self.env['account.move.line'].browse(aml_ids)
                    # Always build new branches
                    res, found = self.probability_tree_iterations(0.0, corresponding, p_tree)
                    level += res
                    p_tree.add_level(level)
                    if found:
                        aml_ids = p_tree.get_zero_branch().get_branch_aml_ids()
                        return self.env['account.move.line'].browse(aml_ids)

            # Check whether partial reconciliation should be executed
            rec_mode = self.env.user.company_id.automatic_bank_reconciliation
            # If mode is 'partial_reconcile', no further amount checks are needed
            reconcile_partially = rec_mode == 'partial_reconcile'
            if not reconcile_partially:
                # If statement line amount is less than zero and partial reconciliation mode is payable,
                # or statement amount is more than zero and mode is receivable - reconcile the line partially
                if tools.float_compare(0.0, amount, precision_digits=2) > 0 \
                        and rec_mode == 'partial_reconcile_payable':
                    reconcile_partially = True
                elif tools.float_compare(amount, 0.0, precision_digits=2) > 0 \
                        and rec_mode == 'partial_reconcile_receivable':
                    reconcile_partially = True

            if reconcile_partially:
                # Build possibility list, condition -> earliest date
                leftovers = abs(amount)
                for date in dates:
                    if tools.float_compare(leftovers, 0.0, precision_digits=2) < 1:
                        break
                    possibility_list = []
                    corresponding = move_lines.filtered(lambda x: x.date_maturity == date)
                    skip_ids = self.env['account.move.line']
                    for a_line in corresponding:
                        batch_leftovers = leftovers - abs(a_line.amount_residual)
                        batch_leftovers_before = batch_leftovers
                        other_aml = corresponding.filtered(lambda x: x.id != a_line.id and x.id not in skip_ids.ids)
                        possibility_list.append({
                            'leftover_amount': batch_leftovers,
                            'aml_ids': a_line
                        })
                        if other_aml:
                            while other_aml:
                                remove_id = self.env['account.move.line']
                                whole_batch = True
                                batch = a_line
                                for a_line_s in other_aml:
                                    batch_leftovers -= abs(a_line_s.amount_residual)
                                    if tools.float_compare(batch_leftovers, 0.0, precision_digits=2) > 0:
                                        batch += a_line_s
                                    else:
                                        # overflow, remove first element of set, register batch, and loop again
                                        remove_id = other_aml[0]
                                        if a_line != batch:
                                            possibility_list.append({
                                                'leftover_amount': batch_leftovers_before,
                                                'payment_amount': amount,
                                                'date': date,
                                                'aml_ids': batch
                                            })
                                        whole_batch = False
                                        break
                                    batch_leftovers_before -= abs(a_line_s.amount_residual)
                                if whole_batch:
                                    possibility_list.append({
                                        'leftover_amount': batch_leftovers,
                                        'aml_ids': batch
                                    })
                                    break
                                other_aml -= remove_id
                                batch_leftovers = leftovers - abs(a_line.amount_residual)
                                batch_leftovers_before = leftovers - abs(a_line.amount_residual)
                        skip_ids += a_line  # we skip current element in future combinations
                    # We take combination with least amount of leftovers:
                    entry = min(possibility_list, key=lambda x: x['leftover_amount'])

                    # if we still have some unreconciled entries that overflow, we do partial reconcile:
                    if entry['leftover_amount'] and \
                            tools.float_compare(entry['leftover_amount'], 0.0, precision_digits=2) > 0 and \
                            corresponding.filtered(lambda x: x.id not in entry['aml_ids'].ids):
                        extra_entry = min(corresponding.filtered(
                            lambda x: x.id not in entry['aml_ids'].ids), key=lambda x: abs(x.amount_residual))
                        entry['aml_ids'] |= extra_entry
                        entry['leftover_amount'] -= abs(extra_entry.amount_residual)
                    leftovers = entry['leftover_amount']
                    matched_lines |= entry['aml_ids']
        return matched_lines

    @api.model
    def probability_tree_iterations(self, branch_total, move_lines, p_tree, parent=False):
        """
        Adds new leaves (new move lines with amount) to the probability tree branch,
        and checks whether the branch with new leave matches the amount that
        is going to be reconciled, if it does, depth level is returned,
        otherwise the process is repeated.
        :param branch_total: Current total amount of the branch
        :param move_lines: Passed move lines that are used to build the tree (recordset)
        :param p_tree: probability tree instance (object)
        :param parent: probability element instance (object)
        :return: depth level (int), Boolean field that indicates whether branch was found
        """
        level = []
        skip_ids = self.env['account.move.line']
        for a_line in move_lines:
            line_balance = abs(a_line.amount_residual)
            new_leave_balance = branch_total + line_balance
            # Added new leave to branch, amounts are equal, we found matching aml!
            if not tools.float_compare(new_leave_balance, p_tree.threshold_amount, precision_digits=2):
                level.append(ProbabilityElement(amount=line_balance, aml_ids=a_line.ids, parent_id=parent))
                return level, True
            # Added new leave to branch, branch amount is smaller than total, we continue
            elif tools.float_compare(new_leave_balance, p_tree.threshold_amount, precision_digits=2) < 0:
                level.append(ProbabilityElement(amount=line_balance, aml_ids=a_line.ids, parent_id=parent))
                # Add initial aml, then start to use combinations
                other_aml = move_lines.filtered(lambda x: x.id != a_line.id and x.id not in skip_ids.ids)
                if other_aml:
                    while other_aml:
                        remove_id = self.env['account.move.line']
                        whole_batch = True
                        combo_amount = new_leave_balance
                        batch_ids = a_line
                        for a_line_s in other_aml:
                            combo_amount += abs(a_line_s.amount_residual)
                            if not tools.float_compare(combo_amount, p_tree.threshold_amount, precision_digits=2):
                                batch_ids |= a_line_s
                                balance = sum(abs(x.amount_residual) for x in batch_ids)
                                level.append(ProbabilityElement(
                                    amount=balance, aml_ids=batch_ids.ids, parent_id=parent))
                                return level, True
                            elif tools.float_compare(combo_amount, p_tree.threshold_amount, precision_digits=2) < 0:
                                batch_ids |= a_line_s
                            else:
                                # overflow, remove first element of set, register batch, and loop again
                                remove_id = other_aml[0]
                                if batch_ids != a_line:
                                    balance = sum(abs(x.amount_residual) for x in batch_ids)
                                    level.append(
                                        ProbabilityElement(amount=balance, aml_ids=batch_ids.ids, parent_id=parent))
                                whole_batch = False
                                break
                        if whole_batch:
                            balance = sum(abs(x.amount_residual) for x in batch_ids)
                            level.append(ProbabilityElement(amount=balance, aml_ids=batch_ids.ids, parent_id=parent))
                            break
                        other_aml -= remove_id
                skip_ids |= a_line
            # Instant overflow, we continue with other lines
            elif tools.float_compare(new_leave_balance, p_tree.threshold_amount, precision_digits=2) > 0:
                continue
        return level, False

    @api.model
    def cron_automatic_reconciliation(self):
        """
        Cron job //
        Used to reconcile account.move.lines with bank statements and invoices
        :return: None
        """
        reconciliation_limit = 1000

        # Get the lock date and static threshold date, use the latest of the two
        lock_date = self.env.user.company_id.get_user_accounting_lock_date()
        threshold_date = (datetime.utcnow() - relativedelta(months=2)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        filter_date = max(lock_date, threshold_date)

        # Bank statement lines
        lines = self.env['account.bank.statement.line'].search([
            ('statement_id.sepa_imported', '=', True),
            ('date', '>=', filter_date),
            ('journal_entry_ids', '=', False),
        ], limit=reconciliation_limit)
        lines = lines.filtered(lambda x: not x.reconciled)
        lines.with_context(reconciliation_actions=True).auto_reconcile_with_accounting_entries()

        # Invoices
        invoices = self.env['account.invoice'].search(
            [('type', 'in', ['in_invoice', 'out_invoice']),
             ('state', '=', 'open'),
             ('skip_global_reconciliation', '=', False),
             ('date_invoice', '>=', filter_date),
             ], limit=reconciliation_limit)

        # Add extra filtering, because 'open' state leaf in search does not always filter correctly,
        # but don't remove it, because most of the entries are filtered, and it's quicker than .filtered method
        invoices = invoices.filtered(lambda x: not tools.float_is_zero(x.residual, precision_digits=2))
        invoices.with_context(reconciliation_actions=True).auto_reconcile_with_accounting_entries()


AccountMoveLine()


class ProbabilityElement:

    """
    Class used for automatic account move line reconciliation. Account move line combinations for each day are stored
    and linked to previous days. Structure is held in ProbabilityTree class.
    """

    def __init__(self, amount, aml_ids, parent_id=False):

        self.aml_ids = aml_ids
        self.parent_id = parent_id
        self.amount = amount

    def get_branch_balance(self):
        branch_balance = self.amount
        parent_id = self.parent_id
        while parent_id:
            branch_balance += parent_id.amount
            parent_id = parent_id.parent_id
        return branch_balance

    def get_branch_aml_ids(self):
        aml_ids = self.aml_ids
        parent_id = self.parent_id
        while parent_id:
            aml_ids += parent_id.aml_ids
            parent_id = parent_id.parent_id
        return aml_ids


class ProbabilityTree:

    """
    Class used for account move line tree forming, dict of possible account move line combinations are stored.
    """

    def __init__(self, threshold_amount):
        self.tree = {}
        self.depth = 0
        self.threshold_amount = threshold_amount
        self.level_threshold = 5000  # May be changed, find the most optimal numbers in the future
        self.depth_threshold = 50  # May be changed, find the most optimal numbers in the future

    def add_level(self, level):
        self.depth += 1
        self.tree[self.depth] = level

    def get_latest_level(self):
        if self.tree.get(self.depth):
            return self.tree.get(self.depth)
        return []

    def get_zero_branch(self):
        if self.tree.get(self.depth):
            latest_level = self.tree.get(self.depth)
            for branch in latest_level:
                if not tools.float_compare(branch.get_branch_balance(), self.threshold_amount, precision_digits=2):
                    return branch
        return False

    def depth_level_overflow(self):
        if self.depth > self.depth_threshold or len(self.get_latest_level()) > self.level_threshold:
            return True
        else:
            return False

