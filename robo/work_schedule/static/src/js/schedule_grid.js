robo.define('workschedule', function (require) {
"use strict";

var Class = require('web.Class');
var View = require('web.View');
var Widget = require('web.Widget');

var core = require('web.core');
var data = require('web.data');
var Dialog = require('web.Dialog');
var form_common = require('web.form_common');
var formats = require('web.formats');
var time = require('web.time');
var Model = require('web.DataModel');
var utils = require('web.utils');
var session = require('web.session');
var pyeval = require('web.pyeval');
var QWeb = core.qweb;
var Pager = require('web.Pager')

var patch = require('snabbdom.patch');
var h = require('snabbdom.h');

var _t = core._t;
var _lt = core._lt;

var mouseDown = false;
$(document).mousedown(function() {
    mouseDown = true;
}).mouseup(function() {
    mouseDown = false;
});

$( document ).ready(function(){
	$(document).click(function(elem){
	    var closest_td = $(elem.target).closest("td");
	    if (!$(elem.target).is("tbody") && !$(elem.target).is("tr") && !$(elem.target).hasClass("o_selected_cell") && !$(elem.target).hasClass("o_unselected_cell") && !$(elem.target).hasClass("o_schedule_column") && !$(elem.target).hasClass("o_schedule_department") && !$(elem.target).hasClass("btn-sm") && !$(closest_td).hasClass("o_selected_cell") && !$(closest_td).hasClass("o_unselected_cell")) {
            $(".o_selected_cell").each(function(i, element) {
                $(element).removeClass("o_selected_cell");
                $(element).addClass("o_unselected_cell");
                $('#delete_time_button').addClass("o_schedule_invisible");
            });
        }
    });
});

var ScheduleView = View.extend({
    icon: 'fa-th',
    display_name: _lt("Lentelė"),
    view_type: 'workschedule',
    add_label: _lt("Pridėti eilutę"),
    events: {
        "mouseenter .o_selected_cell": "_mouse_enter",
        "mouseenter .o_unselected_cell": "_mouse_enter",
        "mouseleave .o_selected_cell": "_mouse_leave",
        "mouseleave .o_unselected_cell": "_mouse_leave",
        'mousedown .o_selected_cell': "_mouse_down",
        'mouseup .o_selected_cell': "_mouse_up",
        'mousedown .o_unselected_cell': "_mouse_down",
        'mouseup .o_unselected_cell': "_mouse_up",
        "click .btn_increase_state": function(event) {
            if (!this.selection_frozen) {
                var $target = $(event.target).closest('span');
                var line_id = [$target[0].getAttribute('line_id')];
                var state = [$target[0].getAttribute('department_state')];
                var self = this;
                var confirm_msg = false;
                if (this.user_group > 3) {
                    confirm_msg = _t("Kadangi turite buhalterio teises, grafiko apribojimai nebus tikrinami.\nJuos galima patikrinti paspaudus mygtuką 'Patikrinti grafikus'\n\nPatvirtinkite, jog norite patvirtinti grafiką nepaisant apribojimų")
                }
                else if (this.allow_bypass_constraints) {
                    confirm_msg = _t("Grafiko apribojimų tikrinimas yra išjungtas, todėl grafikai nebus tikrinami.\nGrafikus galima patikrinti paspaudus mygtuką 'Patikrinti grafikus'.\n\nPatvirtinkite, jog norite patvirtinti grafiką nepaisant apribojimų\n(Tvirtindami grafikus prisiimate atsakomybę už nekorektiškai sudarytus grafikus)")
                }

                if (confirm_msg && state == 'draft') {
                    if (confirm(confirm_msg)) {
                        $.when(this._model.call('increase_state', [line_id], {context: this.get_full_context()})).then(function(){
                             self._fetch();
                        });
                    }
                } else {
                    $.when(this._model.call('increase_state', [line_id], {context: this.get_full_context()})).then(function(){
                        self._fetch();
                    });
                }
            }
        },
        "click .btn_decrease_state": function(event) {
            if (!this.selection_frozen) {
                var $target = $(event.target).closest('span');
                var line_id = [$target[0].getAttribute('line_id')];
                var self = this;
                $.when(this._model.call('decrease_state', [line_id], {context: this.get_full_context()})).then(function(){
                     self._fetch();
                });
            }
        },
        "click .o_schedule_button_add": function(event) {
            if (!this.selection_frozen) {
                var _this = this;
                event.preventDefault();
                var form_context = _this.get_full_context();
                var formDescription = _this.ViewManager.views.form;
                var open_model = 'new.work.schedule.day.wizard';
                (new Model('work.schedule.day')).call('get_wizard_view_id', [open_model]).then(function(view_id){
                    var p = new form_common.FormViewDialog(this, {
                        res_model: 'new.schedule.line.wizard',
                        res_id: false,
                        view_id: view_id,
                        context: form_context,
                        title: _this.add_label.toString(),
                        disable_multiple_selection: true,
                        default_name: '',
                    }).open();
                    p.on('create_completed', this, function () {
                        _this._fetch();
                    });
                });
            }
        },
        'click .btn_remove': function(e){
            if (!this.selection_frozen) {
                var $target = $(e.target).closest('th');
                var line_id = [$target[0].getAttribute('line_ids')];
                var self = this;
                if (confirm(_t("Ar tikrai norite ištrinti šį įrašą?"))) {
                    $.when(this._model.call('remove_schedule_department_line', [line_id], {context: this.get_full_context()})).then(function(){
                         self._fetch();
                    })
                }
            }
        },
        'click .change_planned_schedule_single_lines_state': function(e){
            if (!this.selection_frozen) {
                var $target = $(e.target).closest('th');
                var line_ids = [$target[0].getAttribute('line_ids')];
                var self = this;
                $.when(
                    confirm(_t("Please confirm that you really want to change the planned line usage in payroll calculations"))
                ).then(
                    this._model.call(
                        'action_set_lines_as_used_in_planned_schedule',
                        [line_ids],
                        {context: this.get_full_context()}
                    )
                ).then(
                    function(){
                        self._fetch();
                    }
                );
            }
        },
        'click .o_unselected_cell': function(e){
            if (!this.selection_frozen) {
                if (!this.prevent_unselect) {
                    var $target = $(e.target).closest('td');
                    if ($target.hasClass('o_schedule_draft') || this.is_chief_accountant) {
                        $target.toggleClass('o_unselected_cell', false);
                        $target.toggleClass('o_selected_cell', true);
                    } else {this.do_warn(_t("Šios dienos darbuotojo darbo laikas jau patvirtintas"), _t("Norėdami pakeisti darbo laiką - atstatykite skyriaus darbo grafiką į juodraščio būseną!"));}
                } else {
                    this.prevent_unselect = false;
                }
            }
            this.display_delete_button();
        },
        'click .o_selected_cell': function(e){
            if (!this.selection_frozen) {
                if (!this.prevent_unselect) {
                    var $target = $(e.target).closest('td');
                    $target.toggleClass('o_unselected_cell', true);
                    $target.toggleClass('o_selected_cell', false);
                } else {
                    this.prevent_unselect = false;
                }
            }
            this.display_delete_button();
        },
        'click .o_schedule_department': function(e){
            if (!this.selection_frozen) {
                var $target = $(e.target).closest('tr');
                var any_cells_selected = false;
                $target.find('td').each(function(){
                    if ($(this).hasClass('o_selected_cell')) {
                        any_cells_selected = true;
                    }
                });
                var td_class = ((any_cells_selected) ? 'o_selected_cell' : 'o_unselected_cell')
                $target.find('td').each(function(){
                    if (($(this).hasClass('o_schedule_draft') || this.is_chief_accountant) && $(this).hasClass(td_class)) {
                        $(this).toggleClass('o_unselected_cell');
                        $(this).toggleClass('o_selected_cell');
                    }
                });
            }
            this.display_delete_button();
        },
        'click .o_schedule_column': function(e){
            if (!this.selection_frozen) {
                var $target = $(e.target).closest('th');
                var th_index = ((this.user_group == 1) ? ($target.index() - 4) : ($target.index() - 5));
                var any_cells_selected = false;
                $('tbody tr').each(function(){
                    var sm_square = $(this).find('td').eq(th_index);
                    if (sm_square && sm_square.hasClass('o_selected_cell')){
                        any_cells_selected = true;
                        return false;
                    }
                });
                var td_class = ((any_cells_selected) ? 'o_selected_cell' : 'o_unselected_cell');
                $('tr').each(function(){
                    var sm_square = $(this).find('td').eq(th_index);
                    if (sm_square && sm_square.hasClass(td_class) && (sm_square.hasClass('o_schedule_draft') || this.is_chief_accountant)){
                        sm_square.toggleClass('o_selected_cell');
                        sm_square.toggleClass('o_unselected_cell');
                    }
                });
            }
            this.display_delete_button();
        },
        'click .check-failed-line-constraints-cell-clickable': function(e) {
            var $target = $(e.target).closest('th');
            if (!$target) { return }
            var line_id = $target[0].getAttribute('line_id');
            if (!line_id) { return }
            return this._model.call('show_failed_line_constraints', [parseInt(line_id)]);
        },
    },
    init: function (parent, dataset) {
        this._super.apply(this, arguments);
        this._model = dataset._model;
        this.left_scroll_pos= 0.0;
        this.top_scroll_pos = 0.0;
        this._in_waiting = null;
        this._fetch_mutex = new utils.Mutex();
        this._limit = 50;
        this.current_min = 1;

        this.user_group = 1;
        this.work_schedule_is_planned = false;
        this.allow_bypass_constraints = false;
        this.disable_state_changes = false;
        this.mouse_down_start_col = false;
        this.mouse_down_start_row = false;
        this.force_show_edit_buttons = false;
        this.prevent_unselect = false;
        this.is_chief_accountant = false;
        this.user_department_ids = new Array();

        this.on('change:schedule_data', this, this._render);
        this.first_fetch = true;
        this.sorted_schedule_days = [];

        var today = new Date();
        this.year = today.getFullYear();
        this.month = today.getMonth()+1;
        this.work_schedule_id = false;
        this.selection_frozen = true;

        this.domain = [];

        if (dataset.context.default_month) {
            this.month = dataset.context.default_month;
        }
        if (dataset.context.default_year) {
            this.year = dataset.context.default_year;
        }
    },
    start: function () {
        this._state = document.createElement('div');
        this.el.appendChild(this._state);
        this._render();
        return $.when();
    },
    _mouse_enter: function(event) {
        var $target = $(event.target).closest('td');
        if (mouseDown && (($target.hasClass('o_schedule_draft') || this.is_chief_accountant)&& !this.selection_frozen)) {
            var row_n = $target.attr('row');
            var col_n = $target.attr('column');
            if (this.mouse_down_start_col != false && this.mouse_down_start_row != false) {
                this.mark_selected_days(this.mouse_down_start_col, this.mouse_down_start_row, col_n, row_n, event.ctrlKey);
            }
        }
    },
    _mouse_leave: function(event) {
        var $target = $(event.target).closest('td');
        if (($target.hasClass('o_schedule_draft') || this.is_chief_accountant) && !this.selection_frozen) {
            var row_n = $target.attr('row');
            var col_n = $target.attr('column');
            if (this.mouse_down_start_col != false || this.mouse_down_start_row != false) {
                if (!event.ctrlKey) {
                    this.unmark_selected_days();
                }
            }
        }
    },
    _mouse_down: function(event) {
        var $target = $(event.target).closest('td');
        if (($target.hasClass('o_schedule_draft') || this.is_chief_accountant) && !this.selection_frozen) {
            this.mouse_down_start_col = false;
            this.mouse_down_start_row = false;
            if ($target.attr('column') != false && $target.attr('row') != false) {
                this.mouse_down_start_col = $target.attr('column');
                this.mouse_down_start_row = $target.attr('row');
            }
        }
    },
    _mouse_up: function(event) {
        var $target = $(event.target).closest('td');
        if (($target.hasClass('o_schedule_draft') || this.is_chief_accountant) && !this.selection_frozen) {
            var is_selected = $target.hasClass('o_selected_cell')
            var row_n = $target.attr('row');
            var col_n = $target.attr('column');
            if (this.mouse_down_start_col && this.mouse_down_start_row) {
                this.mark_selected_days(this.mouse_down_start_col, this.mouse_down_start_row, col_n, row_n, event.ctrlKey);
            }
            this.mouse_down_start_col = false;
            this.mouse_down_start_row = false;
            if (!is_selected) this.prevent_unselect = true;
        }
    },
    unmark_selected_days: function() {
        $(".o_selected_cell").each(function(i, element) {
            $(element).removeClass("o_selected_cell");
            $(element).addClass("o_unselected_cell");
        });
        this.display_delete_button();
    },
    mark_selected_days: function(col_s, row_s, col_e, row_e, no_unlink=false) {
        if (col_s != col_e && row_s != row_e && !no_unlink){
            this.unmark_selected_days()
        }
        if (!col_s && col_e) col_s = col_e;
        if (!col_e && col_s) col_e = col_s;
        if (!row_s && row_e) row_s = row_e;
        if (!row_e && row_s) row_e = row_s;
        if (col_s && row_s && col_e && row_e) {
            var column_start = parseInt(col_s);
            var row_start = parseInt(row_s);
            var column_end = parseInt(col_e);
            var row_end = parseInt(row_e);
            for (var i=Math.min(column_start, column_end); i<=Math.max(column_start, column_end); i++) {
                for (var j=Math.min(row_start, row_end); j<=Math.max(row_start, row_end); j++) {
                    var str = 'td[column="' + i + '"][row="' + j + '"]';
                    if ($(str).hasClass('o_schedule_draft') || this.is_chief_accountant) {
                        $(str).removeClass("o_unselected_cell");
                        $(str).addClass("o_selected_cell");
                    }
                }
            }
        }
        this.display_delete_button();
    },
    _render: function () {
        var _this = this;
        this.selection_frozen = true;
        var columns, vnode, schedule, totals;
        var schedule_data = this.get('schedule_data') || false;
        if (schedule_data) {
            this.dataset_length = schedule_data['total_number_of_lines'] || 0;
            this.update_pager();
            this.date_day_totals = schedule_data.dates_day_totals;
            this.date_hour_totals = schedule_data.dates_hour_totals;
            this.department_line_day_totals = schedule_data.departments_day_totals;
            this.department_line_hour_totals = schedule_data.departments_hour_totals;
            this.work_schedule_is_planned = schedule_data.work_schedule_is_planned;
            this.work_schedule_id = schedule_data.work_schedule_id;
            var weekends = schedule_data.weekends;
            var national_holidays = schedule_data.national_holidays;
            this.user_group = schedule_data.user_group;
            this.force_show_edit_buttons = schedule_data.force_show_edit_buttons;
            this.allow_bypass_constraints = schedule_data.allow_bypass_constraints;
            this.user_department_ids = schedule_data.user_department_ids;
            this.disable_state_changes = schedule_data.disable_state_changes;
            $('#payroll_busy_label_container').toggleClass('o_schedule_invisible', schedule_data.hide_busy_label);

            var $selection = this._navigation.$el.find('select')
            $selection.val(schedule_data.work_schedule_id);
            if (this.user_group < 4 || this.user_group == undefined) {
                $('#schedule_selector_label').parent().hide();
            } else {
                $('#schedule_selector_label').parent().show();
            }
            if (this.user_group == 1 && !this.force_show_edit_buttons) {
                $('#schedule_setters_group').hide();
            } else {
                $('#schedule_setters_group').show();
            }

            this.sorted_schedule_days = [];
            for (var key in schedule_data.day_print_data) {
                this.sorted_schedule_days.push(key)
            }
            this.sorted_schedule_days.sort();
            var single_department_name = schedule_data.single_department_name;
            vnode = this._table_base(schedule_data.day_print_data, schedule_data.dates_totals, schedule_data.month_validated || schedule_data.disable_state_changes, schedule_data.month_name, schedule_data.single_department_filtered, single_department_name);
            var schedule_body = vnode.children[0].children;
            schedule_data_lines = [];
            if (schedule_data.schedule) {
                var schedule_data_lines = this._parse_schedule_data_to_lines(schedule_data.schedule, schedule_data.weekends, schedule_data.national_holidays, schedule_data.department_line_totals, schedule_data.single_department_filtered, schedule_data.user_department_ids, schedule_data.day_print_data);
            }

            var empty_lines = this._get_empty_lines(schedule_data_lines.length, schedule_data.day_print_data);
            vnode.children[0].children.push(
                h('tbody', schedule_data_lines.concat(empty_lines))
            );
            this._render_dynamic_buttons(schedule_data.dynamic_buttons);
            this._update_month_labels();
            this._state = patch(_this._state, vnode);
        }

        setTimeout(function () {
            var row_headers = _this.el.querySelectorAll('tbody th:first-child div');
            _this._state.key = Math.random();
            var freeze_left = 6;
            if (_this.user_group == 1) {
                freeze_left = 3;
            }
            if ($(window).width() < 800) {
                freeze_left = 0;
            }

            _this.$('table').tableHeadFixer({'z-index' : 50, left: freeze_left, head: true, 'header-z-index': 50});
            _this.$('table').css({'border-collapse': 'separate'});
            _this.$el.css({height: '100%'});
            _this.$('.o_view_schedule').css({height: '100%'});

            for (var k = 0; k < row_headers.length; k++) {
                var header = row_headers[k];
                if (header.scrollWidth > header.clientWidth) {
                    $(header).addClass('overflow');
                }
            }
            if (_this.left_scroll_pos !== false) {
                $('.o_view_schedule').scrollTo(_this.left_scroll_pos, 0, {axis:'x'});
                _this.left_scroll_pos = false;
            }
            if (_this.top_scroll_pos !== false) {
                $('.o_view_schedule').scrollTo(_this.top_scroll_pos, 0, {axis:'y'});
                _this.top_scroll_pos = false;
            }
            var event_el = document.body;
//            TODO Make it work on specific element, not body
//            var event_el = document.getElementsByTagName('o_main')[0];
            if (event_el) {
                event_el.removeEventListener('keyup',_this.on_keyup);
                event_el.addEventListener('keyup', _this.on_keyup);
            }
        }, 0);
        if (this._navigation) {
            this.display_delete_button();
        }
        this.selection_frozen = false;
    },
    on_keyup: function(event) {
        if(event.which === 46 && this._navigation) {
            this._navigation.call_delete_lines();
        }
    },
    getConstraintIconCell: function (constraintStatus, lineID) {
        var constraintIconParameters = {
            'valid': {
                'class': '.fa.fa-check-circle-o',
                'style': 'color: #2ECC71;',
                'title':  _t('Schedule meets the constraints'),
            },
            'busy': {
                'class': '.fa.fa-spinner.fa-spin',
                'style': 'color: #2980B9;',
                'title':  _t('Constraint check is in progress'),
            },
            'failed': {
                'class': '.fa.fa-warning',
                'style': 'color: #E67E22; cursor: pointer;',
                'title':  _t('Schedule does not meet the constraints'),
            },
        }

        var constraintIcon = ''
        if (constraintStatus != 'not_checked') {
            var statusParameters = constraintIconParameters[constraintStatus];
            constraintIcon = h(
                'i'+statusParameters.class,
                {
                    attrs: {
                        'style': statusParameters.style,
                        'title': statusParameters.title,
                    }
                }, []
            );
        }

        var cellStyle = 'vertical-align: middle;';
        var cellClasses = '';
        if (constraintStatus == 'failed') {
            cellStyle += 'cursor: pointer;';
            cellClasses += '.check-failed-line-constraints-cell-clickable';
        }
        return h('th'+cellClasses,{attrs: {'style': cellStyle, 'line_id': lineID}},[constraintIcon]);
    },
    _parse_schedule_data_to_lines: function (data, weekend_dates, national_holiday_dates, department_line_totals, single_department_filtered, user_department_ids, day_print_data) {
        var schedule_lines = [];
        if (!(Object.keys(data).length > 0)) {
            return schedule_lines; //No data exists
        }
        var current_period_data = data;

        var employee_name_to_id_mapping = {};
        var employee_names = new Array();
        for (var key in current_period_data) {
            var formatted_key = current_period_data[key]['name'] + " " + key
            employee_name_to_id_mapping[formatted_key] = key;
            employee_names.push(formatted_key);
        }
        employee_names.sort(function (a, b) {
            return a.localeCompare(b);
        });
        var sorted_employee_ids_by_name = new Array();
        for (var i = 0; i < employee_names.length; i++) {
            sorted_employee_ids_by_name.push(employee_name_to_id_mapping[employee_names[i]]);
        }

        var states_to_show_increase_state_button = [];
        var states_to_show_decrease_state_button = [];
        switch (this.user_group) {
            case 2:
                states_to_show_increase_state_button = ['draft'];
                states_to_show_decrease_state_button = ['validated'];
                break;
            case 3:
                states_to_show_increase_state_button = ['draft', 'validated'];
                states_to_show_decrease_state_button = ['confirmed', 'validated'];
                break;
            case 4:
                states_to_show_increase_state_button = ['draft', 'validated', 'confirmed'];
                states_to_show_decrease_state_button = ['done', 'confirmed', 'validated'];
                break;
            case 5:
                states_to_show_increase_state_button = ['draft', 'validated', 'confirmed'];
                states_to_show_decrease_state_button = ['done', 'confirmed', 'validated'];
                break;
            default:
                states_to_show_increase_state_button = [];
                states_to_show_decrease_state_button = [];
        }

        var state_name_mapping = {
            'draft': '',
            'validated': _t('Patvirtinta'),
            'confirmed': _t('Pateikta'),
            'done': _t('Priimta'),
        };
        var validate_icons = {
            'draft': 'icon-check',
            'validated': 'icon-check',
            'confirmed': 'icon-checkmark-circle',
        };
        var unvalidate_icons = {
            'validated': 'icon-cross2',
            'confirmed': 'icon-cross2',
            'done': 'icon-cross-circle',
        };
        var curr_row = 1;
        for (var i = 0; i < sorted_employee_ids_by_name.length; i++) {
            var employee_id = sorted_employee_ids_by_name[i];
            var employee_data = current_period_data[employee_id];
            var employee_department_data = employee_data['department_data'];
            var employee_etatas = employee_data['etatas'];
            var employee_job = employee_data['job'];
            var employee_name = employee_data['name'];
            var employee_used_in_planned = employee_data['empl_used_in_planned']
            var number_of_departments = Object.keys(employee_department_data).length;

            var employee_name_block =
            h(
                'th.employee_name_block',
                {attrs:{rowspan: number_of_departments}},
                [h(
                    'div.align_center',
                    {attrs:{title: _t('Darbuotojas')}},
                    employee_name
                )]
            );

            var department_name_to_id_mapping = {};
            var department_names = new Array();
            for (var key in employee_department_data) {
                department_name_to_id_mapping[employee_department_data[key]['name']] = key;
                department_names.push(employee_department_data[key]['name']);
            }
            department_names.sort(function (a, b) {
                return a.localeCompare(b);
            });
            var sorted_department_ids_by_name = new Array();
            for (var j = 0; j < department_names.length; j++) {
                sorted_department_ids_by_name.push(department_name_to_id_mapping[department_names[j]]);
            }

            var remove_row_block = ((this.user_group != 1) ? h('th.icon-trash.btn_remove.align_center', {attrs: {'line_ids': sorted_department_ids_by_name, 'rowspan': number_of_departments, title: _t("Pašalinti")}}, []) : '');
            var set_as_used_in_payroll_calculations = ''
            if (this.user_group > 3 && this.work_schedule_is_planned) {
                if (employee_used_in_planned) {
                    set_as_used_in_payroll_calculations = h('th.align_center', {attrs: {'line_ids': sorted_department_ids_by_name, 'rowspan': number_of_departments, title: _t("Planuojamas grafikas naudojamas")}}, [h('div.change_planned_schedule_single_lines_state', {attrs:{'style': 'background-color:green; border-radius: 50%;width:10px;height:10px;'}}, [])])
                } else {
                    set_as_used_in_payroll_calculations = h('th.align_center', {attrs: {'line_ids': sorted_department_ids_by_name, 'rowspan': number_of_departments, title: _t("Planuojamas grafikas nenaudojamas")}}, [h('div.change_planned_schedule_single_lines_state', {attrs:{'style': 'background-color:red; border-radius: 50%;width:10px;height:10px;'}}, [])])
                }
            }
            var etatas_block = h('th.align_center.o_schedule_etatas', {attrs: {title: _t('Etatas'), 'rowspan': number_of_departments}}, employee_etatas);

            var empl_total_sum_days = 0;
            var empl_total_sum_hours = 0;

            for (var j = 0; j < sorted_department_ids_by_name.length; j++) {
                var single_department_data = employee_department_data[sorted_department_ids_by_name[j]];
                var line_id = sorted_department_ids_by_name[j];
                if (department_line_totals[line_id] !== undefined) {
                    empl_total_sum_days += department_line_totals[line_id]['days']
                    empl_total_sum_hours += department_line_totals[line_id]['hours']
                }
            }

            var all_employee_department_totals_block =
            h(
                'th.o_schedule_total',
                {attrs: {rowspan: number_of_departments}},
                empl_total_sum_days + 'd. ' + this._format_float_to_hours(empl_total_sum_hours)
            );


            var department_lines = [];
            var department_index = 0;
            for (var j = 0; j < sorted_department_ids_by_name.length; j++) {
                if (department_index != 0){
                       employee_name_block='';
                       remove_row_block='';
                       set_as_used_in_payroll_calculations='';
                       etatas_block='';
                }
                var single_department_data = employee_department_data[sorted_department_ids_by_name[j]];
                var line_id = sorted_department_ids_by_name[j];
                var actual_department_id = parseInt(single_department_data['department_id']);
                var department_name = single_department_data['name'];
                var constraintStatus = single_department_data['constraint_status'];
                var department_state = single_department_data['state'];
                if (this.disable_state_changes) {
                    department_state = 'done'; // Force department state as done so that cells are not selectable
                }
                var constraintIcon = (this.user_group > 1) ? this.getConstraintIconCell(constraintStatus, line_id) : '';
                var job_or_department_block_title = ((single_department_filtered) ? _t('Pareigos') : _t('Padalinys'));
                var job_or_department_block_text = ((single_department_filtered) ? employee_job : department_name);
                var job_or_department_block = h('th.align_center.o_schedule_department', {attrs: {title: job_or_department_block_title}}, [job_or_department_block_text, h('br'), h('span.o_state_not_draft_info', state_name_mapping[department_state])]);

                var next_state_block = "";
                var prev_state_block = "";
                var divider_block = "";
                var show_super_actions = false;
                if ((this.user_group == 2 && this.user_department_ids.includes(actual_department_id)) || (this.user_group > 2)) {
                    show_super_actions = true;
                }
                if (this.disable_state_changes) {
                    show_super_actions = false;
                }
                if (show_super_actions) {
                    if (states_to_show_increase_state_button.includes(department_state)) {
                        var element_definition = 'span.' + validate_icons[department_state] + '.btn_increase_state.align_center';
                        next_state_block = h(element_definition, {attrs: {'line_id': line_id, 'department_state': department_state, title: _t("Patvirtinti eilutę")}})
                    }
                    if (states_to_show_decrease_state_button.includes(department_state)) {
                        var element_definition = 'span.' + unvalidate_icons[department_state] + '.btn_decrease_state.align_center';
                        prev_state_block = h(element_definition, {attrs: {'line_id': line_id, 'department_state': department_state, title: _t("Atitvirtinti eilutę")}})
                    }
                    var divider_block = h('br');
                    if (next_state_block == "") {
                        divider_block = '';
                    }
                }

                var department_line_change_state_block = ((this.user_group != 1) ? h('th.align_center.o_schedule_change_line_states', [
                    next_state_block,
                    divider_block,
                    prev_state_block,
                ]) : '');

                var department_days = new Array();
                var curr_col = 1;
                for (var k = 0; k < this.sorted_schedule_days.length; k++) {
                    var date_of_lines = this.sorted_schedule_days[k];
                    var department_day_data = single_department_data[date_of_lines];
                    var user_holiday = department_day_data['user_holiday'];
                    var has_contract = department_day_data['has_contract'];
                    var is_hidden = user_holiday && department_index != 0;
                    var lines = department_day_data['lines'];
                    var day_lines_formatted = "";
                    if (!user_holiday) {
                        if (has_contract) {
                            var line_index = 0;
                            for (var x = 0; x < lines.length; x++) {
                                if (line_index != 0) {
                                    day_lines_formatted += '\n';
                                }
                                day_lines_formatted += lines[x]['name'];
                                line_index++;
                            }
                        }
                    } else if (!is_hidden) {
                        day_lines_formatted += user_holiday['code'];
                    }
                    var is_today = ((day_print_data[date_of_lines]['is_today']) ? true : false);
                    var td_class = {
                        o_schedule_current: is_today,
                        o_schedule_weekend: weekend_dates.includes(date_of_lines),
                        o_schedule_national_holiday: national_holiday_dates.includes(date_of_lines),
                        o_schedule_submitted: ['confirmed'].includes(department_state),
                        o_schedule_validated: ['done'].includes(department_state),
                        o_schedule_user_holiday: (!(!user_holiday)),
                        o_schedule_draft: ['draft'].includes(department_state),
                        cell_no_contract: !has_contract,
                        o_schedule_invisible: is_hidden};

                    var td_attrs = {}
                    var td_rowspan = 1;
                    if (user_holiday && department_index == 0){
                       td_rowspan = number_of_departments;
                    }
                    if ((this.user_group == 1 && !this.force_show_edit_buttons) || !has_contract) {
                        td_class['o_unselected_cell'] = false;
                    } else if (this.user_group == 2 || this.force_show_edit_buttons){
                        if (this.user_department_ids.includes(actual_department_id) || user_holiday || this.force_show_edit_buttons) {
                            td_class['o_unselected_cell'] = true;
                        } else {
                            td_class['o_unselected_cell'] = false;
                        }
                    } else {
                        td_class['o_unselected_cell'] = true;
                    }
                    td_class['align_center'] = true;
                    td_class['o_schedule_time_cell'] = true;
                    td_attrs['att-day-id'] = department_day_data.id;
                    td_attrs['row'] = curr_row;
                    td_attrs['column'] = curr_col;
                    td_attrs['rowspan'] = td_rowspan;

                    var day_display_data =
                    h(
                        'td',
                        {
                            class: td_class,
                            attrs: td_attrs
                        },
                        day_lines_formatted
                    );
                    department_days.push(day_display_data);
                    curr_col++;
                }


                var dep_line_total_days = 0;
                var dep_line_total_hours = 0.0;
                if (department_line_totals[line_id] !== undefined) {
                    dep_line_total_days = department_line_totals[line_id]['days'];
                    dep_line_total_hours = department_line_totals[line_id]['hours'];
                }

                var department_totals_block =
                h(
                    'th.o_schedule_department_total.align_center',
                    {attrs: {title: "Padalinių sumos"}},
                    dep_line_total_days + 'd. ' + this._format_float_to_hours(dep_line_total_hours)
                );

                department_lines.push(
                    h(
                        'tr',
                        {
                            line_id: line_id,
                            class:
                            {
                                o_tr_schedule_confirmed: !(['draft'].includes(department_state))
                            }
                        },
                        [
                            employee_name_block,
                            remove_row_block,
                            set_as_used_in_payroll_calculations,
                            department_line_change_state_block,
                            job_or_department_block,
                            etatas_block,
                            constraintIcon
                        ].concat(
                            department_days
                        ).concat(
                        [
                            department_totals_block,
                            ((department_index == 0) ? all_employee_department_totals_block : ''),
                        ]
                        )

                    )
                );
                curr_row++;
                department_index++;
            }
            schedule_lines = schedule_lines.concat(department_lines);
        }

        return schedule_lines;
    },
    _get_empty_lines: function(schedule_data_length=0, day_print_data) {
        var lines_to_add = Math.max(4 - schedule_data_length, 0);
        if (lines_to_add <= 0){
            return [];
        }
        var th_data = [h('th', "\u00A0"),
                        h('th', "\u00A0"),
                        h('th', "\u00A0")];
        if (this.user_group != 1) {
            th_data = th_data.concat([h('th', "\u00A0"),h('th', "\u00A0"),h('th', "\u00A0")]);
        }
        if (this.user_group > 3 && this.work_schedule_is_planned) {
            th_data.push(h('th', "\u00A0"));
        }

        var empty_days = [];
        for (var i = 0; i < this.sorted_schedule_days.length; i++) {
            var key = this.sorted_schedule_days[i];
            var is_today = ((day_print_data[key]['is_today']) ? true : false);
            var is_weekend = ((day_print_data[key]['is_weekend']) ? true : false);
            var is_national_holiday = ((day_print_data[key]['is_national_holiday']) ? true : false);
            empty_days.push(
                h(
                    'td', {
                        class: {
                            o_schedule_current: is_today,
                            o_schedule_weekend: is_weekend,
                            o_schedule_national_holiday: is_national_holiday
                        }
                    },
                    []
                )
            );
        }

        var empty_lines = [];
        for (var i = 0; i < lines_to_add; i++) {
            empty_lines.push(
                h(
                    'tr.o_schedule_padding',
                    th_data
                    .concat(
                        empty_days,
                        [h('th.o_schedule_total', "\u00A0"), h('th.o_schedule_total', [])]
                    )
                )
            );
        }
        return empty_lines;
    },
    _table_base: function (day_print_data = {}, dates_totals = {}, month_validated = false, month_name = _t('Sausis'), single_department_filtered = false, single_department_name = false) {
        var self = this;
        var initial_colspan = 0;
        var thead_set_as_used = [];
        var tfoot_set_as_used = [];
        if (self.user_group != 1) {
            var thead_change_states = h('th.o_schedule_title_header');
            var thead_delete = h('th.o_schedule_title_header');
            var tfoot_delete = h('th.o_schedule_total');
            var add_record_button = [
                h('th.o_schedule_add_line.o_schedule_total',
                month_validated ? [] : [
                    h('button.btn.btn-sm.btn-primary.o_schedule_button_add', {
                        attrs: {type: 'button'}
                    },
                    self.add_label.toString())
                ])
            ];
            initial_colspan = 5;
        } else {
            var thead_change_states = [];
            var thead_delete = [];
            var tfoot_delete = [];
            var add_record_button = [h('th.o_schedule_total')];
            initial_colspan = 3;
        }
        if (self.user_group > 3 && this.work_schedule_is_planned) {
            thead_set_as_used = h('th.o_schedule_title_header');
            tfoot_set_as_used = h('th.o_schedule_total');
            initial_colspan += 1;
        }
        if (self.user_group > 1) {
            initial_colspan += 1;  // For the line constraint status indication
        }

        var day_colspan = this.sorted_schedule_days.length;
        var dep_col_name = ((single_department_filtered) ? _t("Pareigos") : _t("Padalinys"));

        var table_header_date_string = month_name + ', ' + this.year.toString();
        if (single_department_filtered) {
            table_header_date_string = single_department_name + ' - ' + table_header_date_string;
        }
        var scheduleConstraintsHeaderBlock = (self.user_group > 1) ? h('th.o_schedule_title_header.align_center.o_schedule_constraint_block', '') : '';
        var table_header = h('thead', [
            h('tr',
                [h('th.o_schedule_month_name.align_center', {attrs: {colspan: initial_colspan}}, table_header_date_string),
                 h('th.o_schedule_month_name.align_center', {attrs: {colspan: day_colspan}}, ''),
                 h('th.o_schedule_month_name.align_center', {attrs: {colspan: 2}}, '')]),
            h('tr',
                [h('th.o_schedule_title_header.align_center', _t('Darbuotojas'))]
                .concat(thead_delete)
                .concat(thead_set_as_used)
                .concat(thead_change_states)
                .concat(h('th.o_schedule_title_header.align_center.o_schedule_department.o_schedule_department', dep_col_name))
                .concat(h('th.o_schedule_title_header.align_center.o_schedule_etatas', _t('Etatas')))
                .concat(scheduleConstraintsHeaderBlock)
                .concat(
                    this.sorted_schedule_days.map(function(key, index) {
                        var is_today = ((day_print_data[key]['is_today']) ? true : false);
                        var is_weekend = ((day_print_data[key]['is_weekend']) ? true : false);
                        var is_national_holiday = ((day_print_data[key]['is_national_holiday']) ? true : false);
                        var print_str = day_print_data[key]['print_str']
                        return h(
                            'th.o_schedule_title_header',
                            {
                                class: {
                                    o_schedule_current: is_today,
                                    o_schedule_weekend: is_weekend,
                                    o_schedule_national_holiday: is_national_holiday,
                                    o_schedule_column: true
                                }
                            },
                            print_str
                        );
                    }),
                    [h('th.o_schedule_total', {attrs: {colspan: 2}}, _t("Viso"))]
            ))
        ]);
        var total_hours = 0.0;
        var total_days = 0;
        if (self.user_group != 1) {
            var tfoot_empty = add_record_button.concat(tfoot_delete).concat(tfoot_set_as_used).concat(tfoot_delete).concat(tfoot_delete).concat(h('th.o_schedule_total', _t("Viso"))).concat(tfoot_delete)
        } else {
            var tfoot_empty = add_record_button.concat(h('th.o_schedule_total')).concat(tfoot_delete).concat(tfoot_set_as_used).concat(tfoot_delete).concat(h('th.o_schedule_total', _t("Viso"))).concat(tfoot_delete)
        }
        var table_footer = h('tfoot', [
            h('tr',
                tfoot_empty
                .concat(
                    this.sorted_schedule_days.map(function(key, index) {
                        var hours = (dates_totals && dates_totals[key]) ? dates_totals[key]['hours'] : 0.0;
                        var days = (dates_totals && dates_totals[key]) ? dates_totals[key]['days'] : 0;
                        total_hours += hours
                        total_days += days
                        return h('th.o_schedule_total', {}, self._format_float_to_hours(hours));
                    }),
                h('th.o_schedule_total.o_schedule_bold', total_days + 'd.'),
                h('th.o_schedule_total.o_schedule_bold', self._format_float_to_hours(total_hours))
            ))
        ]);

        return h('div.o_view_schedule', [
            h('table.table.table-condensed.table-responsive.table-striped', [
                table_header,
                table_footer,
            ])
        ]);
    },
    _format_float_to_hours: function(hours) {
        if (isNaN(hours)) return "";
        hours = parseFloat(hours).toFixed(2);
        var v_floor = Math.floor(hours);
        var sub = hours - v_floor;
        var h = Math.round(v_floor);
        var m = Math.round(sub * 60);
        if (h < 10){
            h = "0" + h;
        }
        if (m < 10){
            m = "0" + m;
        }
        var str = h + ":" + m
        return str;
    },
    _render_dynamic_buttons: function(dynamic_buttons_data){
        for (var k in dynamic_buttons_data){
            if (dynamic_buttons_data.hasOwnProperty(k)) {
                var el_selector = ".o_schedule_" + k;
                var elements = $(el_selector);
                if (dynamic_buttons_data[k]){
                    elements.toggleClass("o_schedule_invisible", false);
                }
                else {
                    elements.toggleClass("o_schedule_invisible", true);
                }
            }
        }
    },
    display_delete_button: function(){
        var day_ids = this._navigation.get_selected_ids()
        if (day_ids === undefined || day_ids.length == 0){
            $('#delete_time_button').removeClass("o_schedule_invisible");
            $('#delete_time_button').addClass("o_schedule_invisible");
        } else {
            $('#delete_time_button').removeClass("o_schedule_invisible");
        }
    },
    get_full_context: function (ctx) {
        var c = this._model.context(this.get('context'));
        if (this.get('pagination_context')) {
            c.add(this.get('pagination_context'));
        }
        if (ctx) {
            c.add(ctx);
        }
        if (this.default_month && !c.eval().default_month){
            c.add({'default_month': this.default_month});
        }
        if (this.default_year && !c.eval().default_year){
            c.add({'default_year': this.default_year});
        }
        if (this.month && !c.eval().month){
            c.add({'month': this.month});
        }
        if (this.year && !c.eval().year){
            c.add({'year': this.year});
        }
        if (this.work_schedule_id && !c.eval().work_schedule_id) {
            c.add({'work_schedule_id': this.work_schedule_id});
        }
        return c;
    },
    do_show: function() {
        //!IMPORTANT! THIS PUSHES STATE AFTER ACTION IS OPENED, WHEN WRITING CUSTOM VIEWS, YOU SHOULD INCLUDE THIS FUNCTION
        //This renders the URL and redraws (left) robo menu
        this.do_push_state({});
        return this._super();
    },
    do_search: function (domain, context, groupby) {
        this.domain = domain;
        this.current_min = 1;
        return this._fetch();
    },
    _fetch: function () {
        if (!this.fields_view) {
            return;
        }
        var _this = this;
        this._enqueue(function () {
            _this.left_scroll_pos = $('.o_view_schedule').scrollLeft();
            _this.top_scroll_pos = $('.o_view_schedule').scrollTop();
            return (new Model('work.schedule.line')).call('read_schedule', {
                year: _this.year,
                month: _this.month,
                work_schedule_id: _this.work_schedule_id,
                first_fetch: _this.first_fetch,
                extra_domain: _this.domain,
                offset:_this.current_min-1,
                limit:_this._limit,
            }).then(function (results) {
                _this.set('schedule_data', results);
                _this.first_fetch = false;
                _this.selection_frozen = false;
            });
        });
    },

    _enqueue: function (fn) {
        // We only want a single fetch being performed at any time (because
        // there's really no point in performing 5 fetches concurrently just
        // because the user has just edited 5 records), utils.Mutex does that
        // fine, *however* we don't actually care about all the fetches, if
        // we're enqueuing fetch n while fetch n-1 is waiting, we can just
        // drop the older one, it's only going to delay the currently
        // useful and interesting job.
        //
        // So when requesting a fetch
        // * if there's no request waiting on the mutex (for a fetch to come
        //   back) set the new request waiting and queue up a fetch on the
        //   mutex
        // * if there is already a request waiting (and thus an enqueued fetch
        //   on the mutex) just replace the old request, so it'll get taken up
        //   by the enqueued fetch eventually
        var _this = this;
        if (this._in_waiting) {
            // if there's already a query waiting for a slot, drop it and replace
            // it by the new updated query
            this._in_waiting = fn;
        } else {
            // if there's no query waiting for a slot, add the current one and
            // enqueue a fetch job
            this._in_waiting = fn;
            this._fetch_mutex.exec(function () {
                var fn = _this._in_waiting;
                _this._in_waiting = null;

                return fn();
            })
        }

    },
    call_multiple_line_action: function(action) {
        var year = this.year;
        var month = this.month;
        var domain = this.domain;
        var work_schedule_id = this.work_schedule_id;
        return (new Model('work.schedule.line')).call('execute_multiple_line_action', [action, year, month, domain, work_schedule_id]);
    },
    render_buttons: function ($node) {
        this._navigation = new ScheduleHeader(
            this,
            this.fields_view.arch.children
                .filter(function (c) { return c.tag === 'button'; })
                .map(function (c) { return c.attrs; }),
                this.department
        );
        var self = this;
        self._navigation.appendTo($node);
        return $.when(this._navigation.ready_dropdown_data).then(function(){
            var selection_html = QWeb.render('schedule.selection', {'widget': self._navigation});
            self._navigation.$el.append(selection_html);
            var $selection = self._navigation.$el.find('select');
            $selection.val(self.work_schedule_id);
            if (self.user_group < 4 || self.user_group == undefined) {
                $('#schedule_selector_label').parent().hide();
            } else {
                $('#schedule_selector_label').parent().show();
            }
            self._navigation.fix_schedule_header_style();

            $selection.on('change', self, function (e) {
                self.work_schedule_id = parseInt($(e.target).find(':selected').val());
                self._fetch();
                });
            });
        },
    _update_month_labels: function() {
        //Set month labels
        var curr_month = this.month;
        var curr_year = this.year;
        var this_month = new Date(curr_year, curr_month-1, 1);
        var next_month = new Date(this_month.setMonth(this_month.getMonth()+1));
        var previous_month = new Date(this_month.setMonth(this_month.getMonth()-2));
        var month_names = [
            _t('January'), _t('February'), _t('March'), _t('April'), _t('May'), _t('June'), _t('July'), _t('August'),
            _t('September'), _t('October'), _t('November'), _t('December')
        ];
        $( '.schedule-selection-and-month-box .next-month-text' ).text(month_names[next_month.getMonth()]);
        $( '.schedule-selection-and-month-box .previous-month-text' ).text(month_names[previous_month.getMonth()]);
    },
    render_pager: function($node, options) {
        if (!this.pager && this.options.pager) {
            this.pager = new Pager(this, 100, 1, this._limit || 20, options);
            this.pager.appendTo($node || this.options.$pager);

            this.pager.on('pager_changed', this, function (new_state) {
                var self = this;
                var limit_changed = (this._limit !== new_state.limit);

                this._limit = new_state.limit;
                this.current_min = new_state.current_min;
                this._fetch();
            });
        }
    },
    update_pager: function() {
        if (this.pager) {
            this.pager.update_state({size: this.dataset_length, current_min: this.current_min});
        }
    },
});
core.view_registry.add('workschedule', ScheduleView);

var ScheduleHeader = Widget.extend({
    template: 'schedule.ScheduleController',
    events: {
        'click .schedule_arrow_previous': function (e) {
            e.stopPropagation();
            var parent = this.getParent();
            var curr_month = parent.month;
            var curr_year = parent.year;
            if (curr_month == 1) {
                parent.year = curr_year-1;
                parent.month = 12;
            }
            else {
                parent.month = curr_month-1;
            }
            parent.current_min = 1;
            parent.work_schedule_id = false;
            parent._fetch();
        },
        'click .schedule_arrow_next': function (e) {
            e.stopPropagation();
            var parent = this.getParent();
            var curr_month = parent.month;
            var curr_year = parent.year;
            if (curr_month == 12) {
                parent.year = curr_year+1;
                parent.month = 1;
            }
            else {
                parent.month = curr_month+1;
            }
            parent.current_min = 1;
            parent.work_schedule_id = false;
            parent._fetch();
        },
        'click #main_setter': "open_main_setter_wizard",
        'click #overtime_setter': "open_overtime_setter_wizard",
        'click #absence_setter': "open_absence_setter_wizard",
        'click #holidays_setter': "open_holidays_setter_wizard",
        'click #delete_time_button': "call_delete_lines",
        'click #execute_validate': "call_set_validated",
        'click #execute_confirm': "call_set_confirmed",
        'click #execute_action_done': "call_set_done",
        'click #execute_cancel_validate': "call_cancel_validated",
        'click #execute_cancel_confirm': "call_cancel_confirmed",
        'click #execute_action_cancel_done': "call_cancel_done",
        'click #execute_action_export': "open_export_wizard",
        'click #execute_action_set_all_as_used': "call_set_all_as_used",
        'click #execute_action_set_all_as_unused': "call_set_all_as_unused",
        'click #execute_action_allow_accountant_can_change': "allow_accountant_change",
        'click #execute_action_allow_accountant_cant_change': "allow_accountant_change",
        'click #go_to_ziniarastis': "go_to_ziniarastis",
        'click #go_to_date': "open_go_to_date_wizard",
        'click #execute_action_check_constraints': "call_check_constraints",
        'click #execute_action_check_failed_constraints': "call_check_failed_constraints",
    },
    set_dropdown_data: function(){
        var element_names = [];
        var i;
        var dropdowns = this.getParent().fields_view.arch.children
                .filter(function (c) { return c.tag === 'field' && c.attrs['type'] === 'dropdown' ;})
                .map(function (c) { return c.attrs; });
        for (i = 0; i < dropdowns.length; i++) {
            var dropdown_element = dropdowns[i];
            element_names.push(dropdown_element['name']);
        }
        var model_name = this.getParent()._model.name;
//        this.ready_dropdown_data = $.Deferred();
        var self = this;
        this._dropdown_fields = {};
        new Model(model_name).call("fields_get", [element_names]).then(function(fields) {
            for (var field_name in fields) {
                if (fields.hasOwnProperty(field_name))
                    var field = fields[field_name];
                    if (field.type === 'many2one'){
                        var posible_values = new Model(field.relation).call('search_read', [[]]).then(function(records){
                            var selections = [];
                            records.forEach(function(record){
                                if (record.schedule_type != 'other') {
                                    selections.push([record.id, _t(record.display_name)]);
                                }
                            });
                            self._dropdown_fields['name'] = {'options': selections};
                            self.ready_dropdown_data.resolve();  // only works when exactly one dropdown
                        });
                    }
                }
            });
    },
    init: function (parent, buttons, department) {
        this.ready_dropdown_data = $.Deferred();
        this._super.apply(this, arguments);
        this._buttons = buttons;
        this.department = false;
        if (department != false) {
            this.department = department;
        }
        this.set_dropdown_data();
    },
    start: function () {
        this._super();
        var self = this;
        var def2 = this.ready_dropdown_data;
    },
    destroy: function(){
        var self = this;
        $.when(this._super()).then(function(){
            self.reset_schedule_header_style();
        });
    },
    get_selected_ids: function(){
        var elements = $("td.o_selected_cell");
        var schedule_day_ids = [];
        elements.each(function(indx, el){
            var day_id = $(el).attr('att-day-id');
            day_id = parseInt(day_id);
            schedule_day_ids.push(day_id);
        });
        return schedule_day_ids;
    },
    open_setter_wizard: function(model_name, day_ids, is_absence_setter=false) {
        var self = this;
        self.selection_frozen = true;
        return (new Model('work.schedule.day')).call('get_wizard_view_id', [model_name]).then(function(view_id){
                self.do_action({
                    type: 'ir.actions.act_window',
                    view_id: view_id,
                    res_model: model_name,
                    target: 'new',
                    views: [[view_id, 'form']],
                    view_type: 'form',
                    view_mode: 'form'
                },
                {
                    additional_context:{
                      active_ids: day_ids,
                      is_absence_setter: is_absence_setter
                    },
                   on_close: function() {
                        self.getParent()._fetch()
                    }
                });
            });
    },
    open_export_wizard: function(el) {
        var self = this;
        var columns = $("th.o_schedule_title_header.o_schedule_column");
        var parent = self.getParent()
        var month = parent.month;
        var year = parent.year;
        var work_schedule_id = parent.work_schedule_id;
        var department = this.$el.find('select').val()
        return (new Model('schedule.export.wizard')).call('get_wizard_view_id').then(function(view_id){
                self.do_action({
                    type: 'ir.actions.act_window',
                    view_id: 'schedule_export_wizard_form',
                    res_model: 'schedule.export.wizard',
                    target: 'new',
                    views: [[view_id, 'form']],
                    view_type: 'form',
                    view_mode: 'form'
                },
                {
                    additional_context:{
                        sched_month: month,
                        sched_year: year,
                        department: department,
                        work_schedule_id: work_schedule_id
                    },
                })
                });
    },
    go_to_ziniarastis: function(el) {
        var self = this;
        var parent = self.getParent()
        var month = parent.month;
        var year = parent.year;
        return (new Model('work.schedule.line')).call('go_to_ziniarastis', [year, month]).then(function(action){
            self.do_action(action);
            self.reset_schedule_header_style();
        });
    },
    fix_schedule_header_style: function() {
//        $( '.o_control_panel .o_cp_left' ).width('90%');
//        $( '.o_control_panel .o_cp_right' ).width('10%');
        $( '.o_control_panel .o_cp_right' ).addClass('right-pager-custom-class');
        $( '.o_control_panel .o_cp_right .o_cp_pager' ).addClass('right-pager-div-custom-class');

    },
    reset_schedule_header_style: function() {
//        $( '.o_control_panel .o_cp_left' ).css('width', '');
//        $( '.o_control_panel .o_cp_right' ).css('width', '')  ;
        $( '.o_control_panel .o_cp_right' ).removeClass('right-pager-div-custom-class', '');
        $( '.o_control_panel .o_cp_right .o_cp_pager' ).removeClass('right-pager-div-custom-class', '');
    },
    allow_accountant_change: function(el) {
        var self = this;
        var parent = self.getParent()
        var month = parent.month;
        var year = parent.year;
        return (new Model('work.schedule.line')).call('action_toggle_allow_accountant_change', [year, month]).then(function (a) {
            self.getParent()._fetch();
        });
    },
    open_main_setter_wizard: function(el){
        var day_ids = this.get_selected_ids();
        if (day_ids === undefined || day_ids.length == 0){
            return;
        };
        return this.open_setter_wizard('main.schedule.setter', day_ids);
//        V2 not reset view after closing wizard but reset after changes MOVEDTODO
    },
    open_overtime_setter_wizard: function(el){
        var day_ids = this.get_selected_ids();
        if (day_ids === undefined || day_ids.length == 0){
            return;
        };
        var elements = $("td.o_selected_cell.o_schedule_user_holiday");
        if (elements.length > 0) {
            this.do_warn(_t('Kaikurie įrašai yra atostogos'), _t('Prašome pirma pakeisti atostogas į darbo laiką ir tuomet nustatyti viršvalandžius'));
            return;
        }
        return this.open_setter_wizard('overtime.schedule.setter', day_ids);
    },
    open_absence_setter_wizard: function(el){
        var day_ids = this.get_selected_ids();
        if (day_ids === undefined || day_ids.length == 0){
            return;
        };
        return this.open_setter_wizard('holidays.schedule.setter', day_ids, true);
    },
    open_holidays_setter_wizard: function(el){
        var day_ids = this.get_selected_ids();
        if (day_ids === undefined || day_ids.length == 0){
            return;
        };
        return this.open_setter_wizard('holidays.schedule.setter', day_ids);
    },
    call_delete_lines: function(el) {
        var day_ids = this.get_selected_ids();
        var self = this;
        if (day_ids === undefined || day_ids.length == 0){
            return;
        };
        if (confirm(_t('Ar tikrai norite ištrinti pasirinktus įrašus?'))) {
            return (new Model('work.schedule.line')).call('unlink_all_day_lines', [day_ids]).then(function() {
                self.getParent()._fetch();
            });
        } else {
            return;
        }
    },
    open_go_to_date_wizard: function(el){
        var self = this;
        self.selection_frozen = true;
        return (new Model('work.schedule.day')).call('get_wizard_view_id', ['jump.to.date.wizard']).then(function(view_id){
            self.do_action({
                type: 'ir.actions.act_window',
                view_id: view_id,
                res_model: 'jump.to.date.wizard',
                target: 'new',
                views: [[view_id, 'form']],
                view_type: 'form',
                view_mode: 'form'
            });
        });
    },
    call_check_constraints: function(el){
        var self = this;
        $.when(this.getParent().call_multiple_line_action('call_check_constraints')).then(function (action) {
            if (action) {
                return self.do_action(action);
            }
        });
    },
    call_check_failed_constraints: function(el){
        return this.getParent().call_multiple_line_action('call_check_failed_constraints');
    },
    call_set_validated: function(el){
        var self = this;
        var user_group = this.getParent().user_group;
        var allow_bypass_constraints = this.getParent().allow_bypass_constraints;
        var confirm_msg = false;
        if (user_group > 3) {
            confirm_msg = _t("Kadangi turite buhalterio teises, grafiko apribojimai nebus tikrinami.\nJuos galima patikrinti paspaudus mygtuką 'Patikrinti grafikus'\n\nPatvirtinkite, jog norite patvirtinti grafiką, nepaisant apribojimų")
        }
        else if (allow_bypass_constraints) {
            confirm_msg = _t("Graifiko apribojimų tikrinimas yra išjungtas, todėl grafikai nebus tikrinami.\nGrafikus galima patikrinti paspaudus mygtuką 'Patikrinti grafikus'.\n\nPatvirtinkite, jog norite patvirtinti grafiką, nepaisant apribojimų\n(Tvirtindami grafikus prisiimate atsakomybę už nekorektiškai sudarytus grafikus)")
        }

        if (confirm_msg) {
            if (confirm(confirm_msg)) {
                return this.getParent().call_multiple_line_action('call_set_validated').then(function(){self.getParent()._fetch()});
            }
        } else {
            return this.getParent().call_multiple_line_action('call_set_validated').then(function(){self.getParent()._fetch()});
        }
    },
    call_set_confirmed: function(el){
    var self = this;
        return this.getParent().call_multiple_line_action('call_set_confirmed').then(function(){self.getParent()._fetch()});
    },
    call_set_done: function(el){
        var self = this;
        return this.getParent().call_multiple_line_action('call_set_done').then(function(){self.getParent()._fetch()});

    },
    call_cancel_validated: function(el){
        var self = this;
        return this.getParent().call_multiple_line_action('call_cancel_validated').then(function(){self.getParent()._fetch()});
    },
    call_set_all_as_used: function(el){
        var self = this;
        return $.when(
            confirm(_t("Please confirm that you really want to set all planned lines to be used in payroll calculations"))
        ).then(
            self.getParent().call_multiple_line_action('call_set_all_as_used')
        ).then(
            function(){
                self.getParent()._fetch()
            }
        );
    },
    call_set_all_as_unused: function(el){
        var self = this;
        return $.when(
            confirm(_t("Please confirm that you really want to set all planned lines not to be used in payroll calculations"))
        ).then(
            self.getParent().call_multiple_line_action('call_set_all_as_unused')
        ).then(
            function(){
                self.getParent()._fetch()
            }
        );
    },
    call_cancel_confirmed: function(el){
        var self = this;
        return this.getParent().call_multiple_line_action('call_cancel_confirmed').then(function(){self.getParent()._fetch()});
    },
    call_cancel_done: function(el){
        var self = this;
        return this.getParent().call_multiple_line_action('call_cancel_done').then(function(){self.getParent()._fetch()});
    },
});
return {
    ScheduleView: ScheduleView,
}

});
