# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions, _
from datetime import datetime
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    rivile_kodas = fields.Char(string='Kodas Rivilėje')
    imdeco_history = fields.Boolean(string='Istorinis')
    rivile_saskaitu_rysys = fields.Char(string='Sąskaitų ryšio kodas')


ResPartner()


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    code = fields.Char(string='Kodas', required=True)


HrDepartment()


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    rivile_avansine_saskaita = fields.Char(string='Rivilės avansinė sąskaitą')


HrEmployee()


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    department_id = fields.Many2one('hr.department', string='Skyrius', track_visibility='onchange')

    @api.model
    def cron_assign_departments(self):
        robo_upload_obj = self.env['robo.upload']
        invoice_ids = self.search([('type', 'in', ['in_invoice', 'in_refund']), ('department_id', '=', False)])
        for invoice_id in invoice_ids:
            upload_id = robo_upload_obj.search([('res_model', '=', 'account.invoice'), ('res_id', '=', invoice_id.id)],
                                               limit=1)
            if upload_id and upload_id.employee_id.department_id:
                invoice_id.department_id = upload_id.employee_id.department_id.id


AccountInvoice()


class RivileExportWizard(models.TransientModel):
    _name = 'rivile.export.wizard'

    def default_date_from(self):
        return (datetime.now() - relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def default_date_to(self):
        return (datetime.now() + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    date_from = fields.Date(string='Nuo', default=default_date_from, required=True)
    date_to = fields.Date(string='Iki', default=default_date_to, required=True)

    @api.multi
    def export(self):
        ''' PVZ.
<I06>
     <I06_OP_TIP>1</I06_OP_TIP>
     <I06_DOK_NR>XXX</I06_DOK_NR>
     <I06_OP_DATA>2017.11.21</I06_OP_DATA>
     <I06_KODAS_KS>T232</I06_KODAS_KS>
     <I07>
          <I07_TIPAS>2</I07_TIPAS>
          <I07_KODAS>PXXX</I07_KODAS>
          <I07_PAV>Testavimas</I07_PAV>
          <I07_KODAS_US_A>VNT</I07_KODAS_US_A>
          <I07_MOKESTIS>1</I07_MOKESTIS>
          <I07_MOKESTIS_P>21</I07_MOKESTIS_P>
          <T_KIEKIS>2</T_KIEKIS>
          <I07_KAINA_BE>100.0000</I07_KAINA_BE>
          <I07_PVM>42.00</I07_PVM>
          <I07_SUMA>200.00</I07_SUMA>
     </I07>
</I06>
<N08>
     <N08_KODAS_KS>121411842</N08_KODAS_KS>
     <N08_RUSIS>2</N08_RUSIS>
     <N08_PVM_KODAS>LT214118411</N08_PVM_KODAS>
     <N08_IM_KODAS>121411842</N08_IM_KODAS>
     <N08_PAV>UAB "RIVILĖ"</N08_PAV>
     <N08_ADR>Geležinio Vilko g. 5-48</N08_ADR>
     <N08_KODAS_VS>VILNIUS</N08_KODAS_VS>
     <N08_PASTAS></N08_PASTAS>
     <N08_E_MAIL>rivile@rivile.lt</N08_E_MAIL>
     <N08_TEL>251379</N08_TEL>
     <N08_MOB_TEL></N08_MOB_TEL>
     <N08_KODAS_DS>PT001</N08_KODAS_DS>
     <N08_KODAS_XS_T>PVM</N08_KODAS_XS_T>
     <N08_KODAS_TS_T></N08_KODAS_TS_T>
</N08>
'''

        def add_invoice_header(op_type, no, date, partner_code, avansinis_asmuo='AVN', avansine_saskaita=False):
            op_type = op_type[:8]
            no = no[:20]
            date = date[:10]
            partner_code = partner_code[:12]
            vals = '''<I06>
     <I06_OP_TIP>%s</I06_OP_TIP>
     <I06_DOK_NR>%s</I06_DOK_NR>
     <I06_OP_DATA>%s</I06_OP_DATA>
     <I06_KODAS_KS>%s</I06_KODAS_KS>''' % (op_type, no, date, partner_code)
            if avansine_saskaita:
                vals += '''
     <I06_MOK_DOK>%s</I06_MOK_DOK>
     <I06_MOK_SUMA>1</I06_MOK_SUMA>
     <I06_KODAS_SS>%s</I06_KODAS_SS>''' % (avansinis_asmuo[:12], avansine_saskaita[:12])
            return vals

        def add_invoice_line(product_type, product_code, name, qty, price_wo_vat, vat, amount_wo_vat, vat_code,
                             padalinio_kodas='01'):
            percentage = tools.float_round(vat / amount_wo_vat * 100.0, precision_digits=0)
            mokestis = '1' if vat else '0'
            mokestis_p = int(percentage)
            product_code = product_code[:12]
            name = name[:40]
            vals = '''
    <I07>
        <I07_TIPAS>%s</I07_TIPAS>
        <I07_KODAS_IS>%s</I07_KODAS_IS>
        <I07_KODAS>%s</I07_KODAS>
        <I07_PAV>%s</I07_PAV>
        <I07_MOKESTIS>%s</I07_MOKESTIS>
        <I07_MOKESTIS_P>%s</I07_MOKESTIS_P>
        <I07_KIEKIS>%s</I07_KIEKIS>
        <I07_KAINA_BE>%s</I07_KAINA_BE>
        <I07_PVM>%s</I07_PVM>
        <I07_SUMA>%s</I07_SUMA>
        <I07_KODAS_KL>%s</I07_KODAS_KL>''' % (
                product_type, padalinio_kodas, product_code, name, mokestis, mokestis_p, qty, price_wo_vat, vat,
                amount_wo_vat, vat_code)
            vals += '''
    </I07>'''
            return vals

        self.ensure_one()
        invoice_obj = self.env['account.invoice']
        invoice_ids = invoice_obj.search([('registration_date', '>=', self.date_from),
                                          ('registration_date', '<=', self.date_to),
                                          ('type', 'in', ['in_invoice', 'in_refund']),
                                          ('state', 'in', ['open', 'paid'])])
        if invoice_ids.filtered(lambda r: not r.accountant_validated):
            raise exceptions.Warning(_('Ne visos sąskaitos patvirtintos buhalterio!'))
        if invoice_ids.mapped('invoice_line_ids').filtered(lambda r: not r.product_id.default_code):
            raise exceptions.Warning(_('Ne visi produktai turi kodą!'))
        if invoice_ids.filtered(lambda r: not r.partner_id.rivile_kodas and not r.partner_id.kodas):
            raise exceptions.Warning(_('Šie partneriai neturi Rivilės kodo arba įmonės/asmens kodo:\n%s') % (
                ','.join(map(str, invoice_ids.filtered(
                    lambda r: not r.partner_id.rivile_kodas and not r.partner_id.kodas).mapped('partner_id.name')))))
        invoices_eip = ''
        for invoice_id in invoice_ids:
            if invoice_id.invoice_line_ids.filtered(lambda r: r.product_id.type == 'product'):
                _logger.info('SKIPPED PRODUCT INVOICE %s' % invoice_id.reference or invoice_id.number)
                continue
            if invoice_id.state == 'paid' and invoice_id.payment_mode == 'own_account' and invoice_id.ap_employee_id:
                vardas = invoice_id.ap_employee_id.name.split(' ')
                avansinis_asmuo = vardas[0][0].upper() + '.'
                if len(vardas) > 1:
                    avansinis_asmuo += vardas[1][0].upper() + '.'
                avansine_saskaita = invoice_id.ap_employee_id.rivile_avansine_saskaita
                if not avansine_saskaita:
                    raise exceptions.UserError(
                        _('Sąskaitoje %s nenurodytas atskaitingo asmens Rivilės sąskaitų ryšys.') % (
                                invoice_id.reference or invoice_id.number))
            else:
                avansinis_asmuo = ''
                avansine_saskaita = False
            if invoice_id.type == 'in_refund':
                op_type = '2'
            else:
                op_type = '1'
            invoices_eip += add_invoice_header(op_type,
                                               invoice_id.reference or invoice_id.number,
                                               datetime.strptime(invoice_id.date_invoice,
                                                                 tools.DEFAULT_SERVER_DATE_FORMAT).strftime('%Y.%m.%d'),
                                               invoice_id.partner_id.rivile_kodas or invoice_id.partner_id.kodas or '',
                                               avansinis_asmuo=avansinis_asmuo,
                                               avansine_saskaita=avansine_saskaita)
            for line in invoice_id.invoice_line_ids:
                if line.product_id.type != 'service':
                    raise exceptions.UserError(
                        _('Neteisingas produktas %s sąskaitoje.') % (invoice_id.reference or invoice_id.number))
                tax_ids = line.invoice_line_tax_ids.filtered(lambda r: r.code.startswith('PVM'))
                if not tax_ids or tax_ids and len(tax_ids) > 1:
                    raise exceptions.UserError(_('Neteisingai priskirti mokesčiai %s sąskaitoje') % (
                            invoice_id.reference or invoice_id.number))
                tax_code = tax_ids[0].code
                invoices_eip += add_invoice_line('3',
                                                 line.product_id.default_code,
                                                 line.name,
                                                 line.quantity,
                                                 line.price_unit,
                                                 line.total_with_tax_amount - line.price_subtotal,
                                                 line.price_subtotal,
                                                 tax_code,
                                                 padalinio_kodas=invoice_id.department_id.code or '01')

            invoices_eip += '''
</I06>
'''

        # Process new suppliers
        partners_eip = ''
        partners_obj = self.env['res.partner']
        partner_ids = partners_obj.search([('create_date', '>=', self.date_from + ' 00:00:00'),
                                           ('supplier', '=', True),
                                           ('imdeco_history', '=', False)])
        for partner_id in partner_ids:
            if not partner_id.rivile_kodas and not partner_id.kodas:
                raise exceptions.Warning(_('Nenurodytas įmonės/asmens kodas (%s).') % partner_id.name)
            if not partner_id.rivile_kodas and partner_id.kodas:
                partner_id.rivile_kodas = partner_id.kodas
            partners_eip += '''<N08>
     <N08_KODAS_KS>%s</N08_KODAS_KS>
     <N08_RUSIS>2</N08_RUSIS>
     <N08_PVM_KODAS>%s</N08_PVM_KODAS>
     <N08_IM_KODAS>%s</N08_IM_KODAS>
     <N08_PAV>%s</N08_PAV>
     <N08_ADR>%s</N08_ADR>
     <N08_PASTAS>%s</N08_PASTAS>
     <N08_E_MAIL>%s</N08_E_MAIL>
     <N08_TEL>%s</N08_TEL>
     <N08_MOB_TEL>%s</N08_MOB_TEL>
     <N08_KODAS_DS>%s</N08_KODAS_DS>
     <N08_KODAS_XS_T>PVM</N08_KODAS_XS_T>
     <N08_KODAS_TS_T></N08_KODAS_TS_T>
</N08>
''' % ((partner_id.rivile_kodas or '')[:12], (partner_id.vat or '')[:25], (partner_id.kodas or '')[:13],
       (partner_id.name or '')[:70], (partner_id.contact_address or '').replace('\n', ' ').replace('  ', ' ')[:40],
       (partner_id.zip or '')[:9], (partner_id.email or '')[:40], (partner_id.phone or '')[:40],
       (partner_id.mobile or '')[:40], (partner_id.rivile_saskaitu_rysys or 'PT002')[:12])

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'rivile.export.wizard.download',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'view_id': self.env.ref('imdeco.rivile_export_wizard_download_form').id,
            'target': 'new',
            'context': {
                'invoices_eip': invoices_eip.encode('base64'),
                'partners_eip': partners_eip.encode('base64'),
            },
        }


class RivileExportWizardDownload(models.TransientModel):
    _name = 'rivile.export.wizard.download'

    def default_data_invoices(self):
        return self._context.get('invoices_eip', False)

    def default_data_partners(self):
        return self._context.get('partners_eip', False)

    data_invoices = fields.Binary(string='Pirkimai EIP', default=default_data_invoices, readonly=True)
    filename_invoices = fields.Char(default='pirkimai.EIP')
    data_partners = fields.Binary(string='Tiekėjai EIP', default=default_data_partners, readonly=True)
    filename_partners = fields.Char(default='tiekejai.EIP')


RivileExportWizardDownload()


class eDocument(models.Model):
    _inherit = 'e.document'

    @api.one
    def _set_document_link(self):
        if self.record_model == 'e.document' and self.record_id:
            isakymas = self.sudo().browse(self.record_id)
            msg = {
                'body': 'Naujas laukiantis pasirašymo įsakymas',
                'subject': 'Naujas įsakymas',
                'priority': 'high',
                'front_message': True,
                'rec_model': 'e.document',
                'rec_id': self.record_id,
                'view_id': isakymas.view_id.id or False,
            }
            partner_ids = isakymas.mapped('employee_id1.user_id.partner_id.id')
            if partner_ids:
                msg['partner_ids'] = partner_ids
            else:
                msg['partner_ids'] = self.env['hr.employee'].search([('robo_access', '=', True),
                                                                     ('robo_group', '=', 'manager')]).mapped(
                    'user_id.partner_id.id')
            isakymas.robo_message_post(**msg)


eDocument()
