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

if datetime.utcnow().weekday() not in [6]:
    result = True
    company_id = env['res.company'].search([], limit=1)
    employee_id = env['hr.employee'].search([('name', '=', 'e.doc.test'),
                                             #  ('contract_ids', '=', False),
                                             ('user_id', '!=', False)], limit=1)
    if not employee_id:
        raise exceptions.Warning(
            'Create test employee which has: No Contracts, has login to robo, name = e.doc.test, before running the script')

    # Re-browse and delete everything
    # Delete Docs
    env.cr.execute('''DELETE FROM e_document where employee_id1 = %s or employee_id2 = %s''',
                   (employee_id.id, employee_id.id,))
    env.cr.commit()

    # Delete ziniarastis period lines
    env.cr.execute('''DELETE FROM ziniarastis_period_line where employee_id = %s''', (employee_id.id,))
    env.cr.commit()

    # Delete Holidays
    env.cr.execute('''DELETE FROM work_schedule_holidays WHERE employee_id = %s''', (employee_id.id,))  # skip on test1
    env.cr.execute('''DELETE FROM hr_schedule_holidays WHERE employee_id = %s''', (employee_id.id,))  # skip on test1
    env.cr.execute('''SELECT ID FROM hr_holidays WHERE employee_id = %s''', (employee_id.id,))
    hol_ids = [x[0] for x in env.cr.fetchall() if x]
    if hol_ids:
        env.cr.execute('''DELETE FROM hr_holidays_payment_line WHERE holiday_id in %s''', (tuple(hol_ids),))
        env.cr.execute('''DELETE FROM hr_holidays WHERE id in %s''', (tuple(hol_ids),))
        env.cr.commit()

    # Delete Appointments
    env.cr.execute('''DELETE FROM hr_contract_appointment where employee_id = %s''', (employee_id.id,))
    env.cr.commit()

    # Delete Contracts
    env.cr.execute('''DELETE FROM hr_contract where employee_id = %s''', (employee_id.id,))
    env.cr.commit()

    # Delete Fixes
    env.cr.execute('''DELETE FROM hr_holidays_fix where employee_id = %s''', (employee_id.id,))
    env.cr.commit()

    status = env['hr.holidays.status'].sudo().search([('kodas', '=', 'A')], limit=1).id
    fix_vals = {'employee_id': employee_id.id,
                'date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                'work_days_left': 10.00,
                'holiday_status_id': status,
                }
    env['hr.holidays.fix'].create(fix_vals)

    template_id = env.ref('e_document.isakymas_del_priemimo_i_darba_template').id
    user = env.user.company_id.vadovas.user_id.id
    user_2 = employee_id.user_id.id

    ceo_env = obj.sudo(user=user).env
    emp_env = obj.sudo(user=user_2).env
    ids = []
    for i in range(0, 5):
        vals = {
            'hour_from': 8.0,
            'hour_to': 12.0,
            'dayofweek': str(i)
        }
        ids.append((0, 0, vals))
        vals = {
            'hour_from': 13.0,
            'hour_to': 17.0,
            'dayofweek': str(i)
        }
        ids.append((0, 0, vals))
    fixed_attendance_ids = [(5,)] + ids
    vals = {
        'employee_id2': employee_id.id,
        'date_2': (datetime.utcnow() + relativedelta(months=3)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
        'date_from': (datetime.utcnow() + relativedelta(days=5, months=3)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
        'float_1': 1000,
        'template_id': template_id,
        'fixed_schedule_template': '8_hrs_5_days',
        'fixed_attendance_ids': fixed_attendance_ids,
        'document_type': 'isakymas',
    }
    document_id = ceo_env['e.document'].sudo(user=user).create(vals)
    document_id.toggle_skip_constraints()
    document_id.toggle_skip_constraints_confirm()
    document_id.sudo(user=user).confirm()
    env.cr.commit()
    document_id.sudo(user=user).sign()
    time.sleep(15)
    env.cr.commit()

    template_id = env.ref('e_document.prasymas_del_priemimo_i_darba_ir_atlyginimo_mokejimo_template').id

    vals = {
        'employee_id1': employee_id.id,
        'vieta': 'Test',
        'date_1': (datetime.utcnow() + relativedelta(years=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
        'text_4': 'LT887290000016467487',
        'selection_bool_1': 'false',
        'selection_bool_3': 'false',
        'selection_bool_2': 'false',
        'template_id': template_id,
    }
    document_id1 = emp_env['e.document'].sudo(user=user_2).create(vals)
    document_id1.toggle_skip_constraints()
    document_id1.toggle_skip_constraints_confirm()
    document_id1.sudo(user=user_2).confirm()
    env.cr.commit()
    document_id1.sudo(user=user_2).sign()
    time.sleep(15)
    env.cr.commit()

    template_id = env.ref('e_document.isakymas_del_darbo_uzmokescio_pakeitimo_template').id
    vals = {
        'employee_id2': employee_id.id,
        'date_5': (datetime.utcnow() + relativedelta(years=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
        'selection_bool_1': 'false',
        'selection_bool_2': 'false',
        'float_1': 1000,
        'fixed_schedule_template': '8_hrs_5_days',
        'fixed_attendance_ids': fixed_attendance_ids,
        'template_id': template_id,
        'document_type': 'isakymas',
    }
    document_id2 = env['e.document'].create(vals)
    document_id2.toggle_skip_constraints()
    document_id2.toggle_skip_constraints_confirm()
    document_id2.confirm()
    env.cr.commit()
    document_id2.sudo(user=user).sign()
    time.sleep(15)
    env.cr.commit()

    template_id = env.ref('e_document.isakymas_del_kasmetiniu_atostogu_template').id
    vals = {
        'employee_id2': employee_id.id,
        'date_2': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
        'date_from': (datetime.utcnow() + relativedelta(months=5, days=1)).strftime(
            tools.DEFAULT_SERVER_DATE_FORMAT),
        'date_to': (datetime.utcnow() + relativedelta(months=5, days=6)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
        'template_id': template_id,
        'document_type': 'isakymas',
    }
    document_id3 = env['e.document'].create(vals)
    document_id3.toggle_skip_constraints()
    document_id3.toggle_skip_constraints_confirm()
    document_id3.confirm()
    env.cr.commit()
    document_id3.with_context(skip_from_script=True).sudo(user=user).sign()
    time.sleep(15)
    env.cr.commit()

    # Re-browse and delete everything
    # Delete Docs
    env.cr.execute('''DELETE FROM e_document where employee_id1 = %s or employee_id2 = %s''',
                   (employee_id.id, employee_id.id,))
    env.cr.commit()

    # Delete ziniarastis period lines
    env.cr.execute('''DELETE FROM ziniarastis_period_line where employee_id = %s''', (employee_id.id,))
    env.cr.commit()

    # Delete Holidays

    env.cr.execute('''DELETE FROM work_schedule_holidays WHERE employee_id = %s''', (employee_id.id,))  # skip on test1
    env.cr.execute('''DELETE FROM hr_schedule_holidays WHERE employee_id = %s''', (employee_id.id,))  # skip on test1
    env.cr.execute('''SELECT ID FROM hr_holidays WHERE employee_id = %s''', (employee_id.id,))
    hol_ids = [x[0] for x in env.cr.fetchall() if x]
    if hol_ids:
        env.cr.execute('''DELETE FROM hr_holidays_payment_line WHERE holiday_id in %s''', (tuple(hol_ids),))
        env.cr.execute('''DELETE FROM hr_holidays WHERE id in %s''', (tuple(hol_ids),))
        env.cr.commit()

    # Delete Appointments
    env.cr.execute('''DELETE FROM hr_contract_appointment where employee_id = %s''', (employee_id.id,))
    env.cr.commit()

    # Delete Contracts
    env.cr.execute('''DELETE FROM hr_contract where employee_id = %s''', (employee_id.id,))
    env.cr.commit()

    # Delete Fixes
    env.cr.execute('''DELETE FROM hr_holidays_fix where employee_id = %s''', (employee_id.id,))
    env.cr.commit()
