# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta
from odoo.addons.robo_basic.models.utils import validate_email
from odoo.addons.queue_job.job import job, identity_exact

from odoo import SUPERUSER_ID, _, api, exceptions, fields, models, tools


class PeriodicInvoice(models.Model):
    _name = 'periodic.invoice'

    invoice_id = fields.Many2one('account.invoice', string='Sąskaitos šablonas', required=True,
                                 readonly=True, inverse='_set_invoice_id')
    invoice_ids = fields.One2many('account.invoice', 'periodic_id')
    use_most_recent_as_template = fields.Boolean(string='Naudoti naujausią sąskaitą faktūrą kaip šabloną')
    date = fields.Date(string='Kitos sąskaitos data')
    date_stop = fields.Date(string='Sustabdyti nuo', inverse='_set_date_stop')
    action = fields.Selection([('no', 'Netvirtinti'),
                               ('open', 'Tvirtinti'),
                               ('send', 'Tvirtinti ir išsiųsti')], string='Automatinis veiksmas',
                              default='no', required=True)
    partner_id = fields.Many2one('res.partner', string='Partneris', compute='_compute_partner_id', store=True)
    invoice_number = fields.Char(string='Sąskaitos šablono numeris')
    create_einvoice = fields.Boolean(string='Sukurti eSąskaitą', groups='robo.group_robo_e_invoice')
    interval_number = fields.Integer(string='Intervalas', help='Pakartoti kiekvieną x mėnesį', default=1, required=True)
    informed_about_periodic_invoice_end = fields.Boolean(
        string='Informed about the upcoming end date of the periodic invoice')
    payment_term_days = fields.Integer(string='Mokėjimo terminas dienomis', default=-1)
    running = fields.Boolean(compute='_compute_running')

    @api.multi
    @api.constrains('create_einvoice')
    def _check_create_e_invoice(self):
        """
        Constraints //
        Check if e_invoice can be created by
        validating base constraints.
        :return: None
        """
        for rec in self:
            # For now it's only one check, needs a bigger refactor
            if rec.sudo().create_einvoice and not rec.invoice_id.partner_id.res_partner_bank_e_invoice_id:
                raise exceptions.ValidationError(_('Nenustatytas pagrindinis eSąskaitų gavėjo bankas. '
                                                   'Nueikite į partnerio kortelę, spauskite "eSąskaitų nustatymai" '
                                                   'ir nustatykite banką į kurį turėtų būti siunčiamos eSąskaitos'))

    @api.multi
    def _set_date_stop(self):
        # When the end date is changed we set that the user has not been informed about the upcoming end date yet.
        self.write({'informed_about_periodic_invoice_end': False})

    @api.multi
    def _set_invoice_id(self):
        for rec in self:
            rec.invoice_number = rec.invoice_id.display_name

    @api.depends('invoice_id.partner_id')
    def _compute_partner_id(self):
        for rec in self:
            rec.partner_id = rec.invoice_id.partner_id

    @api.depends('date', 'date_stop')
    def _compute_running(self):
        for rec in self:
            rec.running = True if rec.date and (not rec.date_stop or rec.date <= rec.date_stop) else False

    @api.multi
    @api.constrains('action')
    def constraint_action_send(self):
        """
        Constraint to validate whether all of the related periodic.invoice partner emails are correct
        when the action of periodic invoice is 'send'
        :return: None
        """
        for rec in self:
            rec.assert_email_validity()

    @api.constrains('invoice_id')
    def _check_invoice_id_type(self):
        """ Prevent creation of a periodic invoice where the template is not out_invoice type """
        if any(invoice.type != 'out_invoice' for invoice in self.mapped('invoice_id')):
            raise exceptions.ValidationError(_('Tik kliento sąskaitos gali būti periodinės'))

    @api.constrains('action', 'create_einvoice')
    def _check_invoice_validation_for_einvoice(self):
        """ Allow to select eInvoice creation only if invoice is automatically confirmed """
        if any(rec.action == 'no' and rec.sudo().create_einvoice for rec in self):
            raise exceptions.ValidationError(
                _('eInvoice creation cannot be enabled if the automatic action is set to "Do not confirm"'))

    @api.onchange('date', 'use_most_recent_as_template')
    def _onchange_date(self):
        if self.date:
            following_date = self._get_next_date(
                self.date, self.date if self.use_most_recent_as_template else self.invoice_id.date_invoice)
            return {
                'warning': {
                    'title': _('Įspėjimas'),
                    'message': _('Kita sąskaita-faktūra bus sukurta %s. Dar kita sąskaita-faktūra bus sukurta %s.') % (
                        self.date, following_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)),
                }
            }

    @api.multi
    def assert_email_validity(self, mode='raise'):
        """
        Check whether related partners email is valid, based on mode raise an exception or return True/False
        :param mode: raise - raises the exception, other mode returns boolean value
        :return: True/False
        """
        self.ensure_one()
        if self.action in ['send'] and (not self.partner_id.email or any(
                not validate_email(x.strip()) for x in self.partner_id.email.split(';') if x)):
            if mode in ['raise']:
                raise exceptions.ValidationError(
                    _('Negalite naudoti automatinės sąskaitos išsiuntimo opcijos, '
                      'partneris %s neturi teisingai sukonfigūruoto el.pašto' % self.partner_id.display_name))
            return False
        return True

    @api.multi
    def _get_next_date(self, current_date, invoice_date):
        self.ensure_one()
        if isinstance(current_date, basestring):
            current_date = datetime.strptime(current_date, tools.DEFAULT_SERVER_DATE_FORMAT)
        if isinstance(invoice_date, basestring):
            invoice_date = datetime.strptime(invoice_date, tools.DEFAULT_SERVER_DATE_FORMAT)
        invoice_day = invoice_date.day
        last_day_date = invoice_date + relativedelta(day=31)
        last_day = invoice_date.day == last_day_date.day
        new_day = 31 if last_day else invoice_day
        return current_date + relativedelta(months=self.interval_number, day=new_day)

    @api.multi
    def set_next_date(self):
        self.ensure_one()
        base_date_to_use = self.date if self.use_most_recent_as_template else self.invoice_id.date_invoice
        date = self._get_next_date(self.date, base_date_to_use)
        if self.date_stop and date > datetime.strptime(self.date_stop, tools.DEFAULT_SERVER_DATE_FORMAT):
            self.date = False
        else:
            self.date = date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    def _extra_actions(self, invoice):
        """
        Extra actions to be performed after creating the invoice in the cron job
        :param invoice: account.invoice record -- the newly created invoice
        :return: None
        """
        pass

    @api.multi
    @job
    def run(self):
        """ Create new invoices for periodic invoices """
        for rec in self:
            try:
                cdate = datetime.utcnow()
                if datetime.strptime(rec.date, tools.DEFAULT_SERVER_DATE_FORMAT) > cdate:
                    continue
                if rec.date_stop and datetime.strptime(rec.date_stop, tools.DEFAULT_SERVER_DATE_FORMAT) < cdate:
                    continue
                template_invoice = rec.invoice_id
                if rec.use_most_recent_as_template and rec.invoice_ids:
                    template_invoice = rec.invoice_ids.sorted('date_invoice')[-1]
                invoice_id = template_invoice.copy({
                    'date_invoice': rec.date,
                    'periodic_id': rec.id,
                    'user_id': template_invoice.user_id.id,
                })
                if rec.payment_term_days is not False and rec.payment_term_days >= 0:
                    # if payment term days on periodic.invoice is -1, we let it use default for partner, otherwise we force
                    # the value from periodic.invoice record
                    due_date = datetime.strptime(rec.date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(
                        days=rec.payment_term_days)
                    invoice_id.write({'date_due': due_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)})
                invoice_id.message_unsubscribe([self.env.user.partner_id.id])
                if rec.action in ['open', 'send']:
                    invoice_id.action_invoice_open()
                if rec.action == 'send':
                    if rec.assert_email_validity(mode='validate'):
                        action = invoice_id.action_invoice_sent()
                        if invoice_id.user_id and invoice_id.user_id.id != SUPERUSER_ID:
                            user = invoice_id.user_id
                        elif self.env.user.company_id.vadovas and self.env.user.company_id.vadovas.user_id:
                            user = self.env.user.company_id.vadovas.user_id
                        else:
                            user = self.env.user
                        ctx = action['context']
                        mail = self.sudo(user=user).env['mail.compose.message'].with_context(ctx).create({})
                        mail.onchange_template_id_wrapper()
                        mail.send_mail_action()
                    else:
                        msg = {
                            'body': _('The periodic invoice was not sent on {} due to invalid email set on '
                                      'partner.').format(datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)),
                            'message_type': 'notification',
                            'subtype': 'mail.mt_comment',
                            'priority': 'medium',
                            'front_message': True,
                            'robo_chat': True,
                        }
                        rec.invoice_id.robo_message_post(**msg)
                if rec.action in ['open', 'send'] and rec.create_einvoice and self.env['account.journal'].search_count(
                        [('api_integrated_bank', '=', True), ('currency_id', '=', False)]):
                    date_due = datetime.strptime(invoice_id.date_due, tools.DEFAULT_SERVER_DATE_FORMAT)
                    if (date_due - cdate).days < 3:
                        # Swedbank accepts only a minimum of 3 days between now and due date
                        date_due = cdate + relativedelta(days=3)
                        invoice_id.date_due = date_due.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    ctx = self._context.copy()
                    ctx.update({'invoice_ids': invoice_id.ids, 'custom_name_get': True, 'cron_push_e_invoices': True})
                    wizard_id = self.env['swed.bank.api.import.invoice'].with_context(ctx).create({})
                    wizard_id.with_context(no_warning=True, strict=True).upload_e_invoice_prep()
                rec._extra_actions(invoice_id)
                rec.set_next_date()
                self._cr.commit()
            except:
                import traceback
                message = traceback.format_exc()
                self._cr.rollback()
                if message:
                    self.env['robo.bug'].sudo().create({
                        'user_id': self.env.user.id,
                        'subject': 'Failed to create periodic invoice %s [%s]' % (rec.id, self._cr.dbname),
                        'error_message': message,
                    })
                    self._cr.commit()

    @api.model
    def cron_create_periodic_invoices(self):
        cdate = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        periodic_invoices = self.search([('date', '<=', cdate),
                                         '|', ('date_stop', '=', False), ('date_stop', '>', cdate)])
        for periodic in periodic_invoices:
            periodic.with_delay(channel='root.invoice', eta=30, identity_key=identity_exact).run()

    @api.multi
    def delete(self):
        self.ensure_one()
        self.unlink()

    @api.multi
    def btn_stop(self):
        self.ensure_one()
        self.stop()

    @api.multi
    def stop(self):
        """ Stop the records from creating more entries """
        now = datetime.now()
        for rec in self:
            if rec.date:
                date = datetime.strptime(rec.date, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_stop = min(now, date + relativedelta(days=-1))
                rec.write({
                    'date_stop': date_stop.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                    'date': False,
                })

    @api.multi
    def open_invoices(self):
        self.ensure_one()
        if self.invoice_ids:
            action = self.env.ref('robo.open_client_invoice').read()[0]
            action['domain'] = [('id', 'in', (self.invoice_id + self.invoice_ids).ids)]
            return action
        else:
            raise exceptions.Warning(_('Dar nėra sukurtų periodinių sąskaitų.'))
