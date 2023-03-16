# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _, exceptions, tools
from datetime import datetime
from odoo.addons.robo_basic.models.rpc_object import RPCobject
from odoo import SUPERUSER_ID
import xmlrpclib
from odoo.addons.robo_basic.models.utils import validate_email

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):

    _inherit = 'res.users'

    show_cash_forecast = fields.Boolean(string='Rodyti prognuozuojamą pinigų likutį',
                                        groups='robo_basic.group_robo_premium_manager')
    show_only_personal_income = fields.Boolean(string='Rodyti tik asmenines pajamas',
                                               groups='robo_basic.group_robo_premium_manager')
    show_only_personal_rp_amounts = fields.Boolean(string='Rodyti tik asmenines gautinas/mokėtinas sumas',
                                                   groups='robo_basic.group_robo_premium_manager')
    average_expenses_forecast = fields.Boolean(groups='robo_basic.group_robo_premium_manager')
    average_income_forecast = fields.Boolean(groups='robo_basic.group_robo_premium_manager')
    average_du_forecast = fields.Boolean(groups='robo_basic.group_robo_premium_manager')
    include_income = fields.Boolean(groups='robo_basic.group_robo_premium_manager')
    include_expenses = fields.Boolean(groups='robo_basic.group_robo_premium_manager')
    has_accountant_rights = fields.Boolean(compute='_compute_has_accountant_rights', store=True)
    force_global_readonly_access = fields.Boolean(string='Force global READ-ONLY rights', groups='base.group_system')

    @api.depends('groups_id')
    def _compute_has_accountant_rights(self):
        group = self.env.ref('robo_basic.group_robo_premium_accountant', False)
        accountant_ids = set(group and group.users.ids or [])
        for rec in self:
            rec.has_accountant_rights = rec.id in accountant_ids

    @api.multi
    def get_user_group_ids(self):
        self.ensure_one()
        return self.groups_id.ids

    @api.multi
    def only_reduced_debt_report(self):
        self.ensure_one()
        if self.has_group('robo_basic.group_robo_debt_report'):
            return True
        else:
            return False

    @api.multi
    def is_manager(self):
        self.ensure_one()
        if self.has_group('robo_basic.group_robo_premium_manager') \
                or self.has_group('robo_basic.group_robo_free_manager'):
            return True
        else:
            return False

    @api.multi
    def is_premium_manager(self):
        self.ensure_one()
        if self.has_group('robo_basic.group_robo_premium_manager'):
            return True
        else:
            return False

    @api.multi
    def is_free_manager(self):
        self.ensure_one()
        if self.has_group('robo_basic.group_robo_free_manager'):
            return True
        else:
            return False

    @api.multi
    def is_hr_manager(self):
        self.ensure_one()
        if self.has_group('robo_basic.group_robo_hr_manager'):
            return True
        else:
            return False

    @api.multi
    def accumulate_statistics(self):
        self.ensure_one()
        if self.has_group('robo_basic.robo_statistics'):
            return True
        else:
            return False

    @api.multi
    def is_accountant(self):
        self.ensure_one()
        if self.has_group('robo_basic.group_robo_premium_accountant'):
            return True
        else:
            return False

    @api.multi
    def is_user(self):
        self.ensure_one()
        if self.has_group('robo_basic.group_robo_free_employee') \
                or self.has_group('robo_basic.group_robo_premium_user'):
            return True
        else:
            return False

    @api.multi
    def is_premium_user(self):
        self.ensure_one()
        if self.has_group('robo_basic.group_robo_premium_user'):
            return True
        else:
            return False

    @api.multi
    def is_free_user(self):
        self.ensure_one()
        if self.has_group('robo_basic.group_robo_free_employee'):
            return True
        else:
            return False

    @api.multi
    def is_free(self):
        self.ensure_one()
        if self.has_group('robo_basic.group_robo_free_employee') \
                or self.has_group('robo_basic.group_robo_free_manager'):
            return True
        else:
            return False

    @api.multi
    def is_robo_user(self):
        self.ensure_one()
        return True if self.login[-12:] == '@robolabs.lt' else False

    @api.multi
    def is_premium(self):
        self.ensure_one()
        if self.has_group('robo_basic.group_robo_premium_user') \
                or self.has_group('robo_basic.group_robo_premium_manager'):
            return True
        else:
            return False

    @api.multi
    def is_robo_tour_user(self):
        if self._is_superuser():
            return True

        if self.has_group('robo_basic.group_robo_premium_user') \
          or self.has_group('robo_basic.group_robo_premium_manager')\
          or self.has_group('robo_basic.group_robo_free_employee') \
          or self.has_group('robo_basic.group_robo_free_manager') \
          or self.has_group('robo_basic.group_robo_free_employee'):
            if self.create_date and (datetime.now() - datetime.strptime(self.create_date, tools.DEFAULT_SERVER_DATETIME_FORMAT)).days < 30:
                return True
            else:
                return False
        else:
            return False

    @api.model
    def update_forecast(self, do_show=False):
        self.env.user.show_cash_forecast = True if do_show else False

    @api.model
    def check_income_mode(self):
        return self.env.user.show_only_personal_income

    @api.model
    def update_income_mode(self, do_show=False):
        self.env.user.show_only_personal_income = True if do_show else False

    @api.model
    def check_forecast_income_mode(self):
        return self.env.user.average_income_forecast

    @api.model
    def update_forecast_income_mode(self, do_show=False):
        self.env.user.average_income_forecast = True if do_show else False

    @api.model
    def check_forecast_expense_mode(self):
        return self.env.user.average_expenses_forecast

    @api.model
    def update_forecast_expense_mode(self, do_show=False):
        self.env.user.average_expenses_forecast = True if do_show else False

    @api.model
    def check_forecast(self):
        return self.env.user.show_cash_forecast

    @api.model
    def check_chart_rp_amounts_mode(self):
        return self.env.user.show_only_personal_rp_amounts

    @api.model
    def set_chart_rp_amounts_mode(self, do_show=False):
        self.env.user.show_only_personal_rp_amounts = True if do_show else False

    @api.model
    def new_database_user(self, vals=None):
        if vals is None:
            vals = {}
        login = 'login' in vals and vals['login'] or 'demo'
        name = 'name' in vals and vals['name'] or 'demo'
        if self.search_count([('login', '=', login)]) == 0:
            user_id = self.create({
                'login': login,
                'email': login,
                'name': name,
                'groups_id': [(6, 0, [self.env.ref('robo_basic.group_robo_free_manager').id])]
            })
            if user_id.partner_id:
                user_id.partner_id.write({
                    'customer': False,
                    'supplier': True,
                })
            try:
                department_id = self.env.ref('hr.dep_administration').id
            except:
                department_id = False
            job_id = self.env['hr.job'].create({
                'name': 'Direktorius',
            })
            # default_advance_accountancy_partner_vals = {
            #     'name': 'A.A. ' + name,
            #     'advance_payment': True,
            #     'supplier': True,
            #     'customer': False,
            # }
            # default_advance_partner = self.env['res.partner'].create(default_advance_accountancy_partner_vals)
            emp_id = self.env['hr.employee'].create({
                'name': name,
                'department_id': department_id,
                'job_id': job_id.id,
                'work_email': login,
                'user_id': user_id.id,
                'robo_access': True,
                'robo_group': 'manager',
                'address_home_id': user_id.partner_id.id if user_id.partner_id else False,
                # 'advance_accountancy_partner_id': default_advance_partner.id,
                'savivaldybe': '13',
                'type': 'employee',
            })
            emp_id.company_id.write({
                'vadovas': emp_id.id,
                # 'findir': emp_id.id,
            })
            # self._cr.commit()
            # user_id.action_reset_password()

    # @classmethod
    # def _login(cls, db, login, password):
    #     user_id = super(ResUsers, cls)._login(db=db, login=login, password=password)
    #     if user_id and db not in ['demo', 'demo_copy', 'robo_template', 'robo_internal']:
    #         try:
    #             with cls.pool.cursor() as cr:
    #                 config_obj = api.Environment(cr, SUPERUSER_ID, {})['ir.config_parameter'].sudo()
    #                 central_server_url = tools.config.get('central_server', False) or config_obj.get_param('robo.central_server')
    #                 central_server_database = config_obj.get_param('robo.robo_server_database')
    #                 robo_server_username = config_obj.get_param('robo.robo_server_username')
    #                 robo_server_password = config_obj.get_param('robo.robo_server_password')
    #                 if not central_server_url:
    #                     raise Exception
    #                 if not central_server_database:
    #                     raise Exception
    #                 if not robo_server_username:
    #                     raise Exception
    #                 if not robo_server_password:
    #                     raise Exception
    #                 url, central_db, username, password = central_server_url, central_server_database, robo_server_username, robo_server_password
    #                 common = xmlrpclib.ServerProxy('{}/xmlrpc/2/common'.format(url))
    #                 version_info = common.version()
    #                 if float(version_info['server_version']) < 10.0:
    #                     raise Exception
    #                 uid = common.authenticate(central_db, username, password, {})
    #                 models_obj = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(url))
    #                 statistics_obj = RPCobject(models_obj, 'user.statistics', central_db, uid, password)
    #                 vals = {
    #                     'database': db,
    #                     'email': login,
    #                     'user_id': user_id,
    #                 }
    #                 statistics_obj.execute('add_login', vals)
    #         except:
    #             pass
    #     return user_id

    @api.model
    def message_get_reply_to(self, res_ids, default=None):
        users = self.browse(res_ids)
        return dict((user.id, user.email or default) for user in users)

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if args is None:
            args = []
        if not self.env.user.is_accountant():
            args.append(('id', 'not in', self.env.ref('robo_basic.group_robo_premium_accountant').users.ids))
        return super(ResUsers, self).name_search(name, args, operator, limit)

    @api.multi
    def toggle_active(self):
        res = super(ResUsers, self).toggle_active()
        self.post_user_status_message()
        return res

    @api.multi
    def post_user_status_message(self):
        """Post message about user or employee status and who set that status"""
        user = self.env.user
        for rec in self.sudo():
            msg = {
                'body': _('User {} has {} this user').format(
                    user.name, _('activated') if rec.active else _('deactivated')
                ),
            }
            rec.partner_id.message_post(**msg)


