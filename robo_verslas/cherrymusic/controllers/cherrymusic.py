# -*- coding: utf-8 -*-
import werkzeug
import odoo
from odoo import http
from odoo.addons.web.controllers.main import Binary
import functools
from odoo.http import request
from odoo.modules import get_module_resource
from cStringIO import StringIO
db_monodb = http.db_monodb


class BinaryCustom(Binary):
    @http.route(['/web/binary/account_logo/<int:journal_id>/',], type='http', auth="none")
    def account_logo(self, journal_id=None, dbname=None, **kw):
        if not journal_id:
            werkzeug.utils.redirect('/web/binary/company_logo/')
        imgname = 'logo.png'
        default_logo_module = 'backend_debranding'
        if request.session.db:
            request.env['ir.config_parameter'].sudo().get_param('backend_debranding.default_logo_module')
        placeholder = functools.partial(get_module_resource, default_logo_module, 'static', 'src', 'img')
        account = request.env['account.journal'].sudo().browse(journal_id)
        if not account:
            werkzeug.utils.redirect('/web/binary/company_logo/')
        if request.session.db:
            dbname = request.session.db
        elif dbname is None:
            dbname = db_monodb()

        if not dbname:
            response = http.send_file(placeholder(imgname))
        else:
            try:
                # create an empty registry
                registry = odoo.modules.registry.Registry(dbname)
                with registry.cursor() as cr:
                    cr.execute("""SELECT j.logo_web, j.write_date
                                    FROM account_journal j
                               LEFT JOIN res_company c
                                      ON c.id = j.company_id
                                   WHERE j.id = %s
                               """, (journal_id,))
                    row = cr.fetchone()
                    if row and row[0]:
                        image_data = StringIO(str(row[0]).decode('base64'))
                        return http.send_file(image_data, filename=imgname, mtime=row[1])
                    else:
                        response = http.send_file(placeholder('nologo.png'))
            except Exception:
                response = http.send_file(placeholder(imgname))

        return response

BinaryCustom()