# -*- coding: utf-8 -*-
from odoo import tools


def find_time_to_set(hours_to_find, existing_vals=None, code_to_set=None):
    """
    Appends certain amount of hours (hours_to_find) to existing_vals by checking the existing times and making sure
    those newly appended times don't overlap. In other words this method "wraps" specific amount of hours around
    existing vals.
    :param hours_to_find: Number of hours to find
    :type hours_to_find: float
    :param existing_vals: List of tuples of existing times where the first tuple value is time from and the second
    time to. This method does not ensure, but the existing values should not overlap.
    :type existing_vals: list
    :param code_to_set: Optionally - set a specific attribute for each newly created tuple value (so they can be easily
    identified). Common use would be setting tabelio_zymejimas/work_schedule_code so no further parsing would have to
    be done
    :type code_to_set: string/float/other - basically anything you wish to set as the third tuple value for newly
    created values
    :return: A list of total values set - existing ones plus the amount of hours given to find converted to times not
    overlapping the existing times.
    :rtype: list
    """
    if not existing_vals:
        existing_vals = list()
    if tools.float_is_zero(hours_to_find, precision_digits=2):
        return existing_vals

    min_from = 8.0
    max_to = 22.0

    good_to_set = existing_vals
    assert (isinstance(good_to_set, list))

    if not existing_vals:
        good_to_set.append((min_from, min(max_to, min_from + hours_to_find), code_to_set))
    else:
        existing_vals.sort(key=lambda t: t[0])
        hour_from = min_from
        for intersecting_period in existing_vals:
            to_add = min(intersecting_period[0] - hour_from, hours_to_find)
            if tools.float_compare(to_add, 0.0, precision_digits=2) > 0:
                hour_to = hour_from + to_add
                hour_to = min(hour_to, max_to)
                good_to_set.append((hour_from, hour_to, code_to_set))
                hours_to_find -= to_add
                if tools.float_compare(hour_to, max_to, precision_digits=2) >= 0:
                    break
            hour_from = intersecting_period[1]
        if not tools.float_is_zero(hours_to_find, precision_digits=2):
            to_add = min(max_to - hour_from, hours_to_find)
            if not tools.float_is_zero(to_add, precision_digits=2):
                good_to_set.append((hour_from, hour_from + to_add, code_to_set))

    good_to_set.sort(key=lambda t: t[0])
    return good_to_set


def merge_line_values(existing_lines, lines_to_insert, max_to_set=False):
    """
    Merges a list of new values to set with the existing values by truncating the times if they overlap.
    :param existing_lines: Values to keep - a list of tuples where the first tuple value is time from and the second -
    time to e.g. [(8.0, 9.0), (10.0, 11.0)]
    :type existing_lines: list
    :param lines_to_insert: A list of tuples to wrap around the existing times where the first tuple value is time
    from and the second - time to e.g. [(8.0, 9.0), (10.0, 11.0)]
    :type lines_to_insert: list
    :param max_to_set: Optional maximum number of hours that should be set. Truncates lines_to_insert to the amount of
    hours specified
    :type max_to_set: float
    :return: List of merged values
    :rtype: list
    """
    good_to_set = list(existing_lines)
    if not max_to_set and not isinstance(max_to_set, float):
        max_to_set = sum(l[1] - l[0] for l in lines_to_insert)
    for want_to_set in lines_to_insert:
        schedule_code = False
        try:
            schedule_code = want_to_set[2]
        except:
            pass
        hour_from = want_to_set[0]
        hour_to = min(want_to_set[1], want_to_set[0] + max_to_set)

        periods_that_intersect = [
            (l[0], l[1]) for l in good_to_set if
            (l[0] <= want_to_set[0] <= l[1]) or
            (want_to_set[0] <= l[0] <= want_to_set[1])
        ]
        if not periods_that_intersect:
            good_to_set.append((hour_from, hour_to, schedule_code))
            max_to_set -= hour_to - hour_from
            continue

        periods_that_intersect.sort(key=lambda t: t[0])

        for intersecting_period in periods_that_intersect:
            to_add = intersecting_period[0] - hour_from
            if tools.float_compare(to_add, 0.0, precision_digits=2) > 0:
                hour_to = hour_from + min(to_add, max(max_to_set, 0.0))
                good_to_set.append((hour_from, hour_to, schedule_code))
                max_to_set -= to_add
            hour_from = intersecting_period[1]
        if hour_from < want_to_set[1]:
            time_to = min(want_to_set[1], hour_from + max(max_to_set, 0.0))
            good_to_set.append((hour_from, time_to, schedule_code))
            max_to_set -= time_to - hour_from

    correct_values = []
    for values in good_to_set:
        time_from = max(values[0], 0.0)
        time_to = min(values[1], 24.0)
        code = False
        try:
            code = values[2]
        except:
            pass
        if tools.float_compare(time_from, time_to, precision_digits=2) < 0 or \
                tools.float_is_zero(time_from+time_to, precision_digits=2):
            correct_values.append((time_from, time_to, code))
    correct_values.sort(key=lambda t: t[0])
    return correct_values