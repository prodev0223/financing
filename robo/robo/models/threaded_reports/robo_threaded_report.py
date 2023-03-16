# -*- coding: utf-8 -*-
from odoo import fields, models, api


class RoboThreadedReport(models.AbstractModel):

    """
    Abstract model that contains some computed fields (methods in the future)
    That are shared between all of the threaded reports
    """

    _name = 'robo.threaded.report'

    @api.model
    def default_get(self, field_list):
        """
        Default get value for a computed field, because when the record is not-yet-created
        (as it is with most wizards on form open) compute does not trigger itself
        :param field_list: field-list of the model
        :return: default field values
        """
        res = super(RoboThreadedReport, self).default_get(field_list)
        res['activated_threaded_reports'] = self.sudo().env.user.company_id.activate_threaded_front_reports
        return res

    activated_threaded_reports = fields.Boolean(compute='_compute_activated_threaded_reports')

    @api.multi
    def _compute_activated_threaded_reports(self):
        """
        Compute //
        Check whether front threaded reports are activated
        :return: None
        """
        threaded = self.sudo().env.user.company_id.activate_threaded_front_reports
        for rec in self:
            rec.activated_threaded_reports = threaded


RoboThreadedReport()
