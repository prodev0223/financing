# env: database Environment
# datetime: datetime object
# relativedelta: relativedelta object
# tools: robo tools
# base64: base64 module
# random: random module
# exceptions: exceptions module

def check_15(date):
    emails = env.user.company_id.default_msg_receivers.mapped('email')
    codes = ['1311', '1411']
    date_start = date - relativedelta(day=1)
    date = date.strftime(tools.DEFAULT_SERVER_DATE)
    date_start = date_start.strftime(tools.DEFAULT_SERVER_DATE)
    send = False
    bank_line_gpm = env['account.bank.statement.line'].search([
        ('partner_id.kodas', '=', '188659752'),
        ('amount', '<', 0.00),
        ('date', '<=', date),
        ('date', '>=', date_start),
        ('journal_entry_ids', '!=', False),
        '|',
        ('name', '=', '1311'),
        ('name', '=', '1411')])
    if not bank_line_gpm:
        send = True
    else:
        for code in codes:
            if code not in bank_line_gpm.mapped('name'):
                send = True

    bank_line_252 = env['account.bank.statement.line'].search([
        ('partner_id.kodas', '=', '191630223'),
        ('amount', '<', 0.00),
        ('date', '<=', date),
        ('date', '>=', date_start),
        ('journal_entry_ids', '!=', False),
        ('name', '=', '252')])
    if not bank_line_252:
        send = True

    front_bank_252 = env['front.bank.statement.line'].search([
        ('partner_id.kodas', '=', '191630223'),
        ('amount', '<', 0.00),
        ('date', '<=', date),
        ('date', '>=', date_start),
        ('name', '=', '252')])
    if not front_bank_252:
        send = False

    front_bank_gpm = env['front.bank.statement.line'].search([
        ('partner_id.kodas', '=', '188659752'),
        ('amount', '<', 0.00),
        ('date', '<=', date),
        ('date', '>=', date_start),
        '|',
        ('name', '=', '1311'),
        ('name', '=', '1411')])
    if not front_bank_gpm:
        send = False
    else:
        for code in codes:
            if code not in front_bank_gpm.mapped('name'):
                send = False
    if send:
        body = _('''<p>Sveiki,</p>
        <p>norime priminti, kad iki šiandien turi būti sumokėti mokesčiai. Paruoštus mokėjimo ruošinius galite rasti prisijungus prie sistemos. Jei mokesčius jau sumokėjote - ignoruokite šį laišką.</p>
        <p>Dėkui,</p>
        <p>RoboLabs komanda</p>''')
        subject = _('Priminimas dėl mokesčių sumokėjimo')
        obj.send_email(subject=subject, body=body, emails_to=emails)


def check_25(date):
    emails = env.user.company_id.default_msg_receivers.mapped('email')
    date_start = date - relativedelta(day=1)
    date = date.strftime(tools.DEFAULT_SERVER_DATE)
    date_start = date_start.strftime(tools.DEFAULT_SERVER_DATE)
    send = False
    bank_line_vmi = env['account.bank.statement.line'].search([
        ('partner_id.kodas', '=', '188659752'),
        ('amount', '<', 0.00),
        ('date', '<=', date),
        ('date', '>=', date_start),
        ('journal_entry_ids', '!=', False),
        ('name', '=', '1001')])
    vat_payer = env.user.sudo().company_id.with_context(date=date).vat_payer
    if not bank_line_vmi and vat_payer:
        send = True
    front_statement_vmi = env['front.bank.statement.line'].search([
        ('partner_id.kodas', '=', '188659752'),
        ('amount', '<', 0.00),
        ('date', '<=', date),
        ('date', '>=', date_start),
        ('name', '=', '1001')])
    if not front_statement_vmi:
        send = False
    if send:
        body = _('''<p>Sveiki,</p>
        <p>norime priminti, kad iki šiandien turi būti sumokėti mokesčiai. Paruoštus mokėjimo ruošinius galite rasti prisijungus prie sistemos. Jei mokesčius jau sumokėjote - ignoruokite šį laišką.</p>
        <p>Dėkui,</p>
        <p>RoboLabs komanda</p>''')
        subject = _('Priminimas dėl mokesčių sumokėjimo')
        obj.send_email(subject=subject, body=body, emails_to=emails)


now = datetime.utcnow().date()
vmi_weekday = (datetime.utcnow() - relativedelta(day=25)).weekday()
sodra_weekday = (datetime.utcnow() - relativedelta(day=15)).weekday()

if sodra_weekday in [5, 6]:
    pre = sodra_weekday - 4
    sodra_alert_day = (now - relativedelta(day=15)) - relativedelta(days=pre)
else:
    sodra_alert_day = now - relativedelta(day=15)

if vmi_weekday in [5, 6]:
    pre = vmi_weekday - 4
    vmi_alert_day = (now - relativedelta(day=25)) - relativedelta(days=pre)
else:
    vmi_alert_day = now - relativedelta(day=25)

if now == sodra_alert_day:
    check_15(now)
elif now == vmi_alert_day:
    check_25(now)
