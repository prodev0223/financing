# -*- coding: utf-8 -*-


from odoo import fields, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    privacy_visibility = fields.Selection(related='analytic_account_id.privacy_visibility')
