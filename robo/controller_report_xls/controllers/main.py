# coding: utf-8
from odoo.addons.report.controllers import main
from odoo.http import route, request
from odoo import tools, _, models, api
import time
from werkzeug import url_decode
import simplejson
import lxml.html
import re
import unicodedata
import xlwt
import StringIO
import logging
import codecs
from odoo.addons.web.controllers.main import content_disposition
from six import iteritems
_logger = logging.getLogger(__name__)


kwd_mark = object()
cache_styles = {}


def strip_accents(text):
    try:
        text = unicode(text)
    except:
        pass
    text = unicodedata.normalize('NFD', text)
    text = text.encode('ascii', 'ignore')
    text = text.decode("utf-8")
    return str(text)


def cached_easyxf(string, style):
    # if not hasattr(self, '_cached_easyxf'):
    #     self._cached_easyxf = {}
    key = (string,) + (kwd_mark,) # + tuple(sorted(kwargs.items()))
    return cache_styles.setdefault(key, style)


def get_currency_style(text, decimal_point, thousands_sep):
    text = text.replace("&nbsp;", " ")
    text = text.replace(unichr(160), unichr(32))
    text = text.replace("..", "  ")
    text = text.replace(codecs.BOM_UTF8, '')
    symbol = False
    if '-\n' in text:
        text = text.replace(' ', '').replace('-\n', '-')
    for ch in text.decode('utf-8'):
        if unicodedata.category(ch) == 'Sc':
            symbol = ch
            break
    currency_style = False
    if unichr(8364) in text:  # '€'
        text = text.replace(unichr(8364), "")
        text = text.replace(decimal_point, ".")
        text = text.replace(thousands_sep, "")
        currency_style = cached_easyxf(
            "#,##0.00 [$" + unichr(8364) + "-lt-LT];-#,##0.00 [$" + unichr(8364) + "-lt-LT]",
            xlwt.easyxf(num_format_str="#,##0.00 [$" + unichr(8364) + "-lt-LT];-#,##0.00 [$" + unichr(
                8364) + "-lt-LT]"))
    elif unichr(36) in text:  # $
        text = text.replace(unichr(36), "")
        text = text.replace(decimal_point, ".")
        text = text.replace(thousands_sep, "")
        currency_style = cached_easyxf("[$$-409]#,##0.00;-[$$-409]#,##0.00", xlwt.easyxf(
            num_format_str="[$$-409]#,##0.00;-[$$-409]#,##0.00".encode('utf-8')))
    elif unichr(163) in text:  # pound
        text = text.replace(unichr(163), "")
        text = text.replace(decimal_point, ".")
        text = text.replace(thousands_sep, "")
        formatting = "[$%(ch)s-809]#,##0.00;-[$%(ch)s-809]#,##0.00".encode('utf-8') % {
            'ch': unichr(163)}
        currency_style = cached_easyxf(formatting, xlwt.easyxf(
            num_format_str=formatting))
    elif unichr(322) in text:  # zl
        text = text.replace('z' + unichr(322), "")
        text = text.replace(decimal_point, ".")
        text = text.replace(thousands_sep, "")
        formatting = "# ##0.00\ [$z%(ch)s-415]".encode('utf-8') % {'ch': unichr(322)}
        currency_style = cached_easyxf(formatting, xlwt.easyxf(
            num_format_str=formatting))
    elif unichr(165) in text:
        text = text.replace(unichr(165), "")
        text = text.replace(decimal_point, ".")
        text = text.replace(thousands_sep, "")
        formatting = "[$%(ch)s-804]#,##0.00;[$%(ch)s-804]-#,##0.00".encode('utf-8') % {
            'ch': unichr(165)}
        currency_style = cached_easyxf(formatting, xlwt.easyxf(
            num_format_str=formatting))
    elif symbol:
        text = re.sub('[^a-zA-Z\d:,.]', '', text)
        text = text.replace(decimal_point, ".")
        text = text.replace(thousands_sep, "")
        formatting = "[$%(ch)s-409]#,##0.00;-[$%(ch)s-409]#,##0.00".encode('utf-8') % {'ch': symbol}
        currency_style = cached_easyxf(formatting, xlwt.easyxf(
            num_format_str=formatting))

    currency_symbols = [unichr(8364), unichr(36), unichr(163), unichr(322), unichr(165)]
    if text.count('.') > 1 and (symbol or any(currency_symbol in text for currency_symbol in currency_symbols)):
        count = text.count('.') - 1
        text = text.replace('.', '', count)

    return currency_style, text


