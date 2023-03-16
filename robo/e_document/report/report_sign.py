# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, exceptions


class IrActionsReportXml(models.Model):
    _inherit = 'ir.actions.report.xml'

    signable = fields.Boolean(string='Signable', default=False, readonly=True)
    ir_actions_server_id = fields.Many2one('ir.actions.server', string='Server action')

    @api.multi
    def create_signable(self):
        for report in self:
            if report.ir_actions_server_id:
                raise exceptions.Warning(_('Reportą %s jau galima pateikti pasirašymui') % report.report_name)
            model_id = self.env['ir.model'].search([('model', '=', report.model)], limit=1).id
            server_action_values = {
                'code': "action = object.env['e.document'].general_sign_call('%s', object)" % report.report_name,
                'model_id': model_id,
                'name': _('Pateikti pasirašymui %s') % report.name,
            }
            server_action = self.env['ir.actions.server'].create(server_action_values)
            server_action.create_action()
            report.write({'ir_actions_server_id': server_action.id})
        self.write({'signable': True})

    @api.multi
    def unlink_signable(self):
        for rec in self:
            rec.sudo().ir_actions_server_id.unlink()
        self.write({'signable': False})

    @api.multi
    def unlink(self):
        self.unlink_signable()
        super(IrActionsReportXml, self).unlink()


IrActionsReportXml()


class Edoc(models.Model):
    _inherit = 'e.document'

    @api.model
    def general_sign_call(self, report_name, records, data=None, no_mark=False, user_ids=[]):
        if not records:
            raise exceptions.Warning(_('Negalima atlikti operacijos, nepaduoti įrašai'))
        if not isinstance(records, models.Model):
            raise exceptions.Warning(_('Negalima atlikti operacijos, įrašų formatas nėra multi-aibė'))
        report_obj = self.env['ir.actions.report.xml']
        report = report_obj._lookup_report(report_name)
        if not isinstance(report, basestring):
            raise exceptions.Warning(_('Netinkamas ataskaitos formatas'))
        result = self.env['report'].get_html(records._ids, report, data=data)
        # result = self.env['ir.actions.report.xml'].render_report(records._ids, report_name, data=None)
        # if format != 'pdf':
        #     raise exceptions.Warning(_('Cannot sign a non pdf document'))
        view_id = self.env.ref('e_document.general_document_view').id
        report = self.env['report']._get_report_from_name(report_name)
        try:
            name_force_2 = '%s' % ' '.join(records.mapped(lambda r: r.name or ''))
        except:
            name_force_2 = False
        if name_force_2:
            name_force = ('%s: ' % report.name) + name_force_2
        else:
            name_force = report.name

        form = data.get('form') if data is not None else False
        employee_id = date_from = date_to = False
        if report_name == 'avansine_apyskaita.report_cashbalance_template' and form:
            employee_id = self.env['hr.employee'].search([
                ('address_home_id', '=', form.get('ids')[0])
            ]).id if form.get('ids') else False
            date_from = form.get('date_start', False)[0] if form.get('date_start') else False
            date_to = form.get('date_end', False)[0] if form.get('date_end') else False

        e_doc_vals = {
            'name_force': name_force,
            # 'generated_document': result.encode('base64'),
            'final_document': result,
            'file_name': '%s.pdf' % name_force,
            'force_view_id': view_id,
            'paperformat_id': report.paperformat_id.id,
            'document_type': 'isakymas',
            'no_mark': no_mark,
            'employee_id2': employee_id,
            'date_from': date_from,
            'date_to': date_to,
            'text_10': report_name,
        }
        new_record = self.env['e.document'].create(e_doc_vals)
        # Check if multiple signing is needed
        if user_ids:
            for user_id in user_ids:
                self.sudo().env['signed.users'].create({
                    'document_id': new_record.id,
                    'user_id': user_id,
                })
        new_record.confirm()
        # inform all invited people to sign
        if user_ids:
            partner_ids = set()
            partner_ids.update(self.env['res.users'].browse(user_ids).mapped('partner_id.id'))
            partner_ids = list(partner_ids)
        else:
            partner_ids = self.env.user.company_id.vadovas.user_id.partner_id.ids
        if partner_ids:
            try:
                doc_url = new_record._get_document_url()
                if doc_url:
                    name_force = '<a href=%s>%s</a>' % (doc_url, name_force)
            except:
                pass
            msg = {
                'body': _('Naujas laukiantis pasirašymo dokumentas "%s".') % name_force,
                'subject': _('Naujas dokumentas pasirašymui'),
                'priority': 'high',
                'front_message': True,
                'rec_model': 'e.document',
                'rec_id': new_record.id,
                'view_id': self.env.ref('e_document.general_document_view').id,
            }
            msg['partner_ids'] = partner_ids
            new_record.robo_message_post(**msg)
        return {
            'name': _('El. dokumentai'),
            'view_mode': 'form',
            'view_id': view_id,
            'view_type': 'form',
            'res_model': 'e.document',
            'res_id': new_record.id,
            'type': 'ir.actions.act_window',
            'context': {},
        }


