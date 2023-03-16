# coding=utf-8
from datetime import datetime

from odoo import _, api, exceptions, fields, models


class RoboOnboardingTask(models.Model):
    _name = 'robo.onboarding.task'

    name = fields.Char(string='Task name', required=True, translate=True)
    category_id = fields.Many2one('robo.onboarding.category', string='Category')
    sequence = fields.Integer('Sequence in category', default=1, required=True)

    completed = fields.Boolean(string='Task is completed', default=False)
    completion_date = fields.Datetime(string='Completion time', readonly=True)
    shown_to_client = fields.Boolean(string='Shown to client', default=True)
    action_id = fields.Many2one('ir.actions.act_window',
                                string='Action to open on click in main (front) view', groups="base.group_system")
    url_link = fields.Char(string='URL task redirects to if no action is specified', groups="base.group_system")
    weight = fields.Integer(string='Weight of this task', default=1)
    comment = fields.Html('Comment')
    email_template = fields.Html('Email Template')

    @api.multi
    @api.constrains('sequence')
    def _check_sequence(self):
        tasks_with_same_sequence = self.search([
            ('sequence', '=', self.sequence),
            ('category_id', 'in', self.mapped('category_id.id'))
        ])
        for rec in self:
            if rec.sequence < 1:
                raise exceptions.UserError(_('Sequence must be greater than 0'))
            same_sequence_tasks = tasks_with_same_sequence.filtered(lambda t: t.id != rec.id and
                                                                              t.category_id == rec.category_id)
            if same_sequence_tasks:
                raise exceptions.UserError(_('''Can't set the sequence {} on task {} because another task with the 
                same sequence exists'''.format(rec.sequence, rec.name)))

    @api.multi
    @api.constrains('weight')
    def _check_weight(self):
        for rec in self:
            if rec.weight < 1:
                raise exceptions.ValidationError(_('Task weight has to be positive (Weight of task {} is {})').format(
                    rec.name,
                    rec.weight
                ))


RoboOnboardingTask()
