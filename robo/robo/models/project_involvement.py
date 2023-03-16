# -*- coding: utf-8 -*-


from odoo import _, api, exceptions, fields, models


class ProjectInvolvement(models.Model):
    _name = 'project.involvement'

    project_id = fields.Many2one('project.project', required=False, string="Project name", ondelete='cascade')
    analytic_account_id = fields.Many2one('account.analytic.account', required=True, string="Analytic account id",
                                          ondelete='cascade')
    user_id = fields.Many2one('res.users', required=True, string='User')
    # employee_id = fields.Many2one('hr.employee', required=True, string="Employee")
    # employee_job = fields.Char(string="Job Title", compute='_get_job_title', store=False, compute_sudo=True)

    job_code_compute = fields.Char(string='Pareigų kodas', compute='_job_code', inverse='_set_job_code')
    job_code = fields.Char(string='Pareigų kodas')

    @api.model
    def create(self, vals):
        res = super(ProjectInvolvement, self).create(vals)
        self.env['ir.rule'].clear_caches()
        return res

    @api.multi
    def unlink(self):
        res = super(ProjectInvolvement, self).unlink()
        self.env['ir.rule'].clear_caches()
        return res

    @api.multi
    def write(self, vals):
        res = super(ProjectInvolvement, self).write(vals)
        self.env['ir.rule'].clear_caches()
        return res

    @api.one
    @api.depends('user_id')
    def _job_code(self):
        if self.job_code:
            self.job_code_compute = self.job_code
        elif self.user_id.employee_ids and self.user_id.employee_ids[0].job_code:
            self.job_code_compute = self.employee_id.job_code
        else:
            self.job_code_compute = self.user_id.partner_id.job_code

    @api.one
    def _set_job_code(self):
        self.job_code = self.job_code_compute

    @api.multi
    @api.constrains('project_id', 'user_id')
    def constraint_unique(self):
        for rec in self:
            if self.env['project.involvement'].search_count(
                    [('user_id', '=', rec.user_id.id), ('analytic_account_id', '=', rec.analytic_account_id.id)]) > 1:
                raise exceptions.ValidationError(
                    _('Vartotojas %s yra priskirtas dukart tam pačiam projektui') % rec.user_id.name)

    # @api.one
    # @api.depends('employee_id')
    # def _get_job_title(self):
    #     job = self.sudo().employee_id.job_id.name or ''
    #     self.employee_job = job
