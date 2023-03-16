# -*- coding: utf-8 -*-
import logging
from six import iteritems
from odoo import fields, models, api, _, exceptions
import base64
from odoo.addons.robo_basic.models.utils import validate_email
from odoo.addons.queue_job.job import identity_exact, job


_logger = logging.getLogger(__name__)


EMAIL_MODEL = 'account.invoice'


class InvoiceMassMailingWizard(models.TransientModel):
    """
    Wizard used to mass mail invoices
    """
    _name = 'invoice.mass.mailing.wizard'
    _inherit = 'mail.compose.message'

    @api.model
    def _default_mass_mailing_line_ids(self):
        """
        Create mass mailing lines using active_ids
        :return: [(6, 0, [mass mailing line IDs])]/None if exception is raised
        """
        invoice_ids = self._context.get('active_ids') or []
        invoices = self.env['account.invoice'].browse(invoice_ids)
        if not invoices:
            raise exceptions.UserError(_('Nepaduota nė viena sąskaita!'))
        mass_mailing_lines = []
        for invoice in invoices:
            invoice_pdf = self.with_context(lang=invoice.partner_lang).env['report'].get_pdf(
                [invoice.id], 'saskaitos.report_invoice')
            pdf_base64 = base64.b64encode(invoice_pdf)
            file_name = '{}.pdf'.format(invoice.move_name or 'Sąskaita')

            mass_mailing_line = self.env['invoice.mass.mailing.wizard.line'].create({
                'invoice_id': invoice.id,
                'generated_pdf': pdf_base64,
                'file_name': file_name
            })
            mass_mailing_lines.append(mass_mailing_line.id)
        return [(6, 0, mass_mailing_lines)]

    mass_mailing_line_ids = fields.One2many(
        'invoice.mass.mailing.wizard.line', 'mass_mailing_wizard_id',
        string='Sąskaitos', default=_default_mass_mailing_line_ids)
    template_id = fields.Many2one(
        'mail.template', 'Use template', index=True,
        domain="[('model', '=', 'account.invoice')]")
    sample_invoice_id = fields.Many2one('account.invoice', compute='_compute_sample_invoice')

    show_final_window = fields.Boolean(string='Rodyti paskutinį langą')
    failed_partners = fields.Text(string='Suklyde partneriai', readonly=True)

    # Computes / On-Changes -------------------------------------------------------------------------------------------

    @api.multi
    @api.depends('mass_mailing_line_ids')
    def _compute_sample_invoice(self):
        """
        Compute //
        Prepare sample invoice -- first invoice of the mass mailing list.
        It's data will be displayed in the template for visual representations
        :return: None
        """
        for rec in self.filtered(lambda x: x.mass_mailing_line_ids):
            invoices = rec.mass_mailing_line_ids.mapped('invoice_id')
            if invoices:
                rec.sample_invoice_id = invoices[0]

    @api.multi
    @api.onchange('template_id')
    def onchange_template_id_wrapper(self):
        """
        ! OVERRIDDEN !
        Override onchange of template ID so visual representation of the email template
        is shown to the user using the first invoice of the list
        :return: None
        """
        self.ensure_one()
        if self.sample_invoice_id:
            values = self.onchange_template_id(
                self.template_id.id, False, EMAIL_MODEL, self.sample_invoice_id.id)['value']
            if 'attachment_ids' in values:
                values.pop('attachment_ids')
            if 'partner_ids' in values:
                values.pop('partner_ids')
            for fname, value in iteritems(values):
                setattr(self, fname, value)

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def validator(self):
        """
        Validate emails of the partners that invoices are being send to.
        If emails are of incorrect format, or are missing, raise an error
        :return: None
        """
        self.ensure_one()
        final_error = str()
        missing_emails = str()
        incorrect_emails = str()
        for line in self.mass_mailing_line_ids:
            for partner in line.partner_ids:
                if not partner.email:
                    missing_emails += '{}\n'.format(partner.name)
                else:
                    for email in partner.email.split(';'):
                        if not validate_email(email.strip()):
                            incorrect_emails += '{}\n'.format(partner.name)
        if missing_emails:
            final_error += _('Šiems gavėjams nėra nustatytas el. pašto adresas:\n\n{}\n').format(missing_emails)
        if incorrect_emails:
            final_error += _('Šių gavėjų el. pašto adresas yra netinkamo formato:\n\n{}').format(incorrect_emails)
        if final_error:
            raise exceptions.ValidationError(final_error)

    @api.multi
    def send_mail_action(self):
        """
        Execute mass invoice sending to the partners
        :return: action to reload the view (dict)
        """
        self.ensure_one()
        self.show_final_window = True
        ctx = self._context.copy()

        # Re-render the template so values from sample visual representation are overridden
        values = self.onchange_template_id(
            self.template_id.id, 'mass_mail', EMAIL_MODEL, False)['value']
        for fname, value in iteritems(values):
            setattr(self, fname, value)
        #Do not send again invoices that were already sent
        active_ids = self.mass_mailing_line_ids.mapped('invoice_id').filtered(lambda inv: not inv.sent).ids

        # Build additional context
        ctx.update({
            'active_ids': active_ids,
            'create_statistics': True,
            'mass_invoice_mailing': True,
            'mass_mailing_wizard_id': self.id
        })
        if self._context.get('force_send_message'):
            partners = self.mass_mailing_line_ids.mapped('partner_ids')
            notify_settings_by_partner = dict(partners.mapped(lambda r: (r.id, r.notify_email)))
            partners.sudo().write({'notify_email': 'always'})
            ctx.update({'notify_mail_author': True})
            self.with_delay(channel='root.single_1', identity_key=identity_exact).queue_job_send_mail(ctx)
            for partner in partners.sudo():
                partner.notify_email = notify_settings_by_partner[partner.id]
        else:
            self.with_delay(channel='root.single_1', identity_key=identity_exact).queue_job_send_mail(ctx)
        return {'type': 'ir.actions.act_close_wizard_and_reload_view'}

    @api.multi
    def send_mail(self, auto_commit=False):
        self.write({'use_active_domain': False})
        #TODO: we write sent before sending, and ignoring the potential failures
        self.mapped('mass_mailing_line_ids.invoice_id').sudo().write({'sent': True})
        res = super(InvoiceMassMailingWizard, self).send_mail(auto_commit=auto_commit)
        self.create_and_post_message()
        return res

    @api.multi
    @job
    def queue_job_send_mail(self, ctx=None):
        """
        Method for sending emails as queue jobs
        :param ctx: Context is passed as a parameter because contexts is lost in the queue job creation process
        :return: None
        """
        ctx.pop('active_domain', False)
        self.with_context(ctx).send_mail()

    @api.multi
    def create_and_post_message(self):
        """
        Create a res.company.message record and post a notification for partner containing
        information about invoice mailing
        :return: None
        """
        self.ensure_one()

        if self.failed_partners:
            subject = _('Mass invoice mailing: your message has not reached some of the partners.')
            body = _('Your message has not reached these partners: {}').format(self.failed_partners)
        else:
            subject = _('Mass invoice mailing: your message was successfully sent to all partners.')
            body = _('Your message was successfully sent to all partners.')

        uid = self._context.get('uid')
        user = uid and self.env['res.users'].browse(uid).exists()
        if not uid or not user:
            _logger.info('Mass invoice mailing -- message not sent to any user:\n%s', body)
            return

        message = self.env['res.company.message'].sudo().create({
            'body': body,
            'subject': subject,
            'company_id': self.env.user.sudo().company_id.id
        })

        robo_message_values = {
            'body': body,
            'subject': subject,
            'priority': 'medium',
            'front_message': True,
            'rec_model': 'res.company.message',
            'rec_id': message.id,
            'partner_ids': user.partner_id.ids,
            'view_id': self.env.ref('robo.res_company_message_form').id,
        }
        message.robo_message_post(**robo_message_values)

    # Misc methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def name_get(self):
        """Name get for the wizard"""
        return [(rec.id, _('Masinis sąskaitų siuntimas')) for rec in self]

    @api.multi
    def cancel(self):
        """Return user to main view"""
        self.ensure_one()
        return self.env.ref('robo.open_robo_vadovas_client_action').read()[0]


InvoiceMassMailingWizard()
