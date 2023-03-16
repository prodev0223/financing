# -*- coding: utf-8 -*-
import base64
import cStringIO as StringIO
import functools
import hashlib
import json
import re
import urllib2

import werkzeug.utils
import werkzeug.wrappers
from PIL import ExifTags, Image
from odoo.addons.bus.controllers.main import BusController
from odoo.addons.web.controllers.main import binary_content, serialize_exception

from odoo import http, exceptions
from odoo.http import Controller, request, route
from odoo.modules import get_resource_path
from odoo.tools import image
from odoo.tools.translate import _


def rotateImage(data):
    imgBuffer = StringIO.StringIO()
    imgBuffer.write(data)
    imgBuffer.seek(0)

    img = Image.open(imgBuffer)
    for orientation in ExifTags.TAGS:
        if ExifTags.TAGS[orientation] == 'Orientation':
            break

    if img._getexif():
        exif = dict(img._getexif().items())

        if exif.get(orientation) == 3:
            img = img.rotate(180, expand=True)
        elif exif.get(orientation) == 6:
            img = img.rotate(270, expand=True)
        elif exif.get(orientation) == 8:
            img = img.rotate(90, expand=True)

        imgBuffer = StringIO.StringIO()
        img.save(imgBuffer, format='JPEG')
        data = imgBuffer.getvalue()

    img.close()
    return data


class RoboMessageBusController(BusController):

    # --------------------------
    # Extends BUS Controller Poll
    # --------------------------
    def _poll(self, dbname, channels, last, options):
        if request.session.uid:
            partner_id = request.env.user.partner_id.id
            if partner_id:
                channels = list(channels)
                channels.append((request.db, 'robo.message', request.env.user.partner_id.id))
                channels.append((request.db, 'robo.upload', request.env.user.partner_id.id))  # for robo upload counter
        return super(RoboMessageBusController, self)._poll(dbname, channels, last, options)


