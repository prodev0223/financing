# coding=utf-8
from odoo import _, api, exceptions, fields, models


class RoboOnboardingCategory(models.Model):
    _name = 'robo.onboarding.category'

    name = fields.Char(string='Category name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=1)
    task_ids = fields.One2many('robo.onboarding.task', 'category_id', string='Onboarding tasks')
    shown_to_client = fields.Boolean(string='Shown to client', compute='_compute_shown_to_client', store=True)
    completed = fields.Boolean(string='Category is completed', compute='_compute_completed', store=True)
    comment = fields.Html('Comment')

    @api.multi
    @api.depends('task_ids.shown_to_client')
    def _compute_shown_to_client(self):
        """
        Computes if the category is shown to the client by checking if any of its tasks are set as active
        """
        for rec in self:
            rec.shown_to_client = any(task.shown_to_client for task in rec.task_ids)

    @api.multi
    @api.depends('task_ids.completed', 'task_ids.shown_to_client')
    def _compute_completed(self):
        """
        Computes if the category is completed by checking if all of its tasks are set as completed
        """
        for rec in self:
            rec.completed = all(task.completed for task in rec.task_ids if task.shown_to_client)

    @api.multi
    @api.constrains('sequence')
    def _check_sequence(self):
        """
        Ensures no other categories with the same sequence exist
        """
        if self.filtered(lambda r: r.sequence < 1):
            raise exceptions.client(_('Sequence must be greater than 0'))
        for rec in self:
            if self.search_count([('id', '!=', rec.id), ('sequence', '=', rec.sequence)]):
                raise exceptions.UserError(_('There can only exist one category with one sequence'))

    @api.model
    def get_onboarding_data(self):
        """
        Gets the onboarding data to be displayed using JS
        :return: Dictionary containing info of onboarding categories
        :rtype: dictionary
        """
        res = []
        if self.env.user.is_premium_manager():
            ctx = self._context.copy()
            if not ctx.get('lang'):
                ctx.update({'lang': self.env.user.lang or 'lt_LT'})
            for category in self.with_context(ctx).search([('shown_to_client', '=', True)], order='sequence asc'):
                tasks = category.sudo().task_ids.filtered(lambda t: t.shown_to_client).sorted(key=lambda t: t.sequence)
                res.append({
                    'sequence':  category.sequence,
                    'name':      category.name,
                    'completed': category.completed,
                    'comment': category.comment,
                    'tasks':     [{
                        'name':      task.name,
                        'sequence':  task.sequence,
                        'completed': task.completed,
                        'weight':    task.weight,
                        'action':    task.action_id.xml_id if task.action_id else False,
                        'url_link':  task.url_link if task.url_link else False,
                        'comment':   task.comment,
                    } for task in tasks]
                })
        return res

    @api.model
    def get_robo_onboarding_progress_data(self):
        """
        Returns onboarding progress data - number of tasks total vs number of completed ones of those visible to clients
        :return: {'completed': (int), 'total': (int)}
        :rtype: dictionary
        """
        visible_tasks = self.sudo().env['robo.onboarding.task'].search([
            ('shown_to_client', '=', True)
        ])
        completed_tasks = visible_tasks.filtered(lambda t: t.completed)
        return {
            'completed': len(completed_tasks),
            'total': len(visible_tasks),
            'total_weight': sum(visible_tasks.mapped('weight')),
            'completed_weight': sum(completed_tasks.mapped('weight')),
        }

    @api.model
    def get_full_onboarding_data(self):
        onboarding_categories = self.env['robo.onboarding.category'].sudo().search([])
        data = []
        for category in onboarding_categories:
            data.append({
                'id':              category.id,
                'xml_id':          self.env['ir.model.data'].search([
                    ('model', '=', 'robo.onboarding.category'),
                    ('res_id', '=', category.id)
                ], limit=1).complete_name,
                'sequence':        category.sequence,
                'name':            category.name,
                'completed':       category.completed,
                'shown_to_client': category.shown_to_client,
                'comment':         category.comment,
                'tasks':           [{
                    'id':              task.id,
                    'xml_id':          self.env['ir.model.data'].search([
                        ('model', '=', 'robo.onboarding.task'),
                        ('res_id', '=', task.id)
                    ], limit=1).complete_name,
                    'name':            task.name,
                    'sequence':        task.sequence,
                    'completed':       task.completed,
                    'completion_date': task.completion_date,
                    'shown_to_client': task.shown_to_client,
                    'action':          task.action_id.xml_id if task.action_id else False,
                    'url_link':        task.url_link if task.url_link else False,
                    'weight':          task.weight,
                    'comment':         task.comment,
                } for task in category.task_ids]
            })
        return data

    @api.model
    def set_onboarding_data(self, data_to_set):
        task_obj = self.env['robo.onboarding.category']
        accepted_values = ['completed', 'shown_to_client', 'completion_date', 'weight', 'comment']
        for task_vals in data_to_set:
            task_id = task_vals.get('id')
            task_xml_id = task_vals.get('xml_id')
            if task_id:
                task = task_obj.browse(task_id)
            else:
                task = self.env.ref(task_xml_id)
            vals_to_write = {}
            for val in accepted_values:
                value_to_set = task_vals.get(val)
                if value_to_set or isinstance(value_to_set, bool):
                    vals_to_write.update({val: value_to_set})
            if len(vals_to_write.keys()) != 0:
                task.write(vals_to_write)


RoboOnboardingCategory()
