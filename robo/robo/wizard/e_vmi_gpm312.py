# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, models


class EVmiGpm312(models.TransientModel):
    _inherit = 'e.vmi.gpm312'

    @api.multi
    def form_gpm312(self):
        if self.sudo().env.user.company_id.activate_threaded_front_reports:
            return self.env['robo.report.job'].generate_report(self, 'get_gpm312_ffdata', 'GPM312', returns='base64', forced_name='GPM312', forced_extension='ffdata')
        else:
            return super(EVmiGpm312, self).form_gpm312()

    @api.multi
    def get_gpm312_ffdata(self):
        """ Gets the GPM312 ffdata as base64 """
        failas, error = self._form_gpm312()
        if error:
            body = '''<p>Hello,</p>
            <p>While generating the GPM report, the following error message were returned</p>
            <p>{}</p>'''.format(error)
            try:
                ticket_obj = self.env['mail.thread']._get_ticket_rpc_object()
                vals = {
                    'ticket_dbname': self.env.cr.dbname,
                    'ticket_model_name': self._name,
                    'ticket_record_id': False,
                    'name': 'GPM312 threaded reports',
                    'ticket_user_login': self.env.user.login,
                    'ticket_user_name': self.env.user.name,
                    'description': body,
                    'ticket_type': 'accounting',
                }
                res = ticket_obj.create_ticket(**vals)
                if not res:
                    raise exceptions.UserError(_('The distant method did not create the ticket.'))
            except:
                findir_email = self.sudo().env.user.company_id.findir.partner_id.email
                if findir_email:
                    self.env['script'].send_email(emails_to=[findir_email],
                                                  subject='GPM312 threaded reports',
                                                  body=body)
                else:
                    self.env['robo.bug'].create({
                        'user_id': self.env.user.id,
                        'error_message': body,
                    })
        return failas
