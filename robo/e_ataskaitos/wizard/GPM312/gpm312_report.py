# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions
from odoo.tools.translate import _
from six import iteritems


def round_to_int(num_float):
    return int(round(tools.float_round(num_float, precision_digits=2)))


def convert_to_str(num_float):
    return ('%.2f' % num_float).replace('.', ',')


def convert_to_int_str(num_float):
    num_int = round_to_int(num_float)
    return '%d' % num_int


partner_code_type_map = {'mmak': '1',
                         'PVMmk': '2',
                         'atpdsin': '3'}


class GPM312Report(models.Model):
    _name = 'gpm312.report'
    _order = 'partner_id'

    date = fields.Date(string='Data')
    resident = fields.Selection([('true', 'Rezidentas'), ('false', 'Nerezidentas')], string='Rezidentas')
    klase = fields.Char(string='Klasė')
    kodas = fields.Char(string='Kodas')
    partner_id = fields.Many2one('res.partner', string='Susietas partneris')
    natura = fields.Selection([('true', 'Natūra'), ('false', 'Kita')], string='Išmokos natūra')
    gpm_percentage = fields.Float(string='GPM procentas')
    amount_gpm = fields.Float(string='GPM')
    amount_bruto = fields.Float(string='Bruto')
    country_id = fields.Many2one('res.country', string='Valstybė')
    document_type = fields.Selection([('payslip', 'Pagrindinis atlyginimas'),
                                      ('advance', 'Avansas'),
                                      ('holidays', 'Atostoginiai'),
                                      ('allowance', 'Dienpinigiai'),
                                      ('natura', 'Natūra'),
                                      ('imported', 'Importuota'),
                                      ('other', 'Kita'),
                                      ('own_expense', 'Savom lėšom')], string='Dokumento tipas')

    def quick_create(self, vals):
        if not vals.get('partner_id', False):
            raise exceptions.UserError(_('Nenurodytas partneris %s') % vals.get('origin', ''))
        updates = [
            ('id', "nextval('%s')" % self._sequence),
        ]

        if not vals.get('klase') or not vals.get('kodas'):
            return
        for k, v in iteritems(vals):
            field = self._fields[k]
            if field.store and field.column_type:
                updates.append((k, field.column_format, field.convert_to_column(v, self)))

        query = """INSERT INTO "%s" (%s) VALUES(%s) RETURNING id""" % (
            self._table,
            ', '.join('"%s"' % u[0] for u in updates),
            ', '.join(u[1] for u in updates),
        )
        self._cr.execute(query, tuple(u[2] for u in updates if len(u) > 2))

    @api.model
    def refresh_report(self, data):
        if not data:
            return
        self._cr.execute('''DELETE FROM gpm312_report''')
        for key, values in iteritems(data):
            country_code = values['foreign_country_code']
            country = False
            if country_code:
                country = self.env['res.country'].search([('code', '=', country_code)], limit=1).id
            vals = {
                'date': values['date'],
                'resident': 'true' if values['resident'] else 'false',
                'klase': values['class'],
                'kodas': values['type'],
                'partner_id': key[0],
                'natura': 'true' if values['natura'] else 'false',
                'gpm_percentage': values['gpm_percentage'],
                'amount_gpm': values['gpm_amount'],
                'amount_bruto': values['full_amount'],
                'country_id': country,
                'document_type': 'other',  # values['document_type'],
            }
            self.quick_create(vals)


GPM312Report()
