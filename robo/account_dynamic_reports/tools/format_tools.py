from odoo import tools


def format_number_with_currency(number, currency, language):
    is_number = isinstance(number, (int, float))

    if not is_number:
        return unicode(number)
    elif not currency:
        return tools.float_round(number, precision_rounding=0.01)

    number = tools.float_round(number, precision_rounding=currency.rounding or 0.01)

    if language:
        fmt = "%.{0}f".format(currency.decimal_places)
        formatted_amount = language.format(fmt, number, grouping=True, monetary=True).replace(
            r' ', u'\N{NO-BREAK SPACE}').replace(r'-', u'-\N{ZERO WIDTH NO-BREAK SPACE}')
    else:
        formatted_amount = unicode(number)

    pre = post = u''
    if currency.position == 'before':
        pre = u'{symbol}\N{NO-BREAK SPACE}'.format(symbol=currency.symbol or '')
    else:
        post = u'\N{NO-BREAK SPACE}{symbol}'.format(symbol=currency.symbol or '')

    return u'{pre}{0}{post}'.format(formatted_amount, pre=pre, post=post)
