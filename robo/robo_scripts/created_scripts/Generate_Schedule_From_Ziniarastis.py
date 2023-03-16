# env: database Environment
# datetime: datetime object
# relativedelta: relativedelta object
# tools: robo tools
# base64: base64 module

# This script tests the generation of schedule from ziniarastis for different dates
date_month = 9
date_year = 2018

date_from = (datetime.utcnow() + relativedelta(year=date_year, month=date_month, day=1)).strftime(
    tools.DEFAULT_SERVER_DATE_FORMAT)
date_to = (datetime.utcnow() + relativedelta(year=date_year, month=date_month, day=31)).strftime(
    tools.DEFAULT_SERVER_DATE_FORMAT)

ziniarastis_period_id = env['ziniarastis.period'].search([('date_from', '=', date_from), ('date_to', '=', date_to)],
                                                         limit=1)
ziniarastis_day_line_ids = ziniarastis_period_id.mapped('related_ziniarastis_days.ziniarastis_day_lines')
schedule_day_ids = env['hr.schedule.day'].search([('date', '>=', date_from), ('date', '<=', date_to)])
schedule_day_line_ids = schedule_day_ids.mapped('schedule_day_lines')

schedule_day_line_ids.delete()
schedule_day_ids.unlink()

if len(ziniarastis_day_line_ids) == 0:
    ziniarastis_period_id.generate_ziniarasciai()

ziniarastis_period_id.generate_schedule()
ziniarastis_day_line_ids = ziniarastis_period_id.mapped('related_ziniarastis_days.ziniarastis_day_lines')

schedule_day_ids = env['hr.schedule.day'].search([('date', '>=', date_from), ('date', '<=', date_to)])

for day in schedule_day_ids:
    tabelio_zymejimai = day.mapped('schedule_day_lines.tabelio_zymejimas_id')
    tabelio_zymejimai_ids = tabelio_zymejimai.mapped('id')
    for zymejimas in tabelio_zymejimai_ids:
        for t_zymejimas in tabelio_zymejimai:
            if t_zymejimas.id == zymejimas:
                zymejimas_code = t_zymejimas.code
                tabelio_zymejimas = t_zymejimas

        related_ziniarastis_line_ids_ids = list()
        for line in ziniarastis_day_line_ids:
            if line.date == day.date and line.employee_id.id == day.employee_id.id and line.tabelio_zymejimas_id.id == zymejimas:
                related_ziniarastis_line_ids_ids.append(line.id)

        related_ziniarastis_line_ids = env['ziniarastis.day.line'].browse(related_ziniarastis_line_ids_ids)

        schedule_day_line_ids_ids = list()
        for line in day.schedule_day_lines:
            if line.tabelio_zymejimas_id.id == zymejimas:
                schedule_day_line_ids_ids.append(line.id)

        schedule_day_line_ids = env['hr.schedule.day.line'].browse(schedule_day_line_ids_ids)

        if len(schedule_day_line_ids) == 0:
            msg = "Failed due to no lines on date = " + day.date + ", employee_id =" + day.employee_id.id + ", code = " + zymejimas_code
            {}[msg]

        if not tabelio_zymejimas.is_holidays:
            sched_hour_totals = sum(float(l.worked_time_hours) for l in schedule_day_line_ids)
            sched_minute_totals = sum(float(l.worked_time_minutes) for l in schedule_day_line_ids)
            hours, minutes = divmod(sched_minute_totals * 60, 60)
            sched_worked_time_totals = sched_hour_totals + hours + (minutes / 60.0 * 100.0)
            ziniarastis_hour_totals = sum(float(l.worked_time_hours) for l in related_ziniarastis_line_ids)
            ziniarastis_minute_totals = sum(float(l.worked_time_minutes) for l in related_ziniarastis_line_ids)
            hours, minutes = divmod(ziniarastis_minute_totals * 60, 60)
            ziniarastis_worked_time_totals = ziniarastis_hour_totals + hours + (minutes / 60.0 * 100.0)

            if tools.float_compare(sched_worked_time_totals, ziniarastis_worked_time_totals, precision_digits=2) != 0:
                msg = "Failed due to mismatch time totals on date = " + day.date + ", employee_id =" + day.employee_id.id + ", code = " + zymejimas_code
                {}[msg]