def get_xls(html, context, decimal_point, thousands_sep, header_text, coding='utf-8'):
    wb = xlwt.Workbook(encoding=coding)
    ws = wb.add_sheet('Report')
    cols_max_width = {}
    elements = lxml.html.fromstring(html)
    row = 0
    center = 0
    col_count = 0
    try:
        main_table = elements.get_element_by_id('table_body')
        if len(main_table):
            col_count = len(main_table.findall(".//th"))
            center = int(col_count / 2)
            center += 1 if center % 2 else 0
        main_el = elements.get_element_by_id('main')
    except:
        try:
            main_el = elements.get_element_by_id('main')
        except:
            main_el = elements

    if len(main_el):
        desc = 0
        tables = []
        if dict(main_el.attrib).get('class', False) and 'xls_front' in dict(main_el.attrib).get('class', False):
            tables = [x for x in main_el.findall(".//table") if 'main_table' in x.attrib.get('class', '')]
        style_b = xlwt.easyxf("font: bold on; align: horiz left")
        style_wb = xlwt.easyxf("align: horiz left")
        style_hc = xlwt.easyxf('align: horiz center')
        style_t = xlwt.easyxf("borders: left thin, bottom thin; font: bold on")
        style_bt = xlwt.easyxf("borders: bottom thick;")
        if tables:
            ws.set_panes_frozen(True)
            ws.set_horz_split_pos(2)
            company_info_style = xlwt.easyxf("font: bold on; align: horiz left")
            ws.write_merge(row, 0, 0, 12, header_text, company_info_style)
            row += 1
            force_header = True
            for table in tables:
                if not col_count:
                    col_count = len(table.findall(".//th"))
                head_rows = table.findall(".//thead")
                rows = table.findall(".//tr")
                if head_rows and not table.findall(".//thead//tr"):
                    rows = head_rows + rows
                for tr in rows:
                    style = style_b if dict(tr.attrib).get('style', '') and \
                        'font-weight: bold;' in dict(tr.attrib).get('style', '') or \
                        'font-style:italic' in dict(tr.attrib).get('style', '') else style_wb
                    cols = tr.findall(".//td")
                    if not cols:
                        cols = tr.findall(".//th")
                    if not cols:
                        continue
                    col = 0
                    if len(cols) == 1 and center > 1:
                        col += 1
                    for td in cols:
                        elem = td.find(".//div")
                        if elem is None:
                            elem = td
                        if elem is not None and ('font-weight: bold;' in dict(elem.attrib).get('style', '') or
                                                 'font-style:italic' in dict(elem.attrib).get('style', '')):
                            style = style_b
                        colspan = int(td.get("colspan", 1))
                        text = "%s" % td.text_content().encode(coding, 'ignore')
                        currency_style, text = get_currency_style(text, decimal_point, thousands_sep)
                        text = text.strip()
                        if not row or force_header:
                            ws.write(row, col, text, style_t)
                        else:
                            try:
                                if currency_style:
                                    ws.row(row).set_cell_number(col, float(text), currency_style)
                                elif style:
                                    ws.row(row).set_cell_number(col, float(text), style)
                                else:
                                    ws.row(row).set_cell_number(col, float(text))
                            except ValueError:
                                if style:
                                    ws.write(row, col, text, style)
                                else:
                                    ws.write(row, col, text)
                        cols_max_width[col] = get_width(len(text)+2) if get_width(len(text)+2) > cols_max_width.get(
                            col, 0) else cols_max_width[col]
                        col += colspan
                    row += 1
                    force_header = False
                additional_elements = [x for x in main_el.findall(".//div") if 'xls_include' in x.attrib.get('class', '')]
                if additional_elements:
                    row += 1
                    for col in range(0, col_count):
                        ws.write(row, col, '', style_bt)
                    row += 1
                for element in additional_elements:
                    if element.tag == 'div' and element in element.find_class('row'):
                        row_cells = [[], []]
                        for child in element.iterchildren():
                            row_num = 0
                            for tag in child.iterchildren():
                                if tag.tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'span', 'p']:
                                    style = get_tag_style(tag)
                                else:
                                    continue
                                text = "%s" % tag.text_content().encode(coding, 'ignore')
                                text = text.replace("&nbsp;", " ")
                                if unichr(322) in text or [ch for ch in text.decode(coding) if unicodedata.category(ch) == 'Sc']:
                                    text = text.replace(decimal_point, ".")
                                    text = text.replace(thousands_sep, "")
                                text = text.strip()
                                row_cells[row_num].append((text, style))
                                if row_num < 1:
                                    row_num += 1
                                else:
                                    row_num = 0
                        for row_item in row_cells:
                            col = 0
                            for cell in row_item:
                                try:
                                    if cell[1]:
                                        ws.row(row).set_cell_number(col, float(cell[0]), cell[1])
                                    else:
                                        ws.row(row).set_cell_number(col, float(cell[0]))
                                except ValueError:
                                    if cell[1]:
                                        ws.write(row, col, cell[0], cell[1])
                                    else:
                                        ws.write(row, col, cell[0])
                                cols_max_width[col] = get_width(len(cell[0])) if get_width(len(cell[0])) > cols_max_width.get(col, 0) else \
                                    cols_max_width[col]
                                col += 1
                            if row_item:
                                row += 1

                row += 1
                for col in range(0, col_count):
                    ws.write(row, col, '', style_bt)
                row += 1
        else:
            for element in main_el.iterdescendants():
                if desc > 0:
                    desc -= 1
                    continue
                if dict(element.attrib).get('class', False) and 'xls_exclude' in dict(element.attrib).get('class', False):
                    continue
                desc = 0
                if element.tag == 'table':
                    desc = element.xpath('count(descendant::*)')
                    head_rows = element.findall(".//thead")
                    rows = element.findall(".//tr")
                    if head_rows and not element.findall(".//thead//tr"):
                        rows = head_rows + rows
                    for tr in rows:
                        cols = tr.findall(".//td")
                        if not cols:
                            cols = tr.findall(".//th")
                        if not cols:
                            continue
                        col = 0
                        if len(cols) == 1 and center > 1:
                            col += 1
                        for td in cols:
                            colspan = int(td.get("colspan", 1))
                            style = False
                            for child in td.getchildren():
                                if child.tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                                    style = get_tag_style(child)
                                elif child.find_class('text_centered'):
                                    style = cached_easyxf('align: horiz center', style_hc)
                            text = "%s" % td.text_content().encode(coding, 'ignore')
                            currency_style, text = get_currency_style(text, decimal_point, thousands_sep)
                            text = text.strip()
                            try:
                                if currency_style:
                                    ws.row(row).set_cell_number(col, float(text), currency_style)
                                elif style:
                                    ws.row(row).set_cell_number(col, float(text), style)
                                else:
                                    ws.row(row).set_cell_number(col, float(text))
                            except ValueError:
                                if style:
                                    ws.write(row, col, text, style)
                                else:
                                    ws.write(row, col, text)
                            cols_max_width[col] = get_width(len(text)) if get_width(len(text)) > cols_max_width.get(col, 0) else cols_max_width[col]
                            col += colspan
                        # update the row pointer AFTER a row has been printed
                        # this avoids the blank row at the top of your table
                        row += 1
                    row += 1
                elif element.tag == 'div' and element in element.find_class('row'):
                    desc = element.xpath('count(descendant::*)')
                    row_cells = [[], []]
                    for child in element.iterchildren():
                        row_num = 0
                        for tag in child.iterchildren():
                            if tag.tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'span', 'p']:
                                style = get_tag_style(tag)
                            else:
                                continue
                            text = "%s" % tag.text_content().encode(coding, 'ignore')
                            text = text.replace("&nbsp;", " ")
                            if unichr(322) in text or [ch for ch in text.decode(coding) if unicodedata.category(ch) == 'Sc']:
                                text = text.replace(decimal_point, ".")
                                text = text.replace(thousands_sep, "")
                            text = text.strip()
                            row_cells[row_num].append((text, style))
                            if row_num < 1: # for general ledger report (date from, date to should be on same row)
                                row_num += 1
                            else:
                                row_num = 0
                    for row_item in row_cells:
                        col = 0
                        for cell in row_item:
                            try:
                                if cell[1]:
                                    ws.row(row).set_cell_number(col, float(cell[0]), cell[1])
                                else:
                                    ws.row(row).set_cell_number(col, float(cell[0]))
                            except ValueError:
                                if cell[1]:
                                    ws.write(row, col, cell[0], cell[1])
                                else:
                                    ws.write(row, col, cell[0])
                            cols_max_width[col] = get_width(len(cell[0])) if get_width(len(cell[0])) > cols_max_width.get(col, 0) else \
                                cols_max_width[col]
                            col += 1
                        row += 1
                elif element.tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'strong']:
                    desc = element.xpath('count(descendant::*)')
                    col = 0
                    if center > 1:
                        col += 1
                    style = get_tag_style(element)
                    text = "%s" % element.text_content().encode(coding, 'ignore')
                    text = text.replace("&nbsp;", " ")
                    text = text.replace(decimal_point, ".")
                    text = text.replace(thousands_sep, "")
                    text = text.replace("..", "  ")
                    text = text.strip()
                    try:
                        ws.row(row).set_cell_number(col, float(text), style)
                    except ValueError:
                        ws.write(row, col, text, style)
                    cols_max_width[col] = get_width(len(text)) if get_width(len(text)) > cols_max_width.get(col, 0) else cols_max_width[col]
                    row += 2

        for key in cols_max_width.keys():
            ws.col(key).width = min(65535, cols_max_width[key])

    stream = StringIO.StringIO()
    wb.save(stream)
    return stream.getvalue()


