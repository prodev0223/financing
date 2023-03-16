# -*- coding: utf-8 -*-

import uuid
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import _, api, exceptions, fields, models, tools


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def random_unique_code(self):
        return uuid.uuid4()

    show_remaining_leaves = fields.Boolean(compute='_show_remaining_leaves')
    remaining_leaves_label = fields.Char(compute='_format_remaining_leaves')
    show_personal_info = fields.Boolean(compute='_show_personal_info')
    personal_appointment_ids = fields.Html(string='Sutartys', compute='_payslip_tables')
    personal_slip_ids = fields.Html(string='Atlyginimų istorija', compute='_payslip_tables')
    unique_wizard_id = fields.Text(default=random_unique_code, store=False, sequence=100)
    attachment_drop_lock = fields.Boolean(compute='_compute_attachment_drop_lock')
    user_attachment_ids = fields.Many2many('ir.attachment', compute='_compute_all_attachments', string='Prisegtukai',
                                           readonly=False)
    show_advance_payment = fields.Boolean(compute='_show_advance_payment')
    front_slip_ids = fields.One2many('hr.payslip', 'employee_id', domain=[('state', '=', 'done')],
                                     string='Algalapiai', readonly=True, groups="hr_payroll.group_hr_payroll_user",
                                     sequence=100,
                                     )
    team_id = fields.Many2one('crm.team', string='Pardavimų komanda', compute='_team_id', inverse='_set_team_id',
                              sequence=100,
                              )
    page_no = fields.Integer(string='Puslapis', groups='robo_basic.group_robo_premium_accountant', default=1,
                             sequence=100,
                             )
    pdf = fields.Binary(compute='_pdf', groups='robo_basic.group_robo_premium_accountant')
    show_pdf = fields.Boolean(compute='_show_pdf', groups='robo_basic.group_robo_premium_accountant')
    pdf_count = fields.Integer(compute='_pdf_count', groups='robo_basic.group_robo_premium_accountant')
    display_leaves_summary = fields.Boolean(compute='_display_leaves_summary')
    message_ids = fields.One2many(domain=lambda self: self.get_message_ids_domain(), sequence=100)
    show_messaging_footer = fields.Boolean(compute='_show_messaging_footer')
    attach_board = fields.Boolean(compute='show_attachment_board')
    job_code = fields.Char(string='Pareigų kodas')
    education_year_ids = fields.One2many(
        'hr.employee.education.year',
        'employee_id',
        string='Mokslo/Studijų periodas',
        groups="robo_basic.group_robo_free_manager,"
               "robo_basic.group_robo_premium_manager,"
               "robo_basic.group_robo_hr_manager",
        sequence=100,
    )
    is_underage = fields.Boolean(string='Nepilnametis', compute='_compute_is_underage')
    is_child = fields.Boolean(string='Vaikas', compute='_compute_is_underage')
    is_teenager = fields.Boolean(string='Paauglys', compute='_compute_is_underage')
    date_employee_becomes_18 = fields.Date(string='Date employee becomes 18',
                                           compute='_compute_date_employee_becomes_18')

    show_personal_info_tab = fields.Boolean(compute="_compute_show_personal_info_tab")
    personal_identification_id = fields.Char(string="Asmens kodas", compute="_compute_personal_info")
    personal_street = fields.Char(compute='_compute_personal_info')
    personal_street2 = fields.Char(compute='_compute_personal_info')
    personal_zip = fields.Char(compute='_compute_personal_info')
    personal_city = fields.Char(compute='_compute_personal_info')
    personal_state_id = fields.Many2one('res.country.state', compute='_compute_personal_info')
    personal_country_id = fields.Many2one('res.country', compute='_compute_personal_info')
    personal_nationality_id = fields.Many2one('res.country', string='Pilietybė', compute="_compute_personal_info")
    personal_bank_account_id = fields.Many2one('res.partner.bank', compute="_compute_personal_info")
    personal_birthday = fields.Date(compute="_compute_personal_info")
    personal_gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female')
    ], compute="_compute_personal_info")
    personal_last_medical_certificate_date = fields.Date(compute="_compute_personal_info")
    personal_next_medical_certificate_date = fields.Date(compute="_compute_personal_info")
    signup_valid = fields.Boolean(related='address_home_id.signup_valid')
    show_employment_banner = fields.Boolean(compute='_compute_show_employment_banner')
    employee_child_ids = fields.One2many('hr.employee.child', 'employee_id', string='Employee children',
                                         groups='robo_basic.group_robo_hr_manager,robo_basic.group_robo_premium_manager')
    account_id = fields.Many2one(sequence=100)
    address_home_id = fields.Many2one(sequence=100)
    address_id = fields.Many2one(sequence=100)
    child_ids = fields.One2many(sequence=100)
    children = fields.Integer(sequence=100)
    coach_id = fields.Many2one(sequence=100)
    color = fields.Integer(sequence=100)
    contract_ids = fields.One2many(sequence=100)
    darbdavio_sodra_proc = fields.Float(sequence=100)
    darbuotojo_pensijos_proc = fields.Float(sequence=100)
    darbuotojo_sveikatos_proc = fields.Float(sequence=100)
    identification_id = fields.Char(sequence=100)
    image = fields.Binary(sequence=100)
    image_small = fields.Binary(sequence=100)
    image_medium = fields.Binary(sequence=100)
    last_login = fields.Datetime(sequence=100)
    medic_exam = fields.Date(sequence=100)
    message_partner_ids = fields.Many2many(sequence=100)
    message_needaction = fields.Boolean(sequence=100)
    message_last_post = fields.Datetime(sequence=100)
    message_is_follower = fields.Boolean(sequence=100)
    message_follower_ids = fields.One2many(sequence=100)
    message_channel_ids = fields.Many2many(sequence=100)
    name_related = fields.Char(sequence=100)
    notes = fields.Text(sequence=100)
    parent_id = fields.Many2one(sequence=100)
    passport_id = fields.Char(sequence=100)
    place_of_birth = fields.Char(sequence=100)
    resource_id = fields.Many2one(sequence=100)
    sinid = fields.Char(sequence=100)
    ssnid = fields.Char(sequence=100)
    slip_ids = fields.One2many(sequence=100)
    state_id = fields.Many2one(sequence=100)
    timesheet_cost = fields.Float(sequence=100)
    vehicle = fields.Char(sequence=100)
    vehicle_distance = fields.Integer(sequence=100)
    mobile_phone = fields.Char(sequence=100)
    marital = fields.Selection(sequence=100)
    show_password_reset_button_sign_up_valid = fields.Boolean(string='Show password reset button for signup valid',
                                                              compute='_compute_show_password_reset_button_sign_up_valid_invalid')
    show_password_reset_button_sign_up_invalid = fields.Boolean(string='Show password reset button for signup invalid',
                                                                compute='_compute_show_password_reset_button_sign_up_valid_invalid')

    @api.multi
    @api.depends('robo_access')
    def _compute_show_password_reset_button_sign_up_valid_invalid(self):
        for rec in self:
            if rec.robo_access and rec.signup_valid:
                rec.show_password_reset_button_sign_up_valid = True
            if rec.robo_access and not rec.signup_valid:
                rec.show_password_reset_button_sign_up_invalid = True

    @api.multi
    def _compute_show_employment_banner(self):
        is_manager = self.env.user.is_manager() or self.env.user.has_group('robo_basic.group_robo_edocument_manager')
        if not is_manager:
            return
        for rec in self:
            if rec.sudo().contract_id or rec.type == 'mb_narys':
                continue
            rec.show_employment_banner = True

    @api.multi
    def get_allowed_free_child_support_free_days_amount(self, date):
        self.ensure_one()
        return self.employee_child_ids.get_allowed_parental_leaves_per_month(date)

    @api.multi
    def get_list_of_children_by_age_and_disability(self, date):
        self.ensure_one()
        return self.employee_child_ids.get_number_of_children_by_age_and_disability(date)

    @api.one
    @api.depends('birthday')
    def _compute_is_underage(self):
        is_child = is_teenager = False
        forced_date = self._context.get('date')
        date_dt = datetime.strptime(forced_date, tools.DEFAULT_SERVER_DATE_FORMAT) if forced_date else datetime.utcnow()
        if self.sudo().birthday:
            birthday_dt = datetime.strptime(self.sudo().birthday, tools.DEFAULT_SERVER_DATE_FORMAT)
            employee_age = relativedelta(date_dt, birthday_dt).years
            is_child = employee_age < 16
            is_teenager = 16 <= employee_age < 18
        self.is_underage = is_child or is_teenager
        self.is_child = is_child
        self.is_teenager = is_teenager

    @api.multi
    @api.depends('birthday')
    def _compute_date_employee_becomes_18(self):
        for rec in self:
            birthday = rec.sudo().birthday
            if not birthday:
                continue
            birthday_dt = datetime.strptime(birthday, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_employee_becomes_18 = birthday_dt + relativedelta(years=18)
            rec.date_employee_becomes_18 = date_employee_becomes_18.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    def open_change_user_partner_wizard(self):
        self.ensure_one()
        wizard_id = self.env['change.user.partner.of.employee.wizard'].create({
            'employee_id': self.id,
            'user_id': self.user_id.id,
            'partner_id': self.address_home_id.id,
        })
        return {
            'name': _('Pakeisti vartotoją ir partnerį'),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': False,
            'res_model': 'change.user.partner.of.employee.wizard',
            'res_id': wizard_id.id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.multi
    def open_new_employee_internship_start_wizard(self):
        self.ensure_one()
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'start.employee.internship',
            'res_id': self.env['start.employee.internship'].create({'employee_id': self.id}).id,
            'view_id': self.env.ref('robo.start_employee_internship_view_form').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.one
    def show_attachment_board(self):
        if self.env.user.is_manager() or self.env.user.is_hr_manager():
            self.attach_board = True
        elif self.env.user.employee_ids and self.id == self.env.user.employee_ids[0].id:
            self.attach_board = True
        else:
            self.attach_board = False

    @api.multi
    def get_managing_departments(self):
        return self.env['hr.department'].sudo().search([
            ('manager_id', 'in', self.ids)
        ])

    @api.model
    def should_see_all_other_employees(self):
        return self.env.user.is_hr_manager() or self.env.user.is_manager()

    def employee_action_domain(self):
        domain = []
        if self.sudo().env.user.company_id.worker_policy == 'enabled':
            user = self.env.user
            is_user = user.is_user()
            should_see_all_employees = self.should_see_all_other_employees()
            if is_user and not should_see_all_employees:
                user_employee_records = user.employee_ids
                managing_departments = user_employee_records.get_managing_departments()
                domain += [
                    '|',
                    ('department_id', 'in', managing_departments.ids),
                    ('id', 'in', user_employee_records.ids)
                ]
        action = self.env.ref('robo.open_employees_action')
        action_ret = action.read()[0]
        action_ret['domain'] = domain
        return action_ret

    @api.constrains('parent_id')
    def _check_parent_id(self):
        pass

    def get_message_ids_domain(self):
        domain = [('model', '=', 'hr.employee')]
        if not self.env.user.is_accountant():
            domain.append(('front_message', '=', True))
        if not self.env.user.is_premium_manager():
            domain.append(('rec_id', 'in', self.env.user.employee_ids.ids))
        return domain

    @api.one
    def _show_messaging_footer(self):
        if self.env.user.is_premium_manager() or self.user_id.id == self.env.user.id:
            self.show_messaging_footer = True

    @api.one
    def _display_leaves_summary(self):
        if self.sudo().type == 'mb_narys':
            self.display_leaves_summary = False
        elif self.env.user.is_manager():
            self.display_leaves_summary = True
        elif self.env.user.is_hr_manager():
            self.display_leaves_summary = True
        elif self.env.user.is_employee and (len(self.env.user.employee_ids) == 1 and
                                            self.env.user.employee_ids.id == self.id):
            self.display_leaves_summary = True
        else:
            self.display_leaves_summary = False

    @api.one
    @api.depends('user_attachment_ids')
    def _pdf_count(self):
        self.pdf_count = self.env['ir.attachment'].search([('res_model', '=', 'hr.employee'),
                                                           ('res_id', '=', self.id),
                                                           ('mimetype', '=', 'application/pdf')], count=True)

    @api.one
    @api.depends('pdf_count', 'user_attachment_ids')
    def _show_pdf(self):
        if self.pdf_count > 0:
            self.show_pdf = True
        else:
            self.show_pdf = False

    @api.multi
    def action_reset_password(self):
        server_url = self.sudo().env['ir.config_parameter'].get_param('web.base.url')
        if server_url and 'localhost' in server_url:
            raise exceptions.UserError(_('Neteisingi nustatymai. Kreipkitės į sistemos administratorių.'))
        if self.env.user.is_manager() or self.env.user.is_hr_manager():
            for rec in self:
                if rec.user_id and rec.user_id.active:
                    rec.sudo().user_id.with_context(create_user=rec.user_id.state == 'new').action_reset_password()
                else:
                    raise exceptions.UserError(_('Vartotojas nėra aktyvus'))

    @api.model
    def server_action_print_contract_f(self):
        action = self.env.ref('robo.server_action_print_contract')
        if action:
            action.create_action()

    @api.multi
    def contract_wizard(self):
        if len(self) > 1:
            raise exceptions.Warning(_('Ši operacija negalima keliems darbuotojams tuo pačiu metu!'))
        contract = self.env['hr.contract'].search([('employee_id', '=', self.id)], limit=1)
        appointment = contract.appointment_ids.sorted(lambda x: x.date_start, reverse=True)[0] \
            if contract.appointment_ids else False
        if not contract or not appointment:
            raise exceptions.Warning(_('Negalite atlikti šio veiksmo, darbuotojas neturi darbo sutarties.'))

        wizard_id = self.env['print.contract.wizard'].create({
            'employee_id': self.id,
            'contracts': contract.id,
            'contract_date': appointment.date_start,
            'appointments': appointment.id,
            'contract_liabilities': contract.contract_liabilities,
            'contract_conditions': contract.contract_conditions,
        })
        return {
            'name': _('Spausdinti darbo sutartį'),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': False,
            'res_model': 'print.contract.wizard',
            'res_id': wizard_id.id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.one
    @api.depends('page_no', 'show_pdf', 'pdf_count', 'user_attachment_ids')
    def _pdf(self):
        if not self.show_pdf:
            return
        pdf_files = self.env['ir.attachment'].search([('res_model', '=', 'hr.employee'),
                                                      ('res_id', '=', self.id),
                                                      ('mimetype', '=', 'application/pdf')])
        if self.page_no < 0 or self.page_no > len(pdf_files):
            page_no = 1
        else:
            page_no = self.page_no
        page_no -= 1
        if not pdf_files:
            return
        self.pdf = pdf_files[page_no].datas

    @api.multi
    def next_page(self):
        pdf_count = self.pdf_count
        if self.page_no < pdf_count:
            self.page_no += 1
        else:
            self.page_no = 1

    @api.multi
    def previous_page(self):
        if self.page_no > 1:
            self.page_no -= 1
        else:
            self.page_no = self.pdf_count

    @api.one
    @api.depends('user_id.team_id')
    def _team_id(self):
        self.team_id = self.sudo().user_id.team_id.id

    @api.one
    def _set_team_id(self):
        if self.env.user.is_manager():
            self.sudo().user_id.write({'team_id': self.team_id.id, 'sale_team_id': self.team_id.id})

    @api.one
    def _show_advance_payment(self):
        if self.env.user.is_manager() or self.env.user.id == self.sudo().user_id.id or self.env.user.is_hr_manager():
            self.show_advance_payment = True
        else:
            self.show_advance_payment = False

    @api.depends('name')
    def _show_personal_info(self):
        """ Check if contract/payslip information should be displayed on the employee card """
        # Only manager can see the normal tab, but HR manager should be able to see info for employees with the same
        # conditions as employees can see their own.
        is_manager = self.env.user.is_manager()
        is_hr_manager = self.env.user.is_hr_manager()
        for rec in self:
            if not is_manager and rec.sudo().user_id and rec.sudo().user_id == rec.env.user:
                rec.show_personal_info = True
            elif is_hr_manager:
                rec.show_personal_info = True
            else:
                rec.show_personal_info = False

    @api.depends('name')
    def _compute_show_personal_info_tab(self):
        """ Check if per-user personal information tab should be displayed on employee card """
        # Managers and HR managers already see the normal tab, so new personal info tab should only be shown to users
        # that match the employee
        if not (self.env.user.is_manager() or self.env.user.is_hr_manager()):
            for rec in self:
                if rec.sudo().user_id and rec.sudo().user_id.id == self.env.user.id:
                    rec.show_personal_info_tab = True

    def _payslip_tables(self):
        for rec in self:
            if not rec.show_personal_info:
                rec.personal_appointment_ids = False
                rec.personal_slip_ids = False
                continue
            Qweb = self.env['ir.qweb']
            lines = ''
            for appointment_id in rec.sudo().appointment_ids:
                lines += Qweb.render('robo.robo_employee_contracts_table_line', {
                    'contract_name': appointment_id.contract_id.name,
                    'name': appointment_id.name,
                    'job': appointment_id.job_id.name,
                    'struct': appointment_id.struct_id.name,
                    'date_start': appointment_id.date_start,
                    'date_end': appointment_id.date_end,
                    'wage': appointment_id.wage,
                    'wage_neto': appointment_id.neto_monthly if appointment_id.struct_id.code != 'VAL' else False,
                })
            rec.personal_appointment_ids = Qweb.render('robo.robo_employee_contracts_table', {"table_body": lines})
            lines = ''
            slip_ids = rec.sudo().slip_ids.filtered(lambda r: r.state == 'done' and
                                                              (r.payslip_run_id.state == 'close' or
                                                               r.imported or
                                                               r.employee_is_being_laid_off))
            for slip_id in slip_ids:
                print_payslip_note = 'print_payslip_note' if slip_id.payslip_run_id.state == 'close' or \
                                                             slip_id.employee_is_being_laid_off else False
                print_payslip = 'print_payslip' if self.env.user.is_hr_manager() and print_payslip_note else False
                lines += Qweb.render('robo.robo_employee_payslip_table_line', {
                    'number': slip_id.number,
                    'date_from': slip_id.date_from,
                    'date_to': slip_id.date_to,
                    'atostogu_likutis': slip_id.atostogu_likutis,
                    'bruto': slip_id.bruto,
                    'moketinas': slip_id.moketinas,
                    'id': slip_id.id,
                    'print_payslip': print_payslip,
                    'print_payslip_note': print_payslip_note,
                })
            rec.personal_slip_ids = Qweb.render('robo.robo_employee_payslip_table', {"table_body": lines})

    @api.multi
    def _compute_personal_info(self):
        for rec in self:
            if rec.show_personal_info_tab:
                rec.personal_identification_id = rec.sudo().identification_id
                rec.personal_street = rec.sudo().street
                rec.personal_street2 = rec.sudo().street2
                rec.personal_zip = rec.sudo().zip
                rec.personal_city = rec.sudo().city
                rec.personal_state_id = rec.sudo().state_id
                rec.personal_country_id = rec.sudo().country_id
                rec.personal_nationality_id = rec.sudo().nationality_id
                rec.personal_bank_account_id = rec.sudo().bank_account_id
                rec.personal_birthday = rec.sudo().birthday
                rec.personal_gender = rec.sudo().gender
                rec.personal_last_medical_certificate_date = rec.sudo().last_medical_certificate_date
                rec.personal_next_medical_certificate_date = rec.sudo().next_medical_certificate_date

    @api.multi
    def open_cash_balance(self):
        self.ensure_one()
        return self.address_home_id.with_context(active_ids=self.address_home_id.ids).open_cashbalance_wizard()

    @api.one
    def _compute_all_attachments(self):
        current_user = self.env.user.employee_ids[0].id if self.env.user.employee_ids else False
        if self.check_access_rights('read', raise_exception=False) and \
                (self.env.user.is_manager() or self.env.user.is_hr_manager() or
                 (current_user and current_user == self.id)):
            ids = self.env['ir.attachment'].sudo().search(
                [('res_model', '=', 'hr.employee'), ('res_id', '=', self.id), ('res_field', '=', False)]).ids

            self.user_attachment_ids = [(4, doc_id) for doc_id in ids]
        else:
            self.user_attachment_ids = []

    @api.one
    def _compute_attachment_drop_lock(self):
        self.attachment_drop_lock = True
        if self.env.user.is_manager() or self.env.user.is_hr_manager():
            self.attachment_drop_lock = False

    @api.multi
    @api.depends('name', 'type')
    def _show_remaining_leaves(self):
        for rec in self:
            if rec.sudo().type == 'mb_narys':
                rec.show_remaining_leaves = False
            elif rec.env.user.is_manager() or rec.env.user.is_hr_manager():
                rec.show_remaining_leaves = True
            elif rec.sudo().user_id and rec.sudo().user_id.id == rec.env.user.id:
                rec.show_remaining_leaves = True
            elif rec.env.user.employee_ids and rec.department_id.manager_id.id in rec.env.user.employee_ids.ids \
                    and rec.department_id.id == rec.env.user.employee_ids[0].department_id.id:
                rec.show_remaining_leaves = True
            else:
                rec.show_remaining_leaves = False

    @api.multi
    @api.depends('remaining_leaves', 'appointment_id')
    def _format_remaining_leaves(self):
        for rec in self:
            appointment_id = rec.sudo().appointment_id
            if appointment_id.leaves_accumulation_type == 'calendar_days':
                label = _(' k.d.')
            else:
                label = _(' d.d.')
            rec.remaining_leaves_label = '{0:.2f}'.format(rec.remaining_leaves).replace('.', ',') + label

    @api.multi
    def new_employee_contract(self):
        self.ensure_one()
        return self.env.ref('e_document.isakymas_del_priemimo_i_darba_action').read()[0]

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
    def create(self, vals):
        if self.env.user.is_manager() or self.env.user.is_hr_manager():
            res = super(HrEmployee, self.sudo()).create(vals)
        else:
            res = super(HrEmployee, self).create(vals)

        wizard_id = vals.pop('unique_wizard_id', False)
        if wizard_id and res:
            wizards_records = self.env['ir.attachment.wizard'].search(
                [('res_model', '=', 'hr.employee'), ('wizard_id', '=', wizard_id)])
            if wizards_records:
                for rec in wizards_records:
                    new_vals = {
                        'name': rec['name'],
                        'datas': rec['datas'],
                        'datas_fname': rec['datas_fname'],
                        'res_model': 'hr.employee',
                        'res_id': res.id,
                        'type': rec['type'],
                    }
                    self.env['ir.attachment'].create(new_vals)

        return res

    @api.multi
    def write(self, vals):
        if self.env.user.is_manager():
            return super(HrEmployee, self.sudo()).write(vals)
        else:
            return super(HrEmployee, self).write(vals)

    @api.multi
    def open_advance_wizard(self):
        partner = self.advance_accountancy_partner_id or self.address_home_id
        return partner.open_cashbalance_wizard()

    @api.one
    def add_or_remove_from_default_message_receivers(self):
        if not self.env.user.is_manager():
            return
        partner_id = self.address_home_id.id
        if not partner_id:
            return
        commands = []
        if self.robo_access and self.robo_group == 'manager':
            # commands = [(4, partner_id)]
            pass
        else:
            commands.append((3, partner_id))
        self.env.user.company_id.sudo().default_msg_receivers = commands

    @api.one
    def _set_robo_access(self):
        self.add_or_remove_from_default_message_receivers()
        return super(HrEmployee, self)._set_robo_access()

    @api.model
    def create_multi_toggle_active_employee_action(self):
        action = self.env.ref('robo.multi_toggle_active_employee_action')
        if action:
            action.create_action()

    # Cron-Jobs // ----------------------------------------------------------------------------------------------------

    @api.model
    def cron_form_employee_advance_balance_document(self):
        """
        Cron-job //
        Automatically form advance balance document for each employee on the 21st
        day of the month, if setting in res.company is enabled and invite
        employees for signing
        :return: None
        """
        company = self.sudo().env.user.company_id
        # Only execute the cron if automatic document formation is enabled
        # And if current day is 21st day of the month (hardcoded, agreed)
        if company.auto_form_employee_advance_balance_document and datetime.utcnow().day == 21:
            employees = self.search([('contract_ids', '!=', False), ('address_home_id', '!=', False)])
            report_obj = self.env['report.avansine_apyskaita.report_cashbalance_template']
            wizard_obj = self.env['cashbalance.wizard']

            # Calculate date from and date to - period of the last month
            date_from = (datetime.utcnow() - relativedelta(months=1, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to = (datetime.utcnow() - relativedelta(months=1, day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            for employee in employees:
                partner = employee.address_home_id
                lines, advance = report_obj._get_account_move_lines(
                    partner.ids, date_from, date_to, company.cash_advance_account_id.id)
                # Only form document for employees that have amounts in passed period
                if lines.get(partner.id) and advance.get(partner.id):
                    cash_balance_wizard = wizard_obj.with_context(active_ids=partner.ids).create({
                        'report_start': date_from,
                        'report_end': date_to
                    })
                    cash_balance_wizard.invite_sign()
