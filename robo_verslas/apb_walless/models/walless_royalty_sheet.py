# -*- coding: utf-8 -*-

from odoo import models, api, _, fields, tools, exceptions, SUPERUSER_ID
from dateutil.relativedelta import relativedelta
from datetime import datetime
from odoo.api import Environment
from collections import OrderedDict
import threading
import xlwt
import StringIO
from odoo.addons.apb_walless.models.walless_royalty_sheet_line import validate_email


STATIC_PREFIX = 'WLS-'


class WallessRoyaltySheet(models.Model):
    _name = 'walless.royalty.sheet'
    _inherit = ['mail.thread']
    _order = 'period_start DESC'

    period_start = fields.Date(string='Periodo pradžia')
    period_end = fields.Date(string='Periodo pabaiga')
    name = fields.Char(string='Numeris', required=True)
    automatic_email_sending = fields.Boolean(string='Automatiškai siųsti el. laiškus darbuotojams', default=True)
    state = fields.Selection([('draft', 'Juodraštis'),
                              ('open', 'Patvirtinta, laukiama sąskaitų kūrimo'),
                              ('engaged', 'Sąskaitos kuriamos...'),
                              ('failed', 'Nepavyko sukurti sąskaitų'),
                              ('created', 'Patvirtinta, sąskaitos sukurtos')
                              ], string='Būsena', default='draft')

    # Relational fields
    invoice_ids = fields.Many2many('account.invoice', string='Sąskaitos faktūros')
    royalty_line_ids = fields.One2many('walless.royalty.sheet.line', 'royalty_sheet_id', string='Honorarų eilutės')
    invoice_creation_fail_message = fields.Text(string='Sąskaitų kūrimo klaidos pranešimas')
    included_employee_ids = fields.Many2many('hr.employee', compute='_compute_included_employee_ids')

    # Computes // ------------------------------------------------------------------------------------

    @api.multi
    @api.depends('royalty_line_ids.employee_id')
    def _compute_included_employee_ids(self):
        """
        Compute //
        Collect employees already used in the sheet.
        Used in royalty sheet line domain.
        :return: None
        """
        for rec in self:
            rec.included_employee_ids = rec.royalty_line_ids.mapped('employee_id.id')

    # Constraints // ---------------------------------------------------------------------------------

    @api.multi
    @api.constrains('name')
    def _constrains_name(self):
        """
        Constraints //
        Royalty sheet name must be unique.
        :return: None
        """
        for rec in self:
            if self.search_count([('name', '=', rec.name), ('id', '!=', rec.id)]):
                raise exceptions.ValidationError(_('Honorarų suvestinė su šiuo numeriu jau egzistuoja'))

    # State Actions // --------------------------------------------------------------------------------

    @api.multi
    def action_sheet_draft(self):
        """
        Set sheets to draft
        :return: None
        """
        for rec in self:
            rec.state = 'draft'

    @api.multi
    def action_sheet_open(self):
        """
        Checks constrains and sets sheets to open state
        :return: None
        """
        for rec in self:
            rec.check_constraints()
            rec.state = 'open'

    # Actions // --------------------------------------------------------------------------------------

    @api.multi
    def action_open_created_invoices(self):
        """
        Action to open invoices that were created from the sheet
        action opens - robo_front expenses tree view
        :return: action dict
        """
        self.ensure_one()
        domain = [('id', 'in', self.invoice_ids.ids)]
        ctx = {
            'force_order': "recently_updated DESC NULLS LAST",
            'lang': "lt_LT",
            'limitActive': 0,
            'robo_template': "RecentInvoices",
            'search_add_custom': False,
            'type': "in_invoice",
            'robo_header': {},
            'default_type': "in_invoice",
            'journal_type': "purchase",
            'params': {'action': self.env.ref('robo.robo_expenses_action').id},
            'robo_create_new': self.env.ref('robo.new_supplier_invoice').id,
            'robo_menu_name': self.env.ref('robo.menu_islaidos').id,
            'robo_subtype': 'expenses'
        }
        action = self.env.ref('robo.robo_expenses_action').read()[0]
        action.update({
            'ctx': ctx,
            'domain': domain,
        })
        return action

    @api.multi
    def action_create_invoices(self):
        """
        Sets sheet state to engaged and proceeds to start threaded invoice creation method
        :return: None
        """
        self.ensure_one()
        self.write({'state': 'engaged'})
        self.env.cr.commit()
        threaded_calculation = threading.Thread(target=self.create_invoices_thread,
                                                args=(self.id,))
        threaded_calculation.start()

    @api.multi
    def action_recreate_lines(self):
        """
        Unlink all of the sheet lines and recreates them
        :return: None
        """
        self.ensure_one()
        self.royalty_line_ids.unlink()
        employees = self.env['hr.employee'].sudo().search([('job_id.use_royalty', '=', True)])
        for employee in employees:
            line_vals = {
                'employee_id': employee.id,
                'monthly_royalty': employee.sudo().default_royalty_amount,
                'royalty_sheet_id': self.id,
            }
            self.env['walless.royalty.sheet.line'].create(line_vals)

    @api.multi
    def action_export_xls(self):
        """
        Export XLS based on the royalty sheet and it's lines
        :return: JS download action (dict)
        """
        self.ensure_one()
        if not self.royalty_line_ids:
            raise exceptions.UserError(_('Nėra suvestinės eilučių!'))

        many2one_fields = ['employee_id']

        # Define table column names and correspondence to the fields
        field_name_mapping = OrderedDict([
            ('employee_id', 'Darbuotojas'),
            ('monthly_royalty', 'Mėnesio honoraro\nbazė (Bruto)'),
            ('monthly_days', 'Mėnesio dienos'),
            ('days_worked', 'Dirbta dienų'),
            ('monthly_royalty_factual', 'Mėnesio honoraras\n(Bruto)'),
            ('extra_monthly_bonus', 'Papildomi priedai'),
            ('extra_monthly_deductions', 'Papildomos išskaitos'),
            ('final_amount', 'Galutinė suma'),
            ('vsd_amount', 'VSD suma'),
            ('psd_amount', 'PSD suma'),
            ('gpm_amount', 'GPM suma'),
            ('payable_amount', 'Išmokama suma'),
            ('email_sent', 'Siųstas el. laiškas')
        ])

        # Create workbook
        workbook = xlwt.Workbook(encoding='utf-8')
        worksheet = workbook.add_sheet(_('Honorarų suvestinė'))
        col_margin = 2

        # Create styles
        xlwt.add_palette_colour('robo_background', 0x21)
        workbook.set_colour_RGB(0x21, 236, 240, 241)
        header_style = xlwt.easyxf(
            "font: bold on; pattern: pattern solid, fore_colour robo_background; "
            "borders: left thick, bottom thick, right thick")
        # Write header line
        header_line = _('Honorarų suvestinė - {} // {} - {}').format(self.name, self.period_start, self.period_end)
        worksheet.write_merge(0, 0, 0, 25, header_line, header_style)

        # Loop through items and write them to XLS
        for y, items in enumerate(field_name_mapping.items()):
            field_name, column_name = items
            worksheet.write_merge(col_margin - 1, col_margin, y + y, y + y + 1, column_name, header_style)
            for x, line in enumerate(self.royalty_line_ids, col_margin + 1):
                field_data = getattr(line, field_name)
                # If field is many-to-one use it's display name as data-to-write
                if field_name in many2one_fields:
                    field_data = field_data.display_name
                # If field is boolean, use words
                if isinstance(field_data, bool):
                    field_data = _('Taip') if field_data else _('Ne')
                # Write data to worksheet
                worksheet.write_merge(x, x, y + y, y + y + 1, field_data)

        # Freeze panes
        worksheet.set_panes_frozen(True)
        worksheet.set_horz_split_pos(3)

        f = StringIO.StringIO()
        workbook.save(f)
        base64_file = f.getvalue().encode('base64')

        # Create attachment
        attachment = self.env['ir.attachment'].create({
            'res_model': self._name,
            'res_id': self[0].id,
            'type': 'binary',
            'name': 'name.xls',
            'datas_fname': '{}.xls'.format(header_line),
            'datas': base64_file
        })

        # Return download action
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download?res_model=%s&res_id=%s&attach_id=%s' % (
                self._name, self.id, attachment.id),
            'target': 'self',
        }

    # Threads // --------------------------------------------------------------------------------------

    @api.model
    def create_invoices_thread(self, obj_id):
        """
        Create invoices // THREADED
        :param obj_id: walless.royalty.sheet ID (current object)
        :return: None
        """
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, SUPERUSER_ID, {'lang': 'lt_LT'})
            current_obj = env['walless.royalty.sheet'].browse(obj_id)
            created_invoices = env['account.invoice']
            try:
                if not current_obj.invoice_ids:
                    # Check constraints and get default values
                    current_obj.check_constraints()
                    defaults = current_obj.get_defaults()

                    # Prepare base invoice template
                    vals_template = {
                        'imported_api': True,
                        'external_invoice': True,
                        'account_id': defaults.get('inv_account_id').id,
                        'price_include_selection': 'exc',
                        'date_invoice': current_obj.period_end,
                        'operacijos_data': current_obj.period_end,
                        'force_dates': True,
                        'type': 'in_invoice'
                    }
                    # Prepare values for each account invoice
                    for line in current_obj.royalty_line_ids:
                        partner = line.employee_id.address_home_id
                        invoice_vals = vals_template.copy()
                        invoice_reference = current_obj.get_invoice_sequence(line.employee_id)

                        # Ensure that the reference is unique
                        while env['account.invoice'].search_count([('reference', '=', invoice_reference),
                                                                   ('partner_id', '=', partner.id)]):
                            invoice_reference = current_obj.get_invoice_sequence(line.employee_id)
                        if partner.vat:
                            tax_id = defaults.get('vat_tax_id')
                        else:
                            tax_id = defaults.get('non_vat_tax_id')

                        invoice_lines = []
                        # Add main royalty and bonuses as two separate lines
                        royalty_amount = line.final_amount - line.extra_monthly_bonus
                        lines = [(_('Honorarai'), royalty_amount), (_('Priedai'), line.extra_monthly_bonus)]

                        for line_name, line_mount in lines:
                            if not tools.float_is_zero(line_mount, precision_digits=2):
                                invoice_lines.append(
                                    (0, 0, {
                                        'name': line_name,
                                        'quantity': 1,
                                        'price_unit': tools.float_round(line_mount, precision_digits=2),
                                        'account_id': defaults.get('line_account_id').id,
                                        'invoice_line_tax_ids': [(6, 0, tax_id.ids)],
                                    })
                                )

                        invoice_vals.update({
                            'partner_id': partner.id,
                            'invoice_line_ids': invoice_lines,
                            'reference': invoice_reference,
                        })

                        # Create account invoice
                        try:
                            invoice = env['account.invoice'].create(invoice_vals)
                        except Exception as exc:
                            raise exceptions.ValidationError(
                                _('Nepavyko sukurti sąskaitos darbuotojui - %s. Klaidos pranešimas - %s') % (
                                    line.employee_id.display_name, exc.args[0]))
                        try:
                            invoice.partner_data_force()
                            for invoice_line in invoice.invoice_line_ids:
                                invoice_line._set_additional_fields(invoice)
                            invoice.with_context(skip_attachments=True).action_invoice_open()
                        except Exception as exc:
                            raise exceptions.ValidationError(
                                _('Nepavyko patvirtinti sąskaitos - %s darbuotojui - %s. Klaidos pranešimas - %s') % (
                                    invoice_reference, line.employee_id.display_name, exc.args[0]))
                        line.write({'invoice_id': invoice.id})
                        created_invoices |= invoice

                    # If everything executed without exceptions
                    # send emails to corresponding partners
                    if current_obj.automatic_email_sending:
                        email_sending_errors = str()
                        for obj in current_obj.included_employee_ids:
                            work_email = obj.work_email or ' '
                            if not validate_email(work_email):
                                email_sending_errors += _('{} - "{}" \n').format(obj.name, work_email)
                        if email_sending_errors:
                            raise exceptions.ValidationError(
                                _('Dėl neteisingų arba nesukonfigūruotų el. pašto adresų, suvestinės nepavyko išsiųsti '
                                  'šiems darbuotojams:\n{}').format(email_sending_errors)
                            )
                        current_obj.royalty_line_ids.send_mail_to_employee(current_obj.period_start[:7])
            except Exception as exc:
                new_cr.rollback()
                current_obj.write({'state': 'failed',
                                   'invoice_creation_fail_message': str(exc.args[0])})
            else:
                current_obj.write({'state': 'created', 'invoice_ids': [(6, 0, created_invoices.ids)]})
        new_cr.commit()
        new_cr.close()

    # Misc // ----------------------------------------------------------------------------------------

    @api.multi
    def unlink(self):
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Negalite ištrinti honorarų suvestinės'))
        return super(WallessRoyaltySheet, self).unlink()

    @api.multi
    def check_constraints(self):
        """
        Check constraints before opening the sheet and creating invoices
        Lines can't have zero amount
        :return: None
        """
        self.ensure_one()
        report_str = str()
        if not self.period_start or not self.period_end:
            report_str += 'Nenurodyta periodo pradžios ir/arba pabaigos data\n'
        for line in self.royalty_line_ids:
            if tools.float_is_zero(line.final_amount, precision_digits=2):
                report_str += 'Eilutė - {} turi nulinę galutinę sumą.\n'.format(line.employee_id.display_name)
        if report_str:
            raise exceptions.ValidationError(
                _('Negalite patvirtinti suvestinės, rasta eilučių su nulinėmis galutinėmis sumomis, '
                  'ištrinkite šias eilutes arba įrašykite tinkamas reikšmes:\n\n' + report_str))

    @api.model
    def get_defaults(self):
        return {
            'inv_account_id': self.env['account.account'].search([('code', '=', '4430')]),
            'line_account_id': self.env['account.account'].search([('code', '=', '6001')]),
            'vat_tax_id': self.env['account.tax'].search(
                [('code', '=', 'PVM1'), ('type_tax_use', '=', 'purchase'),
                 ('price_include', '=', False)], limit=1),
            'non_vat_tax_id': self.env['account.tax'].search(
                [('code', '=', 'Ne PVM'), ('type_tax_use', '=', 'purchase'),
                 ('price_include', '=', False)], limit=1)
        }

    @api.multi
    def get_invoice_sequence(self, employee_id):
        """
        Create or get-next number of the invoice sequence for specific employee
        :param employee_id: employee of to-be-created account.invoice
        :return:
        """
        self.ensure_zero_or_one()
        IrSequence = self.env['ir.sequence']
        seq_name_format = 'Walless sąskaitų numeruotė - {}'
        seq_code_format = 'WLS-{}{}{}'
        seq_prefix_format = '{}{}{}-'

        # Get sheet date or use datetime now
        sheet_date_dt = datetime.strptime(
            self.period_start, tools.DEFAULT_SERVER_DATE_FORMAT) if self.period_start else datetime.now()
        employee_name = employee_id.display_name
        name_parts = employee_name.split()
        if len(name_parts) >= 2:
            first_initial = name_parts[0][0]
            last_initial = name_parts[-1][0]
            suffix = sheet_date_dt.strftime('%Y')[2:]
            seq_code = seq_code_format.format(first_initial, last_initial, suffix)
            seq_prefix = seq_prefix_format.format(first_initial, last_initial, suffix)
            # Search for sequence by its name as there may be sequences with matching codes
            # due to employees with the same credentials
            seq_name = seq_name_format.format(employee_name)
            sequence = IrSequence.search([('name', '=', seq_name), ('code', '=', seq_code)], limit=1)
            if not sequence:
                sequence = IrSequence.create({
                    'name': seq_name_format.format(employee_name),
                    'code': seq_code,
                    'prefix': seq_prefix,
                    'padding': 4,
                    'implementation': 'no_gap',
                    'number_increment': 1
                })
            invoice_reference = sequence.next_by_id()
            return invoice_reference
        else:
            raise exceptions.ValidationError(
                _('Nepavyko sukurti numeracijos, vartotojo vardas %s yra neteisingo formato') % employee_name)

    # Cron Jobs // --------------------------------------------------------------------------------------

    @api.model
    def cron_prepare_royalty_sheet(self):
        """
        Cron that creates royalty sheet for previous month
        The sheet would be created on 1st day, since month shift gives it a unique number
        :return: None
        """
        dt_now = datetime.now()
        name = '{}{}'.format(STATIC_PREFIX, dt_now.strftime('%Y%m'))
        if not self.search_count([('name', '=', name)]):
            royalty_line_ids = []
            vals = {
                'royalty_line_ids': royalty_line_ids,
                'period_start': (dt_now - relativedelta(months=1, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                'period_end': (dt_now - relativedelta(months=1, day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                'name': name,
            }
            employees = self.env['hr.employee'].search([('job_id.use_royalty', '=', True)])
            for employee in employees:
                line_vals = {
                    'employee_id': employee.id,
                    'monthly_royalty': employee.sudo().default_royalty_amount,
                }
                royalty_line_ids.append((0, 0, line_vals))
            self.create(vals)


WallessRoyaltySheet()
