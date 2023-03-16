# -*- coding: utf-8 -*-
import re

from odoo.addons.robo_mail_template_manager.model.account_invoice_variables import ACCOUNT_INVOICE_MAIL_TEMPLATE_VARS

from odoo import models, fields, api, _
from six import iteritems


class MailTemplate(models.Model):
    _inherit = 'mail.template'

    robo_custom = fields.Boolean(default=False)

    variable_text = fields.Html(string='Variable text', compute='_compute_variable_text')

    robo_subject = fields.Char(string='Subject', compute='_compute_robo_subject', inverse='_set_subject')
    robo_body_html = fields.Html(string='Body', compute='_compute_robo_body_html', inverse='_set_body_html')
    model_id = fields.Many2one(inverse='_set_report_name')

    @api.multi
    @api.depends('model_id')
    def _compute_variable_text(self):
        for rec in self:
            locale = self._context.get('lang') or 'lt_LT'

            variable_text = _('<h3 style="text-align: center;">Variables that you can use in this template:</h3>')
            if not (rec.model_id.id == rec.env.ref('account.model_account_invoice').id):
                continue
            for account_invoice_robo_ux_variable in ACCOUNT_INVOICE_MAIL_TEMPLATE_VARS:
                variable_key = account_invoice_robo_ux_variable.get('selectors', {}).get(locale)
                variable_description = _(account_invoice_robo_ux_variable.get('description', ''))
                variable_text += '<b>{}</b> - {}.<br/>'.format(variable_key, variable_description)

            rec.variable_text = variable_text

    @api.multi
    @api.depends('subject')
    def _compute_robo_subject(self):
        for rec in self:
            rec.robo_subject = self._parse_robo_template_vars(rec.subject, rec.model_id.id, replacement_type='user')

    @api.multi
    @api.depends('body_html')
    def _compute_robo_body_html(self):
        for rec in self:
            rec.robo_body_html = self._parse_robo_template_vars(rec.body_html, rec.model_id.id, replacement_type='user')

    @api.multi
    def _set_subject(self):
        for rec in self:
            if not rec.robo_custom and not rec.model_id:
                continue
            parsed_subject = self._parse_robo_template_vars(rec.robo_subject, rec.model_id.id,
                                                            replacement_type='actual')
            rec.with_context(lang='lt_LT').write({'subject': parsed_subject})
            rec.with_context(lang='en_US').write({'subject': parsed_subject})

    @api.multi
    def _set_body_html(self):
        for rec in self:
            if not rec.robo_custom and not rec.model_id:
                continue
            parsed_body = self._parse_robo_template_vars(rec.robo_body_html, rec.model_id.id,
                                                         replacement_type='actual')
            rec.with_context(lang='lt_LT').write({'body_html': parsed_body})
            rec.with_context(lang='en_US').write({'body_html': parsed_body})

    @api.onchange('model_id')
    def _onchange_model_id(self):
        if not self.robo_body_html or self.robo_body_html == '':
            empty_template = self.env.ref('robo_mail_template_manager.robo_blank_template', raise_if_not_found=False)
            if empty_template:
                self.robo_body_html = empty_template.body_html

    @api.multi
    def _set_report_name(self):
        for rec in self:
            if rec.model_id.model == 'account.invoice' and rec.robo_custom:
                rec.report_name = '''${(object.number or object.proforma_number or 'isankstine').replace('/','_')}'''
            rec._set_partner_to_if_not_set()

    @api.multi
    def _set_partner_to_if_not_set(self):
        """
        Sets the partner_to field using placeholders if it is not set for specific models
        """
        model_account_invoice = self.env.ref('account.model_account_invoice')

        for rec in self:
            if not rec.partner_to:
                if rec.model_id == model_account_invoice:
                   rec.partner_to = u'${object.partner_id.id}'

    @api.model
    def _parse_robo_template_vars(self, text, model_id=False, replacement_type='actual'):
        parsed_text = text
        if not parsed_text or not isinstance(parsed_text, (str, unicode)):
            return parsed_text

        locale = self.env.user.lang or 'lt_LT'

        model_var_map = {self.env.ref('account.model_account_invoice').id: ACCOUNT_INVOICE_MAIL_TEMPLATE_VARS,}
        model_vars = model_var_map.get(model_id)

        # Parse the allowed model variables
        parsed_vars = []
        if model_vars:
            if replacement_type == 'actual':
                # Replace from string to code
                parsed_vars = list()
                for model_var in model_vars:
                    parsed_vars += [{
                        'selector': selector,
                        'replacement': model_var.get('replacement')
                    } for selector in model_var.get('selectors').values()]
            else:
                # Replace from code to string based on locale
                parsed_vars = [
                    {
                        'selector': model_var.get('replacement'),
                        'replacement': model_var.get('selectors', {}).get(locale)
                    } for model_var in model_vars
                ]
            for parsed_var in parsed_vars:
                selector, replacement = parsed_var.get('selector'), parsed_var.get('replacement')
                if selector and replacement:
                    parsed_text = parsed_text.replace(selector, str(replacement))

        # Determine the safe variables from the hard coded template variables
        safe_vars = [parsed_var.get('replacement') for parsed_var in parsed_vars]

        # Base variable regex string "${...}"
        re_pattern = re.compile("\$\{[^{}]+\}")

        # Find safe variables from base template
        base_template = self.env.ref('robo_mail_template_manager.robo_blank_template', raise_if_not_found=False)
        if base_template:
            # Attributes where allowed vars can exist
            base_template_var_strings = ''.join(str(var) for var in [base_template.body_html, base_template.subject])
            # Find the base variables from the base template
            safe_vars += [match.group() for match in re_pattern.finditer(base_template_var_strings)]

        safe_vars = list(set(safe_vars))

        for i, safe_var in enumerate(safe_vars, start=10):
            parsed_text = parsed_text.replace(safe_var, '__SAFE_VARIABLE__{}'.format(i))

        # Replace all of the variables that are not safe
        unsafe_matches = re_pattern.finditer(parsed_text)
        while unsafe_matches:
            unsafe_match_groups = [match.group() for match in unsafe_matches]
            unsafe_matches = [
                match_group for match_group in unsafe_match_groups
                if match_group and isinstance(match_group, (str, unicode)) and match_group not in safe_vars
            ]
            if not unsafe_matches:
                break  # No more unsafe matches

            for match_group in unsafe_matches:
                parsed_text = parsed_text.replace(match_group, '')

            unsafe_matches = re_pattern.finditer(parsed_text)

        for i, safe_var in enumerate(safe_vars, start=10):
            parsed_text = parsed_text.replace('__SAFE_VARIABLE__{}'.format(i), safe_var)

        return parsed_text
