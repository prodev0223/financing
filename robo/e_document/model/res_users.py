# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResUsers(models.Model):
    _inherit = 'res.users'

    delegated_document_ids = fields.Many2many('e.document', compute='_compute_delegated_document_ids', store=True)
    department_delegated_document_ids = fields.Many2many('e.document', 'e_document_department_delegate_res_user_rel',
                                                         'e_document_id', 'res_users_id', store=True,
                                                         compute='_compute_department_delegated_document_ids')

    @api.one
    @api.depends('employee_ids')
    def _compute_delegated_document_ids(self):
        E_DOCUMENT = self.env['e.document']
        document_ids = E_DOCUMENT
        company = self.env.user.company_id.sudo()

        delegate_ids = self.mapped('employee_ids.delegate_ids')
        for delegate_id in delegate_ids:
            document_ids |= E_DOCUMENT.search([
                ('reikia_pasirasyti_iki', '>=', delegate_id.date_start),
                ('reikia_pasirasyti_iki', '<=', delegate_id.date_stop),
                ('template_id.is_signable_by_delegate', '=', True),
                ('template_id', 'not in', company.manager_restricted_document_templates.ids),
            ])
        self.delegated_document_ids = document_ids

    @api.multi
    @api.depends('employee_ids')
    def _compute_department_delegated_document_ids(self):
        E_DOCUMENT = self.env['e.document']
        company = self.env.user.company_id.sudo()

        for rec in self:
            documents = E_DOCUMENT
            if company.politika_atostogu_suteikimas == 'department':
                delegates = rec.mapped('employee_ids.department_delegate_ids')
                for delegate in delegates:
                    documents |= E_DOCUMENT.search([
                        ('date_document', '>=', delegate.date_start),
                        ('date_document', '<=', delegate.date_stop),
                        ('template_id.send_manager', '=', True),
                        ('document_type', '=', 'prasymas'),
                        ('employee_id1.department_id', '=', delegate.department_id.id),
                        ('template_id', 'not in', company.manager_restricted_document_templates.ids),
                    ])
            rec.department_delegated_document_ids = documents

    @api.model
    def get_accountant_mail_channel_ids(self):
        """
        Return a list of mail channel ids that accountant should be subscribed to by default
        :return: List of mail channel ids
        """
        accountant_mail_channel_ids = [
            'e_document.isakymas_del_3_menesiu_atostogu_vaikui_priziureti_suteikimo_mail_channel',
            'e_document.isakymas_del_ankstesnio_vadovo_isakymo_panaikinimo_mail_channel',
            'e_document.isakymas_del_atleidimo_is_darbo_mail_channel',
            'e_document.isakymas_del_kurybiniu_atostogu_suteikimo_mail_channel',
            'e_document.isakymas_del_nemokamu_atostogu_mail_channel',
            'e_document.isakymas_del_nestumo_ir_gimdymo_atostogu_mail_channel',
            'e_document.isakymas_del_priemimo_i_darba_mail_channel',
            'e_document.isakymas_del_tevystes_atostogu_suteikimo_mail_channel',
            'e_document.isakymas_del_vaiko_prieziuros_atostogu_mail_channel',
            'e_document.isakymas_del_vaiko_prieziuros_atostogu_nutraukimo_mail_channel',
            'e_document.signed_orders_about_bonus_award_mail_channel',
            'e_document.mark_signed_requests_mail_channel',
        ]

        if self.env.user.company_id.sudo().send_notifications_of_free_form_order:
            accountant_mail_channel_ids += ['e_document.laisvos_formos_isakymas_mail_channel']

        channel_ids = super(ResUsers, self).get_accountant_mail_channel_ids() or []
        channel_ids.extend(
            channel.id for channel in map(lambda x: self.env.ref(x, False), accountant_mail_channel_ids) if channel
        )
        return channel_ids


ResUsers()
