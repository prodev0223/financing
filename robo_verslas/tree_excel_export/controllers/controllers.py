# -*- coding: utf-8 -*-
try:
    import json
except ImportError:
    import simplejson as json

import odoo.http as http
from odoo.http import request
from odoo.addons.web.controllers.main import ExcelExport
from cStringIO import StringIO
from odoo.tools.misc import xlwt
import datetime
import re
from odoo.exceptions import UserError
from odoo import _, tools

# Excel only supports cell length up to 32767 characters
# https://support.office.com/en-us/article/excel-specifications-and-limits-1672b34d-7043-467e-8e27-269d656771c3
XLS_MAX_CELL_LENGTH = 32767

class ExcelExportView(ExcelExport):
    def __getattribute__(self, name):
        if name == 'fmt':
            raise AttributeError()
        return super(ExcelExportView, self).__getattribute__(name)

    @http.route('/web/export/xls_view', type='http', auth='user')
    def export_xls_view(self, data, token):
        data = json.loads(data)
        columns_headers = data.get('headers', [])
        rows = data.get('rows', [])

        return request.make_response(
            self.from_data(columns_headers, rows),
            headers=[
                ('Content-Disposition', 'attachment; filename="%s"'
                 % self.filename('Eksportas-%s' % datetime.datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))),
                ('Content-Type', self.content_type)
            ],
            cookies={'fileToken': token}
        )

    def from_data(self, fields, rows):
        if len(rows) > 65535:
            raise UserError(_('Faile per daug eilučių (%s eilučių, limitas: 65535). Pabandykite išskaidyti prieš eksportuojant.') % len(rows))
        workbook = xlwt.Workbook()
        worksheet = workbook.add_sheet('Sheet 1')
        header_style = xlwt.easyxf('font: bold on; borders: bottom thin;')
        for i, fieldname in enumerate(fields):
            worksheet.write(0, i, fieldname, header_style)
            worksheet.col(i).width = 8000

        base_style = xlwt.easyxf('align: wrap yes')
        date_style = xlwt.easyxf('align: wrap yes', num_format_str='YYYY-MM-DD')
        datetime_style = xlwt.easyxf('align: wrap yes', num_format_str='YYYY-MM-DD HH:mm:SS')

        for row_index, row in enumerate(rows):
            for cell_index, cell_value in enumerate(row):
                cell_style = base_style
                if isinstance(cell_value, basestring):
                    cell_value = re.sub("\r", " ", cell_value)
                    if len(cell_value) > XLS_MAX_CELL_LENGTH:
                        cell_value = cell_value[:XLS_MAX_CELL_LENGTH - 5] + '(...)'
                elif isinstance(cell_value, datetime.datetime):
                    cell_style = datetime_style
                elif isinstance(cell_value, datetime.date):
                    cell_style = date_style
                worksheet.write(row_index + 1, cell_index, cell_value, cell_style)
        worksheet.set_panes_frozen(True)
        worksheet.set_horz_split_pos(1)
        fp = StringIO()
        workbook.save(fp)
        fp.seek(0)
        data = fp.read()
        fp.close()
        return data