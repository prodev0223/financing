from odoo import models, api


class MailComposer(models.TransientModel):
    _inherit = 'mail.compose.message'

    @api.multi
    def onchange_template_id(self, template_id, composition_mode, model, res_id):
        ctx = self._context.copy()
        if model == 'account.invoice':
            invoice_lang = self.env[model].sudo().browse(res_id).partner_lang
            ctx.update(lang=invoice_lang)
        return super(MailComposer, self.with_context(ctx)).onchange_template_id(template_id, composition_mode, model, res_id)


MailComposer()