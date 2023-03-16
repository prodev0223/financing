# env: database Environment
# datetime: datetime object
# relativedelta: relativedelta object
# tools: robo tools
# base64: base64 module
# random: random module

# Sets different time for different days
date_month = 9
date_year = 2018
days_to_reschedule = 500

date_from = (datetime.utcnow() + relativedelta(month=date_month, year=date_year, day=1)).strftime(
    tools.DEFAULT_SERVER_DATE_FORMAT)
date_to = (datetime.utcnow() + relativedelta(month=date_month, year=date_year, day=31)).strftime(
    tools.DEFAULT_SERVER_DATE_FORMAT)

schedule_day_ids = env['hr.schedule.day'].search([('date', '>=', date_from), ('date', '<=', date_to)])
schedule_day_ids_ids = schedule_day_ids.mapped('id')

if len(schedule_day_ids) == 0:
    {}["No days for period exist, please create a schedule first"]

for i in range(0, days_to_reschedule + 1):
    rand_day_id = random.randint(0, (len(schedule_day_ids_ids) - 1))
    for sched_day in schedule_day_ids:
        if sched_day.id == schedule_day_ids_ids[rand_day_id]:
            day = sched_day

    hours_from = random.randint(6, 14)
    minutes_from = random.randint(1, 59)
    time_from = float(hours_from + (minutes_from / 60.0))

    hours_to = random.randint(15, 21)
    minutes_to = random.randint(1, 59)
    time_to = float(hours_to + (minutes_to / 60.0))

    time_diff = time_to - time_from

    time_diff = round(time_diff, 2)
    vals = {'work_hours_from': time_from,
            'work_hours_to': time_to,
            'break_hours_from': 0.0,
            'break_hours_to': 0.0,
            'lunch_break': False,
            'free_day': False,
            'business_trip': False}
    sched_setter = env['main.schedule.setter'].with_context(active_ids=[day.id]).create(vals)
    sched_setter.confirm()

    day_line_ids = list()

    for line in env['hr.schedule.day'].browse(day.id).mapped('schedule_day_lines'):
        if line.tabelio_zymejimas_id.id == env.ref('l10n_lt_payroll.tabelio_zymejimas_FD').id:
            day_line_ids.append(line.id)

    day_lines = env['hr.schedule.day.line'].browse(day_line_ids)

    if len(day_lines) != 0:
        totals = sum(float(l.worked_time_total) for l in day_lines)
        if not tools.float_is_zero(abs(totals - time_diff), precision_digits=1):
            {}["Failed, lines created have different work time values", totals, time_diff]
    else:
        {}["Failed, lines not created"]

for i in range(0, days_to_reschedule + 1):
    rand_day_id = random.randint(0, (len(schedule_day_ids_ids) - 1))
    for sched_day in schedule_day_ids:
        if sched_day.id == schedule_day_ids_ids[rand_day_id]:
            day = sched_day

    hours_from = random.randint(6, 14)
    minutes_from = random.randint(1, 59)
    time_from = float(hours_from + (minutes_from / 60.0))

    hours_to = random.randint(16, 21)
    minutes_to = random.randint(1, 56)
    time_to = float(hours_to + (minutes_to / 60.0))

    break_time_from = round(random.uniform(time_from + 0.1, time_to - 0.2), 3)
    break_time_to = round(random.uniform(break_time_from + 0.1, time_to - 0.1), 3)

    if tools.float_compare(break_time_from, break_time_to, precision_digits=2) > 0:
        {}[break_time_from, break_time_to]

    time_diff = (break_time_from - time_from) + (time_to - break_time_to)
    time_diff = round(time_diff, 2)
    vals = {'work_hours_from': time_from,
            'work_hours_to': time_to,
            'break_hours_from': break_time_from,
            'break_hours_to': break_time_to,
            'lunch_break': True,
            'free_day': False,
            'business_trip': False}
    sched_setter = env['main.schedule.setter'].with_context(active_ids=[day.id]).create(vals)
    sched_setter.confirm()

    day_line_ids = list()

    for line in env['hr.schedule.day'].browse(day.id).mapped('schedule_day_lines'):
        if line.tabelio_zymejimas_id.id == env.ref('l10n_lt_payroll.tabelio_zymejimas_FD').id:
            day_line_ids.append(line.id)

    day_lines = env['hr.schedule.day.line'].browse(day_line_ids)

    if len(day_lines) != 0:
        totals = sum(float(l.worked_time_total) for l in day_lines)
        if not tools.float_is_zero(abs(totals - time_diff), precision_digits=1):
            {}["Failed, lines created have different work time values", totals, time_diff]
    else:
        {}["Failed, lines not created"]

multiple_days = list()
if len(schedule_day_ids_ids) >= 10:
    while len(multiple_days) < 10:
        rand_day_id = schedule_day_ids_ids[random.randint(0, (len(schedule_day_ids_ids) - 1))]
        if rand_day_id not in multiple_days:
            multiple_days.append(rand_day_id)

    hours_from = random.randint(6, 14)
    minutes_from = random.randint(1, 59)
    time_from = float(hours_from + (minutes_from / 60.0))

    hours_to = random.randint(16, 21)
    minutes_to = random.randint(1, 56)
    time_to = float(hours_to + (minutes_to / 60.0))

    break_time_from = round(random.uniform(time_from + 0.1, time_to - 0.2), 3)
    break_time_to = round(random.uniform(break_time_from + 0.1, time_to - 0.1), 3)

    if tools.float_compare(break_time_from, break_time_to, precision_digits=2) > 0:
        {}[break_time_from, break_time_to]

    time_diff = (break_time_from - time_from) + (time_to - break_time_to)
    time_diff = round(time_diff, 2)
    vals = {'work_hours_from': time_from,
            'work_hours_to': time_to,
            'break_hours_from': break_time_from,
            'break_hours_to': break_time_to,
            'lunch_break': True,
            'free_day': False,
            'business_trip': False}
    sched_setter = env['main.schedule.setter'].with_context(active_ids=multiple_days).create(vals)
    sched_setter.confirm()

    day_line_ids = list()

    for line in env['hr.schedule.day'].browse(multiple_days).mapped('schedule_day_lines'):
        if line.tabelio_zymejimas_id.id == env.ref('l10n_lt_payroll.tabelio_zymejimas_FD').id:
            day_line_ids.append(line.id)

    day_lines = env['hr.schedule.day.line'].browse(day_line_ids)

    if len(day_lines) != 0:
        totals = sum(float(l.worked_time_total) for l in day_lines)
        if not tools.float_is_zero(abs(totals - (time_diff * 10)), precision_digits=1):
            {}["Failed, lines created have different work time values", totals, time_diff]
    else:
        {}["Failed, lines not created"]
