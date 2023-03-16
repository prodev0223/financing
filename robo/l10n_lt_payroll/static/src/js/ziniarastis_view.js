robo.define('l10n_lt_payroll.action_manager', function(require) {
  var action_manager = require('web.ActionManager');
  var ActionManagerPayrollExtend = action_manager.include({
    _act_wizard_move_id: function(action, options, direction){
        var current_id = this.dialog_widget.action.context.current_id;
        var ids = this.dialog_widget.action.context.day_ids;
        var index = ids.indexOf(current_id);
        var id;

        if (direction ==='next') {
            if (~index && index + 1 < ids.length) {
                id = ids[index + 1];
            }
        }
        else if (direction === 'prev'){
            if (~index && index - 1 >= 0){
              id = ids[index-1];
            }
        }
        if (!this.dialog) {
            options.on_close();
        }
        this.go_fetch_boy = false;
        this.dialog_stop();
        if (id) {
          this.inner_widget.active_view.controller.open_other_day(id);
        }
        return $.when();
    },
    ir_actions_act_reload_wizard_next_id: function (action, options) {
        this._act_wizard_move_id(action, options, 'next');
    },
    ir_actions_act_reload_wizard_prev_id: function (action, options) {
        this._act_wizard_move_id(action, options, 'prev');
    },
  });
  return ActionManagerPayrollExtend;
});

$( document ).ready(function(){
	$(document).click(function(elem){
	    var closest_td = $(elem.target).closest("td");
	    if (!$(elem.target).is("tbody") && !$(elem.target).is("tr") && !$(elem.target).hasClass("o_selected_cell") && !$(elem.target).hasClass("o_unselected_cell") && !$(elem.target).hasClass("o_schedule_column") && !$(elem.target).hasClass("o_schedule_department") && !$(elem.target).hasClass("btn-sm") && !$(closest_td).hasClass("o_selected_cell") && !$(closest_td).hasClass("o_unselected_cell")) {
            $(".o_selected_cell").each(function(i, element) {
                $(element).removeClass("o_selected_cell");
                $(element).addClass("o_unselected_cell");
            });
            $('#ziniarastis_setter_group').toggleClass("o_ziniarastis_invisible", true);
        }
    });
});

var mouseDown = false;
$(document).mousedown(function() {
    mouseDown = true;
}).mouseup(function() {
    mouseDown = false;
});