ResUsers()


class HrEmployee(models.Model):

    _inherit = 'hr.employee'

    robo_access = fields.Boolean(string='Robo prisijungimas', track_visibility='onchange',
                                 inverse='_set_robo_access',
                                 )
    robo_group = fields.Selection([('employee', 'Darbuotojas'),
                                   ('hr_manager', 'Personalo vadovas'),
                                   ('manager', 'Vadovas')], string='Teisių grupė', inverse='_set_robo_access',
                                  track_visibility='onchange',
                                  groups='robo_basic.group_robo_premium_manager,robo_basic.group_robo_free_manager,robo_basic.group_robo_hr_manager')
    robo_access_check = fields.Boolean(compute='_robo_access_check')
    work_email = fields.Char(inverse='_set_email', track_visibility='onchange')

    @api.constrains('work_email', 'robo_access')
    def mail_constrain(self):
        for rec in self:
            if rec.robo_access_check:
                if not validate_email(self.work_email.strip()) and not self._context.get('do_not_check_email', False):
                    raise exceptions.UserError(_('El. Pašto adresas neatitinka formato!'))

    @api.onchange('robo_group')
    def _onchange_robo_group(self):
        message = _('Pakeitus pagrindinę teisių grupę bus iš naujo pakeistos prieigos teisės.')
        if self.robo_group == 'manager':
            message += '\n' + _('Šiam darbuotojui suteiksite vadovo teises.')
        if self.robo_group:
            return {'warning': {
                'title': _('Įspėjimas'),
                'message': message,
            }}

    @api.onchange('work_email')
    def onchange_work_email(self):
        if self.work_email:
            self.work_email = self.work_email.strip()

    @api.multi
    def _set_email(self):
        for rec in self:
            if self.sudo().env['res.users'].search([('email', '!=', False), ('active', '=', False), ('email', '=', rec.work_email)], count=True) != 0:
                raise exceptions.UserError(_('Egzistuoja suarchyvuotas naudotojas su tokiu el. pašto adresu.\nNorėdami naudotis šiuo el. pašto adresu, prašome suaktyvinti jau egzistuojantį vartotoją.'))
            if rec.sudo().user_id and rec.work_email and rec.robo_access:
                if rec.env.user.is_manager() or rec.env.user.is_hr_manager():
                    old_email = rec.sudo().user_id.login
                    rec.sudo().user_id.write({
                        'login': rec.work_email,
                        'email': rec.work_email,
                    })
                    rec.sudo().user_id.partner_id.write({
                        'email': rec.work_email,
                    })
                    user_new = rec.user_id.state == 'new'
                    if user_new:
                        rec.sudo().user_id.with_context(create_user=user_new).action_reset_password()
                    elif not user_new and rec.work_email.lower() != old_email.lower():
                        rec.sudo().user_id.action_reset_password()
                else:
                    raise exceptions.UserError(_('Negalite keisti darbuotojo el. pašto adreso.'))

    @api.one
    @api.depends('robo_access')
    def _robo_access_check(self):
        if self.robo_access:
            self.robo_access_check = True
        else:
            self.robo_access_check = False

    @api.one
    def _set_robo_access(self):
        if self.env.user.is_free_manager():
            premium = False
        elif self.user_has_hr_management_rights():
            premium = True
        else:
            return
        if self.env.user.is_hr_manager() and not self.env.user.is_manager() and self.robo_group != 'employee':  # this check has no effect since write is done with sudo, check is done in write function
            raise exceptions.UserError(_('Neturite pakankamai teisių. Personalo vadovas gali valdyti tik darbuotojų grupės teises.'))
        if self.robo_access:
            if not self.sudo().user_id:
                if not self.address_home_id:
                    default_partner_vals = {'name': self.name}
                    if self.work_email:
                        default_partner_vals['email'] = self.work_email
                    if self.work_phone:
                        default_partner_vals['phone'] = self.work_phone
                    if self.country_id:
                        default_partner_vals['country_id'] = self.country_id.id

                    default_partner_vals.update({
                        x: self[x] for x in ['city', 'street', 'street2', 'zip'] if self[x]
                    })

                    default_partner = self.env['res.partner'].create(default_partner_vals)
                    self.address_home_id = default_partner.id
                # if not self.advance_accountancy_partner_id:
                #     default_advance_accountancy_partner_vals = {'name': 'A.A. ' + self.name, 'advance_payment': True,
                #                                                 'supplier': True}
                #     default_advance_partner = self.env['res.partner'].create(default_advance_accountancy_partner_vals)
                #     self.advance_accountancy_partner_id = default_advance_partner.id
                existing_user = self.sudo().env['res.users'].with_context(active_test=False).search([
                    ('login', '=', self.work_email)
                ])
                if existing_user:
                    # Conditions
                    is_user_active = existing_user.active
                    is_employee_attached = True if existing_user.employee_ids.id else False
                    is_employee_active = existing_user.employee_ids[0].active if is_employee_attached else False
                    # Exception message building and raising
                    message = _('There is an {} user {} an {} employee attached.\n\n').format(
                        _('active') if is_user_active else _('archived'),
                        _('with') if is_employee_attached else _('without'),
                        '' if not is_employee_attached else _('activated') if is_employee_active else _('deactivated'),
                    )
                    # --- Leaving this commented in case we want to use it in the future;

                    # solution = _('Depending on what you\'re trying to do you may want to:\n{}{}{}').format(
                    #     _('Activate the archived user;\n') if is_user_active else _(''),
                    #     _('Detach the current employee / use a different email;\n') if is_employee_attached
                    #     else _('Attach this user to an existing one;\n'),
                    #     '' if not is_employee_attached else _('') if is_employee_active
                    #     else _('Activate and use the employee related to the user / use a different email;\n'),
                    # )
                    if self.env.user.is_accountant():
                        message += _("""
                        If you are unsure of how to handle this, make sure to refer to your team lead
                        or write to support specifying what you wish to achieve.
                        """)
                    raise exceptions.UserError(message)
                else:
                    user_id = self.sudo().env['res.users'].create({
                        'name': self.name,
                        'login': self.work_email,
                        'email': self.work_email,
                        'partner_id': self.address_home_id.id if self.address_home_id else False,
                    })
                user_id.partner_id.customer = False
            else:
                user_id = self.sudo().user_id
            user_id.active = True
            groups = []
            if self.sudo().env.ref('robo_basic.group_robo_create_on_behalf').id in user_id.groups_id.ids:
                groups.append(self.sudo().env.ref('robo_basic.group_robo_create_on_behalf').id)
            if self.robo_group == 'employee' and not premium:
                groups.append(self.sudo().env.ref('robo_basic.group_robo_free_employee').id)
                user_id.groups_id = [(6, 0, groups)]

            elif self.robo_group == 'employee' and premium:
                groups.append(self.sudo().env.ref('robo_basic.group_robo_premium_user').id)
                user_id.groups_id = [(6, 0, groups)]

            elif self.robo_group == 'hr_manager':
                groups.extend([self.sudo().env.ref('robo_basic.group_robo_premium_user').id,
                               self.sudo().env.ref('robo_basic.group_robo_hr_manager').id])
                user_id.groups_id = [(6, 0, groups)]

            elif self.robo_group == 'manager' and not premium:
                groups.append(self.sudo().env.ref('robo_basic.group_robo_free_manager').id)
                user_id.groups_id = [(6, 0, groups)]

            elif self.robo_group == 'manager' and premium:
                groups.append(self.sudo().env.ref('robo_basic.group_robo_premium_manager').id)
                user_id.groups_id = [(6, 0, groups)]

            if not self.sudo().user_id:
                self.user_id = user_id.id

        else:
            if self.sudo().user_id:
                if self.env.user.is_hr_manager() and not self.env.user.is_manager() and self.sudo().user_id.is_manager():
                    raise exceptions.UserError(_('Negalite suarchyvuoti vadovo teises turinčių darbuotojų.'))
                self.sudo().user_id.active = False

    @api.multi
    def toggle_active(self):
        if not self.env.user.is_manager() and not self.env.user.is_hr_manager():
            raise exceptions.AccessError(_('Negalite atlikti šio veiksmo.'))
        for rec in self:
            active = not rec.active
            if rec.sudo().user_id:
                if self.env.user.is_hr_manager() and not self.env.user.is_manager() and rec.sudo().robo_group != 'employee':
                    raise exceptions.UserError(_('Negalite suarchyvuoti vadovo teises turinčių darbuotojų.'))
                rec.sudo().user_id.write({
                    'active': active,
                })
                rec.sudo().user_id.sudo(self.env.user.id).post_user_status_message()
        return super(HrEmployee, self).toggle_active()

    @api.model
    def create(self, vals):
        if 'robo_access' in vals and not self.env.user.is_manager() and not self.env.user.is_hr_manager():
            vals.pop('robo_access')
        if not self._context.get('no_check', False) and vals.get('user_id', False) and self.with_context(active_test=False).search([('user_id', '=', vals['user_id'])], count=True) > 0:
            raise exceptions.ValidationError(_('Vartotojas negali kartotis.'))
        return super(HrEmployee, self).create(vals)

    @api.multi
    def user_has_hr_management_rights(self):
        self.ensure_one()
        user = self.env.user
        return user.is_premium_manager() or user.is_hr_manager()

    @api.multi
    def write(self, vals):
        has_hr_management_rights = all(rec.user_has_hr_management_rights() for rec in self)
        robo_group = vals.get('robo_group')
        if 'robo_access' in vals and not has_hr_management_rights:
            vals.pop('robo_access')
        if 'robo_group' in vals and has_hr_management_rights and not self.env.user.is_manager():
            if robo_group in ['hr_manager', 'manager']:
                raise exceptions.UserError(
                    _('Neturite pakankamai teisių. Personalo vadovas negali suteikti šių teisių'))
        if self.env.user.is_manager() or has_hr_management_rights:
            if robo_group:
                for rec in self:
                    _logger.info('User %s changed employee %s from group %s to group %s', self.env.user.login,
                                 rec.name_related,
                                 rec.robo_group,
                                 robo_group,
                                 )
            res = super(HrEmployee, self.sudo()).write(vals)
        else:
            res = super(HrEmployee, self).write(vals)
        if not self._context.get('no_check', False) and vals.get('user_id', False) and self.with_context(active_test=False).search([('user_id', '=', vals['user_id'])], count=True) > 1:
            raise exceptions.ValidationError(_('Vartotojas negali kartotis.'))
        return res

    @api.model
    def cron_check_user_token(self):
        robo_access_users = self.env['hr.employee'].search([('robo_access', '=', True)])
        users_to_reset = robo_access_users.filtered(lambda x: not x.user_id.partner_id.signup_url and x.user_id.active)
        users_to_reset.action_reset_password()

    @api.multi
    def unlink(self):
        for rec in self:
            if rec.user_id and not rec.user_id.employee_ids.filtered(lambda x: x.id != rec.id and x.active):
                rec.user_id.active = False
        return super(HrEmployee, self).unlink()


HrEmployee()
