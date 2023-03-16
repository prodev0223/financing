# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class MailTemplate(models.Model):
    _inherit = 'mail.template'

    body_header = fields.Text(string='Body header', translate=False)
    robo_company_template_wrap = fields.Boolean(string='Wrap template in default company branded template html')
    robo_template_wrap = fields.Boolean(string='Wrap template in default RoboLabs template html')
    body_footer = fields.Text(string='Body footer', translate=False)

    @api.model
    def format_body_based_on_branded_template(self, template, body):
        """
        Formats body based on templates header and footer.
        Returns:
            string: Formatted template text
        """
        if not template:
            return body
        header = template.sudo().body_header
        footer = template.sudo().body_footer

        # Determine language
        try:
            language = self.lang
        except AttributeError as e:
            pass
        supported_languages = ['en_US', 'lt_LT']
        default_language = 'lt_LT'
        if language not in supported_languages:
            language = self._context.get('lang')
        if language not in supported_languages:
            language = default_language

        # FIXME - make mail template body header/footer html templates translatable and remove the following code
        # Adjust context language
        self = self.with_context(lang=language)
        try:
            footer = footer.format(_('Buhalterija šiuolaikiškai'))  # Get text based on language set above
        except:
            pass  # robo_disable_marketing nothing to format
        return header + body + footer

    @api.multi
    def read(self, fields=None, load='_classic_read'):
        result = super(MailTemplate, self).read(fields=fields, load=load)
        try:
            robo_branding_base_template = self.env.ref('robo_core.robo_branded_mail_template', False)
            robo_branding_company_base_template = self.env.ref('robo_core.robo_branded_company_mail_template', False)
            for rec in result:
                body = rec.get('body_html')

                if not body or '''id="templatePreheader"''' in body:  # Template already wrapped in HTML
                    continue

                if rec.get('robo_company_template_wrap') and robo_branding_company_base_template:
                    rec['body_html'] = self.format_body_based_on_branded_template(
                        robo_branding_company_base_template,
                        body
                    )
                elif rec.get('robo_template_wrap') and robo_branding_base_template:
                    rec['body_html'] = self.format_body_based_on_branded_template(
                        robo_branding_base_template,
                        body
                    )
        except:
            pass
        return result

    @api.model
    def render_template(self, template_txt, *args, **kwargs):
        if template_txt and kwargs.get('post_process'):
            template_txt = self._wrap_in_robo_template(template_txt)
        return super(MailTemplate, self).render_template(template_txt, *args, **kwargs)

    @api.model
    def _wrap_in_robo_template(self, html):
        """ Post-processing of html content to wrap template in robo template. """
        res_id = self._context.get('mail_template_res_id')
        if not res_id:
            return html
        if not html or '''id="templatePreheader"''' in html:  # Template already wrapped in HTML
            return html
        template = self.browse(res_id)
        try:
            if template.robo_company_template_wrap:
                robo_branding_company_base_template = self.env.ref('robo_core.robo_branded_company_mail_template', False)
                if robo_branding_company_base_template:
                    html = self.format_body_based_on_branded_template(
                        robo_branding_company_base_template,
                        html
                    )
            elif template.robo_template_wrap:
                robo_branding_base_template = self.env.ref('robo_core.robo_branded_mail_template', False)
                if robo_branding_base_template:
                    html = self.format_body_based_on_branded_template(
                        robo_branding_base_template,
                        html
                    )
        except:
            pass
        return html


MailTemplate()
