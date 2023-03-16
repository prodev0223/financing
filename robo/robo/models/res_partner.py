# -*- coding: utf-8 -*-
from six import iteritems

import logging
import threading

from dateutil.relativedelta import relativedelta
from lxml import etree

from odoo import SUPERUSER_ID, _, api, exceptions, fields, models, registry, tools
from odoo.tools.misc import ustr


_logger = logging.getLogger(__name__)


def get_text(root, element):
    try:
        return root.find(element).text.strip()
    except:
        return ''


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def default_payment_term_days(self):
        company = self.env.user.company_id
        if company.default_payment_term_id:
            return company.default_payment_term_id.num_days
        else:
            return 0

    def default_supplier_payment_term_days(self):
        company = self.env.user.company_id
        if company.default_supplier_payment_term_id:
            return company.default_supplier_payment_term_id.num_days
        else:
            return 0

    image = fields.Binary(inverse='set_image')
    locked = fields.Boolean(string='Partneris užrakintas', readonly=True)
    job_code = fields.Char(string='Pareigų kodas')
    show_balance_account_invoice_document = fields.Boolean(
        string='Rodyti skolą/permoką spausdinant sąskaitą faktūrą')
    company_type = fields.Selection([('person', 'Fizinis asmuo'), ('company', 'Juridinis asmuo')])
    payment_term_days = fields.Integer(string='Kliento mokėjimo terminas dienomis', compute='_payment_term_days',
                                       inverse='_inverse_create_payment_term', default=default_payment_term_days)
    supplier_payment_term_days = fields.Integer(string='Tiekėjo mokėjimo terminas dienomis',
                                                compute='_supplier_payment_term_days',
                                                inverse='_inverse_create_supplier_payment_term',
                                                default=default_supplier_payment_term_days)
    partner_category_id = fields.Many2one('partner.category', string='Partnerio kategorija')
    do_not_embed_einvoice_xml = fields.Boolean(string='Neįterpti e-sąskaitos duomenų sąskaitų PDF failuose')
    show_do_not_embed_xml = fields.Boolean(related='company_id.embed_einvoice_xml', readonly=True)
    parent_id = fields.Many2one('res.partner', string='Susijusi įmonė', inverse='_set_parent_id')
    credit = fields.Monetary(groups="robo_basic.group_robo_free_manager,robo_basic.group_robo_premium_manager")
    debit = fields.Monetary(groups="robo_basic.group_robo_free_manager,robo_basic.group_robo_premium_manager")
    country_id = fields.Many2one(track_visibility='onchange')
    email = fields.Char(track_visibility='onchange')

    # debit_limit = fields.Monetary(groups="robo_basic.group_robo_free_manager,robo_basic.group_robo_premium_manager")

    vz = fields.Boolean(store=False, default=False)
    balance_reconciliation_date = fields.Datetime(string='Paskutinio skolų suderinimo data', copy=False,
                                                  groups='account.group_account_user,'
                                                         'robo.group_robo_see_reconciliation_information_partner_cards')
    balance_reconciliation_send_date = fields.Datetime(string='Paskutinio skolų suderinimo siuntimo data', copy=False,
                                                       groups='account.group_account_user')
    balance_reconciliation_comment = fields.Text(string='Skolų suderinimo akto komentaras', copy=False,
                                                 groups='account.group_account_user')
    balance_reconciliation_attachment_id = fields.Many2one('ir.attachment', string='Paskutinio laiško prisegtukas',
                                                           copy=False, groups='account.group_account_user')
    balance_reconciliation_attachment_ids = fields.One2many('ir.attachment', 'res_id', readonly=True,
                                                            domain=[('res_model', '=', 'res.partner')],
                                                            string='Reconciliation attachments',
                                                            groups='robo.group_robo_see_reconciliation_information_partner_cards,'
                                                                   'robo_basic.group_robo_premium_accountant')
    balance_reconciliation_email = fields.Char(string='Email for balance reconciliations')
    opt_out_robo_mails = fields.Boolean(string='Nesiųsti visų Robo pranešimų')
    opt_out_representation_mails = fields.Boolean(string='Nesiųsti reprezentacinių pranešimų')
    send_company_mails = fields.Boolean(string='Siųsti papildomus kompanijos laiškus', copy=False,
                                        groups='robo_basic.group_robo_premium_accountant')
    has_multiple_bank_accounts = fields.Boolean(compute='_compute_has_multiple_bank_accounts',
                                                search='_search_has_multiple_bank_accounts')

    @api.multi
    def _set_parent_id(self):
        """
        Inverse //
        If current partner has a parent partner
        ensure that current partner is not
        marked as company
        :return: None
        """
        for rec in self:
            if rec.is_company and rec.parent_id:
                rec.is_company = False

    @api.multi
    def _notify_by_email(self, message, force_send=False, send_after_commit=True, user_signature=True):
        """ Method to send email linked to notified messages. The recipients are
        the recordset on which this method is called.

        :param boolean force_send: send notification emails now instead of letting the scheduler handle the email queue
        :param boolean send_after_commit: send notification emails after the transaction end instead of durign the
                                          transaction; this option is used only if force_send is True
        :param user_signature: add current user signature to notification emails """
        if not self.ids:
            return True

        # existing custom notification email
        base_template = None
        if message.model and self._context.get('custom_layout', False):
            base_template = self.env.ref(self._context['custom_layout'], raise_if_not_found=False)
        if not base_template:
            base_template = self.env.ref('due_payments.mail_template_data_notification_email_default')

        base_template_ctx = self._notify_prepare_template_context(message)
        if not user_signature:
            base_template_ctx['signature'] = False
        base_mail_values = self._notify_prepare_email_values(message)

        # check for email_cc
        email_cc = False
        if base_template.email_cc:
            email_cc = base_template.email_cc

        # classify recipients: actions / no action
        if message.model and message.res_id and hasattr(self.env[message.model], '_message_notification_recipients'):
            recipients = self.env[message.model].browse(message.res_id)._message_notification_recipients(message, self)
        else:
            recipients = self.env['mail.thread']._message_notification_recipients(message, self)

        emails = self.env['mail.mail']
        recipients_nbr, recipients_max = 0, 50
        for email_type, recipient_template_values in iteritems(recipients):
            if recipient_template_values['followers']:
                # generate notification email content
                template_fol_values = dict(base_template_ctx,
                                           **recipient_template_values)  # fixme: set button_unfollow to none
                template_fol_values['has_button_follow'] = False
                template_fol = base_template.with_context(**template_fol_values)
                # generate templates for followers and not followers
                fol_values = template_fol.generate_email(message.id, fields=['body_html', 'subject'])
                # send email
                new_emails, new_recipients_nbr = self._notify_send(fol_values['body'], fol_values['subject'],
                                                                   recipient_template_values['followers'],
                                                                   **base_mail_values)
                # update notifications
                self._notify_udpate_notifications(new_emails)

                emails |= new_emails
                recipients_nbr += new_recipients_nbr
            if recipient_template_values['not_followers']:
                # generate notification email content
                template_not_values = dict(base_template_ctx,
                                           **recipient_template_values)  # fixme: set button_follow to none
                template_not_values['has_button_unfollow'] = False
                template_not = base_template.with_context(**template_not_values)
                # generate templates for followers and not followers
                not_values = template_not.generate_email(message.id, fields=['body_html', 'subject'])
                # send email
                new_emails, new_recipients_nbr = self._notify_send(not_values['body'], not_values['subject'],
                                                                   recipient_template_values['not_followers'],
                                                                   **base_mail_values)
                # update notifications
                self._notify_udpate_notifications(new_emails)

                emails |= new_emails
                recipients_nbr += new_recipients_nbr

        if email_cc:
            for m in emails:
                m.email_cc = m.email_cc + ';' + email_cc if m.email_cc else email_cc

        # NOTE:
        #   1. for more than 50 followers, use the queue system
        #   2. do not send emails immediately if the registry is not loaded,
        #      to prevent sending email during a simple update of the database
        #      using the command-line.
        test_mode = getattr(threading.currentThread(), 'testing', False)
        if force_send and recipients_nbr < recipients_max and \
                (not self.pool._init or test_mode):
            email_ids = emails.ids
            dbname = self.env.cr.dbname

            def send_notifications():
                db_registry = registry(dbname)
                with api.Environment.manage(), db_registry.cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    env['mail.mail'].browse(email_ids).send()

            # unless asked specifically, send emails after the transaction to
            # avoid side effects due to emails being sent while the transaction fails
            if not test_mode and send_after_commit:
                self._cr.after('commit', send_notifications)
            else:
                emails.send()

        return True

    def _execute_vz_function(self, method, args):
        """
        Execute VZ function in internal
        :param method: method name
        :param args: dict of arguments to pass to the method
        :return:
        """
        internal = self.env['res.company']._get_odoorpc_object()
        result = internal.execute_kw('rekvizitai', method, (), args)
        if not result:
            return False
        return result

    @api.model
    def execute_vz_function(self, method, args):
        """
        Execute VZ function in internal (wrapper)
        :param method: method name
        :param args: dict of arguments to pass to the method
        :return:
        """
        try:
            res = self._execute_vz_function(method, args)
        except:
            res = False
        return res

    @api.multi
    def vz_read(self):
        self.ensure_one()
        code = self.kodas
        category_obj = self.env['res.partner.category']
        result = self.env['res.partner'].execute_vz_function('vz_read', {'code': code, 'user': self.env.user.login,
                                                                         'database': self.env.cr.dbname})
        if not result:
            return False
        xml = result.encode('utf-8')
        root = etree.fromstring(xml)
        status = get_text(root, 'status')
        if status == 'success':
            companies = root.find('companies').findall('company')
            if not companies:
                return False
            for company in companies:
                code = get_text(company, 'code')
                categories = get_text(company, 'categories')
                partner_cat_ids = []
                for category in categories.split(';'):
                    category = category.strip()
                    partner_cat_id = category_obj.search([('name', '=', category)], limit=1)
                    if not partner_cat_id:
                        partner_cat_id = category_obj.create({'name': category})
                    partner_cat_ids.append(partner_cat_id.id)
                address_rest = get_text(company, 'addressRest')
                if address_rest:
                    street_ext = '-' + address_rest
                else:
                    street_ext = ''
                vals = {
                    'kodas': code,
                    'name': get_text(company, 'title'),
                    'city': get_text(company, 'city'),
                    'street': get_text(company, 'street') + ' ' + get_text(company, 'houseNo') + street_ext,
                    # 'street2': get_text(company, 'addressRest'),
                    'zip': get_text(company, 'postCode'),
                    'category_id': [(6, 0, partner_cat_ids)],
                    'phone': get_text(company, 'phone'),
                    'mobile': get_text(company, 'mobile'),
                    'fax': get_text(company, 'fax'),
                    'website': get_text(company, 'website'),
                    'email': get_text(company, 'email'),
                    'vat': get_text(company, 'pvmCode'),
                    'is_company': True,
                    'company_type': 'company',
                    'country_id': self.env.ref('base.lt').id,
                }
                self.sudo().write(vals)
                return True
        return False

    @api.model
    def vz_read_dict(self, kodas):
        code = kodas
        if not code:
            return False
        category_obj = self.env['res.partner.category']

        result = self.execute_vz_function('vz_read',
                                          {'code': code, 'user': self.env.user.login, 'database': self.env.cr.dbname})
        if not result:
            return False
        xml = result.encode('utf-8')
        root = etree.fromstring(xml)
        status = get_text(root, 'status')
        if status == 'success':
            companies = root.find('companies').findall('company')
            if not companies:
                return False
            for company in companies:
                code = get_text(company, 'code')
                categories = get_text(company, 'categories')
                partner_cat_ids = []
                for category in categories.split(';'):
                    category = category.strip()
                    partner_cat_id = category_obj.search([('name', '=', category)], limit=1)
                    if not partner_cat_id:
                        partner_cat_id = category_obj.create({'name': category})
                    partner_cat_ids.append(partner_cat_id.id)
                address_rest = get_text(company, 'addressRest')
                if address_rest:
                    street_ext = '-' + address_rest
                else:
                    street_ext = ''
                vat = get_text(company, 'pvmCode')
                partner_id = self.env['res.partner'].search([('kodas', '=', code), ('vat', '=', vat)], limit=1)
                if not partner_id:
                    partner_id = self.env['res.partner'].search([('kodas', '=', code)], limit=1)
                vals = {
                    'kodas': code,
                    'name': get_text(company, 'title'),
                    'city': get_text(company, 'city'),
                    'street': get_text(company, 'street') + ' ' + get_text(company, 'houseNo') + street_ext,
                    # 'street2': get_text(company, 'addressRest'),
                    'zip': get_text(company, 'postCode'),
                    'category_id': [(6, 0, partner_cat_ids)],
                    'phone': get_text(company, 'phone'),
                    'mobile': get_text(company, 'mobile'),
                    'fax': get_text(company, 'fax'),
                    'website': get_text(company, 'website'),
                    'email': get_text(company, 'email'),
                    'vat': get_text(company, 'pvmCode'),
                    'is_company': True,
                    'company_type': 'company',
                    'country_id': self.env.ref('base.lt').id,
                }
                if partner_id:
                    partner_id.write(vals)
                vals['partner_id'] = partner_id.id
                return vals
        return False

    @api.model
    def vz_search(self, name):
        if not name or len(name) <= 4:
            return False
        result = self.execute_vz_function('vz_search', {'name': name})
        if not result:
            return False
        xml = result.encode('utf-8')
        root = etree.fromstring(xml)
        status = get_text(root, 'status')
        result = []
        if status == 'success':
            companies = root.find('companies').findall('company')
            if not companies:
                return []
            for company in companies:
                code = get_text(company, 'code')
                name = get_text(company, 'title')
                result.append({
                    'name': name,
                    'kodas': code,
                })
        return result

    @api.model
    def default_get(self, fields):
        res = super(ResPartner, self).default_get(fields)
        if self._context.get('default_email', False):
            res['email'] = self._context.get('default_email')
        if self._context.get('default_company_type', False):
            company_type = self._context.get('default_company_type', False)
            if company_type == 'company':
                res['is_company'] = True
            else:
                res['is_company'] = False
        return res

    @api.model
    def simple_vat_check(self, country_code, vat_number):
        '''
        ROBO OVERRIDED FROM ADDONS BASE VAT
        Skip country code check for VAT.
        '''
        res = super(ResPartner, self).simple_vat_check(country_code, vat_number)
        if not res and not ustr(country_code).encode('utf-8').isalpha():
            return True
        return res

    @api.model
    def get_lock_status_js(self, ids):
        partners = self.browse(ids)
        if self.env['account.move.line'].search_count([('partner_id', 'in', partners.ids)]):
            body = _('Partneris  turi susijusių duomenų, ' \
                     'nerekomenduojama modifikuoti šio partnerio, ar tikrai norite keisti?')
        else:
            body = _('Ar tikrai norite keisti?')
        return True, body

    @api.multi
    def overpay_transfer_request(self):
        self.ensure_one()
        if not (self.env.user.is_accountant() or self.env.user.has_group('robo.group_overpay_transfer_requests')):
            raise exceptions.AccessError(_('User does not have the correct rights to form overpay transfer request'))
        force_lang = self.lang or self.env.user.lang or 'lt_LT'
        # TODO: Remove following lines if ru_RU translations are introduced;
        if force_lang == 'ru_RU':
            force_lang = 'lt_LT'
        ctx = {
            'partner_ids': self.mapped('id'),
            'default_all_partners': False,
            'default_force_lang': force_lang,
        }
        return {
            'context': ctx,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'overpay.transfer.request.wizard',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.multi
    def change_lock_status(self):
        if not self.env.user.is_accountant():
            raise exceptions.AccessError(_('Tik buhalteriai gali atlikti šį veiksmą.'))
        self.write({'locked': True if self._context.get('lock') else False})

    @api.multi
    def write(self, vals):
        for rec in self:
            if rec.locked and not self.env.user.is_accountant():
                raise exceptions.AccessError(_('Negalite koreguoti užrakinto partnerio.'
                                               ' Kreipkitės į jus aptarnaujantį buhalterį'))
        res = super(ResPartner, self).write(vals)
        return res

    @api.one
    def set_image(self):
        if self.image:
            if self.employee_ids:
                employee_id = self.employee_ids[0]
                if employee_id:
                    employee_id.with_context(skip_inverse=True).write({'image': self.image})

    @api.multi
    def toggle_active(self):
        if not self.env.user.is_manager():
            for rec in self:
                if len(rec.employee_ids) > 0 and rec.active:
                    raise exceptions.UserError(
                        _('Neturite pakankamai teisių suarchyvuoti partnerį, kuris turi darbuotojo kortelę'))
        return super(ResPartner, self).toggle_active()

    @api.multi
    @api.constrains('street', 'street2', 'zip', 'city', 'state_id', 'country_id')
    def _check_contact_info(self):
        if not self.env.user.is_manager() and not self.env.user.is_hr_manager():
            for rec in self:
                if rec.user_ids and self.env.user not in rec.user_ids:
                    raise exceptions.ValidationError(_('Negalite keisti ne savo kliento kortelės'))

    @api.constrains('email')
    def _check_email(self):
        for rec in self:
            if any(employee.work_email != rec.email for employee in rec.sudo().employee_ids):
                raise exceptions.ValidationError(_('You can only edit employee\'s email from the employee card'))
            if any(user.login != rec.email for user in rec.sudo().user_ids):
                raise exceptions.ValidationError(_('You can only edit user\'s email from the employee card'))

    @api.multi
    @api.constrains('name')
    def _check_name(self):
        for rec in self:
            if any(employee.name != rec.name for employee in rec.employee_ids):
                raise exceptions.ValidationError(_('Negalite keisti partnerio vardo, kuris turi susijusį darbuotoją'))

    @api.multi
    @api.depends('property_payment_term_id')
    def _payment_term_days(self):
        for rec in self:
            if rec.property_payment_term_id:
                rec.payment_term_days = rec.property_payment_term_id.num_days

    @api.multi
    @api.depends('property_supplier_payment_term_id')
    def _supplier_payment_term_days(self):
        for rec in self:
            if rec.property_supplier_payment_term_id:
                rec.supplier_payment_term_days = rec.property_supplier_payment_term_id.num_days

    @api.one
    def _inverse_create_payment_term(self):
        new_payment_term_days = self.payment_term_days
        self.property_payment_term_id = self.env['account.payment.term'].get_or_create_payment_term_by_days(
            new_payment_term_days)

    @api.one
    def _inverse_create_supplier_payment_term(self):
        new_supplier_payment_term_days = self.supplier_payment_term_days
        self.property_supplier_payment_term_id = self.env['account.payment.term'].get_or_create_payment_term_by_days(
            new_supplier_payment_term_days)

    @api.multi
    def get_formview_id(self):
        """ Return an view id to open the document ``self`` with. This method is
            meant to be overridden in addons that want to give specific view ids
            for example.
        """
        view_ref = self._context.get('form_view_ref', False)
        if view_ref:
            view_id = self.env.ref(view_ref, raise_if_not_found=False)
            if not view_id:
                view_id = self.env.ref(self._module + '.' + view_ref, raise_if_not_found=False)
            if view_id:
                return view_id.id
        return False

    @api.multi
    def get_formview_action(self):
        """ Return an action to open the document ``self``. This method is meant
            to be overridden in addons that want to give specific view ids for
            example.
        """
        view_id = self.get_formview_id()
        view_type = 'form'  # self._context.get('form_view_type', 'form')
        view_mode = self._context.get('form_view_mode', 'form')

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_type': view_type,
            'view_mode': view_mode,
            'views': [(view_id, view_type)],
            'target': 'current',
            'res_id': self.id,
            'context': dict(self._context),
        }

    @api.model
    def get_roboNeedaction_count(self):
        """ compute the number of robo front messages of the current user """
        robo_message_subtype = self.env.ref('robo.mt_robo_front_message')
        if self.env.user.partner_id:
            self.env.cr.execute("""
                    SELECT count(*) as needaction_count
                    FROM mail_message_res_partner_needaction_rel R
                    INNER JOIN mail_message M ON M.id = R.mail_message_id and M.front_message = true and M.subtype_id = %s
                    WHERE R.res_partner_id = %s AND (R.is_read = false OR R.is_read IS NULL)""",
                                (robo_message_subtype.id, self.env.user.partner_id.id,))
            res = self.env.cr.dictfetchall()
            if res:
                return res[0].get('needaction_count')
        _logger.error('Call to needaction_count without partner_id')
        return 0

    @api.model
    def get_lastRoboNeedaction_messages(self):
        """ find last Robo front messages"""

        def convert_to_local_date_str(utc_date_str, offset):
            non_offset = fields.Datetime.from_string(utc_date_str)
            if offset[0] == '-':
                to_offset_time = non_offset - relativedelta(hours=int(offset[1:3]), minutes=int(offset[3:]))
            else:
                to_offset_time = non_offset + relativedelta(hours=int(offset[1:3]), minutes=int(offset[3:]))
            return to_offset_time.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

        robo_message_subtype = self.env.ref('robo.mt_robo_front_message')
        if self.env.user.partner_id:
            self.env.cr.execute("""
                            SELECT M.id, M.body, M.subject, M."priority", M."date", M.rec_id, M.rec_model, M.view_id, M.action_id
                            FROM mail_message_res_partner_needaction_rel R
                            INNER JOIN mail_message M ON M.id = R.mail_message_id and M.front_message = true and M.subtype_id = %s
                            WHERE R.res_partner_id = %s AND (R.is_read = false OR R.is_read IS NULL)
                            ORDER BY R.id DESC 
                            """,
                                (robo_message_subtype.id, self.env.user.partner_id.id,))
            rows = self.env.cr.dictfetchall()
            offset = self.env.user.tz_offset
            if offset:
                for row in rows:
                    if row['date'] and row['date'] != '':
                        row['date'] = convert_to_local_date_str(row['date'], offset)
            # for row in rows:
            #     row['body'] = tools.plaintext2html(row['body'])
            return rows
        _logger.error('Call to needaction_count without partner_id')
        return 0

    @api.multi
    @api.constrains('country_id', 'is_company')
    def _check_country(self):
        for rec in self:
            if rec.is_company and not rec.country_id:
                raise exceptions.ValidationError(_("Juridinis asmuo turi turėti šalį"))

    @api.model
    def create(self, vals):
        if 'email' in vals and not vals['email']:
            vals.pop('email')
        res = super(ResPartner, self).create(vals)
        if not res.country_id and res.company_type == 'person':
            country_id = self.env['res.country'].search([('code', '=', 'LT')])
            if country_id:
                res.write({'country_id': country_id.id})
        return res

    @api.multi
    def btn_send_debt_reconciliation_act(self):
        """ Returns reconciliation debt wizard """
        if not self.env.user.is_accountant():
            raise exceptions.AccessError(_('Tik buhalteris gali pasiekti šią ataskaitą'))
        action = self.env.ref('robo.open_debt_send_action_back').read()[0]
        partner_languages = list(set(self.mapped('lang')))
        if False in partner_languages:
            partner_languages.remove(False)
        force_lang = partner_languages[0] if len(partner_languages) == 1 else self.env.user.lang or 'lt_LT'
        # TODO: Remove following lines if ru_RU translations are introduced;
        if force_lang == 'ru_RU':
            force_lang = 'lt_LT'
        ctx = {
            'default_filtered_partner_ids': [(6, 0, self.ids)],
            'default_display_partner': 'filter',
            'default_target_move': 'posted',
            'default_report_type': 'debt_act',
            'default_detail_level': 'detail',
            'default_force_lang': force_lang,
        }
        action.update(context=ctx, target='new')
        return action

    @api.model
    def create_action_multi_send_debt_reconciliation_act(self):
        action = self.env.ref('robo.action_multi_send_debt_reconciliation_act')
        if action:
            action.create_action()

    @api.multi
    @api.depends('bank_ids')
    def _compute_has_multiple_bank_accounts(self):
        for rec in self:
            if len(rec.mapped('bank_ids')) > 1:
                rec.has_multiple_bank_accounts = True

    @api.model
    def _search_has_multiple_bank_accounts(self, operator, operand):
        if (operator == '=' and operand is True) or (operator == '!=' and operand is False):
            partners = self.search([]).filtered(lambda p: len(p.mapped('bank_ids')) > 1)
            return [('id', 'in', partners.ids)]
        else:
            return []
