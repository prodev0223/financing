# -*- coding: utf-8 -*-
import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _, exceptions


class TurtoSarasasWizard(models.TransientModel):
    _name = "turto.sarasas.wizard"

    def _date_to_default(self):
        return datetime.datetime.utcnow() + relativedelta(day=31)

    def _date_from_default(self):
        return datetime.datetime.utcnow() + relativedelta(day=1)

    date_from = fields.Date(string="Periodas nuo", required=True, default=_date_from_default)
    date_to = fields.Date(string="Periodas iki", required=True, default=_date_to_default)
    advanced_report = fields.Boolean(string="Išsamus sąrašas", default=False)
    by_department = fields.Boolean(string="Filtruoti pagal ilgalaikio turto skyrių", default=False)
    asset_department_ids = fields.Many2many('account.asset.department', string='Ilgalaikio turto skyriai', default=False)
    by_category = fields.Boolean(string="Filtruoti pagal ilgalaikio turto kategoriją")
    asset_category_ids = fields.Many2many('account.asset.category', string='Ilgalaikio turto kategorijos')
    force_lang = fields.Selection([('lt_LT', 'Lietuvių kalba'),
                                   ('en_US', 'Anglų kalba')], string='Priverstinė ataskaitos kalba')
    include_closed_assets = fields.Boolean(string="Įtraukti užvertus įrašus", default=True)
    include_all_open_assets = fields.Boolean(string='Įtraukti visą einamąjį ilgalaikį turtą')

    @api.multi
    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_to < rec.date_from:
                raise exceptions.ValidationError(_('Data nuo negali būti vėliau, nei data iki'))

    @api.multi
    def name_get(self):
        return [(rec.id, _('Turto sąrašas')) for rec in self]

    @api.multi
    def check_advanced_report(self):
        self.ensure_one()
        AccountAsset = self.env['account.asset.asset']
        data = {}
        dates = self.read(['date_from', 'date_to'])
        dates = dates[0] if dates else False
        if not dates or not dates.get('date_from') or not dates.get('date_from'):
            raise exceptions.ValidationError(_('Date from and date to fields need to be provided for the report.'))
        date_from = dates.get('date_from')
        date_to = dates.get('date_to')

        states = ['open', 'close'] if self.include_closed_assets else ['open']
        assets = self.env['account.asset.depreciation.line'].search([
            ('depreciation_date', '<=', date_to),
            ('depreciation_date', '>=', date_from),
            ('move_check', '=', True)
        ]).mapped('asset_id').filtered(
            lambda r: r.active and (r.state in states or (r.state == 'close' and r.sale_line_ids))
        )
        assets |= AccountAsset.search([
            ('active', '=', True),
            '|',
            ('state', 'in', states),
            '&',
            ('state', '=', 'close'),
            ('sale_line_ids', '!=', False),
            '|',
            ('pirkimo_data', '<=', date_to),
            ('date', '<=', date_to),
            '|',
            ('date', '>=', date_from),
            ('date_close', '>=', date_from)
        ])
        # Including all the remaining ones that are open
        if self.include_all_open_assets:
            assets |= AccountAsset.search([
                ('active', '=', True),
                ('state', '=', 'open'),
                ('date', '<=', date_to),
            ])
        if self.by_department:
            if not self.asset_department_ids:
                raise exceptions.UserError(_('Nepasirinktas ilgalaikio turto skyrius, pagal kurį filtruoti'))
            assets = assets.filtered(lambda a: a.asset_department_id.id in self.mapped('asset_department_ids.id'))
        if self.by_category:
            if not self.asset_category_ids:
                raise exceptions.UserError(_('Nepasirinktos ilgalaikio turto kategorijos, pagal kurias filtruoti'))
            assets = assets.filtered(lambda a: a.category_id.id in self.mapped('asset_category_ids.id'))
        data['ids'] = assets.ids
        data['model'] = 'account.asset.asset'
        data['form'] = dates

        if assets:
            return assets.export_excel(data)
        else:
            raise exceptions.UserError(_('Neturite jokio ilgalaikio turto.'))

    @api.multi
    def _print_report(self, data):
        self._check_dates()
        ctx = self._context.copy()
        user = self.env.user
        company = user.company_id
        lang = company.partner_id.lang if company.partner_id.lang else ctx.get('lang')
        ctx.update({'lang': self.force_lang or lang, 'force_lang': self.force_lang})
        self = self.with_context(ctx)
        return self.env['report'].get_action(self, 'ilgalaikis_turtas.robo_report_ilgalaikio_turto_sarasas', data=data)

    @api.multi
    def check_report(self):
        self.ensure_one()
        AccountAsset = self.env['account.asset.asset']
        self._check_dates()
        data = {}
        dates = self.read(['date_from', 'date_to'])
        dates = dates[0] if dates else False
        if not dates or not dates.get('date_from') or not dates.get('date_from'):
            raise exceptions.ValidationError(_('Date from and date to fields need to be provided for the report.'))
        date_from = dates.get('date_from')
        date_to = dates.get('date_to')

        states = ['open', 'close'] if self.include_closed_assets else ['open']
        assets = self.env['account.asset.depreciation.line'].search([
            ('depreciation_date', '<=', date_to),
            ('depreciation_date', '>=', date_from),
            ('move_check', '=', True)
        ]).mapped('asset_id').filtered(
            lambda r: r.active and (r.state in states or (r.state == 'close' and r.sale_line_ids)))
        assets |= AccountAsset.search([
            ('active', '=', True),
            '|',
            ('state', 'in', states),
            '&',
            ('state', '=', 'close'),
            ('sale_line_ids', '!=', False),
            '|',
            ('pirkimo_data', '<=', date_to),
            ('date', '<=', date_to),
            '|',
            ('date', '>=', date_from),
            ('date_close', '>=', date_from)
        ])
        # Including all the remaining ones that are open
        if self.include_all_open_assets:
            assets |= AccountAsset.search([
                ('active', '=', True),
                ('state', '=', 'open'),
                ('date', '<=', date_to),
            ])
        if self.by_department:
            if not self.asset_department_ids:
                raise exceptions.UserError(_('Nepasirinktas ilgalaikio turto skyrius, pagal kurį filtruoti'))
            assets = assets.filtered(lambda a: a.asset_department_id.id in self.mapped('asset_department_ids.id'))
        if self.by_category:
            if not self.asset_category_ids:
                raise exceptions.UserError(_('Nepasirinktos ilgalaikio turto kategorijos, pagal kurias filtruoti'))
            assets = assets.filtered(lambda a: a.category_id.id in self.mapped('asset_category_ids.id'))
        data['ids'] = assets.ids
        data['model'] = 'account.asset.asset'
        data['form'] = dates
        res = self.with_context(date_from=date_from, date_to=date_to)._print_report(data)
        if 'report_type' in res:
            if self._context.get('force_pdf'):
                res['report_type'] = 'qweb-pdf'
            if self._context.get('force_html'):
                res['report_type'] = 'qweb-html'
        return res

    @api.multi
    def xls_export(self):
        if self.date_to or self.date_from:
            date_header = ' / {} - {}'.format(self.date_from or '', self.date_to or '')
            self = self.with_context(date_header=date_header)
        return self.check_report()


TurtoSarasasWizard()
