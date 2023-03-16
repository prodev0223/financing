# -*- coding: utf-8 -*-
from odoo.addons.sepa import api_bank_integrations as abi
from odoo import models, api, SUPERUSER_ID, _


class BankExportBase(models.AbstractModel):
    _inherit = 'bank.export.base'

    @api.multi
    def send_to_bank_base(self, data):
        """Override and extend the method by informing company's CEO about exported objects"""
        self.ensure_one()
        res = super(BankExportBase, self).send_to_bank_base(data)

        # Get current record model and record-set
        record_model = self._name
        record_set = self

        # If origin is front bank statement, check the state directly
        if data['origin'] == 'front.bank.statement':
            inform_about_exports = self.bank_export_state in abi.POSITIVE_STATES
        else:
            # Otherwise, gather the exports with the states, and parse the model from the exports
            invoices = data['export_lines'].mapped('invoice_ids').filtered(
                lambda x: x.bank_export_state in abi.POSITIVE_STATES
            )
            move_lines = data['export_lines'].mapped('aml_ids').filtered(
                lambda x: x.bank_export_state in abi.POSITIVE_STATES
            )

            try:
                # When data['origin'] != 'invoice.export.line':
                bank_export_job_ids = data['export_lines'].mapped('bank_export_job_ids').filtered(
                    lambda x: x.export_state in abi.POSITIVE_STATES
                )
                statements = bank_export_job_ids.mapped('bank_statement_line_id.statement_id')
            except KeyError:
                statements = self.env['account.bank.statement']

            # Check whether there's any successful move lines or invoices
            inform_about_exports = exported_objects = invoices or move_lines or statements
            # If there's any successful objects, assign it to recordset and the model
            record_set, record_model = exported_objects, exported_objects._name

        # If export was successfully uploaded - inform CEO about it
        if inform_about_exports:
            self.inform_about_exported_payments(
                records=record_set, record_model=record_model,
            )
        return res

    @api.model
    def get_bank_mail_channel_partners(self):
        """
        Collects the partners that should be informed when exportable objects
        (move lines/invoices/statements) are uploaded to bank.
        :return: res.partner (recordset)
        """
        company = self.env.user.sudo().company_id
        # Search for the bank export channel, and map out subscribed partners
        bank_export_mail_channel = self.env.ref(
            'robo.bank_export_message_mail_channel', raise_if_not_found=False)
        channel_partner_ids = bank_export_mail_channel.sudo().channel_partner_ids.ids
        # Get the base receivers
        partners = company.vadovas.user_id.partner_id or company.vadovas.address_home_id
        partners |= company.default_msg_receivers
        # Since there is no default receivers/ceo group,
        # we filter out partners like this.
        partners = partners.filtered(lambda x: x.id in channel_partner_ids)
        return partners

    @api.multi
    def inform_about_exported_payments(self, records, record_model):
        """
        Informs the CEO of the company if exportable objects
        (move lines/invoices/statements) were sent to bank by an accountant.
        :return: None
        """

        c_user = self.env.user
        not_ceo_user = c_user.id != c_user.sudo().company_id.vadovas.user_id.id
        # Check whether the message should be sent -- if user is manager other than ceo
        if c_user.has_group('robo_basic.group_robo_premium_accountant') and not_ceo_user:
            # Return if there's no mail channel partners
            partners = self.get_bank_mail_channel_partners()
            if not partners:
                return

            # Build base message body
            base_body = _('''Informuojame, kad {} "{}" buvo išsiųsti (-as) į banką.\n 
            Jei duomenys sėkmingai praeis bankinę validaciją, jie netrukus atsiras Jūsų paskyroje. 
            Banko sąskaita - {}.\n''')

            # Collect record names and the journal
            record_names = ', '.join(records.mapped('display_name'))
            singleton = len(records) == 1
            # We're taking the journal from exporting model not the exported model
            journal_name = self.journal_id.display_name

            # Prepare custom message data based on the export model
            if record_model == 'front.bank.statement':
                base_body = base_body.format(_('mokėjimo ruošinys'), record_names, journal_name)
                # Build custom message data
                custom_data = {
                    'subject': _('Į banką išsiųstas mokėjimo ruošinys [{}]').format(self.env.cr.dbname),
                    'view_id': self.env.ref('robo.robo_payments_report_form_view').id,
                    'rec_id': records.id,  # Always a single record on front statements
                }
            elif record_model == 'account.invoice':
                base_body = base_body.format(_('sąskaitų faktūrų mokėjimai (-as)'), record_names, journal_name)
                # Build custom message data
                custom_data = {
                    'subject': _('Į banką išsiųsta (-os) sąskaita (-os) [{}]').format(self.env.cr.dbname),
                }
                # If single invoice is being exported, add the form data to it
                if singleton:
                    custom_data.update({
                        'view_id': self.env.ref('robo.robo_expenses_form').id,
                        'rec_id': records.id,
                    })
            else:
                base_body = base_body.format(_('mokėjimai (-as)'), record_names, journal_name)
                custom_data = {
                    'subject': _('Į banką išsiųsti mokėjimai [{}]').format(self.env.cr.dbname),
                }
            # Append uploader information to the message
            base_body += _('Automatiškai pateikė sistema.') if c_user.id == SUPERUSER_ID \
                else _('Pateikęs naudotojas - {}.').format(c_user.name)

            # Prepare base message data
            base_message = {
                'body': base_body,
                'priority': 'medium',
                'front_message': True,
                'robo_chat': True,
                'client_message': True,
                'message_type': 'notification',
                'partner_ids': partners.ids,
            }
            base_message.update(custom_data)

            # If there's a single record that is uploaded, post the message to it directly
            # otherwise use company message to post the message about export
            if singleton and record_model != 'account.move.line':
                base_message.update({
                    'rec_model': record_model,
                })
                records.sudo().robo_message_post(**base_message)
            else:
                company_message = self.env['res.company.message'].sudo().create({
                    'body': base_body,
                    'subject': custom_data['subject'],
                    'company_id': c_user.company_id.id,
                })
                base_message.update({
                    'rec_model': 'res.company.message',
                    'rec_id': company_message.id,
                    'view_id': self.env.ref('robo.res_company_message_form').id,
                })
                company_message.sudo().robo_message_post(**base_message)
