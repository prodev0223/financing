# env: database Environment
# datetime: datetime object
# relativedelta: relativedelta object
# tools: robo tools
# base64: base64 module
# random: random module
# exceptions: exceptions module

date_month = 2
date_year = 2020

date_from = (datetime.utcnow() + relativedelta(year=date_year, month=date_month, day=1)).strftime(
    tools.DEFAULT_SERVER_DATE_FORMAT)
date_to = (datetime.utcnow() + relativedelta(year=date_year, month=date_month, day=31)).strftime(
    tools.DEFAULT_SERVER_DATE_FORMAT)

contracts = env['hr.contract'].search(['|', ('date_end', '=', False), ('date_end', '>=', date_to)])
employee_ids = contracts.mapped('employee_id.id')
employee_ids = list(set(employee_ids))
employee_ids = env['hr.employee'].browse(employee_ids)
department_ids = employee_ids.mapped('department_id')

for employee in employee_ids:
    vals = {'employee_id': employee.id,
            'department_id': employee.department_id.id,
            'date_from': date_from,
            'date_to': date_to}
    sched_setter = env['new.schedule.day.wizard'].with_context({'auto_confirm': False}).create(vals)
    sched_setter.confirm()

for department in department_ids:
    day_line_ids = env['hr.schedule.day.line'].search(
        [('date', '>=', date_from), ('date', '<=', date_to), ('department_id.id', '=', department.id)])
    day_line_ids.action_validate_1()

day_line_ids = env['hr.schedule.day.line'].search(
    [('date', '>=', date_from), ('date', '<=', date_to), ('employee_id.id', 'in', employee_ids.mapped('id'))])
day_line_ids.action_validate_2()
day_line_ids.action_done()

for employee in employee_ids:
    schedule_day_ids = env['hr.schedule.day'].search(
        [('date', '>=', date_from), ('date', '<=', date_to), ('employee_id.id', 'in', [employee.id])])
    for day in schedule_day_ids:
        ziniarastis_day = env['ziniarastis.day'].search([('date', '=', day.date), ('employee_id', '=', employee.id)])
        sum = 0
        schedule_codes = list()
        for line in day.mapped('schedule_day_lines'):
            schedule_codes.append(line.tabelio_zymejimas_id.code)
        schedule_codes = list(set(schedule_codes))
        ziniarastis_codes = list()
        for line in ziniarastis_day.mapped('ziniarastis_day_lines'):
            ziniarastis_codes.append(line.tabelio_zymejimas_id.code)
        if len(ziniarastis_codes) != 0:
            ziniarastis_codes = list(set(ziniarastis_codes))
            codes_not_in = False
            for code in schedule_codes:
                if code not in ziniarastis_codes:
                    codes_not_in = True
            if len(ziniarastis_codes) != len(schedule_codes) or codes_not_in:
                str = "Ziniarastis codes do not match schedule codes for date %s, employee %s (%s)" % (
                day.date, employee.id, employee.name)
                {}[str]
        else:
            if len(schedule_codes) != 0 and not tools.float_is_zero(
                    sum(day.mapped('schedule_day_lines.worked_time_total')), precision_digits=2):
                str = "Ziniarastis codes do not match schedule codes for date %s, employee %s (%s)" % (
                day.date, employee.id, employee.name)
                {}[str]