Edoc()


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    sign_id = fields.Many2one('e.document', string='eDokumentas', ondelete='set null', readonly=True)
    show_invite_sign = fields.Boolean(compute='_compute_show_invite_sign')

    @api.one
    @api.depends('sign_id.state')
    def _compute_show_invite_sign(self):
        if not self.sudo().sign_id or (self.sudo().sign_id and self.sudo().sign_id.state == 'cancel'):
            self.show_invite_sign = True
        else:
            self.show_invite_sign = False

    @api.multi
    def invite_sign(self):
        self.ensure_one()
        action = self.env['e.document'].general_sign_call('l10n_lt_payroll.report_suvestine_sl', self)
        if action and 'res_id' in action and action['res_id']:
            self.sign_id = action['res_id']
        return action

    @api.multi
    def cancel_summary_document(self):
        self.ensure_one()
        if self.sign_id:
            self.sign_id.sudo().write({'active': False})
            self.sign_id = False
        else:
            raise exceptions.UserError(_('Nėra susieto darbo užmokesčio suvestinės dokumento.'))


HrPayslipRun()


class CashBalanceWizard(models.TransientModel):
    _inherit = 'cashbalance.wizard'

    show_button_to_manager = fields.Boolean(string='Show manager\'s button with a confirm',
                                            compute='_compute_show_button_to_manager')

    @api.multi
    def _compute_show_button_to_manager(self):
        user = self.env.user
        show_button_to_manager = not user.is_accountant() and user.is_manager()
        for rec in self:
            rec.show_button_to_manager = show_button_to_manager

    @api.multi
    def invite_sign(self):
        self.ensure_one()
        active_ids = self._context.get('active_ids', [])
        data = {
            'ids': active_ids,
            'model': 'res.partner',
            'form': {
                'ids': active_ids,
                'date_start': [self.report_start],
                'date_end': [self.report_end],
            },
        }
        user_ids = []
        if not self.env.user.company_id.vadovas:
            raise exceptions.UserError(_('Nenustatytas įmonės direktorius.'))
        if active_ids:
            user_ids = self.env['res.partner'].browse(active_ids).mapped('employee_ids.user_id.id')
            user_ids += [self.env.user.company_id.vadovas.user_id.id]
        user_ids = list(set(user_ids))
        action = self.env['e.document'].general_sign_call('avansine_apyskaita.report_cashbalance_template', self, data=data, no_mark=True, user_ids=user_ids)
        if action and 'res_id' in action and action['res_id']:
            self.sign_id = action['res_id']
        if self.show_button_to_manager:
            employee = self.env['hr.employee'].browse(self._context.get('active_id'))
            message = _('User {0} invited {1} to sign advanced accounting report.').format(
                self.env.user.display_name, employee.name_related)
            employee.message_post(subtype='mt_comment', body=message)

        return action


CashBalanceWizard()
