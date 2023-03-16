# -*- coding: utf-8 -*-

from odoo import models, api, _, fields, tools, exceptions
from datetime import datetime
from dateutil.relativedelta import relativedelta
from . import apb_walless_tools as awt
from account_invoice import SODRA_ROYALTY_PERCENTAGE_MAPPER as PERCENTAGE_MAPPER
from collections import OrderedDict
import re


def validate_email(email):
    """Validate the email using custom regex not to ignore spaces"""
    regex_pattern = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
    return re.match(regex_pattern, email) is not None


class WallessRoyaltySheetLine(models.Model):
    _name = 'walless.royalty.sheet.line'

    monthly_royalty = fields.Float(string='Mėnesio honoraro bazė (Bruto)')
    monthly_days = fields.Integer(compute='_compute_monthly_days', string='Mėnesio dienos')
    days_worked = fields.Integer(string='Dirbta dienų')
    monthly_royalty_factual = fields.Float(string='Mėnesio honoraras (Bruto)',
                                           compute='_compute_monthly_royalty_factual')
    extra_monthly_bonus = fields.Float(string='Papildomi priedai')
    extra_monthly_deductions = fields.Float(string='Papildomos išskaitos')
    final_amount = fields.Float(string='Galutinė suma', compute='_compute_final_amount')
    vsd_amount = fields.Float(string='VSD suma', compute='_compute_move_line_amounts')
    hypothetical_vsd_amount = fields.Float(string='Menamas VSD', compute='_compute_hypothetical_vsd_amount')
    psd_amount = fields.Float(string='PSD suma', compute='_compute_move_line_amounts')
    gpm_amount = fields.Float(string='GPM suma', compute='_compute_move_line_amounts')
    payable_amount = fields.Float(string='Išmokama suma', compute='_compute_move_line_amounts')
    email_sent = fields.Boolean(string='Siųstas el. laiškas')

    # Relational fields
    royalty_sheet_id = fields.Many2one('walless.royalty.sheet', string='Tėvinis objektas')
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', inverse='_set_days_worked')
    invoice_id = fields.Many2one('account.invoice', string='Sąskaita faktūra')

    # Computes & Inverses // -----------------------------------------------------------------------------------

    @api.multi
    def _set_days_worked(self):
        """
        Inverse //
        Set days worked based on monthly days as 'default' value if days_worked is zero
        :return: None
        """
        for rec in self.filtered(lambda x: not x.days_worked):
            start_of_work = rec.employee_id.start_of_work
            if start_of_work:
                start_of_work_dt = datetime.strptime(start_of_work, tools.DEFAULT_SERVER_DATE_FORMAT)
                period_end_dt = datetime.strptime(rec.royalty_sheet_id.period_end, tools.DEFAULT_SERVER_DATE_FORMAT)
                year = start_of_work_dt.year == period_end_dt.year
                month = start_of_work_dt.month == period_end_dt.month
                if year and month:
                    rec.days_worked = (period_end_dt - start_of_work_dt).days
                else:
                    rec.days_worked = rec.monthly_days
            else:
                rec.days_worked = rec.monthly_days

    @api.multi
    @api.depends('invoice_id.move_id.line_ids')
    def _compute_move_line_amounts(self):
        """
        Compute //
        Calculate VSD, PSD, GPM and payable amounts based on account move lines
        of related account.invoice record
        :return: None
        """
        for rec in self.filtered(lambda x: x.invoice_id.move_id):
            lines = rec.invoice_id.move_id.line_ids
            rec.vsd_amount = self.fetch_amount(
                lines.filtered(lambda l: l.account_id.code == awt.VSD_ACCOUNT_CODE))
            rec.psd_amount = self.fetch_amount(
                lines.filtered(lambda l: l.account_id.code == awt.PSD_ACCOUNT_CODE))
            rec.gpm_amount = self.fetch_amount(
                lines.filtered(lambda l: l.account_id.code == awt.GPM_ACCOUNT_CODE))
            rec.payable_amount = self.fetch_amount(
                lines.filtered(lambda l: l.account_id.code == awt.PAYABLE_ACCOUNT_CODE))

    @api.multi
    @api.depends('royalty_sheet_id.period_start', 'royalty_sheet_id.period_end')
    def _compute_monthly_days(self):
        """
        Compute //
        Calculate month days number
        :return: None
        """
        for rec in self:
            if rec.royalty_sheet_id.period_start and rec.royalty_sheet_id.period_end:
                period_start_dt = datetime.strptime(
                    rec.royalty_sheet_id.period_start, tools.DEFAULT_SERVER_DATE_FORMAT)
                period_end_dt = datetime.strptime(rec.royalty_sheet_id.period_end, tools.DEFAULT_SERVER_DATE_FORMAT)
                rec.monthly_days = (period_end_dt + relativedelta(days=1) - period_start_dt).days

    @api.multi
    @api.depends('monthly_days', 'monthly_royalty', 'days_worked')
    def _compute_monthly_royalty_factual(self):
        """
        Compute //
        Calculate monthly royalty factual: Formula - base royalty / all days * days worked
        :return: None
        """
        for rec in self:
            royalty_factual = float(rec.monthly_royalty) / float(
                rec.monthly_days) * float(rec.days_worked) if rec.monthly_days else 0
            rec.monthly_royalty_factual = tools.float_round(royalty_factual, precision_digits=2)

    @api.multi
    @api.depends('monthly_royalty_factual', 'extra_monthly_deductions', 'extra_monthly_bonus')
    def _compute_final_amount(self):
        """
        Compute //
        Calculate final amount: Formula - royalty factual + bonuses - deductions
        :return: None
        """
        for rec in self:
            final_amount = rec.monthly_royalty_factual - abs(
                rec.extra_monthly_deductions) + abs(rec.extra_monthly_bonus)
            rec.final_amount = tools.float_round(final_amount, precision_digits=2)

    @api.multi
    @api.depends('final_amount')
    def _compute_hypothetical_vsd_amount(self):
        """
        Compute //
        Calculate hypothetical VSD amount: Formula - ((final amount - final amount * 0.3) * 0.9)
        * royalty percentage
        :return: None
        """
        for rec in self:
            static_num = PERCENTAGE_MAPPER.get(rec.invoice_id.partner_id.sodra_royalty_percentage or '0')
            result = ((rec.final_amount - rec.final_amount * 0.3) * 0.9) * static_num
            rec.hypothetical_vsd_amount = tools.float_round(result, precision_digits=2)

    # On-changes // --------------------------------------------------------------------------------------------

    @api.onchange('days_worked')
    def _onchange_days_worked(self):
        """
        Onchange //
        If days worked exceed monthly days amount, normalize them
        :return: None
        """
        if self.days_worked > self.monthly_days:
            self.days_worked = self.monthly_days

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        """
        Onchange //
        Recompute date fields and set monthly royalty amount on employee change
        :return: None
        """
        if self.employee_id:
            self._compute_monthly_days()
            self._set_days_worked()
            self.monthly_royalty = self.employee_id.sudo().default_royalty_amount

    # Misc methods // ------------------------------------------------------------------------------------------

    @api.model
    def fetch_amount(self, line):
        """
        Check whether passed account move line record is singleton,
        if so return absolute balance amount
        :param line: account.move.line object
        :return: amount (float)
        """
        amount = 0.0
        if line and len(line) == 1:
            amount = abs(line.balance)
        return amount

    @api.multi
    def send_mail_to_employee(self, month, manual_action=False):
        """
        Send mail to employee of the walless.royalty.sheet line
        and inform them about royalty amounts
        :param month: Signifies month of the royalty sheet (str e.g. 2020-04)
        :param manual_action: Indicates whether action is done directly
        by hand or executed in the background by some other method
        :return: None
        """

        email_sending_errors = str()
        # User ordered dict, so order is preserved in the email
        field_name_mapping = OrderedDict([
            ('monthly_royalty', 'Mėnesio honoraro bazė (Bruto)'),
            ('monthly_days', 'Mėnesio dienos'),
            ('days_worked', 'Dirbta dienų'),
            ('monthly_royalty_factual', 'Mėnesio honoraras (Bruto)'),
            ('extra_monthly_bonus', 'Papildomi priedai'),
            ('extra_monthly_deductions', 'Papildomos išskaitos'),
            ('final_amount', 'Galutinė suma'),
            ('vsd_amount', 'VSD suma'),
            ('psd_amount', 'PSD suma'),
            ('gpm_amount', 'GPM suma'),
            ('payable_amount', 'Išmokama suma')
        ])

        template = '''
            Sveiki, siunčiame jums {0} mėn. paskaičiuoto honoraro detalizaciją. <br/><br/>
            <table border="2" width=100%>
        '''.format(month)

        for rec in self.filtered(lambda x: x.employee_id and x.invoice_id and not x.email_sent):
            message = template
            for field, name in field_name_mapping.items():
                message += '''
                <tr><th>{}<th/><tr/>
                <tr><td style="text-align:center">{}<td/><tr/>
                '''.format(name, getattr(rec, field))
            message += '<table/>'
            work_email = rec.employee_id.work_email
            # Check whether email is valid of not
            valid_email = work_email and validate_email(work_email)
            if valid_email:
                self.env['script'].send_email(emails_to=[work_email],
                                              subject='Honorarų suvestinė - {}'.format(month),
                                              body=message)
                rec.email_sent = True
            else:
                if manual_action:
                    raise exceptions.ValidationError(
                        _('Nepavyko išsiųsti suvestinės darbuotojui - {}. '
                          'Nekorektiškas arba nenurodytas darbuotojo el. paštas'.format(rec.employee_id.name))
                    )
                # Gather up the email error information that should be posted
                email_sending_errors += '''<tr><td>{}<td/><td>{}<td/><tr/>'''.format(
                    rec.employee_id.name, work_email
                )

        # Post the errors to the record
        if email_sending_errors:
            email_sending_errors = '''Dėl neteisingų arba nesukonfigūruotų el. pašto adresų, 
            suvestinės nepavyko išsiųsti šiems darbuotojams:  
            <br/><br/> <table border="1" width=100%>{}</table>'''.format(email_sending_errors)
            # Should always be single record, but just in case
            for sheet in self.mapped('royalty_sheet_id'):
                sheet.message_post(body=email_sending_errors)

    @api.multi
    def send_royalty_sheet_line(self):
        self.ensure_one()
        if not self.env.user.is_accountant():
            raise exceptions.AccessError(_('Negalite atlikti šio veiksmo.'))

        if self.email_sent:
            self.email_sent = False
        self.send_mail_to_employee(self.royalty_sheet_id.period_start[:7], manual_action=True)
