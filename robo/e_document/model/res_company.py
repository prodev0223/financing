# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    send_notifications_of_free_form_order = fields.Boolean(string='Buhalteriui siųsti pranešimus, kai pasirašomas '
                                                                  'laisvos formos įsakymas',
                                                           groups='robo_basic.group_robo_premium_accountant',
                                                           inverse='_set_send_notifications_of_free_form_order')
    allow_delegate_to_sign_related_documents = fields.Boolean(string='Leisti įgaliotiniui pasirašyti su juo susijusius '
                                                                     'dokumentus',
                                                              compute='_compute_allow_delegate_to_sign_related_documents',
                                                              inverse='_set_allow_delegate_to_sign_related_documents')
    manager_restricted_document_templates = fields.Many2many('e.document.template',
                                                             'res_company_e_document_template_manager_restricted_rel',
                                                             string='Dokumentai, kurie gali būti pasirašyti/patvirtinti tik vadovo',
                                                             groups='robo_basic.group_robo_premium_accountant')
    process_edoc_signing_as_job = fields.Boolean(string='Sign e-documents in background',
                                                 compute='_compute_process_edoc_signing_as_job',
                                                 inverse='_set_process_edoc_signing_as_job')
    minimum_wage_adjustment_document_creation_deadline_days = fields.Integer(
        string='Number of days before minimum wage changes to create the salary change documents',
        groups='robo_basic.group_robo_premium_accountant',
        compute='_compute_minimum_wage_adjustment_document_parameters',
        inverse='_set_minimum_wage_adjustment_document_parameters'
    )
    keep_salary_differences_when_changing_minimum_wage = fields.Boolean(
        string='Keep the difference between the current minimum wage and the current salary when changing the minimum '
               'wage for employees who earn less than the next new minimum wage',
        groups='robo_basic.group_robo_premium_accountant',
        compute='_compute_minimum_wage_adjustment_document_parameters',
        inverse='_set_minimum_wage_adjustment_document_parameters'
    )
    mma_adjustment_when_creating_salary_change_documents = fields.Float(
        string='Amount to adjust the minimum monthly wage by when creating minimum wage adjustment documents',
        groups='robo_basic.group_robo_premium_accountant',
        compute='_compute_minimum_wage_adjustment_document_parameters',
        inverse='_set_minimum_wage_adjustment_document_parameters'
    )
    mmh_adjustment_when_creating_salary_change_documents = fields.Float(
        string='Amount to adjust the minimum hourly wage by when creating minimum wage adjustment documents',
        groups='robo_basic.group_robo_premium_accountant',
        compute='_compute_minimum_wage_adjustment_document_parameters',
        inverse='_set_minimum_wage_adjustment_document_parameters'
    )

    @api.multi
    def _compute_allow_delegate_to_sign_related_documents(self):
        self.allow_delegate_to_sign_related_documents = self.env['ir.config_parameter'].sudo().get_param(
            'allow_delegate_to_sign_related_documents') == 'True'

    @api.multi
    def _set_allow_delegate_to_sign_related_documents(self):
        self.env['ir.config_parameter'].sudo().set_param('allow_delegate_to_sign_related_documents',
                                                         str(self.allow_delegate_to_sign_related_documents))

    @api.multi
    def _compute_process_edoc_signing_as_job(self):
        self.process_edoc_signing_as_job = self.env['ir.config_parameter'].sudo().get_param(
            'process_edoc_signing_as_job') == 'True'

    @api.multi
    def _set_process_edoc_signing_as_job(self):
        self.env['ir.config_parameter'].sudo().set_param('process_edoc_signing_as_job',
                                                         str(self.process_edoc_signing_as_job))

    @api.multi
    def _compute_minimum_wage_adjustment_document_parameters(self):
        self.ensure_one()
        IrConfigParameter = self.env['ir.config_parameter'].sudo()
        self.minimum_wage_adjustment_document_creation_deadline_days = int(IrConfigParameter.get_param(
            'minimum_wage_adjustment_document_creation_deadline_days', '14'))
        self.keep_salary_differences_when_changing_minimum_wage = IrConfigParameter.get_param(
            'keep_salary_differences_when_changing_minimum_wage'
        ) == 'True'
        self.mma_adjustment_when_creating_salary_change_documents = float(IrConfigParameter.get_param(
            'minimum_monthly_wage_adjustment', '0.0'))
        self.mmh_adjustment_when_creating_salary_change_documents = float(IrConfigParameter.get_param(
            'minimum_hourly_wage_adjustment', '0.0'))

    @api.multi
    def _set_minimum_wage_adjustment_document_parameters(self):
        self.ensure_one()
        IrConfigParameter = self.env['ir.config_parameter'].sudo()
        IrConfigParameter.set_param('minimum_wage_adjustment_document_creation_deadline_days',
                                    str(self.minimum_wage_adjustment_document_creation_deadline_days))
        IrConfigParameter.set_param('keep_salary_differences_when_changing_minimum_wage',
                                    str(self.keep_salary_differences_when_changing_minimum_wage))
        IrConfigParameter.set_param('minimum_monthly_wage_adjustment',
                                    str(self.mma_adjustment_when_creating_salary_change_documents))
        IrConfigParameter.set_param('minimum_hourly_wage_adjustment',
                                    str(self.mmh_adjustment_when_creating_salary_change_documents))

    def _set_send_notifications_of_free_form_order(self):
        channel = self.env.ref('e_document.laisvos_formos_isakymas_mail_channel')
        accountant_id = self.env.user.sudo().company_id.findir.partner_id.id
        for rec in self:
            operation = [(4, accountant_id)] if rec.send_notifications_of_free_form_order else [(3, accountant_id)]
            channel.sudo().write({'channel_partner_ids': operation})

    @api.model
    def get_manager_mail_channels(self):
        channels = super(ResCompany, self).get_manager_mail_channels()
        channel_eids = [
            'e_document.orders_waiting_for_signature_mail_channel',
            'e_document.unsigned_prasymas_del_priemimo_i_darba_ir_atlyginimo_mokejimo_mail_channel',
            'e_document.delegate_changes_mail_channel',
            'e_document.user_rights_changes_mail_channel',
            'e_document.inform_about_limited_capacity_of_work_documents',
        ]
        for eid in channel_eids:
            channel = self.env.ref(eid, False)
            if channel:
                channels |= channel
        return channels