class roboControler(Controller):

    # @route('/roboMessage/needaction', type='json', auth='user')
    # def needaction(self):
    #     return request.env['res.partner'].get_needRoboAction_count()

    @route('/e_document/needaction', type='json', auth='user')
    def needaction(self):
        return request.env['e.document'].get_needaction_count()

    @route('/robomessage/needaction', type='json', auth='user')
    def countRoboFrontMessages(self):
        return request.env['res.partner'].get_roboNeedaction_count()

    @route('/robomessage/lastmessages', type='json', auth='user')
    def lastRoboFrontMessages(self):
        return request.env['res.partner'].get_lastRoboNeedaction_messages()

    @route('/roboupload/statistics', type='json', auth='user')
    def countRoboUploadFiles(self, **dates):
        return request.env['robo.upload'].get_roboUpload_count(**dates)

    @route('/robo/upload', type='http', auth="user")
    @serialize_exception
    def upload(self, callback, ufile):
        # uploaded_for_scanning = False
        try:
            data = ufile.read()

            if re.compile("image/jpeg").match(ufile.content_type):
                data = rotateImage(data)

            md5 = hashlib.md5(data).hexdigest()

            Model = request.env['robo.upload']
            ir_attachment = request.env['ir.attachment']
            try:
                Model.check_global_readonly_access()
            except exceptions.AccessError:
                return request.make_response(_('You have readonly access enabled. If you think this is a mistake - '
                                               'please contact the system administrator'))
            if Model.sudo().search([('datas_md5', '=', md5), ('state', 'not in', ['rejected'])], count=True) == 0:
                new_upload_record = {
                    # 'name': ufile.filename,
                    'datas_md5': md5,
                    'datas_fname': ufile.filename,
                    'mimetype': ufile.content_type,
                    'state': 'sent',
                    'person': request.env.user.name,
                    'employee_id': request.env.user.employee_ids[0].id if request.env.user.employee_ids else False,
                    'user_id': request.env.user.id if request.env.user else False,
                    'ref': _('Pateikta per Robo platformą'),
                }
                if re.compile("image/.*").match(ufile.content_type):
                    new_upload_record['thumbnail_force'] = image.image_resize_image_medium(data.encode('base64'))
                uploadRecord = Model.sudo().create(new_upload_record)
                attach_id = ir_attachment.sudo().create({
                    'res_model': 'robo.upload',
                    'res_id': uploadRecord.id,
                    'type': 'binary',
                    'name': ufile.filename,
                    'datas_fname': ufile.filename,
                    'datas': base64.b64encode(data),
                })
                uploadRecord.attachment_id = attach_id.id
                request.env.cr.commit()
                uploaded_for_scanning = Model.upload_file(base64.b64encode(data), ufile.filename, uploadRecord.id)
                if not uploaded_for_scanning:
                    uploadRecord.unlink()
                    if not request.env.user.is_premium():
                        response = request.make_response(_('Pateikti dokumentus gali tik Premium vartotojai.'))
                    else:
                        response = request.make_response(_('Dokumento nepavyko pateikti apdorojimui.'))
                    # uploadRecord.state = 'rejected'
                else:
                    response = request.make_response('success')
                    if not ufile.filename.lower().endswith('.xml'):
                        uploadRecord.state = 'accepted'
            else:
                response = request.make_response(_('Toks dokumentas jau pateiktas'))
        except Exception:
            response = request.make_response(_('Dokumento nepavyko pateikti apdorojimui.'))

        return response

    # def placeholder(self, image='placeholder.png'):
    #     addons_path = http.addons_manifest['web']['addons_path']
    #     return open(os.path.join(addons_path, 'web', 'static', 'src', 'img', image), 'rb').read()

    @route(['/web/binary/robolabs_logo', '/robolabs_logo', '/robolabs_logo.png', ], type='http', auth="none", cors="*")
    def robo_logo(self):
        imgname = 'robolabs'
        imgext = '.png'
        placeholder = functools.partial(get_resource_path, 'robo', 'static', 'src', 'img')
        response = http.send_file(placeholder(imgname + imgext))
        if not response:
            placeholder = functools.partial(get_resource_path, 'web', 'static', 'src', 'img')
            response = http.send_file(placeholder('nologo.png'))

        return response

    @http.route('/web/binary/upload_attachment_invoice', type='http', auth="user")
    @serialize_exception
    def upload_attachment(self, model, id, wizard_id, ufile):
        Model = request.env['ir.attachment']
        try:
            Model.check_global_readonly_access()
        except exceptions.AccessError:
            args = {'error': _('You have readonly access enabled. If you think this is a mistake - '
                               'please contact the system administrator')}
            return json.dumps(args)
        # bin_data = ufile.read()
        # sha1 = hashlib.sha1(bin_data or '').hexdigest()
        if model not in ['account.invoice', 'hr.expense', 'hr.employee', 'project.project', 'project.task',
                         'account.payment', 'cash.receipt', 'stock.inventory', 'e.document.upload', 'e.document',
                         'client.support.ticket.wizard', 'support.ticket.create.wizard', 'product.template', 'mail.compose.message']:
            args = {'error': _("Prisegti dokumento nepavyko. Netinkamas modelis.")}
            return json.dumps(args)

        try:
            data = ufile.read()
            if re.compile("image/jpeg").match(ufile.content_type):
                data = rotateImage(data)
        except Exception:
            return json.dumps({'error': _('Dokumento nepavyko pateikti.')})

        if not int(id) > 0:
            try:
                attachment = request.env['ir.attachment.wizard'].create({
                    'name': ufile.filename,
                    'datas': base64.encodestring(data),
                    'datas_fname': ufile.filename,
                    'res_model': model,
                    'res_id': 0,
                    'wizard_id': wizard_id
                })
                args = {
                    'filename': ufile.filename,
                    'mimetype': ufile.content_type,
                    'wizard_id': attachment.id
                }
            except Exception:
                args = {'error': _('Pabandykite prisegti dokumentą jau išsaugotai sąskaitai.')}
            return json.dumps(args)

        # ROBO: each model drop lock exception messages
        if model == 'account.invoice':
            if request.env[model].sudo().browse(int(id)).exists().attachment_drop_lock:
                args = {'error': _('Negalite pateikti naujų dokumentų, nes sąskaita jau patvirtinta.')}
                return json.dumps(args)

        if model == 'hr.expense':
            if request.env[model].sudo().browse(int(id)).exists().attachment_drop_lock:
                args = {'error': _('Negalite pateikti naujų dokumentų, nes čekio redagavimas sustabdytas. Grįžkite į sąskaitą faktūrą.')}
                return json.dumps(args)
        if model == 'product.template':
            if request.env[model].sudo().browse(int(id)).exists().attachment_drop_lock:
                args = {'error': _('Negalite pateikti dokumentų, nes neturite reikiamų teisių.')}
                return json.dumps(args)
        if model == 'hr.employee':
            doc = request.env[model].search([('id', '=', int(id))], limit=1)
            if doc and doc.attachment_drop_lock:
                args = {'error': _('Negalite pateikti dokumentų, nes neturite reikiamų teisių.')}
                return json.dumps(args)
        if model in ['project.project', 'project.task', 'cash.receipt', 'account.payment']:
            doc = request.env[model].search([('id', '=', int(id))], limit=1)
            if doc and doc.attachment_drop_lock:
                args = {'error': _('Negalite pateikti dokumentų.')}
                return json.dumps(args)

        if Model.sudo().search([('res_model', '=', model), ('res_id', '=', id)], count=True) >= 15:
            args = {'error': _('Negalite pateikti daugiau dokumentų.')}
            return json.dumps(args)

        if Model.sudo().search([('name', '=', ufile.filename), ('res_model', '=', model), ('res_id', '=', id)],
                               count=True) != 0:
            args = {'error': _('Tokiu pavadinimu failas jau pateiktas.')}
            return json.dumps(args)

        try:
            attachment = Model.create({
                'name': ufile.filename,
                'datas': base64.encodestring(data),
                'datas_fname': ufile.filename,
                'res_model': model,
                'res_id': int(id)
            })
            args = {
                'filename': ufile.filename,
                'mimetype': ufile.content_type,
                'id': attachment.id
            }
        except Exception:
            args = {'error': _("Sistemos klaida. Bandykite pakartoti operaciją.")}
            # _logger.exception("Fail to upload attachment %s" % ufile.filename)
        return json.dumps(args)

    @http.route(['/web/content/wizard',
                 '/web/content/wizard/<int:id>'], type='http', auth="public")
    def content_common(self, xmlid=None, model='ir.attachment.wizard', id=None, field='datas', filename=None,
                       filename_field='datas_fname', unique=None, mimetype=None, download=None, data=None, token=None):
        status, headers, content = binary_content(xmlid=xmlid, model=model, id=id, field=field, unique=unique,
                                                  filename=filename, filename_field=filename_field, download=download,
                                                  mimetype=mimetype)
        if status == 304:
            response = werkzeug.wrappers.Response(status=status, headers=headers)
        elif status == 301:
            return werkzeug.utils.redirect(content, code=301)
        elif status != 200:
            response = request.not_found()
        else:
            content_base64 = base64.b64decode(content)
            headers.append(('Content-Length', len(content_base64)))
            response = request.make_response(content_base64, headers)
        if token:
            if data and status != 200:
                content_base64 = base64.b64decode(data)
                headers.append(('Content-Length', len(content_base64)))
                headers.append(('Content-Type', 'application/octet-stream'))
                escaped = urllib2.quote(filename.encode('utf8'))
                browser = request.httprequest.user_agent.browser
                version = int((request.httprequest.user_agent.version or '0').split('.')[0])
                if browser == 'msie' and version < 9:
                    pav = "attachment; filename=%s" % escaped
                elif browser == 'safari' and version < 537:
                    pav = u"attachment; filename=%s" % filename.encode('ascii', 'replace')
                else:
                    pav = "attachment; filename*=UTF-8''%s" % escaped
                headers.append(('Content-Disposition', pav))
                response = request.make_response(content_base64, headers)
            response.set_cookie('fileToken', token)
        return response