robo.define('ziniarastis', function (require) {
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
var ListView = require('web.ListView');
var QWeb = core.qweb;
var Pager = require('web.Pager');

var patch = require('snabbdom.patch');
var h = require('snabbdom.h');

var _t = core._t;
var _lt = core._lt;


var ZiniarastisView = View.extend({
    icon: 'fa-th',
    display_name: _lt("Žiniaraštis"),
    view_type: 'ziniarastis',
    multi_record: false,
    sidebar: false,
    editable: true,
    pager: false,
    events: {
        "mouseenter .o_selected_cell": "_mouse_enter",
        "mouseenter .o_unselected_cell": "_mouse_enter",
        "mouseleave .o_selected_cell": "_mouse_leave",
        "mouseleave .o_unselected_cell": "_mouse_leave",
        'mousedown .o_selected_cell': "_mouse_down",
        'mouseup .o_selected_cell': "_mouse_up",
        'mousedown .o_unselected_cell': "_mouse_down",
        'mouseup .o_unselected_cell': "_mouse_up",
        'click th.change_state_to_done': "_confirm_line",
        'click th.change_state_to_draft': "_cancel_line",
        'click th.refresh_button': "_refresh_line",
        'click .ziniarastis_day': "_open_ziniarastis_day_wizard",
        'click .employee': "_open_employee_backend_view",
        'click .o_unselected_cell': function(e){
            if (!this.selection_frozen) {
                if (!this.prevent_unselect) {
                    var $target = $(e.target).closest('td');
                    $target.toggleClass('o_unselected_cell', false);
                    $target.toggleClass('o_selected_cell', true);
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
        'click .o_ziniarastis_contract': function(e){
            if (!this.selection_frozen) {
                var $target = $(e.target).closest('tr');
                var any_cells_selected = false;
                $target.find('td').each(function(){
                    if ($(this).hasClass('o_selected_cell')) {
                        any_cells_selected = true;
                    }
                });
                var td_class = ((any_cells_selected) ? 'o_selected_cell' : 'o_unselected_cell');
                $target.find('td').each(function(){
                    if ($(this).hasClass(td_class)) {
                        $(this).toggleClass('o_unselected_cell');
                        $(this).toggleClass('o_selected_cell');
                    }
                });
            }
            this.display_delete_button();
        },
        'click .o_ziniarastis_column': function(e){
            if (!this.selection_frozen) {
                var $target = $(e.target).closest('th');
                var th_index = 6;
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
                    if (sm_square && sm_square.hasClass(td_class)){
                        sm_square.toggleClass('o_selected_cell');
                        sm_square.toggleClass('o_unselected_cell');
                    }
                });
            }
            this.display_delete_button();
        },
    },
    open_other_day: function(id){
        var $find_el = this.$('.ziniarastis_day[day_id='+id+']');
        if ($find_el.length){
            this.selection_frozen = false;
            $($find_el[0]).trigger('click');
        }
    },
    init: function (parent, dataset) {
        this._super.apply(this, arguments);
        this._model = dataset._model;
        this.go_fetch_boy = true;
        this.left_scroll_pos= 0.0;
        this.month = false;
        this.year = false;
        this.options.editable = true;
        this.top_scroll_pos = 0.0;
        this._in_waiting = null;
        this._fetch_mutex = new utils.Mutex();
        this.table_shown = 'main';
        this.mouse_down_start_col = false;
        this.mouse_down_start_row = false;
        this.prevent_unselect = false;
        this.line_ids = null;
        this._limit = 50;
        this.current_min = 1;

        this.on('change:ziniarastis_data', this, this._render);
        this.ziniarastis_period_id = false;
        this.selection_frozen = true;
        this.domain = [];

        if (dataset.context.dataset_ids && dataset.context.dataset_index) {
            this.dataset.ids = dataset.context.dataset_ids;
            this.dataset.index = dataset.context.dataset_index;
        }

    },
    start: function () {
        this._state = document.createElement('div');
        this.el.appendChild(this._state);
        this._render();
        return $.when();
    },
    _archnodes_of_type: function (type) {
        return _.filter(this.fields_view.arch.children, function (c) {
            return c.tag === 'field' && c.attrs.type === type;
        });
    },
    _make_field: function (name, arch_f) {
        var descr = this.fields_view.fields[name];
        var Cls = fields[descr.type]
               || (arch_f && fields[arch_f.attrs.widget])
               || Field;

        return new Cls(name, descr, arch_f);
    },
    _fields_of_type: function (type) {
        return _(this._archnodes_of_type(type)).map(function (arch_f) {
            var name = arch_f.attrs.name;
            return this._make_field(name, arch_f);
        }.bind(this));
    },
    _mouse_enter: function(event) {
        var $target = $(event.target).closest('td');
        if (mouseDown && !this.selection_frozen) {
            var row_n = $target.attr('row');
            var col_n = $target.attr('column');
            if (this.mouse_down_start_col != false && this.mouse_down_start_row != false) {
                this.mark_selected_days(this.mouse_down_start_col, this.mouse_down_start_row, col_n, row_n, event.ctrlKey);
            }
        }
    },
    _mouse_leave: function(event) {
        var $target = $(event.target).closest('td');
        if (!this.selection_frozen) {
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
        if (!this.selection_frozen) {
            this.mouse_down_start_col = false;
            this.mouse_down_start_row = false;
            if ($target.attr('column') != false && $target.attr('row') != false) {
                this.mouse_down_start_col = $target.attr('column');
                this.mouse_down_start_row = $target.attr('row');
            }
        }
        this.display_delete_button();
    },
    _mouse_up: function(event) {
        var $target = $(event.target).closest('td');
        if (!this.selection_frozen) {
            var is_selected = $target.hasClass('o_selected_cell');
            var row_n = $target.attr('row');
            var col_n = $target.attr('column');
            if (this.mouse_down_start_col && this.mouse_down_start_row) {
                this.mark_selected_days(this.mouse_down_start_col, this.mouse_down_start_row, col_n, row_n, event.ctrlKey);
            }
            this.mouse_down_start_col = false;
            this.mouse_down_start_row = false;
            if (!is_selected) this.prevent_unselect = true;
        }
        this.display_delete_button();
    },
    _call_line_method: function(event, method_to_call) {
        if (!this.selection_frozen) {
            var $target = $(event.target).closest('th');
            var self = this;
            self.selection_frozen = true;
            var date_from = $target.attr('date_from');
            var date_to = $target.attr('date_to');
            var contract_id = parseInt($target.attr('contract_id'));
            return (new Model('ziniarastis.period')).call(method_to_call, [date_from, date_to, contract_id]).then(function() {
                self._fetch();
            });
        }
    },
    _switch_table: function(event) {
        var the_target = $('i#button_switch_table');
        if (this.table_shown == 'main') {
            this.table_shown = 'other';
            the_target.toggleClass('fa-toggle-on', false);
            the_target.toggleClass('fa-toggle-off', true);
        } else {
            this.table_shown = 'main';
            the_target.toggleClass('fa-toggle-off', false);
            the_target.toggleClass('fa-toggle-on', true);
        }
        return this._render();
    },
    _open_employee_backend_view: function(event) {
        var $target = $(event.target).closest('th.employee');
        var empl_id = $target.attr('employee_id');
        var self = this;
        if (empl_id) {
            return (new Model('ziniarastis.period')).call('get_back_end_empl_view', [empl_id]).then(function(action){
                self.do_action(action);
            });
        }
    },
    _open_ziniarastis_day_wizard: function(event) {
        if (!this.selection_frozen) {
            var $target = $(event.target).closest('td');
            var self = this;
            self.selection_frozen = true;
            var day_id = parseInt($target.attr(("day_id")));
            var day_ids = [];
            $target.prevAll('.ziniarastis_day').each(function(indx, el){
                day_ids.push(parseInt(el.attributes.day_id.value));
            });
            day_ids.reverse();
            day_ids.push(day_id);
            $target.nextAll('.ziniarastis_day').each(function(indx, el){
                day_ids.push(parseInt(el.attributes.day_id.value));
            });
            return (new Model('ziniarastis.day')).call('get_wizard_view_id', []).then(function(view_id){
                self.do_action({
                    type: 'ir.actions.act_window',
                    view_id: view_id,
                    res_model: "ziniarastis.day",
                    res_id: day_id,
                    target: 'new',
                    views: [[view_id, 'form']],
                    view_type: 'form',
                    view_mode: 'form',
                },
                {
                    additional_context:{
                      day_ids: day_ids,
                      current_id: day_id,
                    },
                    on_close: _.bind(function(){
                        if (self.go_fetch_boy) {
                            self._fetch();
                        } else {
                            self.go_fetch_boy = true;
                        }
                    }, self),
                });
            });
        }
    },
    _confirm_line: function(event) {
        return this._call_line_method(event, 'call_button_single_done')
    },
    _cancel_line: function(event) {
        return this._call_line_method(event, 'cancel_done_line')
    },
    _refresh_line: function(event) {
        return this._call_line_method(event, 'refresh_line')
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
            this.unmark_selected_days();
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
                    $(str).removeClass("o_unselected_cell");
                    $(str).addClass("o_selected_cell");
                }
            }
        }
        this.display_delete_button();
    },
    _render: function () {
        var _this = this;
        this.selection_frozen = true;
        var columns, vnode, ziniarastis, totals;
        var ziniarastis_data = this.get('ziniarastis_data') || false;
        if (ziniarastis_data && ziniarastis_data.header_data.date_data) {
            this.dataset_length = ziniarastis_data['total_number_of_lines'] || 0;
            this.update_pager();
            var header_data = ziniarastis_data.header_data;
            var main_data = ziniarastis_data.main_data;
            var button_data = ziniarastis_data.button_data;
            this.ziniarastis_period_id = ziniarastis_data.ziniarastis_period_id;
            this.year = ziniarastis_data.year;
            this.month = ziniarastis_data.month;
            this._render_dynamic_buttons(button_data)
            this.line_ids = ziniarastis_data.line_ids;
            var is_draft = ziniarastis_data.ziniarastis_state == 'draft';
            var ziniarastis_state = ((is_draft) ? _t('Juodraštis') : _t('Patvirtinta'))
            var ziniarastis_state_string = ziniarastis_data.ziniarastis_state_title;
            $('span#ziniarastis_state').html(ziniarastis_state_string);
            var is_busy = ziniarastis_data.busy;
            var busy_el = $('i#ziniarastis_busy_icon');
            if (is_busy) {
                busy_el.toggleClass("o_ziniarastis_invisible", false);
            } else {
                busy_el.toggleClass("o_ziniarastis_invisible", true);
            }
            var last_confirm_msg = ziniarastis_data.last_confirm_fail_message;
            var last_confirm_msg_el = $('span#confirm_msg');
            if (is_draft && last_confirm_msg) {
                last_confirm_msg_el.html(last_confirm_msg);
                last_confirm_msg_el.toggleClass("o_ziniarastis_invisible", false);
            } else {
                last_confirm_msg_el.toggleClass("o_ziniarastis_invisible", true);
            }

            vnode = this._table_base(header_data);
            var ziniarastis_body = vnode.children[0].children;
            var ziniarastis_data_lines = [];
            if (ziniarastis_data.main_data) {
                ziniarastis_data_lines = this._render_ziniarastis_lines(main_data, header_data);
            }
            ziniarastis_body.push(
                h('tbody', ziniarastis_data_lines)
            );
            this._state = patch(_this._state, vnode);
        }

        setTimeout(function () {
            var row_headers = _this.el.querySelectorAll('tbody th:first-child div');
            _this._state.key = Math.random();
            var freeze_left = 6;
            if ($(window).width() < 800) {
                freeze_left = 0;
            }

            _this.$('table').tableHeadFixer({'z-index' : 99, left: freeze_left, head: true, 'header-z-index': 99});
            _this.$('table').css({'border-collapse': 'collapse'});
            _this.$el.css({height: '100%'});
            _this.$('.o_view_ziniarastis').css({height: '100%'});

            for (var k = 0; k < row_headers.length; k++) {
                var header = row_headers[k];
                if (header.scrollWidth > header.clientWidth) {
                    $(header).addClass('overflow');
                }
            }
//            if (_this.left_scroll_pos !== false && _this.top_scroll_pos !== false) {
////                $('.o_view_ziniarastis').scrollTo(_this.left_scroll_pos, _this.top_scroll_pos);
//                _this.left_scroll_pos = false;
//                _this.top_scroll_pos = false;
//            }
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
    _render_ziniarastis_lines: function (data, header_data) {
        var ziniarastis_lines = [];
        if (!(Object.keys(data).length > 0)) {
            return ziniarastis_lines; //No data exists
        }

        var day_data = header_data.date_data;
        var day_data_dict = {};
        for (var day_data_index in day_data) {
            var day_data_line = day_data[day_data_index];
            day_data_dict[day_data_line.date] = {
                'is_national_holiday': day_data_line.is_national_holiday,
                'is_weekend': day_data_line.is_weekend,
                'is_today': day_data_line.is_today,
            }
        }
        var sum_totals = {
            'days_total': 0.0,
            'hours_worked': 0.0,
            'hours_night': 0.0,
            'hours_overtime': 0.0,
            'hours_not_regular': 0.0,
            'hours_watch_home': 0.0,
            'hours_watch_work': 0.0,
            'hours_weekends': 0.0,
            'hours_holidays': 0.0,
            'days_not_worked': 0.0,
            'hours_not_worked': 0.0,
        }
        for (var index in data) {
            var line = data[index];

            // REFRESH BLOCK START
            var refresh_icon_block = h('span', '');
            if (line.state == 'draft') {
                refresh_icon_block = h('a',
                    [
                        h(
                            'i.fa.fa-refresh.line_refresh',
                            {attrs:{title: _t('Atnaujinti')}},
                        )
                    ]
                );
            }
            var refresh_button_block = h(
                    'th.refresh_button',
                    {attrs:{
                        'date_from': line.date_from,
                        'date_to': line.date_to,
                        'contract_id': line.contract_id[0]
                    }},
                    [refresh_icon_block]
                );
            // REFRESH BLOCK END

            // CHANGE STATE BLOCK START
            var change_state_decorator = ((line.state == 'draft') ? 'i.fa.fa-check.line_confirm' : 'i.fa.fa-close.line_cancel');
            var change_state_th_class = ((line.state == 'draft') ? 'th.change_state_to_done' : 'th.change_state_to_draft');
            var change_state_title = ((line.state == 'draft') ? _t('Patvirtinti') : _t('Atitvirtinti'));
            var change_state_button_block = h(
                change_state_th_class,
                {attrs:{
                    'date_from': line.date_from,
                    'date_to': line.date_to,
                    'contract_id': line.contract_id[0]
                }},
                [
                    h(
                        change_state_decorator,
                        {attrs:{
                            title: change_state_title,
                        }}
                    )
                ]
            );
            // CHANGE STATE BLOCK END

            // LINE NUMBER BLOCK START
            var line_number = parseInt(index)+1;
            var title = line_number;
            if (line.show_warning) {
                title = line_number + '\nEgzistuoja nepasirašyti įsakymai';
            }
            var line_number_block = h(
                'th.line_number',
                {
                    class: {show_warning: line.show_warning},
                    attrs: {'title': title}
                },
                line_number
            );
            // LINE NUMBER BLOCK END

            // EMPLOYEE NUMBER BLOCK START
            var employee_number = line.tabelio_numeris || ''
            var employee_number_block = h(
                'th.employee_number',
                employee_number
            );
            // EMPLOYEE NUMBER BLOCK END

            // EMPLOYEE BLOCK START
            var show_hours_mismatch = line.hours_worked != line.num_regular_work_hours_without_holidays;
            var employee_blocks = [];
            var employee_decorator = 'th.employee';
            if (show_hours_mismatch) {
                employee_decorator = 'th.employee.oe_worked_less_than_agreed';
                var title = 'Dirba: ' + line.hours_worked + ', Turėtų: ' + line.num_regular_work_hours_without_holidays;
                employee_blocks.push(
                    h(
                        'span.worked_less_than_agreed_tooltip',
                        title
                    )
                );
            }
            employee_blocks.push(
                h(
                    'span',
                    line.employee_id[1]
                )
            );
            var employee_block = h(
                employee_decorator,
                {attrs: {'employee_id': line.employee_id[0]}},
                employee_blocks
            );
            // EMPLOYEE BLOCK END

            // CONTRACT BLOCK START
            var contract_link = '/web#id=' + line.contract_id[0] + '&model=hr.contract'
            var contract_block = h(
                'th.contract',
                [
                    h(
                        'a',
                        {attrs: {'href': contract_link, 'target': '_blank'}},
                        line.contract_id[1]
                    )
                ]
            );
            // CONTRACT BLOCK END

            // SECONDARY BLOCKS START
            var secondary_blocks = [];
            if (this.table_shown == 'main') {
                for (var day_index in line.days) {
                    var day = line.days[day_index];
                    var date_data = day_data_dict[day.date];
                    var day_title = line.employee_id[1] + ' (' + line.contract_id[1] + ') ' + day.date;
                    if (!day.holidays_match) {
                        day_title += '\nEgzistuoja neatitikimai tarp atostogų įrašų ir nurodyto darbo laiko';
                    }
                    secondary_blocks.push(
                        h(
                            'td',
                            {
                                class: {
                                    ziniarastis_day: true,
                                    holidays_mismatch: !day.holidays_match,
                                    o_ziniarastis_current: ((date_data.is_today) ? true : false),
                                    o_ziniarastis_weekend: ((date_data.is_weekend) ? true : false),
                                    o_ziniarastis_national_holiday: ((date_data.is_national_holiday) ? true : false),
                                    o_unselected_cell: true
                                },
                                attrs: {
                                    title: day_title,
                                    day_id: day.id,
                                    contract_id: line.contract_id,
                                    row: parseInt(index)+1,
                                    column: parseInt(day_index)+1
                                }
                            }, day.name
                        )
                    );

                }
            } else {
                var beggining_of_s_b_title = line.employee_name + ' (' + line.contract_id[1] + ') ';
                var secondary_block = [
                    h('td.align_center', {attrs: {title: beggining_of_s_b_title + _t('Dirbta dienų')}}, line.days_total),
                    h('td.align_center', {attrs: {title: beggining_of_s_b_title + _t('Dirbta valandų')}}, line.hours_worked),
                    h('td.align_center', {attrs: {title: beggining_of_s_b_title + _t('Dirbta naktį')}}, line.hours_night),
                    h('td.align_center', {attrs: {title: beggining_of_s_b_title + _t('Dirbta viršvalandžių')}}, line.hours_overtime),
                    h('td.align_center', {attrs: {title: beggining_of_s_b_title + _t('Dirbta nukrypus nuo normalių darbo sąlygų')}}, line.hours_not_regular),
                    h('td.align_center', {attrs: {title: beggining_of_s_b_title + _t('Budėjimas namuose')}}, line.hours_watch_home),
                    h('td.align_center', {attrs: {title: beggining_of_s_b_title + _t('Budėjimas darbe')}}, line.hours_watch_work),
                    h('td.align_center', {attrs: {title: beggining_of_s_b_title + _t('Poilsio dienomis')}}, line.hours_weekends),
                    h('td.align_center', {attrs: {title: beggining_of_s_b_title + _t('Švenčių dienomis')}}, line.hours_holidays),
                    h('td.align_center', {attrs: {title: beggining_of_s_b_title + _t('Nedirbtų dienų skaičius')}}, line.days_not_worked),
                    h('td.align_center', {attrs: {title: beggining_of_s_b_title + _t('Nedirbtų valandų skaičius')}}, line.hours_not_worked)
                ];
                secondary_blocks = secondary_blocks.concat(secondary_block);
                sum_totals.days_total = sum_totals.days_total + line.days_total
                sum_totals.hours_worked = sum_totals.hours_worked + line.hours_worked
                sum_totals.hours_night = sum_totals.hours_night + line.hours_night
                sum_totals.hours_overtime = sum_totals.hours_overtime + line.hours_overtime
                sum_totals.hours_not_regular = sum_totals.hours_not_regular + line.hours_not_regular
                sum_totals.hours_watch_home = sum_totals.hours_watch_home + line.hours_watch_home
                sum_totals.hours_watch_work = sum_totals.hours_watch_work + line.hours_watch_work
                sum_totals.hours_weekends = sum_totals.hours_weekends + line.hours_weekends
                sum_totals.hours_holidays = sum_totals.hours_holidays + line.hours_holidays
                sum_totals.days_not_worked = sum_totals.days_not_worked + line.days_not_worked
                sum_totals.hours_not_worked = sum_totals.hours_not_worked + line.hours_not_worked
            }
            // SECONDARY BLOCKS END

            var line_data = h(
                'tr.ziniarastis_period_line',
                [
                    refresh_button_block,
                    change_state_button_block,
                    line_number_block,
                    employee_number_block,
                    employee_block,
                    contract_block
                ].concat(secondary_blocks)
            );
            ziniarastis_lines.push(line_data)
        }

        if (this.table_shown != 'main') {
            ziniarastis_lines.push(h('tr.ziniarastis_period_line', [
                h('th', {attrs: {colspan: 6}}, ''),
                h('td.align_center.bold', {attrs: {title: _t('Viso dirbta dienų')}}, Math.round(sum_totals.days_total * 100) / 100),
                h('td.align_center.bold', {attrs: {title: _t('Viso dirbta valandų')}}, Math.round(sum_totals.hours_worked * 100) / 100),
                h('td.align_center.bold', {attrs: {title: _t('Viso dirbta naktį')}}, Math.round(sum_totals.hours_night * 100) / 100),
                h('td.align_center.bold', {attrs: {title: _t('Viso dirbta viršvalandžių')}}, Math.round(sum_totals.hours_overtime * 100) / 100),
                h('td.align_center.bold', {attrs: {title: _t('Viso dirbta nukrypus nuo normalių darbo sąlygų')}}, Math.round(sum_totals.hours_not_regular * 100) / 100),
                h('td.align_center.bold', {attrs: {title: _t('Viso budėjimo namuose')}}, Math.round(sum_totals.hours_watch_home * 100) / 100),
                h('td.align_center.bold', {attrs: {title: _t('Viso budėjimo darbe')}}, Math.round(sum_totals.hours_watch_work * 100) / 100),
                h('td.align_center.bold', {attrs: {title: _t('Viso poilsio dienomis')}}, Math.round(sum_totals.hours_weekends * 100) / 100),
                h('td.align_center.bold', {attrs: {title: _t('Viso švenčių dienomis')}}, Math.round(sum_totals.hours_holidays * 100) / 100),
                h('td.align_center.bold', {attrs: {title: _t('Visas nedirbtų dienų skaičius')}}, Math.round(sum_totals.days_not_worked * 100) / 100),
                h('td.align_center.bold', {attrs: {title: _t('Visas nedirbtų valandų skaičius')}}, Math.round(sum_totals.hours_not_worked * 100) / 100)
            ]));
        }

        return ziniarastis_lines;
    },
    _table_base: function (header_data) {
        var self = this;
        var initial_colspan = 0;
        var thead_set_as_used = [];
        var tfoot_set_as_used = [];

        var day_colspan = header_data.number_of_days;
        if (this.table_shown != 'main') {
            day_colspan = 11;
        }
        var day_data = header_data.date_data;
        var month_name = header_data.month_name;
        var year = header_data.year;

        var table_header_date_string = month_name + ', ' + year.toString();

        var first_tr = h('tr.ziniarastis_header', [
            h('th.o_ziniarastis_month_name.align_center', {attrs: {colspan: 6, title: table_header_date_string}}, table_header_date_string),
            h('th.o_ziniarastis_month_name.align_center', {attrs: {colspan: day_colspan}}, '')
        ]);

        var second_tr_main = [
            h('th.o_ziniarastis_title_header.align_center', ''),
            h('th.o_ziniarastis_title_header.align_center', ''),
            h('th.o_ziniarastis_title_header.align_center', {attrs: {title: _t('Eilės nr.')}}, _t('Eilės nr.')),
            h('th.o_ziniarastis_title_header.align_center', {attrs: {title: _t('Tabelio nr.')}}, _t('Tabelio nr.')),
            h('th.o_ziniarastis_title_header.align_center', {attrs: {title: _t('Darbuotojas')}}, _t('Darbuotojas')),
            h('th.o_ziniarastis_title_header.align_center', {attrs: {title: _t('Kontrakto nr.')}}, _t('Kontrakto nr.'))
        ];

        if (this.table_shown == 'main') {
            var second_tr_secondary = day_data.map(function(date_day_data) {
                return h('th.o_ziniarastis_title_header', {
                    class: {
                        o_ziniarastis_current: ((date_day_data.is_today) ? true : false),
                        o_ziniarastis_weekend: ((date_day_data.is_weekend) ? true : false),
                        o_ziniarastis_national_holiday: ((date_day_data.is_national_holiday) ? true : false),
                        o_ziniarastis_column: true
                    },
                    attrs: {title: date_day_data.print_str}
                },
                date_day_data.print_str
            )});
        } else {
            var second_tr_secondary = [
                h('th.o_ziniarastis_title_header.align_center', {attrs: {title: _t('Dirbta dienų')}}, _t('Dirbta dienų')),
                h('th.o_ziniarastis_title_header.align_center', {attrs: {title: _t('Dirbta valandų')}}, _t('Dirbta valandų')),
                h('th.o_ziniarastis_title_header.align_center', {attrs: {title: _t('Dirbta naktį')}}, _t('Dirbta naktį')),
                h('th.o_ziniarastis_title_header.align_center', {attrs: {title: _t('Dirbta viršvalandžių')}}, _t('Dirbta viršvalandžių')),
                h('th.o_ziniarastis_title_header.align_center', {attrs: {title: _t('Dirbta nukrypus nuo normalių darbo sąlygų')}}, _t('Dirbta nukrypus nuo normalių darbo sąlygų')),
                h('th.o_ziniarastis_title_header.align_center', {attrs: {title: _t('Budėjimas namuose')}}, _t('Budėjimas namuose')),
                h('th.o_ziniarastis_title_header.align_center', {attrs: {title: _t('Budėjimas darbe')}}, _t('Budėjimas darbe')),
                h('th.o_ziniarastis_title_header.align_center', {attrs: {title: _t('Poilsio dienomis')}}, _t('Poilsio dienomis')),
                h('th.o_ziniarastis_title_header.align_center', {attrs: {title: _t('Švenčių dienomis')}}, _t('Švenčių dienomis')),
                h('th.o_ziniarastis_title_header.align_center', {attrs: {title: _t('Nedirbtų dienų skaičius')}}, _t('Nedirbtų dienų skaičius')),
                h('th.o_ziniarastis_title_header.align_center', {attrs: {title: _t('Nedirbtų valandų skaičius')}}, _t('Nedirbtų valandų skaičius'))
            ];
        }

        var table_header = h('thead', [
            first_tr,
            h('tr.ziniarastis_header', second_tr_main.concat(second_tr_secondary))
        ]);
        return h('div.o_view_ziniarastis', [
            h('table.table.table-responsive', [
                table_header,
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
                var el_selector = "#" + k;
                var elements = $(el_selector);
                if (dynamic_buttons_data[k]){
                    elements.toggleClass("o_ziniarastis_invisible", false);
                }
                else {
                    elements.toggleClass("o_ziniarastis_invisible", true);
                }
            }
        }
    },
    display_delete_button: function(){
        var day_ids = this._navigation.get_selected_ids()
        if (day_ids === undefined || day_ids.length == 0){
            $('#ziniarastis_setter_group').toggleClass("o_ziniarastis_invisible", true);
        } else {
            $('#ziniarastis_setter_group').toggleClass("o_ziniarastis_invisible", false);
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
        if (this.ziniarastis_period_id && !c.eval().ziniarastis_period_id) {
            c.add({'ziniarastis_period_id': this.ziniarastis_period_id});
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
        if (this.dataset.ids && (this.dataset.index || this.dataset.index === 0)) {
            this.ziniarastis_period_id = this.dataset.ids[this.dataset.index];
        }
        var _this = this;
        this._enqueue(function () {
            _this.left_scroll_pos = $('.o_view_ziniarastis').scrollLeft();
            _this.top_scroll_pos = $('.o_view_ziniarastis').scrollTop();
            return (new Model('ziniarastis.period')).call('get_data_for_view', {
                ziniarastis_period_id: _this.ziniarastis_period_id,
                year: _this.year,
                month: _this.month,
                extra_domain: _this.domain,
                offset:_this.current_min-1,
                limit:_this._limit,
            }).then(function (results) {
                _this.set('ziniarastis_data', results);
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
    render_buttons: function ($node) {
        this._navigation = new ZiniarastisHeader(
            this,
            this.fields_view.arch.children
                .filter(function (c) { return c.tag === 'button'; })
                .map(function (c) { return c.attrs; })
        );
        var self = this;
        self._navigation.appendTo($node);
        if (!this.pager && this.options.pager) {
            this.pager = new Pager(this, 100, 1, this._limit || 20);
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
core.view_registry.add('ziniarastis', ZiniarastisView);

var ZiniarastisHeader = Widget.extend({
    template: 'ziniarastis.ZiniarastisController',
    events: {
        'click .ziniarastis_arrow_previous': function (e) {
            e.stopPropagation();
            var parent = this.getParent();
            var ids = parent.dataset.ids;
            var index = parent.dataset.index;
            if (ids && index) {
                parent.dataset.index = index-1;
                parent.ziniarastis_period_id = ids[index - 1];
                parent.current_min = 1;
                parent._fetch();
            }
        },
        'click .ziniarastis_arrow_next': function (e) {
            e.stopPropagation();
            var parent = this.getParent();
            var ids = parent.dataset.ids;
            var index = parent.dataset.index;
            if (ids && index && index !== ids.length - 1) {
                parent.dataset.index = index+1;
                parent.ziniarastis_period_id = ids[index + 1];
                parent.current_min = 1;
                parent._fetch();
            }
        },
        'click .button': "execute_ziniarastis_header_button_action",
        'click #button_switch_table': "_switch_table",
        'click .setter_button': "_set_time_for_selected_days",
    },
    init: function (parent, buttons, department) {
        this._super.apply(this, arguments);
        this._buttons = buttons;
    },
    start: function () {
        this._super();
    },
    _switch_table: function() {
        return this.getParent()._switch_table();
    },
    _set_time_for_selected_days: function(e) {
        var selected_ids = this.get_selected_ids();
        var closest_div = $(e.target).closest("div");
        var code = closest_div.attr('code');
        var self = this;
        if (!selected_ids || !code) {
            return
        } else {
            return (new Model('ziniarastis.day')).call('set_marked_values', [code, selected_ids]).then(function() {
                self.getParent()._fetch();
            });
        }
    },
    call_ziniarastis_period_method: function(method_to_call) {
        var ziniarastis_id = this.getParent().ziniarastis_period_id;
        var self = this;
        return (new Model('ziniarastis.period')).call(method_to_call, [ziniarastis_id]).then(function(data_returned) {
            if (Boolean(data_returned)) {
                self.do_action(data_returned,
                {
                    on_close: function() {
                        self.getParent()._fetch()
                    }
                });
            } else {
                self.getParent()._fetch();
            }
        });
    },
    call_delete_lines: function() {
        $('.setter_button[code="DEL"]').trigger('click');
    },
    get_selected_ids: function(){
        var elements = $("td.o_selected_cell");
        var ziniarastis_day_ids = [];
        elements.each(function(indx, el){
            var day_id = $(el).attr('day_id');
            day_id = parseInt(day_id);
            ziniarastis_day_ids.push(day_id);
        });
        return ziniarastis_day_ids;
    },
    execute_ziniarastis_header_button_action: function(e){
        var target = $(e.target).closest("div");
        var method_to_call = target.attr('id');
        var confirm_msg = target.attr('confirm');
        var good_to_execute_action = false;
        if (confirm_msg) {
            if (confirm(confirm_msg)) {
                good_to_execute_action = true;
            }
        } else {
            good_to_execute_action = true;
        }
        if (good_to_execute_action) {
            if (method_to_call == 'button_check') {
                var self = this;
                var line_ids = this.getParent().line_ids;
                return (new Model('ziniarastis.period.line').call("check_dk_constraints", [line_ids]).then(function(data_returned) {
                    self.getParent()._fetch();
                }));
            } else if (method_to_call == 'button_done_selected') {
                var self = this;
                var line_ids = this.getParent().line_ids;
                return (new Model('ziniarastis.period.line').call("confirm_selected_lines", [line_ids]).then(function(data_returned) {
                    self.getParent()._fetch();
                }));
            } else {
                return this.call_ziniarastis_period_method(method_to_call);
            }
        }
    },
});

ListView.List.include(/** @lends instance.web.ListView.List# */{
    row_clicked: function (event) {
        if (this.view.model == 'ziniarastis.period') {
            var period_id = this.dataset.ids[this.dataset.index];
            this.dataset.ids = this.dataset.ids.reverse();
            this.dataset.index = this.dataset.ids.indexOf(period_id);
            $(this).trigger('row_link', [
                period_id,
                this.dataset,
                'ziniarastis'
            ]);
        } else {
            return this._super.apply(this, arguments);
        }
    },
});

return {
    ZiniarastisView: ZiniarastisView,
}

});
