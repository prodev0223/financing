# -*- coding: utf-8 -*-
import datetime
import dateutil
import functools
import itertools
import logging
import operator
import pytz
import re
from dateutil.relativedelta import relativedelta
import odoo
from odoo import api, models, exceptions, tools, fields
from odoo.tools import OrderedSet
from odoo.tools.translate import _
from collections import OrderedDict
from dateutil.parser import parse
import babel.dates


def convert_to_local_date_str(utc_date_str, offset):
    non_offset = fields.Datetime.from_string(utc_date_str)
    if offset[0] == '-':
        to_offset_time = non_offset - relativedelta(hours=int(offset[1:3]), minutes=int(offset[3:]))
    else:
        to_offset_time = non_offset + relativedelta(hours=int(offset[1:3]), minutes=int(offset[3:]))
    return to_offset_time.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)


class ReadGroupFullExpand(models.Model):
    '''model to inherit if you try full expansion'''
    _name = 'read.group.full.expand'

    # @api.model
    # def get_min_max_date(self, domain, date_field):
    #     date_min = None
    #     date_max = None
    #     for el in domain:
    #         if len(el) == 3:
    #             f_name, operator, value = el
    #             if f_name == date_field:
    #                 if operator in ['<', '<=']:
    #                     if not date_max or date_max < value:
    #                         date_max = value
    #                 elif operator in ['>', '>=']:
    #                     if not date_min or date_min > value:
    #                         date_min = value
    #     if date_min and date_max:
    #         offset = self.env.user.tz_offset
    #         date_min_dt = convert_to_local_date_str(date_min, offset)
    #         date_max_dt = convert_to_local_date_str(date_max, offset)
    #         return date_min_dt, date_max_dt
    #     else:
    #         return False, False
    #
    # @api.model
    # def guess_date_value(self, domain, date_field):
    #     date_min_str, date_max_str = self.get_min_max_date(domain, date_field)
    #     if not (date_min_str and date_max_str):
    #         return ''
    #     date_min_dt = datetime.datetime.strptime(date_min_str, tools.DEFAULT_SERVER_DATETIME_FORMAT)
    #     date_max_dt = datetime.datetime.strptime(date_max_str, tools.DEFAULT_SERVER_DATETIME_FORMAT)
    #     day_difference = (date_max_dt - date_min_dt).days
    #     if day_difference < 2:
    #         period = 'day'
    #     elif day_difference < 8:
    #         period = 'week'
    #     elif day_difference < 32:
    #         period = 'month'
    #     elif day_difference < 95:
    #         period = 'quarter'
    #     elif day_difference < 367:
    #         period = 'year'
    #     else:
    #         return
    #     display_formats = {
    #         'day': 'dd MMM yyyy',  # yyyy = normal year
    #         'week': "'W'w YYYY",  # w YYYY = ISO week-year
    #         'month': 'MMMM yyyy',
    #         'quarter': 'QQQ yyyy',
    #         'year': 'yyyy',
    #     }
    #     display_format = display_formats[period]
    #     locale = self._context.get('lang', 'en_US')
    #     tzinfo = None
    #     range_start = date_min_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
    #     range_end = date_max_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
    #     label = babel.dates.format_datetime(
    #             date_min_dt, format=display_format,
    #             tzinfo=tzinfo, locale=locale
    #         )
    #     return '%s/%s' % (range_start, range_end), label
    #
    # @api.model
    # def get_date_fields(self, domain):
    #     res = []
    #     for el in domain:
    #         if len(el) == 3:
    #             f_name = el[0]
    #             if self._fields[f_name].type in ('date', 'datetime') and f_name not in res:
    #                 res.append(f_name)
    #     return res
    #
    # @api.model
    # def _read_group_process_groupby_simplified(self, gb):  # does not work on inherited fields
    #     """
    #         Helper method to collect important information about groupbys: raw
    #         field name, type, time information, qualified name, ...
    #     """
    #     split = gb.split(':')
    #     field_type = self._fields[split[0]].type
    #     gb_function = split[1] if len(split) == 2 else None
    #     temporal = field_type in ('date', 'datetime')
    #     tz_convert = field_type == 'datetime' and self._context.get('tz') in pytz.all_timezones
    #     qualified_field = self._table + split[0]
    #     if temporal:
    #         display_formats = {
    #             # Careful with week/year formats:
    #             #  - yyyy (lower) must always be used, *except* for week+year formats
    #             #  - YYYY (upper) must always be used for week+year format
    #             #         e.g. 2006-01-01 is W52 2005 in some locales (de_DE),
    #             #                         and W1 2006 for others
    #             #
    #             # Mixing both formats, e.g. 'MMM YYYY' would yield wrong results,
    #             # such as 2006-01-01 being formatted as "January 2005" in some locales.
    #             # Cfr: http://babel.pocoo.org/docs/dates/#date-fields
    #             'day': 'dd MMM yyyy',  # yyyy = normal year
    #             'week': "'W'w YYYY",  # w YYYY = ISO week-year
    #             'month': 'MMMM yyyy',
    #             'quarter': 'QQQ yyyy',
    #             'year': 'yyyy',
    #         }
    #         time_intervals = {
    #             'day': dateutil.relativedelta.relativedelta(days=1),
    #             'week': datetime.timedelta(days=7),
    #             'month': dateutil.relativedelta.relativedelta(months=1),
    #             'quarter': dateutil.relativedelta.relativedelta(months=3),
    #             'year': dateutil.relativedelta.relativedelta(years=1)
    #         }
    #         if tz_convert:
    #             qualified_field = "timezone('%s', timezone('UTC',%s))" % (
    #                 self._context.get('tz', 'UTC'), qualified_field)
    #         qualified_field = "date_trunc('%s', %s)" % (gb_function or 'month', qualified_field)
    #     if field_type == 'boolean':
    #         qualified_field = "coalesce(%s,false)" % qualified_field
    #     return {
    #         'field': split[0],
    #         'groupby': gb,
    #         'type': field_type,
    #         'display_format': display_formats[gb_function or 'month'] if temporal else None,
    #         'interval': time_intervals[gb_function or 'month'] if temporal else None,
    #         'tz_convert': tz_convert,
    #         'qualified_field': qualified_field
    #     }
    #
    # @api.model
    # def get_all_vals(self, groupby, read_group_result):
    #     res = set()
    #
    #     for row in read_group_result:
    #         vals = tuple([row.get(key, '') for key in groupby])
    #         res.add(vals)
    #     return res
    #
    # @api.model
    # def get_example_data_from_domain(self, domain, groupby, remaining_group_bys):
    #     res = {'id': 0}
    #     groupby = [groupby] if isinstance(groupby, basestring) else groupby
    #     for field in remaining_group_bys:
    #         orig_field = field  # keeps format like date:week
    #         if ':' in field:
    #             field = field.split(':')[0]
    #         relevant_nodes = filter(lambda k: k[0] == field, domain)
    #         operators_equal_nodes = filter(lambda k: k[1] == '=', relevant_nodes)
    #         if operators_equal_nodes:
    #             res[orig_field] = operators_equal_nodes[0][2]
    #         elif relevant_nodes:
    #             if field[:4] != 'date':
    #                 raise exceptions.UserError(_('Field %s does not have equal domain' % field))
    #             date_to_nodes = filter(lambda r: r[1] in ['<', '<='], relevant_nodes)
    #             date_from_nodes = filter(lambda r: r[1] in ['>', '>='], relevant_nodes)
    #             if date_to_nodes:
    #                 date_to = min([r[2] for r in date_to_nodes])
    #             else:
    #                 date_to = None
    #             if date_from_nodes:
    #                 date_from = max([r[2] for r in date_from_nodes])
    #             else:
    #                 date_from = None
    #             res[orig_field] = date_to or date_from or False  # todo
    #         else:
    #             raise exceptions.UserError(_('Field %s not found in domain' % field))
    #     annotated_groupbys = [
    #         self._read_group_process_groupby_simplified(gb)
    #         for gb in remaining_group_bys
    #     ]
    #     many2onefields = [gb['field'] for gb in annotated_groupbys if gb['type'] == 'many2one']
    #     if many2onefields:  # todo
    #         for m20nefield in many2onefields:
    #             rec_id = res[m20nefield]
    #             m2one_model_name = self._fields[m20nefield].comodel_name
    #             res[m20nefield] = self.env[m2one_model_name].browse(rec_id).name_get()
    #     groupby_dict = {gb['groupby']: gb for gb in annotated_groupbys}
    #     date_fields = self.get_date_fields(domain)
    #     data = map(
    #         lambda r: {k: self._read_group_prepare_data(k, v, groupby_dict) for k, v in r.iteritems()},
    #         [res])
    #     result = [self._read_group_format_result(d, annotated_groupbys, groupby, domain)
    #               for d in
    #               data]
    #     result = dict(tuple([(k, result[0][k]) for k in remaining_group_bys]))
    #     for date_field in date_fields:
    #         date_name = self.guess_date_value(domain, date_field)
    #         if date_name:
    #             result[date_field] = date_name
    #     result['__count'] = 1
    #     return result

    # def _read_group_fill_results_nonempty(self, domain, groupby, remaining_groupbys,
    #                                       aggregated_fields, count_field,
    #                                       read_group_result, read_group_order=None):
    #     """Helper method for filling in empty groups for all possible values in pivot views of
    #        the field being grouped by"""
    #
    #     # self._group_by_full should map groupable fields to a method that returns
    #     # a list of all aggregated values that we want to display for this field,
    #     # in the form of a m2o-like pair (key,label).
    #     # This is useful to implement kanban views for instance, where all columns
    #     # should be displayed even if they don't contain any record.
    #
    #     # Grab the list of all groups that should be displayed, including all present groups
    #     present_group_ids = [x[groupby][0] for x in read_group_result if x[groupby]]
    #     # if groupby in self._columns and self._columns[groupby]._type == 'many2one':
    #     all_groups, folded = self._fields[groupby].group_expand(self, present_group_ids, domain,
    #                                                             read_group_order=read_group_order,
    #                                                             access_rights_uid=odoo.SUPERUSER_ID)
    #     result_template = dict.fromkeys(aggregated_fields, 0.0)
    #     # result_template[groupby + '_count'] = 0
    #     result_template['_' + '_count'] = 1l
    #     if remaining_groupbys:
    #         result_template['__context'] = {'group_by': remaining_groupbys}
    #
    #     # Merge the left_side (current results as dicts) with the right_side (all
    #     # possible values as m2o pairs). Both lists are supposed to be using the
    #     # same ordering, and can be merged in one pass.
    #     distinct_vals = self.get_all_vals(remaining_groupbys, read_group_result)  # todo ar reikia?
    #     distinct_vals.add(
    #         self.get_example_data_from_domain(domain, groupby, remaining_groupbys))
    #     result = []
    #     known_values = {}
    #
    #     def append_left(left_side):
    #         grouped_value = left_side[groupby] and left_side[groupby][0]
    #         if not grouped_value in known_values:
    #             result.append(left_side)
    #             known_values[grouped_value] = left_side
    #         else:
    #             known_values[grouped_value].update({count_field: left_side[count_field]})
    #
    #     def append_right(right_side):
    #         grouped_value = right_side[0]
    #         if not grouped_value in known_values:
    #             for val in distinct_vals:
    #                 line = dict(result_template)
    #                 line.update(dict(zip(remaining_groupbys, val)))
    #                 line[groupby] = right_side
    #                 line['__domain'] = [(groupby, '=', grouped_value)] + domain
    #                 result.append(line)
    #                 known_values[grouped_value] = line
    #
    #     while read_group_result or all_groups:
    #         left_side = read_group_result[0] if read_group_result else None
    #         right_side = all_groups[0] if all_groups else None
    #         assert left_side is None or left_side[groupby] is False \
    #                or isinstance(left_side[groupby], (tuple, list)), \
    #             'M2O-like pair expected, got %r' % left_side[groupby]
    #         assert right_side is None or isinstance(right_side, (tuple, list)), \
    #             'M2O-like pair expected, got %r' % right_side
    #         if left_side is None:
    #             append_right(all_groups.pop(0))
    #         elif right_side is None:
    #             append_left(read_group_result.pop(0))
    #         elif left_side[groupby] == right_side:
    #             append_left(read_group_result.pop(0))
    #             all_groups.pop(0)  # discard right_side
    #         elif not left_side[groupby] or not left_side[groupby][0]:
    #             # left side == "Undefined" entry, not present on right_side
    #             append_left(read_group_result.pop(0))
    #         else:
    #             append_right(all_groups.pop(0))
    #
    #     if folded:
    #         for r in result:
    #             r['__fold'] = folded.get(r[groupby] and r[groupby][0], False)
    #     return result

    # @api.model
    # def _read_group_fill_results_nonempty(self, domain, groupby, remaining_groupbys,
    #                              aggregated_fields, count_field,
    #                              read_group_result, read_group_order=None):
    #     """Helper method for filling in empty groups for all possible values of
    #        the field being grouped by"""
    #     field = self._fields[groupby]
    #     if not field.group_expand:
    #         return read_group_result
    #
    #     # field.group_expand is the name of a method that returns a list of all
    #     # aggregated values that we want to display for this field, in the form
    #     # of a m2o-like pair (key,label).
    #     # This is useful to implement kanban views for instance, where all
    #     # columns should be displayed even if they don't contain any record.
    #
    #     # Grab the list of all groups that should be displayed, including all present groups
    #     group_ids = [x[groupby][0] for x in read_group_result if x[groupby]]
    #     groups = self.env[field.comodel_name].browse(group_ids)
    #     # determine order on groups's model
    #     order = groups._order
    #     if read_group_order == groupby + ' desc':
    #         order = tools.reverse_order(order)
    #     groups = getattr(self, field.group_expand)(groups, domain, order)
    #     groups = groups.sudo()
    #
    #     result_template = dict.fromkeys(aggregated_fields, 0)
    #     # result_template[groupby + '_count'] = 0
    #     result_template['_' + '_count'] = 1l
    #     if remaining_groupbys:
    #         result_template['__context'] = {'group_by': remaining_groupbys}
    #
    #     # Merge the current results (list of dicts) with all groups (recordset).
    #     # Determine the global order of results from all groups, which is
    #     # supposed to be in the same order as read_group_result.
    #     # result = OrderedDict((group.id, {}) for group in groups)
    #     result = OrderedDict((group.id, {}) for group in groups)
    #
    #     # fill in results from read_group_result
    #     for left_side in read_group_result:
    #         left_id = (left_side[groupby] or (False,))[0]
    #         if not result.get(left_id):
    #             result[left_id] = left_side
    #         else:
    #             result[left_id][count_field] = left_side[count_field]
    #
    #     # fill in missing results from all groups
    #     for right_side in groups.name_get():
    #         right_id = right_side[0]
    #         if not result[right_id]:
    #             # line = dict(result_template)
    #             line = dict(result_template, **self.get_example_data_from_domain(domain, groupby, remaining_groupbys))
    #             line[groupby] = right_side
    #             line['__domain'] = [(groupby, '=', right_id)] + domain
    #             result[right_id] = line
    #
    #     result = result.values()
    #
    #     if groups._fold_name in groups._fields:
    #         for r in result:
    #             group = groups.browse(r[groupby] and r[groupby][0])
    #             r['__fold'] = group[groups._fold_name]
    #     return result
    #
    # @api.model
    # def _read_group_raw(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True, expand_full=False):
    #
    #     groupby = [groupby] if isinstance(groupby, basestring) else groupby
    #     if expand_full and len(groupby) > 1:
    #         groupby = sorted(groupby, key=lambda f: self._fields[f.split(':')[0]].group_expand)
    #         field_to_group_by = groupby[0]
    #         remaining_to_group_by = groupby[1:]
    #         group_by_other = self._read_group_raw(domain, fields, remaining_to_group_by, offset=offset, limit=limit,
    #                                          orderby=orderby, lazy=lazy, expand_full=expand_full)
    #         res = []
    #         for row in group_by_other:
    #             dom = row.get('__domain')
    #             if not dom:
    #                 raise exceptions.UserError(_('No domain'))
    #             new_el = self._read_group_raw(dom, fields, [field_to_group_by], offset=offset, limit=limit,
    #                                      orderby=orderby, lazy=lazy, expand_full=expand_full)
    #             if not new_el:
    #                 new_el = [dict(self.get_example_data_from_domain(dom, field_to_group_by, groupby))]
    #                 new_el[0]['__domain'] = dom
    #                 for field_measure in fields:
    #                     if field_measure not in groupby:
    #                         new_el[0][field_measure] = 0
    #             for r in new_el:
    #                 for field_to_group in remaining_to_group_by:
    #                     r[field_to_group] = row.get(field_to_group, '')
    #             res.extend(new_el)
    #         return res
    #     self.check_access_rights('read')
    #     query = self._where_calc(domain)
    #     fields = fields or [f.name for f in self._fields.itervalues() if f.store]
    #     groupby_list = groupby[:1] if lazy else groupby
    #     annotated_groupbys = [self._read_group_process_groupby(gb, query) for gb in groupby_list]
    #     groupby_fields = [g['field'] for g in annotated_groupbys]
    #     order = orderby or ','.join([g for g in groupby_list])
    #     groupby_dict = {gb['groupby']: gb for gb in annotated_groupbys}
    #
    #     self._apply_ir_rules(query, 'read')
    #     for gb in groupby_fields:
    #         assert gb in fields, "Fields in 'groupby' must appear in the list of fields to read (perhaps it's missing in the list view?)"
    #         assert gb in self._fields, "Unknown field %r in 'groupby'" % gb
    #         gb_field = self._fields[gb].base_field
    #         assert gb_field.store and gb_field.column_type, "Fields in 'groupby' must be regular database-persisted fields (no function or related fields), or function fields with store=True"
    #
    #     aggregated_fields = [
    #         f for f in fields
    #         if f != 'sequence'
    #         if f not in groupby_fields
    #         for field in [self._fields.get(f)]
    #         if field
    #         if field.group_operator
    #         if field.base_field.store and field.base_field.column_type
    #     ]
    #
    #     field_formatter = lambda f: (
    #         self._fields[f].group_operator,
    #         self._inherits_join_calc(self._table, f, query),
    #         f,
    #     )
    #     select_terms = []
    #
    #     for f in aggregated_fields:
    #         gr_op = self._fields[f].group_operator
    #
    #         if gr_op in self._fields:
    #             select_terms.append(
    #                 "sum(%(arg1)s * %(arg2)s)/nullif(sum(case when %(arg1)s <> 0.0 then %(arg2)s else null end),0) AS %(f)s" % {
    #                     'arg1': self._inherits_join_calc(self._table, f, query),
    #                     'arg2': str(self._table) + '.' + str(gr_op),
    #                     'f': f,
    #                 })
    #         else:
    #             select_terms.append("%s(%s) AS %s" % field_formatter(f))
    #
    #     for gb in annotated_groupbys:
    #         select_terms.append('%s as "%s" ' % (gb['qualified_field'], gb['groupby']))
    #
    #     groupby_terms, orderby_terms = self._read_group_prepare(order, aggregated_fields, annotated_groupbys, query)
    #     from_clause, where_clause, where_clause_params = query.get_sql()
    #     if lazy and (len(groupby_fields) >= 2 or not self._context.get('group_by_no_leaf')):
    #         count_field = groupby_fields[0] if len(groupby_fields) >= 1 else '_'
    #     else:
    #         count_field = '_'
    #     count_field += '_count'
    #
    #     prefix_terms = lambda prefix, terms: (prefix + " " + ",".join(terms)) if terms else ''
    #     prefix_term = lambda prefix, term: ('%s %s' % (prefix, term)) if term else ''
    #
    #     query = """
    #             SELECT min(%(table)s.id) AS id, count(%(table)s.id) AS %(count_field)s %(extra_fields)s
    #             FROM %(from)s
    #             %(where)s
    #             %(groupby)s
    #             %(orderby)s
    #             %(limit)s
    #             %(offset)s
    #         """ % {
    #         'table': self._table,
    #         'count_field': count_field,
    #         'extra_fields': prefix_terms(',', select_terms),
    #         'from': from_clause,
    #         'where': prefix_term('WHERE', where_clause),
    #         'groupby': prefix_terms('GROUP BY', groupby_terms),
    #         'orderby': prefix_terms('ORDER BY', orderby_terms),
    #         'limit': prefix_term('LIMIT', int(limit) if limit else None),
    #         'offset': prefix_term('OFFSET', int(offset) if limit else None),
    #     }
    #     self._cr.execute(query, where_clause_params)
    #     fetched_data = self._cr.dictfetchall()
    #
    #     if not groupby_fields:
    #         return fetched_data
    #
    #     many2onefields = [gb['field'] for gb in annotated_groupbys if gb['type'] == 'many2one']
    #     if many2onefields:
    #         data_ids = [r['id'] for r in fetched_data]
    #         many2onefields = list(set(many2onefields))
    #         data_dict = {d['id']: d for d in self.browse(data_ids).read(many2onefields)}
    #         for d in fetched_data:
    #             d.update(data_dict[d['id']])
    #
    #     data = map(lambda r: {k: self._read_group_prepare_data(k, v, groupby_dict) for k, v in r.iteritems()},
    #                fetched_data)
    #     result = [self._read_group_format_result(d, annotated_groupbys, groupby, domain) for d in data]
    #     if lazy:
    #         # Right now, read_group only fill results in lazy mode (by default).
    #         # If you need to have the empty groups in 'eager' mode, then the
    #         # method _read_group_fill_results need to be completely reimplemented
    #         # in a sane way
    #         result = self._read_group_fill_results(
    #             domain, groupby_fields[0], groupby[len(annotated_groupbys):],
    #             aggregated_fields, count_field, result, read_group_order=order,
    #         )
    #     elif expand_full and self._fields[groupby_fields[0]].group_expand:
    #         result = self._read_group_fill_results_nonempty(domain, groupby[0], groupby[1:],
    #                                                    aggregated_fields, count_field, result, read_group_order=order)
    #     return result
    #
    # @api.model
    # def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True, expand_full=False):
    #     """
    #     Get the list of records in list view grouped by the given ``groupby`` fields
    #
    #     :param domain: list specifying search criteria [['field_name', 'operator', 'value'], ...]
    #     :param list fields: list of fields present in the list view specified on the object
    #     :param list groupby: list of groupby descriptions by which the records will be grouped.
    #             A groupby description is either a field (then it will be grouped by that field)
    #             or a string 'field:groupby_function'.  Right now, the only functions supported
    #             are 'day', 'week', 'month', 'quarter' or 'year', and they only make sense for
    #             date/datetime fields.
    #     :param int offset: optional number of records to skip
    #     :param int limit: optional max number of records to return
    #     :param list orderby: optional ``order by`` specification, for
    #                          overriding the natural sort ordering of the
    #                          groups, see also :py:meth:`~osv.osv.osv.search`
    #                          (supported only for many2one fields currently)
    #     :param bool lazy: if true, the results are only grouped by the first groupby and the
    #             remaining groupbys are put in the __context key.  If false, all the groupbys are
    #             done in one call.
    #     :return: list of dictionaries(one dictionary for each record) containing:
    #
    #                 * the values of fields grouped by the fields in ``groupby`` argument
    #                 * __domain: list of tuples specifying the search criteria
    #                 * __context: dictionary with argument like ``groupby``
    #     :rtype: [{'field_name_1': value, ...]
    #     :raise AccessError: * if user has no read rights on the requested object
    #                         * if user tries to bypass access rules for read on the requested object
    #     """
    #     result = self._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy, expand_full=expand_full)
    #
    #     groupby = [groupby] if isinstance(groupby, basestring) else list(OrderedSet(groupby))
    #     dt = [
    #         f for f in groupby
    #         if self._fields[f.split(':')[0]].type in ('date', 'datetime')
    #     ]
    #
    #     # iterate on all results and replace the "full" date/datetime value
    #     # (range, label) by just the formatted label, in-place
    #     for group in result:
    #         for df in dt:
    #             # could group on a date(time) field which is empty in some
    #             # records, in which case as with m2o the _raw value will be
    #             # `False` instead of a (value, label) pair. In that case,
    #             # leave the `False` value alone
    #             if group.get(df):
    #                 group[df] = group[df][1]
    #     return result


ReadGroupFullExpand()