def prepare_excel(env, doc_ids, report_name, data, context, uid):
    """
    !! Important. Functionality from 'report_routes' method was moved here.

    Tt's used by other methods and, for it not be redudant
    it was splitted. Method prepares some extra data and calls XLS
    export function
    :param env: odoo environment
    :param doc_ids: records used in report generation
    :param report_name: name of the report
    :param data: data used in report rendering
    :param context: context used in report rendering
    :param uid: ID of the user which renders the report
    :return: XLS stream
    """
    report_obj = env['report']
    html = report_obj.get_html(doc_ids, report_name, data=data)

    user = env['res.users'].browse(uid)
    lang_code = user.lang or context.get('lang') or 'lt_LT'
    report_lang = env['res.lang'].search([('code', '=', lang_code)], limit=1)
    decimal_sep = report_lang.decimal_point if report_lang else '.'
    thousands_sep = report_lang.thousands_sep if report_lang else ''
    company_id = env.user.sudo().company_id
    header_text = str()
    company_data = [company_id.name, company_id.company_registry, company_id.street]
    for line in company_data:
        if line:
            header_text += ' / {}'.format(line) if header_text else '{}'.format(line)
    header_text += context.get('date_header', '')
    xls_stream = get_xls(html, context, decimal_sep or u'', thousands_sep or u'', header_text)
    return xls_stream


