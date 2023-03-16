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

invoices = env['account.invoice'].search([('type', 'in', ('in_invoice', 'in_refund')),
                                          ('state', 'in', ('open', 'paid')),
                                          ('nbr_of_attachments', '!=', 0)])


saved_payment_lines = dict()
for inv in invoices:
    saved_payment_lines[inv.id] = inv.payment_move_line_ids
for inv in invoices:
    for line in inv.mapped('move_id.line_ids'):
        if line.account_id == inv.account_id:
            line.remove_move_reconcile()

    inv.action_invoice_cancel()
    inv.action_invoice_draft()
    inv.action_invoice_open()

for inv_id, lines in saved_payment_lines.iteritems():
    inv = env['account.invoice'].browse(inv_id)
    for line in lines:
        try:
            inv.assign_outstanding_credit(line.id)
        except:
            pass