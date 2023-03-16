# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models


class EDocumentDelegate(models.Model):
    _name = 'e.document.delegate'
    _rec_name = 'employee_id'
    _order = 'date_stop DESC'

    employee_id = fields.Many2one('hr.employee', string='Įgaliotinis', required=True)
    date_start = fields.Date(string='Nuo', required=True)
    date_stop = fields.Date(string='Iki', required=True)

    @api.multi
    @api.constrains('date_start', 'date_stop')
    def constraint_intersection(self):
        for rec in self:
            if self.search([('employee_id', '=', rec.employee_id.id), ('date_stop', '>=', rec.date_start),
                            ('date_start', '<=', rec.date_stop)], count=True) > 1:
                raise exceptions.ValidationError(_('Negali persidengti periodai'))
            if rec.date_start > rec.date_stop:
                raise exceptions.ValidationError(_('Pradžios data negali būti vėlesnė už pabaigos datą.'))

    @api.model
    def create(self, vals):
        res = super(EDocumentDelegate, self).create(vals)
        employee = res.employee_id
        user = employee.user_id
        ceo = employee.company_id.vadovas
        if user:
            user.sudo()._compute_delegated_document_ids()
        if ceo.user_id != self.env.user:
            subject = '{0} Naujas įgaliotinis'.format(employee.company_id.name)
            body = """
            Įmonėje {0} buvo paskirtas naujas įgaliotinis {1}.<br>
            Jūs esate informuojamas el. laišku, nes esate įmonės vadovas.
            """.format(employee.company_id.name, employee.name)
            self.env['e.document'].message_post_to_mail_channel(
                subject, body, 'e_document.delegate_changes_mail_channel'
            )
        self.env['ir.rule'].clear_caches()
        if employee:
            self.subscribe_delegate_to_mail_channels(delegate=employee)
        return res

    @api.multi
    def unlink(self):
        employee_ids = self.mapped('employee_id')
        ceo = self.env.user.company_id.vadovas
        if ceo.user_id != self.env.user:
            subject = '{0} Pašalintas įgaliotinis'.format(ceo.company_id.name)
            body = """
            Įmonėje {0} buvo pašalinti įgaliotiniai {1}.<br>
            Jūs esate informuojamas el. laišku, nes esate įmonės vadovas.
            """.format(ceo.company_id.name, ', '.join([emp.name for emp in employee_ids]))
            self.env['e.document'].message_post_to_mail_channel(
                subject, body, 'e_document.delegate_changes_mail_channel'
            )
        res = super(EDocumentDelegate, self).unlink()
        employee_ids.mapped('user_id').sudo()._compute_delegated_document_ids()
        self.env['ir.rule'].clear_caches()
        return res

    @api.multi
    def write(self, vals):
        changes_list_str = []
        for key, val in vals.items():
            if key == 'employee_id':
                new_name = self.employee_id.search([('id', '=', val)]).name
                changes_list_str.append('Pakeistas įgaliotinis iš {0} į {1}.'.format(self.employee_id.name, new_name))
            elif key == 'date_start':
                changes_list_str.append(
                    'Pakeista įgaliotinio pradžios data iš {0} į {1}.'.format(self.date_start, vals.get('date_start')))
            elif key == 'date_stop':
                changes_list_str.append(
                    'Pakeista įgaliotinio pabaigos data iš {0} į {1}.'.format(self.date_stop, vals.get('date_stop')))

        employee_ids = self.mapped('employee_id')
        res = super(EDocumentDelegate, self).write(vals)
        employee_id = vals.get('employee_id', False)
        if employee_id:
            employee_ids |= self.env['hr.employee'].browse(employee_id)
        employee_ids.mapped('user_id').sudo()._compute_delegated_document_ids()
        self.env['ir.rule'].clear_caches()

        ceo = self.env.user.company_id.vadovas
        if self.env.user != ceo.user_id:
            if ceo.address_home_id.email:
                subject = '{0} Pakeisti įgaliotiniai'.format(ceo.company_id.name)
                body = """
                Įmonėje {0} buvo pakeisti įgaliotinio duomenys, padaryti šie pakeitimai:<br>
                {1}<br>
                Jūs esate informuojamas el. laišku, nes esate įmonės vadovas.
                """.format(self.env.user.company_id.name, '<br>'.join(changes_list_str))
                self.env['e.document'].message_post_to_mail_channel(
                    subject, body, 'e_document.delegate_changes_mail_channel'
                )
        return res

    @api.multi
    def subscribe_delegate_to_mail_channels(self, delegate):
        channels = self.get_delegate_mail_channels()
        if delegate and channels:
            channels.write({'channel_partner_ids': [(4, delegate.address_home_id.id)]})

    def get_delegate_mail_channels(self):
        """ return default mail channel records for delegate """
        channels = self.env['mail.channel']
        channel_eids = [
            'e_document.inform_about_limited_capacity_of_work_documents',
        ]
        for eid in channel_eids:
            channel = self.env.ref(eid, False)
            if channel:
                channels |= channel
        return channels


EDocumentDelegate()
