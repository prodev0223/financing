# env: database Environment
# datetime: datetime object
# relativedelta: relativedelta object
# tools: robo tools
# base64: base64 module
# random: random module
# exceptions: exceptions module
# logging: logging module
# string: string module
# _: translation module
# obj: current script


if env.cr.dbname != 'demo':

    invoice_ids = env['account.invoice'].search([('type', 'in', ['in_invoice', 'out_invoice']),
                                                 ('state', '=', 'open')], order='date_invoice asc')
    for invoice in invoice_ids:
        company_currency = invoice.company_id.currency_id
        invoice_currency = invoice.currency_id
        if invoice_currency and invoice_currency.id == company_currency.id:
            domain = [('account_id', '=', invoice.account_id.id),
                      ('partner_id', '=', env['res.partner']._find_accounting_partner(invoice.partner_id).id),
                      ('reconciled', '=', False), ('amount_residual', '!=', 0.0)]
            if invoice.type in ('out_invoice', 'in_refund'):
                domain.extend([('credit', '>', 0), ('debit', '=', 0)])
            else:
                domain.extend([('credit', '=', 0), ('debit', '>', 0)])
            line_ids = env['account.move.line'].search(domain, order='date asc')

            line_ids_corresponding = env['account.move.line']
            for line in invoice.move_id.line_ids:
                if line.account_id.id == invoice.account_id.id:
                    line_ids_corresponding += line

            line_ids |= line_ids_corresponding
            if len(line_ids) > 1:
                try:
                    line_ids.reconcile()
                except:
                    pass
