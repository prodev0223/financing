# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import api, fields, models, tools, exceptions, _


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    region_manager_ids = fields.One2many('e.document.region.manager', 'employee_id')
    show_region_info = fields.Boolean(compute='_compute_show_region_info')
    department_ids = fields.Many2many('hr.department', compute='_compute_department_ids')
    # HR fields with overridden groups
    is_non_resident = fields.Boolean(groups='robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager,'
                                            'robo_basic.group_robo_free_manager,'
                                            'e_document_region_manager.group_e_document_region_manager')
    nationality_id = fields.Many2one(groups='robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager,'
                                            'e_document_region_manager.group_e_document_region_manager')
    gender = fields.Selection(groups='robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager,'
                                     'e_document_region_manager.group_e_document_region_manager')
    birthday = fields.Date(groups='robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager,'
                                  'e_document_region_manager.group_e_document_region_manager')
    identification_id = fields.Char(groups='robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager,'
                                           'e_document_region_manager.group_e_document_region_manager')
    last_medical_certificate_date = fields.Date(groups='robo_basic.group_robo_free_manager,'
                                                       'robo_basic.group_robo_premium_manager,'
                                                       'robo_basic.group_robo_hr_manager,'
                                                       'e_document_region_manager.group_e_document_region_manager',
                                                track_visibility='onchange')
    next_medical_certificate_date = fields.Date(groups='robo_basic.group_robo_free_manager,'
                                                       'robo_basic.group_robo_premium_manager,'
                                                       'robo_basic.group_robo_hr_manager,'
                                                       'e_document_region_manager.group_e_document_region_manager',
                                                track_visibility='onchange')
    tevystes = fields.Boolean(groups='robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager,'
                                     'e_document_region_manager.group_e_document_region_manager')
    invalidumas = fields.Boolean(groups='robo_basic.group_robo_premium_manager,'
                                        'e_document_region_manager.group_e_document_region_manager,'
                                        'robo_basic.group_robo_hr_manager')
    darbingumas = fields.Many2one(groups='robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager,'
                                         'e_document_region_manager.group_e_document_region_manager')
    sodra_id = fields.Char(groups='robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager,'
                                  'e_document_region_manager.group_e_document_region_manager')
    personal_phone_number = fields.Char(groups='robo_basic.group_robo_free_manager,'
                                               'robo_basic.group_robo_premium_manager,'
                                               'robo_basic.group_robo_hr_manager,'
                                               'e_document_region_manager.group_e_document_region_manager')
    bank_account_id = fields.Many2one(groups='robo_basic.group_robo_premium_manager,robo_basic.group_robo_hr_manager,'
                                             'e_document_region_manager.group_e_document_region_manager')

    @api.model
    def default_get(self, fields):
        res = super(HrEmployee, self).default_get(fields)
        departments = self.env.user.get_accessible_departments()
        res['department_ids'] = [(6, 0, departments.ids)]
        if self.env.user.is_region_manager():
            res['show_region_info'] = True
        return res

    @api.multi
    def action_reset_password(self):
        server_url = self.sudo().env['ir.config_parameter'].get_param('web.base.url')
        user = self.env.user
        if server_url and 'localhost' in server_url:
            raise exceptions.UserError(_('Neteisingi nustatymai. Kreipkitės į sistemos administratorių.'))
        for rec in self:
            if user.is_manager() or user.is_hr_manager() or \
                    user.is_region_manager_at_date(department_id=rec.department_id.id):
                if rec.user_id and rec.user_id.sudo().active:
                    rec.sudo().user_id.with_context(create_user=rec.user_id.state == 'new').action_reset_password()
                else:
                    raise exceptions.UserError(_('Vartotojas nėra aktyvus'))
            else:
                raise exceptions.UserError(_('Jūs neturite reikiamų teisių'))

    @api.multi
    @api.depends('robo_access')
    def _compute_show_password_reset_button_sign_up_valid_invalid(self):
        for rec in self:
            region_info = rec.show_region_info and rec.robo_access
            if region_info and rec.signup_valid:
                rec.show_password_reset_button_sign_up_valid = True
            if region_info and not rec.signup_valid:
                rec.show_password_reset_button_sign_up_invalid = True

    @api.multi
    def _compute_show_employment_banner(self):
        is_region_manager = self.env.user.is_region_manager()
        if not (self.env.user.is_manager() or self.env.user.has_group(
                'robo_basic.group_robo_edocument_manager') or is_region_manager):
            return
        if is_region_manager and self.env.user.employee_ids:
            manager = self.env.user.employee_ids[0]
            template = self.env.ref('e_document.isakymas_del_priemimo_i_darba_template')
        elif is_region_manager:
            return

        for rec in self:
            if is_region_manager and not manager.is_region_manager_at_date(rec.department_id.id, template.id,
                                                                           fields.Date.context_today(self)):
                continue
            if rec.sudo().contract_id or rec.type == 'mb_narys':
                continue

            rec.show_employment_banner = True

    @api.multi
    def is_region_manager_at_date(self, department_id, template_id, date):
        """Find out if employee is a manager of a provided department in a region"""
        self.ensure_one()
        return any([x.date_start <= date <= x.date_stop and department_id in x.department_ids.ids and
                    template_id in x.e_document_template_ids.ids for x in self.region_manager_ids])

    @api.multi
    def get_managing_departments(self):
        departments = super(HrEmployee, self).get_managing_departments()
        EDocumentRegionManager = self.env['e.document.region.manager']
        for rec in self:
            user = rec.sudo().user_id
            if user and user.is_region_manager():
                date = datetime.today().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                region_manager_domain = EDocumentRegionManager.get_region_manager_domain(user.id, date)
                departments |= EDocumentRegionManager.sudo().search(region_manager_domain).mapped('department_ids')
        return departments

    # ! This method should not depend on department_id, as it will let region manager select a different department
    # and see personal information
    def _compute_show_region_info(self):
        user = self.env.user
        show_personal_info = user.is_manager() or user.is_hr_manager()
        for rec in self:
            is_region_manager = user.is_region_manager_at_date(rec.department_id.id)
            rec.show_region_info = show_personal_info or is_region_manager

    @api.multi
    @api.depends('name', 'type')
    def _show_remaining_leaves(self):
        super(HrEmployee, self)._show_remaining_leaves()
        user = self.env.user
        if not user.is_region_manager():
            return
        managed_departments = user.employee_ids.get_managing_departments()
        for rec in self:
            if rec.department_id in managed_departments:
                rec.show_remaining_leaves = True

    @api.multi
    def _remaining_leaves(self):
        super(HrEmployee, self)._remaining_leaves()
        date = self._context.get('date', datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
        user = self.env.user
        if not user.is_region_manager():
            return
        managed_departments = user.employee_ids.get_managing_departments()
        for rec in self:
            if rec.department_id in managed_departments:
                rec.remaining_leaves = rec._compute_employee_remaining_leaves(date)

    @api.depends('name')
    def _show_personal_info(self):
        """ Check if contract/payslip information should be displayed on the employee card
        ROBO: COMPLETE OVERRIDE """
        # Only manager can see the normal tab, but HR and region managers should be able to see info for
        # employees with the same conditions as employees can see their own.
        user = self.env.user
        is_manager = user.is_manager()
        is_hr_manager = user.is_hr_manager()
        for rec in self:
            is_region_manager = user.is_region_manager_at_date(rec.department_id.id)
            if (not is_manager and rec.sudo().user_id and rec.sudo().user_id == rec.env.user) or is_hr_manager \
                    or is_region_manager:
                rec.show_personal_info = True

    @api.multi
    def _compute_department_ids(self):
        departments = self.env.user.get_accessible_departments()
        for rec in self:
            rec.department_ids = [(6, 0, departments.ids)]

    @api.model
    def create(self, vals):
        user = self.env.user
        if user.is_manager() or user.is_hr_manager():
            return super(HrEmployee, self).create(vals)

        if not user.is_region_manager_at_date(vals.get('department_id')):
            raise exceptions.ValidationError(_('You do not have sufficient rights to create this record'))

        if vals.get('robo_group') in ['hr_manager', 'manager']:
            raise exceptions.UserError(_('Neturite pakankamai teisių. Personalo vadovas negali suteikti šių teisių'))

        return super(HrEmployee, self.sudo()).create(vals)

    @api.multi
    def write(self, vals):
        user = self.env.user
        error = _('You do not have sufficient rights to modify this record')
        if user.is_manager() or user.is_hr_manager():
            return super(HrEmployee, self).write(vals)
        department_is_changed = 'department_id' in vals
        if department_is_changed and not user.is_region_manager_at_date(vals.get('department_id')):
            raise exceptions.ValidationError(error)
        for rec in self:
            if not user.is_region_manager_at_date(rec.department_id.id):
                raise exceptions.ValidationError(error)
        return super(HrEmployee, self).write(vals)

    @api.multi
    def user_has_hr_management_rights(self):
        self.ensure_one()
        return self.show_region_info
