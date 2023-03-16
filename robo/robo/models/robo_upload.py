# -*- coding: utf-8 -*-
import base64
import hashlib
import mimetypes as import_mimetypes
import re

from odoo import _, api, exceptions, fields, models, tools
from odoo.modules import get_module_resource
from odoo.tools import image
from odoo.tools.mimetypes import guess_mimetype


class RoboUpload(models.Model):
    _name = 'robo.upload'
    _inherit = ['mail.thread']
    _order = 'create_date DESC'

    date_done = fields.Datetime(string='Apdorojimo data')
    datas_md5 = fields.Char(string='Išlaidos')
    datas_fname = fields.Char(string='Failo pavadinimas')
    mimetype = fields.Char(string='Failo tipas')
    state = fields.Selection([('sent', 'Išsiųstas'),
                              ('accepted', 'Priimtas'),
                              ('done', 'Apdorotas'),
                              ('rejected', 'Atmestas'),
                              ('need_action', 'Papildykite duomenis'),
                              ],
                             default='sent', string='Būsena',
                             required=True, readonly=True, inverse='_set_state', track_visibility='onchange')
    attachment_id = fields.Many2one('ir.attachment', string='Siunčiamas failas', ondelete='set null')
    need_action_payment = fields.Boolean(default=False)
    need_action_repr = fields.Boolean(default=False)

    def _track_subtype(self, init_values):
        self.ensure_one()
        if 'state' in init_values:
            self._update_roboUpload_counter()
        else:
            super(RoboUpload, self)._track_subtype(init_values)

    person = fields.Char(string='Pateikė')
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', readonly=True, inverse='_set_employee_id')
    user_id = fields.Many2one('res.users')
    type = fields.Char(string='Dokumento tipas')
    res_model = fields.Char(string='Modelis', readonly=True)
    res_id = fields.Integer(string='Dokumento ID', readonly=True)
    res_type = fields.Char(string='Dokumento tipas')
    ref = fields.Char(string='Nuoroda', readonly=True)
    reason = fields.Text(string='Atmetimo priežastis', readonly=True)
    # uploaded_document = fields.Binary(_('Atsiųstas dokumentas'))
    thumbnail = fields.Binary(string='Nuotrauka', compute="_compute_thumbnail")
    thumbnail_mobile = fields.Binary(string='Nuotrauka', compute="_compute_thumbnail_mobile")
    thumbnail_force = fields.Binary(string='Nuotrauka', attachment=True)
    thumbnail_force_enabled = fields.Boolean(string='Nuotrauka', compute="_thumbnail_force_enabled")
    image_force = fields.Binary(string='Nuotrauka', attachment=True)
    image = fields.Binary(string='Nuotrauka', compute='_image')
    image_id = fields.Integer(string='Programėlės unikalus numeris')
    title = fields.Char(string='Pavadinimas', compute="_title")
    active = fields.Boolean(string='Aktyvus', default=True)

    @api.multi
    def _set_employee_id(self):
        for rec in self:
            if not rec.user_id and rec.sudo().employee_id and rec.sudo().employee_id.user_id:
                rec.user_id = rec.sudo().employee_id.user_id.id

    @api.multi
    @api.depends('datas_fname', 'ref')
    def _title(self):
        for rec in self:
            if rec.ref and 'Robo platform' in rec.ref:
                rec.title = rec.datas_fname
            else:
                rec.title = rec.ref

    @api.multi
    @api.depends('thumbnail_force')
    def _thumbnail_force_enabled(self):
        for rec in self:
            rec.thumbnail_force_enabled = bool(rec.thumbnail_force)

    @api.multi
    @api.depends('thumbnail')
    def _compute_thumbnail_mobile(self):
        for rec in self:
            rec.thumbnail_mobile = image.image_resize_image_small(rec.thumbnail)

    @staticmethod
    def get_mime_type_picture(mime_type):
        if mime_type:
            mime_type = mime_type.lower()
            # the main mime types groups in web module
            if re.compile("^image").match(mime_type):
                return 'image.png'
            if re.compile("application/pdf").match(mime_type):
                return 'pdf.png'
            if re.compile("^text").match(mime_type):
                return 'text.png'
            if re.compile("^text-master").match(mime_type) or ('document' in mime_type) or ('msword' in mime_type):
                return 'document.png'
            if mime_type.endswith('postscript') or mime_type.endswith('cdr') or mime_type.endswith('xara') \
                    or mime_type.endswith('cgm') or mime_type.endswith('graphics') or mime_type.endswith('draw') \
                    or ('svg' in mime_type):
                return 'vector.png'
            if 'xml' in mime_type or mime_type.endswith('css') or mime_type.endswith('html'):
                return 'html.png'
            if mime_type.endswith('csv') or ('vc' in mime_type) or ('excel' in mime_type) \
                    or mime_type.endswith('numbers') or mime_type.endswith('calc') or ('mods' in mime_type) \
                    or ('spreadsheet' in mime_type):
                return 'spreadsheet.png'
        return 'file-empty.png'

    @api.multi
    @api.depends('datas_fname', 'mimetype', 'thumbnail_force')
    def _compute_thumbnail(self):
        for rec in self:
            if rec.thumbnail_force:
                rec.thumbnail = rec.thumbnail_force
            else:
                default_img_path = get_module_resource('web', 'static/src/img/mimetypes/', 'unknown.png')
                if not rec.mimetype and rec.datas_fname:
                    mimetype = import_mimetypes.guess_type(rec.datas_fname)[0]
                    mime_type_picture = RoboUpload.get_mime_type_picture(mimetype)
                else:
                    mime_type_picture = RoboUpload.get_mime_type_picture(rec.mimetype)

                img_path = get_module_resource('web', 'static/src/img/mimetypes/', mime_type_picture) or default_img_path
                if img_path:
                    rec.thumbnail = image.image_resize_image_medium(open(img_path, 'rb').read().encode('base64'))

    @api.multi
    @api.depends('image_force', 'thumbnail')
    def _image(self):
        for rec in self:
            if rec.image_force:
                rec.image = rec.image_force
            else:
                rec.image = rec.thumbnail

    @api.model
    def upload_file_app(self, file_base64, filename, image_id=False):
        md5 = hashlib.md5(file_base64.decode('base64')).hexdigest()
        if self.sudo().search([('datas_md5', '=', md5), ('state', 'not in', ['rejected'])], count=True) != 0:
            return {
                'status': 'error',
                'error': _('Toks failas jau pateiktas'),
            }
        new_upload_record = {
            'datas_md5': md5,
            'datas_fname': filename,
            'state': 'sent',
            'person': self.env.user.name,
            'employee_id': self.env.user.employee_ids[0].id if self.env.user.employee_ids else False,
            'user_id': self.env.user.id,
            'ref': _('Pateikta per Robo platformą'),
        }
        if image_id:
            new_upload_record['image_id'] = image_id
        mimetype = guess_mimetype(file_base64.decode('base64'))
        if re.compile("image/.*").match(mimetype):
            new_upload_record['thumbnail_force'] = image.image_resize_image_medium(file_base64)
            new_upload_record['image_force'] = image.image_resize_image_big(file_base64, size=(640, 640))
        upload_id = self.sudo().create(new_upload_record)
        attach_id = self.env['ir.attachment'].sudo().create({
            'res_model': 'robo.upload',
            'res_id': upload_id.id,
            'type': 'binary',
            'name': filename,
            'datas_fname': filename,
            'datas': file_base64
        })
        upload_id.attachment_id = attach_id.id
        if self.env.user.is_premium():
            try:
                self.upload_file(file_base64, filename, upload_id.id)
            except:
                upload_id.unlink()
                return {
                    'status': 'error',
                    'error': _('Nepavyko pateikti dokumento apdorojimui.'),
                }
            upload_id.state = 'accepted'
        return {
            'status': 'success',
        }

    @api.model
    def cron_re_upload(self):
        uploads = self.env['robo.upload'].search([('state', '=', 'sent'), ('attachment_id', '!=', False)])
        for upload in uploads:
            data = upload.attachment_id.datas
            f_name = upload.attachment_id.name
            self.upload_file(data, f_name, upload.id)

    @api.model
    def upload_file(self, uploaded_file, filename, external_id):
        if not self.env.user.is_premium():
            return False
        internal = self.env['res.company']._get_odoorpc_object()
        vals = {
            'uploaded_file': uploaded_file,
            'filename': filename,
            'external_id': external_id,
            'company_code': self.sudo().env.user.company_id.company_registry,
            'employee_id': self.env.user.employee_ids[0].id if self.env.user.employee_ids else False,
        }
        return internal.execute_kw('project.issue', 'upload_file', (), vals)

    @api.multi
    def get_representation_partner_ids(self):
        """
        Fetch ceo of the company and other partner ids if they belong to need action group and are not opting out
        representation mails
        :return: res.partner records
        """
        self.ensure_one()
        group_id = self.env.ref('robo.group_robo_need_action')

        ceo_partner = self.sudo().user_id.company_id.vadovas.user_id.partner_id

        partner_ids = self.env['res.partner']
        if not ceo_partner.opt_out_representation_mails:
            partner_ids |= ceo_partner

        partner_ids |= self.env['res.users'].search([
            ('groups_id', 'in', group_id.id),
            ('partner_id.opt_out_representation_mails', '=', False)
        ]).mapped('partner_id')

        partner_ids |= self.sudo().env['res.partner'].search([('send_company_mails', '=', True)])

        representative_need_action_mail_channel = self.env.ref('robo.representation_message_mail_channel',
                                                               raise_if_not_found=False)
        if representative_need_action_mail_channel:
            partner_ids |= representative_need_action_mail_channel.sudo().channel_partner_ids

        return partner_ids

    @api.multi
    def get_need_action_message_body(self, body, view_id):
        """
        :return: need action message body in dict format
        """
        self.ensure_one()
        return {
            'body': body,
            'subject': _('Prašymas papildyti dokumento duomenis'),
            'priority': 'high',
            'front_message': True,
            'robo_chat': True,
            'client_message': True,
            'rec_model': self.res_model,
            'rec_id': self.res_id,
            'view_id': view_id,
        }

    @api.multi
    def _set_state(self):
        self.filtered(lambda r: r.state not in ['sent', 'rejected']).mapped('attachment_id').unlink()

        default_msg_receivers = self.env.user.company_id.sudo().default_msg_receivers
        manager_partners = self.env['hr.employee'].search([
            ('robo_access', '=', True), ('robo_group', '=', 'manager')
        ]).mapped('address_home_id')

        # Get mail channel partners
        need_action_payment_mail_channel = self.env.ref('robo.need_action_payment_message_mail_channel',
                                                        raise_if_not_found=False)
        mail_channel_partners = self.env['res.partner']
        if need_action_payment_mail_channel:
            mail_channel_partners |= need_action_payment_mail_channel.sudo().channel_partner_ids

        # Get base views
        income_form = self.env.ref('robo.pajamos_form')
        expenses_form = self.env.ref('robo.robo_expenses_form')
        cheque_form = self.env.ref('robo.cheque_form')

        for rec in self:
            # Determine view
            if rec.res_model == 'account.invoice':
                view_id = income_form.id if rec.res_type in ['out_invoice', 'out_refund'] else expenses_form.id
            elif rec.res_model == 'hr.expense':
                view_id = cheque_form.id
            else:
                view_id = False

            # Build title
            title = rec.datas_fname
            if rec.ref and 'Robo platform' not in rec.ref:
                title = rec.datas_fname + ' (' + rec.ref + ')'

            if rec.state == 'done':
                msg = {
                    'body': _('Pateiktas dokumentas "%s" buvo sėkmingai apdorotas. Dokumentą pateikė %s.') % (
                    title, rec.person),
                    'subject': _('Apdorotas dokumentas'),
                    'priority': 'medium',
                    'front_message': True,
                    'rec_model': rec.res_model,
                    'rec_id': rec.res_id,
                    'view_id': view_id,
                }
            elif rec.state == 'rejected' and not self._context.get('do_not_inform_rejected'):
                msg = {
                    'body': _('Jūsų pateiktas dokumentas buvo atmestas. %s') % (rec.reason or ''),
                    'subject': _('Atmestas dokumentas'),
                    'priority': 'high',
                    'front_message': True,
                    'rec_model': 'robo.upload',
                    'action_id': self.env.ref('robo.show_rejected_files').id,
                }
                if rec.attachment_id:
                    msg['attachments'] = [('dokumentas.pdf', base64.b64decode(rec.attachment_id.datas))]
            elif rec.state == 'need_action' and not self._context.get('do_not_inform_need_action'):
                additional_info = ''
                if rec.res_model and rec.res_id:
                    try:
                        doc_id = self.sudo().env[rec.res_model].browse(rec.res_id)
                        if doc_id.reference:
                            additional_info += '\nDokumento nr.: %s.' % doc_id.reference
                        if doc_id.partner_id:
                            additional_info += '\nTiekėjas: %s.' % doc_id.partner_id.display_name
                    except:
                        pass

                if rec.need_action_repr and not rec.need_action_payment:
                    body = _('Pateiktas naujas dokumentas "%s", reikia papildomos informacijos iš '
                             'Jūsų. Patikslinkite, ar šios sąnaudos yra laikomos įmonės reprezentacinėmis sąnaudomis. %s'
                             ) % (title, additional_info)
                elif rec.need_action_payment and not rec.need_action_repr:
                    body = _('Jūsų pateiktas dokumentas "%s" buvo importuotas, bet reikia papildomos informacijos iš '
                             'Jūsų. Patikslinkite, kaip apmokėjote, kompanijos ar asmeninėmis lėšomis. %s'
                             ) % (title, additional_info)
                elif rec.need_action_payment and rec.need_action_repr:
                    body = _('Jūsų pateiktas dokumentas "%s" buvo importuotas, bet reikia papildomos informacijos iš '
                             'Jūsų. Patikslinkite, kaip apmokėjote, kompanijos ar asmeninėmis lėšomis. %s'
                             ) % (title, additional_info)

                    body_ceo = _('Pateiktas naujas dokumentas "%s", reikia papildomos informacijos iš '
                                 'Jūsų. Patikslinkite, ar šios sąnaudos yra laikomos įmonės reprezentacinėmis sąnaudomis. %s'
                                 ) % (title, additional_info)

                    msg_ceo = rec.get_need_action_message_body(body_ceo, view_id)
                    partner_ids = rec.get_representation_partner_ids()
                    if partner_ids:
                        msg_ceo['partner_ids'] = partner_ids.ids
                        rec.robo_message_post(**msg_ceo)
                else:
                    body = _('Jūsų pateiktas dokumentas "%s" buvo importuotas, bet '
                             'reikia papildomos informacijos iš Jūsų. %s') % (title, additional_info)
                msg = rec.get_need_action_message_body(body, view_id)
            else:
                msg = False
            if msg:
                if rec.need_action_repr and not rec.need_action_payment:
                    partner_ids = rec.get_representation_partner_ids()
                else:
                    partner_ids = rec.mapped('user_id.partner_id')
                    partner_ids |= mail_channel_partners

                if not partner_ids:
                    partner_ids = default_msg_receivers
                if not partner_ids:
                    partner_ids = manager_partners
                if partner_ids:
                    msg['partner_ids'] = partner_ids.ids
                rec.robo_message_post(**msg)

    @api.multi
    def unlink(self):
        self._update_roboUpload_counter()
        return super(RoboUpload, self).unlink()

    # @api.multi
    # def create(self, vals):
    #     res = super(RoboUpload, self).create(vals)
    #     if res:
    #         self._update_roboUpload_counter()
    #     return res

    @api.model
    def get_roboUpload_count(self, **interval):
        docs = self.env['robo.upload'].search([('create_date', '>=', interval['start']),
                                               ('create_date', '<=', interval['end'])])
        vals = {status: len(docs.filtered(lambda r: r.state == status))
                for status in ['accepted', 'done', 'rejected', 'need_action']}
        return vals

    @api.model
    def _update_roboUpload_counter(self):
        message = {'type': 'robo_message'}
        partner_ids = [self.env.user.partner_id.id]
        company_id = self.env.user.company_id.id

        if company_id:
            find_partner_ids = self.env['hr.employee'].search([['company_id', '=', company_id], ['active', '=', True]]) \
                .mapped('user_id').filtered(lambda r: r.active).mapped('partner_id.id')
            if find_partner_ids:
                partner_ids = find_partner_ids

        for partner_id in partner_ids:
            self.env['bus.bus'].sendone((self._cr.dbname, 'robo.upload', partner_id), message)
