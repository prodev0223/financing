# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, tools, exceptions
from datetime import datetime
from dateutil.relativedelta import relativedelta
from six import iteritems
from .. import nsoft_tools as nt


class NsoftReportMove(models.Model):
    """
    Model for nSoft report acts. Creates account.move record based on
    passed amounts.
    """
    _name = 'nsoft.report.move'
    _inherit = ['mail.thread']

    # External ID's
    ext_doc_id = fields.Integer(string='Išorinis ID')
    ext_doc_number = fields.Char(string='Akto numeris')
    ext_warehouse_id = fields.Integer(string='Sandėlio ID')

    # Dates
    report_date = fields.Date(string='Akto data')
    report_period_start = fields.Date(string='Akto pradžios data', compute='_compute_report_period_start')
    ext_create_date = fields.Datetime(string='Išorinė sukūrimo data')

    # Sums
    total_move_quantity = fields.Float(string='Bendras akto kiekis', compute='_compute_total_move_sums')
    total_move_amount = fields.Float(string='Bendra akto suma', compute='_compute_total_move_sums')

    # Relational fields
    nsoft_report_move_line_ids = fields.One2many(
        'nsoft.report.move.line', 'nsoft_report_move', string='Akto eilutės')
    report_type_id = fields.Many2one('nsoft.report.move.category', string='Akto tipo įrašas')

    # Others
    report_type = fields.Selection(
        [(2, 'Pardavimo savikainos'),
         (6, 'Inventorizacija'),
         (7, 'Nurašymai'),
         (9, 'Uždarymai')], string='Akto tipas', inverse='_set_report_type')

    state = fields.Selection([('imported', 'Įrašas importuotas'),
                              ('failed', 'Klaida kuriant aktą'),
                              ('partially_failed', 'Klaida kuriant dalį įrašų'),
                              ('created', 'Įrašas sukurtas'),
                              ('cancelled_dub', 'Dublikatas -- atšaukta')], string='Būsena',
                             default='imported', compute='_compute_state', store=True)

    potential_duplicate = fields.Boolean(string='Potencialus dublikatas', compute='_compute_potential_duplicate')

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    @api.depends('report_type', 'report_date', 'ext_warehouse_id')
    def _compute_potential_duplicate(self):
        """
        Compute //
        Checks if current report is potential duplicate -
        if other report of the same type, date and warehouse_id exists
        mark this as potential duplicate
        :return: None
        """
        for rec in self.filtered(lambda x: x.state != 'cancelled_dub'):
            dup_count = self.search_count([('report_type', '=', rec.report_type),
                                           ('report_date', '=', rec.report_date),
                                           ('ext_warehouse_id', '=', rec.ext_warehouse_id),
                                           ('ext_create_date', '!=', rec.ext_create_date),
                                           ('state', '!=', 'cancelled_dub'),
                                           ('id', '!=', rec.id)])

            rec.potential_duplicate = dup_count

    @api.multi
    @api.depends('report_date')
    def _compute_report_period_start(self):
        """
        Compute //
        Calculate date start of specific prime cost move.
        Date start is previous' entry date_end + 1 day
        :return: None
        """
        for rec in self:
            latest_rec = self.env['nsoft.report.move'].search(
                [('id', '<', rec.id), ('report_type', '=', rec.report_type)], order='id desc', limit=1)
            if latest_rec:
                date_st = (datetime.strptime(
                    latest_rec.report_date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(
                    days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                rec.report_period_start = date_st
            else:
                date_st = (datetime.strptime(
                    rec.report_date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(
                    day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                rec.report_period_start = date_st

    @api.multi
    @api.depends('nsoft_report_move_line_ids.line_quantity', 'nsoft_report_move_line_ids.line_amount')
    def _compute_total_move_sums(self):
        """
        Compute //
        Calculate total move amount and quantity
        based on line values
        :return: None
        """
        for rec in self:
            rec.total_move_quantity = sum(
                x.line_quantity for x in rec.nsoft_report_move_line_ids)
            rec.total_move_amount = sum(
                x.line_amount for x in rec.nsoft_report_move_line_ids)

    @api.multi
    @api.depends('nsoft_report_move_line_ids.state')
    def _compute_state(self):
        """
        Compute //
        Compute parent move state based on line states
        :return: None
        """
        for rec in self:
            if all(x.state == 'failed' for x in rec.nsoft_report_move_line_ids):
                # If set is empty it will be failed as well,
                # since all() returns True on empty set
                rec.state = 'failed'
            elif all(x.state == 'created' for x in rec.nsoft_report_move_line_ids):
                rec.state = 'created'
            elif all(x.state == 'cancelled_dub' for x in rec.nsoft_report_move_line_ids):
                rec.state = 'cancelled_dub'
            elif any(x.state == 'created' for x in rec.nsoft_report_move_line_ids):
                rec.state = 'partially_failed'
            else:
                rec.state = 'imported'

    @api.multi
    def _set_report_type(self):
        """
        Inverse //
        Assign related report move category type to the
        report move record
        :return: None
        """
        for rec in self:
            report_type = self.env['nsoft.report.move.category'].search([('report_type', '=', rec.report_type)])
            rec.report_type_id = report_type

            # If we receive spec doc type, we send a bug to support
            if rec.report_type == nt.SPEC_SUM_DOC_TYPE:
                body = 'Received closing report type with non-matching amounts. DB - {}'.format(self.env.cr.dbname)
                self.env['robo.bug'].sudo().create({
                    'user_id': self.env.user.id,
                    'error_message': body,
                })

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def button_move_creation_prep(self):
        """
        Method that calls move_creation_prep,
        called from the view. If used this way
        it ignores potential duplicate records
        :return: None
        """
        self.move_creation_prep(include_duplicates=True)

    @api.multi
    def button_remove_duplicates(self):
        """
        Method that deletes duplicate
        report account.move records
        :return: None
        """
        self.delete_duplicate_moves()

    @api.multi
    def move_creation_prep(self, include_duplicates=False):
        """
        Prepare report acts for account.move creation
        Validate them, and pass them to creation method
        :return: None
        """
        validated_moves = self.validator(include_duplicates)
        validated_moves.create_account_moves()

    @api.multi
    def validator(self, include_duplicates=False):
        """
        Validate nsoft.report.move records for constraints before passing them for account.move creation
        :return: filtered nsoft.report.move records
        """

        error_base = _('Nepavyko sukurti įrašo | ')
        filtered_records = self.env['nsoft.report.move']
        for rec in self.filtered(lambda x: x.state not in ['created', 'cancelled_dub'] and not tools.float_is_zero(
                x.total_move_amount, precision_digits=2) and x.report_type != nt.SPEC_SUM_DOC_TYPE):

            # Continue if duplicates are not included and current record
            # is potential duplicate.
            # Used continue instead of lambda in filtered because of better performance
            if not include_duplicates and rec.potential_duplicate:
                continue

            failed_lines = self.env['nsoft.report.move.line']
            error_report = str()
            if not rec.report_date:
                error_report += error_base + _('Nerasta akto data\n')
            if not rec.report_type_id.account_id:
                error_report += error_base + _('Susijęs akto tipas neturi buh. sąskaitos\n')
            if not rec.report_type_id.journal_id:
                error_report += error_base + _('Susijęs akto tipas neturi nustatyto žurnalo\n')
            for line in rec.nsoft_report_move_line_ids:
                line.recompute_fields()
                if not line.nsoft_product_category_id:
                    error_report += error_base + _('Eilutė | Nerasta susijusiu suminės apskaitos produktų kategorija\n')
                    failed_lines |= line
                if line.nsoft_product_category_id and line.nsoft_product_category_id.state in ['failed']:
                    error_report += error_base + _('Eilutė | Nesukonfigūruota suminės apskaitos produktų kategorija\n')
                    failed_lines |= line
            if error_report:
                rec.post_message(body=error_report, data_set=rec, state='failed', lines=failed_lines)
            else:
                filtered_records |= rec
        return filtered_records

    @api.multi
    def create_account_moves(self):
        """
        Create account move for each record, write states
        :return: None
        """
        for report in self:
            # Take only those lines that do not have created move already
            lines = report.nsoft_report_move_line_ids.filtered(lambda x: not x.move_id)
            grouped_data = {}

            for line in lines:
                # Loop through lines and build dict of dicts with following mapping
                # {category_id: lines, ...}
                category = line.nsoft_product_category_id
                grouped_data.setdefault(category, self.env['nsoft.report.move.line'])
                grouped_data[category] |= line

            for category, report_lines in iteritems(grouped_data):

                # Prepare move values
                move_name = '{} // {}'.format(report.ext_doc_number, category.name)
                debit_account = report.report_type_id.account_id.id
                credit_account = category.parent_product_id.property_account_expense_id.id

                # Prepare credit and debit lines
                credit_line = {
                    'name': move_name,
                    'account_id': credit_account,
                    'credit': 0.0,
                    'debit': 0.0
                }
                debit_line = credit_line.copy()
                debit_line['account_id'] = debit_account
                move_lines = []

                # Prepare amounts
                amount_to_use = sum(report_lines.mapped('line_amount')) * -1
                if tools.float_compare(amount_to_use, 0.0, precision_digits=2) > 0:
                    credit_line['credit'] = abs(amount_to_use)
                    debit_line['debit'] = abs(amount_to_use)
                else:
                    credit_line['debit'] = abs(amount_to_use)
                    debit_line['credit'] = abs(amount_to_use)

                # Create the account move
                move_lines.append((0, 0, credit_line))
                move_lines.append((0, 0, debit_line))
                move_vals = {
                    'name': move_name,
                    'line_ids': move_lines,
                    'journal_id': report.report_type_id.journal_id.id,
                    'date': report.report_date,
                }

                # Try to create the account move record
                try:
                    move_id = self.env['account.move'].create(move_vals)
                    move_id.post()
                    report_lines.write({'move_id': move_id.id, 'state': 'created'})
                except Exception as exc:
                    self.env.cr.rollback()
                    body = _('Nepavyko sukurti akto, sisteminė klaida %s') % str(exc.args[0])
                    self.post_message(lines=lines, data_set=report, state='failed', body=body)

                self.env.cr.commit()

    @api.multi
    def unlink_related_moves(self, forced_state='imported'):
        """
        Unlinks all of related account.move records
        and resets current report state to draft
        :param forced_state: indicates what state should
        be forced to report lines after unlinking
        :return: None
        """
        # Map only the lines, for later state writing
        report_lines = self.mapped('nsoft_report_move_line_ids')
        # Map the account.move records
        account_moves = report_lines.mapped('move_id')
        # These moves use accounts that are
        # not reconcilable, so they can be unlinked easily
        account_moves.button_cancel()
        account_moves.unlink()
        report_lines.write({'state': forced_state})

    @api.multi
    def delete_duplicate_moves(self):
        """
        If current record has potential duplicate,
        delete related account move entries and
        set the record to 'imported' state
        :return: None
        """
        for rec in self.filtered(lambda x: x.potential_duplicate and x.state in ['created', 'imported']):
            # Loop through account move records and write state to cancelled dub
            duplicates = self.search([('report_type', '=', rec.report_type),
                                      ('report_date', '=', rec.report_date),
                                      ('ext_warehouse_id', '=', rec.ext_warehouse_id)])

            # Filter out duplicates
            latest_date = max(duplicates.mapped('ext_create_date'))
            duplicates = duplicates.filtered(lambda x: x.ext_create_date < latest_date)

            # delete related moves
            duplicates.unlink_related_moves(forced_state='cancelled_dub')
            duplicates._compute_state()

    # Actions ---------------------------------------------------------------------------------------------------------

    @api.model
    def create_report_move_create_multi_func(self):
        """
        Tree view function. Create action for multi record.set
        :return: None
        """
        action = self.env.ref('nsoft.create_report_move_create_multi_act')
        if action:
            action.create_action()

    @api.multi
    def action_open_journal_move_lines(self):
        """
        Open a view with related/created account.move.line objects
        :return: JS action (dict)
        """
        self.ensure_one()
        return {
            'name': _('Žurnalo elementai'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move.line',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', self.mapped('nsoft_report_move_line_ids.move_id.line_ids.id'))],
        }

    @api.multi
    def action_open_journal_moves(self):
        """
        Open a view with related/created account.move objects
        :return: JS action (dict)
        """
        self.ensure_one()
        return {
            'name': _('Žurnalo įrašai'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', self.mapped('nsoft_report_move_line_ids.move_id.id'))],
        }

    @api.multi
    def action_mark_act_duplicates(self):
        """
        Force state to nsoft.report.move records
        that are potential duplicates and not
        yet created in the system
        :return: None
        """
        for rec in self:
            if rec.state not in ['imported', 'failed']:
                raise exceptions.ValidationError(
                    _('Aktus atšaukti galima tik "importuota" būsenoje'))
            if not rec.potential_duplicate:
                raise exceptions.ValidationError(
                    _('Aktas turi būti pažymėtas kaip "Potencialus dublikatas", kad galėtume jį atšaukti'))

            lines = rec.nsoft_report_move_line_ids
            lines.write({'state': 'cancelled_dub'})
            rec._compute_state()

    @api.model
    def action_mark_act_duplicates_func(self):
        """
        Function that calls the action
        for duplicate marking
        :return: None
        """
        action = self.env.ref('nsoft.action_mark_act_duplicates')
        if action:
            action.create_action()

    # Misc methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def name_get(self):
        """Custom name-get"""
        return [(rec.id, rec.ext_doc_number) for rec in self]

    @api.model
    def post_message(self, body=str(), data_set=None, state=None, lines=None):
        """
        Post specific message to the object and write it's state
        :param body: message body
        :param data_set: nsoft.prime.cost.move records
        :param lines: nsoft.prime.cost.move.line
        :param state: record state imported/failed/created
        :return: None
        """
        if data_set is None:
            data_set = self.env['nsoft.report.move']
        if not lines:
            lines = data_set.nsoft_report_move_line_ids
        if state:
            lines.write({'state': state})
        for line in data_set:
            line.message_post(body=body)


NsoftReportMove()



