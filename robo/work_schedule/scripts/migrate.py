date_from = '2019-01-01'

env['ir.module.module'].update_list()
env['ir.module.module'].search([('name', '=', 'work_schedule')], limit=1).button_immediate_install()

payroll_schedule_days = env['hr.schedule.day'].search([
    ('date', '>=', date_from)
])

schedule_to_use = env.ref('work_schedule.factual_company_schedule')
planned_schedule = env.ref('work_schedule.planned_company_schedule')

schedule_state_mapping = {
    'draft': 'draft',
    'validate_1': 'validated',
    'validate_2': 'confirmed',
    'done': 'done'}

for employee_id in payroll_schedule_days.mapped('employee_id'):
    employee_days = env['hr.schedule.day'].search([
        ('date', '>=', date_from),
        ('employee_id', '=', employee_id.id)
    ])
    for department_id in employee_days.mapped('department_id'):
        employee_department_days = env['hr.schedule.day'].search([
            ('date', '>=', date_from),
            ('employee_id', '=', employee_id.id),
            ('department_id', '=', department_id.id)
        ]).sorted(key='date')

        for payroll_schedule_day_id in employee_department_days:
            date_dt = datetime.strptime(payroll_schedule_day_id.date, tools.DEFAULT_SERVER_DATE_FORMAT)
            if date_dt.day == 1:
                year = date_dt.year
                month = date_dt.month
                schedule_to_use.with_context(creating_new=True).create_empty_schedule(year, month, [employee_id.id], [department_id.id], bypass_validated_ziniarastis=True)

            day_empl_dep_work_schedule_day = env['work.schedule.day'].search([
                ('employee_id', '=', employee_id.id),
                ('department_id', '=', department_id.id),
                ('date', '=', payroll_schedule_day_id.date),
                ('work_schedule_id', '=', schedule_to_use.id),
            ])

            day_empl_dep_work_schedule_day.with_context(no_raise=True, creating_new=True).write({
                'business_trip': payroll_schedule_day_id.business_trip,
                'free_day': payroll_schedule_day_id.free_day
            })

            day_empl_dep_work_schedule_day.work_schedule_line_id.write({
                'state': schedule_state_mapping[payroll_schedule_day_id.state],
            })

            for payroll_schedule_line_id in payroll_schedule_day_id.mapped('schedule_day_lines').filtered(lambda l: l.time_from != l.time_to and l.tabelio_zymejimas_id.code in ['BĮ', 'BN', 'DN', 'DP', 'FD', 'KS', 'KV', 'KVN', 'MD', 'NS', 'S', 'SŽ', 'V', 'VD', 'VDN', 'VV', 'SNV', 'NDL', 'VDL']):
                env['work.schedule.day.line'].create({
                    'date': payroll_schedule_line_id.date,
                    'day_id': day_empl_dep_work_schedule_day.id,
                    'time_from': payroll_schedule_line_id.time_from,
                    'time_to': payroll_schedule_line_id.time_to,
                    'work_schedule_code_id': env['work.schedule.codes'].search([('tabelio_zymejimas_id', '=', payroll_schedule_line_id.tabelio_zymejimas_id.id)]).id
                })

            for payroll_schedule_holiday_id in payroll_schedule_day_id.mapped('schedule_holidays_id'):
                existing_holiday = env['work.schedule.holidays'].search([
                    ('date_from', '=', payroll_schedule_holiday_id.date_from),
                    ('date_to', '=', payroll_schedule_holiday_id.date_to),
                    ('holiday_status_id', '=', payroll_schedule_holiday_id.holiday_status_id.id),
                    ('employee_id', '=', employee_id.id),
                ])
                if not existing_holiday:
                    env['work.schedule.holidays'].create({
                        'date_from': payroll_schedule_holiday_id.date_from,
                        'date_to': payroll_schedule_holiday_id.date_to,
                        'holiday_status_id': payroll_schedule_holiday_id.holiday_status_id.id,
                        'employee_id': employee_id.id,
                    })

schedule_to_use.copy_to_schedule(planned_schedule)

payroll_schedule_analytics_installed = env['ir.module.module'].search([('name', '=', 'payroll_schedule_analytics')], limit=1).state == 'installed'

env.cr.execute("DELETE FROM ir_ui_view WHERE id in (SELECT res_id FROM ir_model_data WHERE module in ('payroll_schedule', 'payroll_schedule_analytics') AND model = 'ir.ui.view');")
env.cr.execute("DELETE FROM ir_ui_menu WHERE id in (SELECT res_id FROM ir_model_data WHERE module in ('payroll_schedule', 'payroll_schedule_analytics') AND model = 'ir.ui.menu');")
env.cr.execute("UPDATE ir_module_module SET state = 'uninstalled' WHERE name in ('payroll_schedule', 'payroll_schedule_analytics');")

if payroll_schedule_analytics_installed:
    env['ir.module.module'].search([('name', '=', 'work_schedule_analytics')], limit=1).button_immediate_install()

regular_users = env.ref('payroll_schedule.group_schedule_user').users
manager_users = env.ref('payroll_schedule.group_schedule_manager').users
super_users = env.ref('payroll_schedule.group_schedule_super').users

work_schedule_user_group = env.ref('work_schedule.group_schedule_user')
work_schedule_manager_group = env.ref('work_schedule.group_schedule_manager')
work_schedule_super_group = env.ref('work_schedule.group_schedule_super')

regular_users.mapped('employee_ids').write({'robo_work_schedule_group': 'employee'})
manager_users.mapped('employee_ids').write({'robo_work_schedule_group': 'department_manager'})
super_users.mapped('employee_ids').write({'robo_work_schedule_group': 'super_user'})