def get_tag_style(element):
    if element.tag == 'h1':
        height = 320
        bold = 'on'
        align = 'horiz center'
    elif element.tag == 'h2':
        height = 300
        bold = 'on'
        align = 'horiz center'
    elif element.tag == 'h3':
        height = 280
        bold = 'off'
        align = 'horiz center'
    elif element.tag == 'span':
        height = 200
        bold = 'off'
        align = 'horiz left'
    elif element.tag == 'strong':
        height = 200
        bold = 'on'
        align = 'horiz left'
    else:
        height = 240
        bold = 'off'
        align = 'horiz center'
    style_def = 'font: bold ' + bold + ', height ' + str(height) + '; align: ' + align
    font_size_style = cached_easyxf(style_def, xlwt.easyxf(style_def))
    return font_size_style


def get_width(num_characters):
    return min(65535, int((1+num_characters) * 256))  # 256


class ReportController(main.ReportController):

    @route(['/report/download'], type='http', auth="user")
    def report_download(self, data, token):
        """This is an override of original method in ReportController class in
        report module
        What is intended here is to properly assign to the extension to XLS
        """
        response = super(ReportController, self).report_download(data, token)
        context = request.context
        if response is None:
            return response

        requestcontent = simplejson.loads(data)
        url = requestcontent[0]

        # decoding the args represented in JSON
        url_split = url.split('?')
        index = len(url_split) > 1 and 1 or 0
        new_data = url_decode(url_split[index]).items()

        new_data = dict(new_data)
        if new_data.get('context'):
            context = simplejson.loads(new_data['context']) or {}

        if not context.get('xls_report'):
            return response

        reportname = url.split('/report/pdf/')[1].split('?')[0]
        docids = None
        if '/' in reportname:
            reportname, docids = reportname.split('/')
        report = request.env['report']._get_report_from_name(reportname)
        filename = report.name
        if docids:
            ids = [int(x) for x in docids.split(",")]
            obj = request.env[report.model].browse(ids)
            if report.print_report_name and not len(obj) > 1:
                filename = tools.safe_eval(report.print_report_name, {'object': obj, 'time': time})
        elif report.print_report_name:
            filename = tools.safe_eval(report.print_report_name, {'time': time})

        headers = dict(response.headers.items())
        headers.update(
            {'Content-Disposition':
                'attachment; filename=%s.xls;' % content_disposition(filename)})
        response.headers.clear()
        for key, value in iteritems(headers):
            response.headers.add(key, value)
        return response

    @route([
        '/report/<converter>/<reportname>',
        '/report/<converter>/<reportname>/<docids>',
    ], type='http', auth='user', website=True)
    def report_routes(self, reportname, docids=None, converter=None, **data):
        report_obj = request.env['report']
        cr, uid, context = request.cr, request.uid, dict(request.context)
        origin_docids = docids
        if docids:
            docids = [int(idx) for idx in docids.split(',')]
        options_data = None
        if data.get('options'):
            options_data = simplejson.loads(data['options'])
        if data.get('context'):
            # Ignore 'lang' here, because the context in data is the one from
            # the webclient *but* if the user explicitely wants to change the
            # lang, this mechanism overwrites it.
            data_context = simplejson.loads(data['context']) or {}

            if data_context.get('lang'):
                del data_context['lang']
            context.update(data_context)

        if not context.get('xls_report'):
            return super(ReportController, self).report_routes(
                reportname, docids=origin_docids, converter=converter, **data)

        xls_stream = prepare_excel(
                        env=request.env,
                        doc_ids=docids,
                        report_name=reportname,
                        data=options_data,
                        context=context,
                        uid=uid)

        report = report_obj._get_report_from_name(reportname)
        filename = report.name
        if docids:
            ids = [int(x) for x in docids.split(",")]
            obj = request.env[report.model].browse(ids)
            if report.print_report_name and not len(obj) > 1:
                filename = tools.safe_eval(report.print_report_name, {'object': obj, 'time': time})
        elif report.print_report_name:
            filename = tools.safe_eval(report.print_report_name, {'time': time})
        # remove non-ascii letters from filename
        filename = filename.encode('ascii', 'replace')
        if filename.endswith('.pdf'):
            filename = filename[:-4]
        xlshttpheaders = [('Content-Type', 'application/vnd.ms-excel'),
                          ('Content-Length', len(xls_stream)),
                          ('Content-Disposition', 'attachment; filename=%s.xls;' % filename)
                          ]
        return request.make_response(xls_stream, headers=xlshttpheaders)


class IrActionsReportXml(models.Model):
    _inherit = 'ir.actions.report.xml'

    @api.model
    def render_report(self, res_ids, name, data):
        report = self._lookup_report(name)
        if isinstance(report, basestring):
            if self._context.get('render_excel', False):
                html = self.env['report'].get_html(res_ids, report, data=data)
                user = self.env.user
                lang_code = user.lang or self._context.get('lang', 'lt_LT') or 'lt_LT'
                report_lang = self.env['res.lang'].search([('code', '=', lang_code)], limit=1)
                decimal_sep = report_lang.decimal_point if report_lang else '.'
                thousands_sep = report_lang.thousands_sep if report_lang else ''
                company_id = self.env.user.sudo().company_id
                header_text = str()
                company_data = [company_id.name, company_id.company_registry, company_id.street]
                for line in company_data:
                    if line:
                        header_text += ' / {}'.format(line) if header_text else '{}'.format(line)
                header_text += self._context.get('date_header', '')
                xls_stream = get_xls(html, self._context, decimal_sep or u'', thousands_sep or u'', header_text)
                return xls_stream, 'excel'
        return super(IrActionsReportXml, self).render_report(res_ids, name, data)


IrActionsReportXml()
