# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import _, api, exceptions, fields, models, tools


class EDocumentTemplate(models.Model):
    _name = 'e.document.template'

    template = fields.Text(string='template', compute='_template', store=True, groups='base.group_system')
    name = fields.Char(sting=_('Name'))
    header = fields.Text(string='header', default='', groups='base.group_system')
    force_header = fields.Text(string='forced header', default='', groups='base.group_system')
    body = fields.Text(string='body', default='', groups='base.group_system')
    force_body = fields.Text(string='forced body', default='', groups='base.group_system')
    footer = fields.Text(string='footer', default='', groups='base.group_system')
    force_footer = fields.Text(string='forced footer', default='', groups='base.group_system')
    view_id = fields.Many2one('ir.ui.view')
    python_code = fields.Text(string='Python code', groups='base.group_system')
    date_from_field_name = fields.Char(string='Date from field name', groups='base.group_system')
    date_to_field_name = fields.Char(string='Date to field name', groups='base.group_system')
    send_manager = fields.Boolean()
    allow_copy = fields.Boolean()
    is_signable_by_delegate = fields.Boolean(string='Document is signable by delegate')
    sign_mail_channel_ids = fields.Many2many('mail.channel', string='Mail channels',
                                             help='Mail channels to inform when a document with this '
                                                  'template gets signed')
    date_lim_for_signing_field_name = fields.Char(string='Date field to use for specific template')

    @api.one
    @api.depends('header', 'body', 'footer', 'force_header', 'force_body', 'force_footer')
    def _template(self):
        header = self.force_header or self.header or ''
        body = self.force_body or self.body or ''
        footer = self.force_footer or self.footer or ''
        self.template = '<div class="page">' + header + body + footer + '</div>'

    @api.constrains('date_from_field_name')
    def _check_date_from_field_name(self):
        for rec in self.sudo():
            if rec.date_from_field_name and rec.date_from_field_name not in self.env['e.document']._fields:
                raise exceptions.ValidationError('Wrong date from field name %s' % rec.date_from_field_name)

    @api.constrains('date_to_field_name')
    def _check_date_to_field_name(self):
        for rec in self.sudo():
            if rec.date_to_field_name and rec.date_to_field_name not in self.env['e.document']._fields:
                raise exceptions.ValidationError('Wrong date to field name %s' % rec.date_to_field_name)

    @api.model
    def date_to_string(self, date, date_format=tools.DEFAULT_SERVER_DATE_FORMAT):
        if isinstance(date, datetime):
            date_dt = date
        else:
            try:
                date_dt = datetime.strptime(date, date_format)
            except (ValueError, TypeError):
                return date
        year = date_dt.strftime('%Y')
        month = date_dt.strftime('%B')
        day = date_dt.strftime('%d')
        date_string = '{}{} {} {}'.format(year, _('m.'), _(month), day)  # 2021 January 01
        return date_string
