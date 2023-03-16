# -*- coding: utf-8 -*-
from odoo import _

ACCOUNT_INVOICE_MAIL_TEMPLATE_VARS = [
    {
        'selectors': {
            'lt_LT': '*IMONES_PAVADINIMAS*',
            'en_US': '*COMPANY_NAME*',
        },
        'description': _('Company name'),
        'replacement': '${object.company_id.name | safe}',
    },
    {
        'selectors': {
            'lt_LT': '*NUMERIS*',
            'en_US': '*NUMBER*',
        },
        'description': _('Invoice number'),
        'replacement':
            '${object.proforma_number if object.proforma_number and object.state in ["proforma", "proforma2"] else "" | safe}' +
            '${object.number if object.number and object.state not in ["proforma", "proforma2"] else "" | safe}',
    },
    {
        'selectors': {
            'lt_LT': '*VALIUTA*',
            'en_US': '*CURRENCY*',
        },
        'description': _('Currency code'),
        'replacement': '${object.currency_id.name | safe}',
    },
    {
        'selectors': {
            'lt_LT': '*SUMA_SU_PVM*',
            'en_US': '*TOTAL_WITH_VAT*',
        },
        'description': _('Total including VAT'),
        'replacement': '${object.amount_total | safe}',
    },
    {
        'selectors': {
            'lt_LT': '*SUMA*',
            'en_US': '*TOTAL*',
        },
        'description': _('Total excluding VAT'),
        'replacement': '${object.suma_eur_bepvm | safe}',
    },
    {
        'selectors': {
            'lt_LT': '*PVM*',
            'en_US': '*VAT*',
        },
        'description': _('VAT amount'),
        'replacement': '${object.amount_tax | safe}',
    },
    {
        'selectors': {
            'lt_LT': '*DATA*',
            'en_US': '*DATE*',
        },
        'description': _('Date the invoice has to be paid by'),
        'replacement': '${format_date(object.date_due) | safe}',
    },
    {
        'selectors': {
            'lt_LT': '*SASKAITOS_DATA*',
            'en_US': '*INVOICE_DATE*',
        },
        'description': _('Invoice date'),
        'replacement': '${format_date(object.date_invoice) | safe}',
    },
    {
        'selectors': {
            'lt_LT': '*IMONES_REKVIZITAI*',
            'en_US': '*COMPANY_INFO*',
        },
        'description': _('Company info (if set)'),
        'replacement': '''
${user.company_id.name}
%if user.company_id.email:
<br/>${user.company_id.email}
%endif
%if user.company_id.phone:
<br/>${user.company_id.phone}
%endif
''',
        'allowed_in_subject': False
    },
    {
        'selectors': {
            'lt_LT': '*DARBUOTOJO_REKVIZITAI*',
            'en_US': '*EMPLOYEE_INFO*',
        },
        'description': _('Employee info (if set)'),
        'replacement': '''
%if user.employee_ids:
<span>${user.employee_ids[0].name}</span>
%if user.employee_ids[0].work_email:
<br/><span>${user.employee_ids[0].work_email}</span>
%endif
%if user.employee_ids[0].mobile_phone:
<br/><span>${user.employee_ids[0].mobile_phone}</span>
%endif
%if user.employee_ids[0].work_phone:
<br/><span>${user.employee_ids[0].work_phone}</span>
%endif
%else:
%if user.name:
<span>${user.name}</span>
%endif
%if user.email:
<br/><span>${user.email}</span>
%endif
%if user.phone:
<br/><span>${user.phone}</span>
%endif
%endif
''',
        'allowed_in_subject': False
    },
    {
        'selectors': {
            'lt_LT': '*DARBUOTOJO_PARASAS*',
            'en_US': '*EMPLOYEE_FOOTER*',
        },
        'description': _('Employee mail footer set in "My profile"'),
        'replacement': '''${user.custom_email_footer|safe}''',
        'allowed_in_subject': False
    },
    {
        'selectors': {
            'lt_LT': '*KLIENTAS*',
            'en_US': '*CLIENT*',
        },
        'description': _('Name of the client'),
        'replacement': '''${object.partner_id.name|safe}''',
        'allowed_in_subject': True
    },
]
