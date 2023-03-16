# -*- coding: utf-8 -*-

from odoo import api, fields, models

from downtime_order_import import import_downtime_order


class RoboCompanySettings(models.TransientModel):
    _inherit = 'robo.company.settings'

    import_full_downtime_orders = fields.Binary()
    send_notifications_of_free_form_order = fields.Boolean(string='Buhalteriui siųsti pranešimus, kai pasirašomas '
                                                                  'laisvos formos įsakymas',
                                                           groups='robo_basic.group_robo_premium_accountant')
    allow_delegate_to_sign_related_documents = fields.Boolean(string='Leisti įgaliotiniui pasirašyti su juo susijusius '
                                                                     'dokumentus')
    manager_restricted_document_templates = fields.Many2many('e.document.template',
                                                             string='Dokumentai, kurie gali būti pasirašyti/patvirtinti tik vadovo',
                                                             groups='robo_basic.group_robo_premium_accountant')
    process_edoc_signing_as_job = fields.Boolean(string='Sign e-documents in background')

    @api.model
    def default_get(self, field_list):
        res = super(RoboCompanySettings, self).default_get(field_list)
        company = self.env.user.sudo().company_id
        res.update({
            'allow_delegate_to_sign_related_documents': company.allow_delegate_to_sign_related_documents,
        })

        if self.env.user.is_accountant():
            res.update({
                'send_notifications_of_free_form_order': company.send_notifications_of_free_form_order,
                'process_edoc_signing_as_job': company.process_edoc_signing_as_job,
                'manager_restricted_document_templates': [(6, 0, company.manager_restricted_document_templates.ids)],
            })
        return res

    @api.model
    def _get_company_policy_field_list(self):
        res = super(RoboCompanySettings, self)._get_company_policy_field_list()
        res.append('send_notifications_of_free_form_order')
        res.append('process_edoc_signing_as_job')
        return res

    @api.model
    def _get_company_info_field_list(self):
        res = super(RoboCompanySettings, self)._get_company_info_field_list()
        res.append('allow_delegate_to_sign_related_documents')
        return res

    @api.multi
    def save_e_document_template_settings(self):
        self.ensure_one()
        if self.env.user.is_accountant():
            company = self.company_id
            company.sudo().write({
                'manager_restricted_document_templates': [(6, 0, self.sudo().manager_restricted_document_templates.ids)]
            })

    @api.multi
    def set_default_import(self):
        """
        Calls threaded import preparation method
        on all possible front XLS files.
        :return: None
        """
        super(RoboCompanySettings, self).set_default_import()
        self.threaded_import_prep(
            'import_full_downtime_orders',
            function=import_downtime_order,
            imported_file=self.import_full_downtime_orders
        )
