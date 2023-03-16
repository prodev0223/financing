# -*- coding: utf-8 -*-


import base64

from odoo.addons.robo_basic.models.utils import validate_email

from odoo import _, api, exceptions, fields, models


class MailComposeMessage(models.TransientModel):
    _name = 'robo.mail.compose.message'
    _inherit = 'mail.compose.message'

    def _default_mailing_ids(self):
        lines = []
        if self._context.get('active_model') == 'overpay.transfer.request.wizard':
            pdf_data = self._context.get('document_data', False)
            partner_data = self._context.get('partner_data', False)
            if not pdf_data or not partner_data:
                raise exceptions.ValidationError(_('Missing data, cannot generate the report to send.'))
            pdf = self.with_context(lang=self._context.get('lang', 'lt_LT')).env['report'].get_pdf(
                None, 'robo.report_overpay_transfer_request', data=pdf_data)

            for partner in partner_data:
                partner_name = str((partner.get('name') or _('Partneris')).replace(' ', '_'))
                values = {
                    'partner_id': partner['partner_id'],
                    'email': partner['email'],
                    'generated_report': base64.b64encode(pdf),
                    'file_name': partner_name + _('\'_overpay_transfer_request') + '.pdf',
                }
                lines.append([0, 0, values])
        else:
            movelines = self._context.get('partners_movelines') or []
            date = self._context.get('date')
            account_type_filter = self._context.get('account_type_filter')
            account_ids = self._context.get('filtered_account_ids')

            report_name = 'skolu_suderinimas.report_aktas_multi'
            for move in movelines:
                lang = self.env['res.partner'].browse(move['partner_id']).lang
                data = {
                    'partner_ids': [move['partner_id']],
                    'date': date,
                    'account_type_filter': account_type_filter,
                    'date_from': None,
                    'date_to': self._context.get('default_date_to'),
                    'type': self._context.get('default_type') or 'unreconciled',
                    'detail_level': self._context.get('default_detail_level') or 'sum',
                    'show_original_amounts': self._context.get('default_show_original_amounts', True),
                    'show_accounts': self._context.get('default_show_accounts', False),
                    'account_ids': account_ids,
                }
                if self._context.get('default_type', 'reconciled') == 'all':
                    data.update(date_from=self._context.get('default_date_from_debt'),
                                date_to=self._context.get('default_date_to_debt'))

                pdf = self.with_context(lang=lang).env['report'].get_pdf(None, report_name, data=data)

                partner = self.env['res.partner'].browse(move['partner_id'])
                partner_name = str((partner.name if partner else _('Partneris')).replace(' ', '_'))
                lines.append([0, 0, {
                    'partner_id': move['partner_id'],
                    'email': partner.balance_reconciliation_email or partner.email,
                    'amount': move['total'],
                    'forced_amount': move['total'],
                    'generated_report': base64.b64encode(pdf),
                    'file_name': partner_name + '.pdf',
                    'currency_id': self.env.user.company_id.currency_id.id,
                    'last_attachment': partner.balance_reconciliation_attachment_id.datas,
                    'comment': partner.balance_reconciliation_comment,
                    'last_email_date': partner.balance_reconciliation_send_date,
                    'last_balance_reconciliation_date': partner.balance_reconciliation_date,
                    'last_attachment_file_name': partner.balance_reconciliation_attachment_id.datas_fname,
                }])
        return lines

    mass_mailling_partner_ids = fields.One2many('robo.mail.mass.mailing.partners', 'mail_compose_message_id',
                                                string='Siųsti', default=_default_mailing_ids)
    result_selection = fields.Selection('_get_result_selection', readonly=True, string='Partnerio')
    date_from = fields.Date(string='Skaičiavimų pradžia', readonly=True)
    target_move = fields.Selection('_get_target_move', readonly=True, string='Rodyti įrašus', default='posted')
    show_final_window = fields.Boolean(default=False)
    failed_emails = fields.Text(default='', readonly=True)

    @api.model
    def default_get(self, fields):
        res = super(MailComposeMessage, self).default_get(fields)
        wizard_form = self._context.get('wizard_form')
        if wizard_form:
            res.update({
                'date_from': wizard_form['date_from'],
                'result_selection': wizard_form['result_selection'],
                'target_move': wizard_form['target_move'],
            })
        return res

    @api.model
    def _get_result_selection(self):
        return self.env['account.common.partner.report']._fields['result_selection'].selection

    @api.model  # just translation
    def _get_target_move(self):
        return [('posted', 'Registruoti įrašai'), ('all', 'Visi įrašai')]

    @api.multi
    def write(self, vals):
        if self.env.user.is_accountant() and not self.env.user.has_group('base.group_system'):
            return self.sudo().write(vals)
        return super(MailComposeMessage, self).write(vals)

    @api.multi
    def send_mail_action(self):

        if not all(self.mass_mailling_partner_ids.mapped('email')):
            missing_mail_partners = self.mass_mailling_partner_ids.filtered(lambda r: not r.email).mapped(
                'partner_id.name')
            raise exceptions.UserError(
                _('Pašalinkite gavėjus, kuriems nesuvestas el. pašto adresas:\n\n') + '\n'.join(missing_mail_partners))

        partners_check_emails = self.mass_mailling_partner_ids
        partners_with_bad_email = []
        for partner in partners_check_emails:
            if not partner.email:
                partners_with_bad_email.append(partner.name)
            else:
                for email in partner.email.split(';'):
                    if not validate_email(email.strip()):
                        partners_with_bad_email.append(partner.partner_id.name)
                        break

        if len(partners_with_bad_email):
            raise exceptions.UserError(
                _('Pašalinkite šiuos gavėjus, nes jų el. pašto adresas sukonfigūruotas netinkamai: \n\n') + " \n".join(
                    partners_with_bad_email))

        active_ids = self.mass_mailling_partner_ids.ids
        if self._context.get('force_send_message'):
            partners = self.mass_mailling_partner_ids.mapped('partner_id')
            notify_settings_by_partner = dict(partners.mapped(lambda r: (r.id, r.notify_email)))
            partners.sudo().write({'notify_email': 'always'})
            res = self.with_context(mail_notify_author=True, active_ids=active_ids, create_statistics=True).send_mail()
            for partner in partners.sudo():
                partner.notify_email = notify_settings_by_partner[partner.id]
        else:
            res = self.with_context(active_ids=active_ids, create_statistics=True).send_mail()

        self.show_final_window = True
        return res

    # ROBO: attachments_ids should be generated using report template. We need to modify mail.template method
    # generate_email by adding "data" parameter.
    @api.multi
    def get_mail_values(self, res_ids):
        res = super(MailComposeMessage, self).get_mail_values(res_ids)
        if res_ids:
            for res_id in res_ids:
                if res[res_id]:
                    attachments = self.env['ir.attachment'].search([
                        ('res_model', '=', 'robo.mail.mass.mailing.partners'),
                        ('res_field', '=', 'generated_report'),
                        ('res_id', '=', res_id)
                    ]).ids
                    res[res_id]['attachment_ids'] = [(4, x) for x in attachments]
                    res[res_id]['email_to'] = self.env['robo.mail.mass.mailing.partners'].browse(res_id).email
                    res[res_id].pop('recipient_ids') #we replace it with email_to from the wizard line
        return res

    @api.multi
    def recompute_reports(self):
        date = self._context.get('date')
        account_type_filter = self._context.get('account_type_filter')
        for line in self.mass_mailling_partner_ids:
            pdf = self.with_context(lang=self.env['res.partner'].browse(line.partner_id.id).lang).env['report'].get_pdf(
                None, 'skolu_suderinimas.report_aktas_multi',
                data={
                    'partner_ids': [line.partner_id.id],
                    'date': date,
                    'account_type_filter': account_type_filter,
                    'date_from': None,
                    'date_to': None,
                    'type': 'unreconciled',
                    'detail_level': 'sum',
                    'show_original_amounts': True,
                    'show_accounts': False,
                    'forced_amount': line.forced_amount
                })
            line.write({'generated_report': base64.b64encode(pdf)})

    @api.multi
    def check_access_rule(self, operation):
        is_accountant = self.env.user.is_accountant()

        group = self._context.get('group_email_send')
        has_group = self.env.user.has_group(group) if group else False
        user_can_send = has_group and self.sudo().template_id.id == self._context.get('default_template_id')

        if operation == 'create' and (is_accountant or user_can_send):
            return True
        else:
            return super(MailComposeMessage, self).check_access_rule(operation)
