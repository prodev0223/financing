from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import calendar

from odoo import tools


def get_date_range_selection_from_selection(date_range_selection='today', fiscalyear_last_day=31,
                                            fiscalyear_last_month=12):
    date = datetime.today()
    date_format = tools.DEFAULT_SERVER_DATE_FORMAT
    date_from = date_to = None
    if date_range_selection == 'today':
        date_from = date.strftime(date_format)
        date_to = date.strftime(date_format)
    if date_range_selection == 'this_week':
        day_today = date - timedelta(days=date.weekday())
        date_from = day_today.strftime(date_format)
        date_to = (day_today + timedelta(days=6)).strftime(date_format)
    if date_range_selection == 'this_month':
        date_from = datetime(date.year, date.month, 1).strftime(date_format)
        date_to = datetime(date.year, date.month, calendar.mdays[date.month]).strftime(date_format)
    if date_range_selection == 'this_quarter':
        if int((date.month - 1) / 3) == 0:  # First quarter
            date_from = datetime(date.year, 1, 1).strftime(date_format)
            date_to = datetime(date.year, 3, calendar.mdays[3]).strftime(date_format)
        if int((date.month - 1) / 3) == 1:  # Second quarter
            date_from = datetime(date.year, 4, 1).strftime(date_format)
            date_to = datetime(date.year, 6, calendar.mdays[6]).strftime(date_format)
        if int((date.month - 1) / 3) == 2:  # Third quarter
            date_from = datetime(date.year, 7, 1).strftime(date_format)
            date_to = datetime(date.year, 9, calendar.mdays[9]).strftime(date_format)
        if int((date.month - 1) / 3) == 3:  # Fourth quarter
            date_from = datetime(date.year, 10, 1).strftime(date_format)
            date_to = datetime(date.year, 12, calendar.mdays[12]).strftime(date_format)
    if date_range_selection == 'this_fiscal_year':
        fiscalyear_last_day = fiscalyear_last_day or 31
        fiscalyear_last_month = fiscalyear_last_month or 12
        date_to_dt = datetime(date.year, fiscalyear_last_month, fiscalyear_last_day)
        date_from_dt = date_to_dt + relativedelta(days=1)
        if date > date_to_dt:
            date_to_dt = datetime(date.year + 1, fiscalyear_last_month, fiscalyear_last_day)
        else:
            date_from_dt += relativedelta(years=-1)
        date_from = date_from_dt.strftime(date_format)
        date_to = date_to_dt.strftime(date_format)
    date = (datetime.now() - relativedelta(days=1))
    if date_range_selection == 'yesterday':
        date_from = date.strftime(date_format)
        date_to = date.strftime(date_format)
    date = (datetime.now() - relativedelta(days=7))
    if date_range_selection == 'last_week':
        day_today = date - timedelta(days=date.weekday())
        date_from = (day_today - timedelta(days=date.weekday())).strftime(date_format)
        date_to = (day_today + timedelta(days=6)).strftime(date_format)
    date = (datetime.now() - relativedelta(months=1))
    if date_range_selection == 'last_month':
        date_from = datetime(date.year, date.month, 1).strftime(date_format)
        date_to = datetime(date.year, date.month, calendar.mdays[date.month]).strftime(date_format)
    date = (datetime.now() - relativedelta(months=3))
    if date_range_selection == 'last_quarter':
        if int((date.month - 1) / 3) == 0:  # First quarter
            date_from = datetime(date.year, 1, 1).strftime(date_format)
            date_to = datetime(date.year, 3, calendar.mdays[3]).strftime(date_format)
        if int((date.month - 1) / 3) == 1:  # Second quarter
            date_from = datetime(date.year, 4, 1).strftime(date_format)
            date_to = datetime(date.year, 6, calendar.mdays[6]).strftime(date_format)
        if int((date.month - 1) / 3) == 2:  # Third quarter
            date_from = datetime(date.year, 7, 1).strftime(date_format)
            date_to = datetime(date.year, 9, calendar.mdays[9]).strftime(date_format)
        if int((date.month - 1) / 3) == 3:  # Fourth quarter
            date_from = datetime(date.year, 10, 1).strftime(date_format)
            date_to = datetime(date.year, 12, calendar.mdays[12]).strftime(date_format)
    date = (datetime.now() - relativedelta(years=1))
    if date_range_selection == 'last_financial_year':
        fiscalyear_last_day = fiscalyear_last_day or 31
        fiscalyear_last_month = fiscalyear_last_month or 12
        date_to_dt = datetime(date.year, fiscalyear_last_month, fiscalyear_last_day)
        date_from_dt = date_to_dt + relativedelta(days=1)
        if date > date_to_dt:
            date_to_dt = datetime(date.year + 1, fiscalyear_last_month, fiscalyear_last_day)
        else:
            date_from_dt += relativedelta(years=-1)
        date_from = date_from_dt.strftime(date_format)
        date_to = date_to_dt.strftime(date_format)
    return date_from, date_to
