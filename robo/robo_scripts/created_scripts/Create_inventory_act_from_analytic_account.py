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


# CREATE AN INVENTORY ACT FOR ALL SUPPLIER INVOICE LINES WITH A GIVEN ANALYTIC ACCOUNT CODE BETWEEN date_from AND date_to
date_from = '2019-01-01'
date_to = '2019-03-01'
analytic_code = '2019/1'

# ACT WILL USE THIS LOCATION
location = env['stock.location'].search([('usage', '=', 'internal')], limit=1)

analytic_account = env['account.analytic.account'].search([('code', '=', analytic_code)], limit=1)
invoice_lines = env['account.invoice.line'].search([
    ('invoice_id.type', 'in', ['in_invoice', 'in_refund']),
    ('account_analytic_id', '=', analytic_account.id),
    ('invoice_id.date_invoice', '<=', date_to),
    ('invoice_id.date_invoice', '>=', date_from),
    ('invoice_id.state', 'in', ['open', 'paid'])
])

act = env['stock.inventory'].create({'location_id': location.id,
                                     'filter': 'partial',
                                     'name': 'Automatic Inventory from Analytic account',
                                     'account_analytic_id': analytic_account.id})
act.prepare_inventory()

products = invoice_lines.mapped('product_id')
for product in products:
    product_invoice_lines = env['account.invoice.line'].search([
        ('id', 'in', invoice_lines.ids),
        ('product_id', '=', product.id)
    ])
    env['stock.inventory.line'].create({
        'location_id': location.id,
        'inventory_id': act.id,
        'product_id': product.id,
        'consumed_qty': -sum(product_invoice_lines.mapped('quantity'))
    })
