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
        this.dialog_stop();
        if (id) {
          this.inner_widget.active_view.controller.trigger('other_day', id);
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
	if (!$(elem.target).is("tbody") && !$(elem.target).is("tr") && !$(elem.target).hasClass("oe_ziniarastis_day") && !$(elem.target).hasClass("oe_fd_button") && !$(elem.target).hasClass("oe_vd_button") && !$(elem.target).hasClass("oe_absences_button")) {
        $(".oe_mousedown_selected").each(function(i, element) {
            $(element).removeClass("oe_mousedown_selected");
        });
      }
     });
});

robo.define('l10n_lt_payroll.MonthlyZiniarastis', function (require) {
"use strict";
var core = require('web.core');
var data = require('web.data');
var form_common = require('web.form_common');
var formats = require('web.formats');
var Model = require('web.DataModel');
var time = require('web.time');
var utils = require('web.utils');
var roboUtils = require('robo.utils');


var QWeb = core.qweb;
var _t = core._t;


var MonthlyZiniarastis = form_common.FormWidget.extend(form_common.ReinitializeWidgetMixin, {
    id: 'MonthlyZiniarastis',
    events: {
        "click .oe_ziniarastis_day": "go_to_ziniarastis_day",
        "click .oe_hr_employee": "go_to_hr_employee",
        "click .oe_hr_contract": "go_to_hr_contract",
        "click .oe_hr_refresh": "refresh_line",
        "click .oe_hr_cancel": "cancel_line",
        "click .oe_hr_single_done": "line_single_done",
        "mouseenter .mark_color": "_mouse_enter", //mouseover more bubbling...
        "mouseleave .mark_color": "_mouse_leave",
        'click .o_table_tab': '_tab_clicked',
        'mousedown .oe_ziniarastis_day': "_mouse_down",
        'mouseup .oe_ziniarastis_day': "_mouse_up",
        'click .oe_absence_button': "set_marked_values",
        'click .oe_vd_button': "set_marked_values",
        'click .oe_fd_button': "set_marked_values",
        'click .oe_check_button': "check_all_values"
    },
    open_other_day: function(id){
        var $find_el = this.$('.oe_ziniarastis_day[data-id='+id+']');
        if ($find_el.length){
            $($find_el[0]).trigger('click');
        }
    },
    _tab_clicked: function(e){
        var first_class="o_dienos";
        var second_class="o_faktiskai";

        var my_class = $(e.target).data("class");

        if (my_class === first_class){
            this.$('.o_dienos').toggleClass("o_hidden",false);
            this.$('.o_faktiskai').toggleClass("o_hidden",true);
        }
        else{
            this.$('.o_dienos').toggleClass("o_hidden",true);
            this.$('.o_faktiskai').toggleClass("o_hidden",false);
        }
    },
    init: function() {
        this._super.apply(this, arguments);
        this.getParent().on('other_day', this, this.open_other_day);
        this.set({
            ziniarastis_days: [],
            date_from: false,
            date_to: false,
        });
        this.field_manager.on("field_changed:related_ziniarastis_days", this, this.fetch_data);
        this.field_manager.on("field_changed:date_from", this, function() {
            this.set({"date_from": time.str_to_date(this.field_manager.get_field_value("date_from"))});
        });
        this.field_manager.on("field_changed:date_to", this, function() {
            this.set({"date_to": time.str_to_date(this.field_manager.get_field_value("date_to"))});
        });
        this.description_line = _t("/");
        this.mouse_down_start_col = false;
        this.mouse_down_start_row = false;
        this.res_o2m_drop = new utils.DropMisordered();
        this.render_drop = new utils.DropMisordered();
        this.robo_drop_previous = new roboUtils.MutexDropPrevious();
        this.locker = {locker_byId: {}, locker_global: false};
        this.holiday = []; //better {}
    },
    go_to_ziniarastis_day: function(event) {
        var id = JSON.parse($(event.currentTarget).data("id"));
        var day_ids = [];
        $(event.currentTarget).prevAll().each(function(indx, el){
            day_ids.unshift(JSON.parse($(el).data('id')));
        });
        day_ids.push(id);
        $(event.currentTarget).nextAll().each(function(indx, el){
            day_ids.push(JSON.parse($(el).data("id")));
        });
        var self = this;
        if (id){
            return (new Model('ziniarastis.day')).call('get_wizard_view_id', []).then(function(view_id){
                self.do_action({
                    type: 'ir.actions.act_window',
                    view_id: view_id,
                    res_model: "ziniarastis.day",
                    res_id: id,
                    target: 'new',
                    views: [[view_id, 'form']],
                    view_type: 'form',
                    view_mode: 'form',
                },
                {
                    additional_context:{
                      day_ids: day_ids,
                      current_id: id,
                    },
                    on_close: _.bind(function(){
                        self.fetch_data();
                    }, self),
                });
            });
        }
    },
    go_to_hr_employee: function(event) {
        var id = JSON.parse($(event.target).data("id"));
        this.do_action({
            type: 'ir.actions.act_window',
            res_model: "hr.employee",
            res_id: id,
            views: [[false, 'form']],
            view_type: 'form',
            view_mode: 'form',
            });
    },
    go_to_hr_contract: function(event) {
        var id = JSON.parse($(event.target).data("id"));
        this.do_action({
            type: 'ir.actions.act_window',
            res_model: "hr.contract",
            res_id: id,
            views: [[false, 'form']],
            view_type: 'form',
            view_mode: 'form',
            });
    },
    _line_change: function(event, call_function){
        var self = this;
        var date_from = JSON.parse($(event.target).data("date_from"));
        var date_to = JSON.parse($(event.target).data("date_to"));
        var contract_id = JSON.parse($(event.target).data("contract_id"));

        var def = new Model(self.view.model).call(call_function, [date_from, date_to, contract_id], {});
        this.robo_drop_previous.add(def).then(function(){
                return self.fetch_data();
        });
        return def;
    },
    //during refresh all other buttons in all lines are locked
    refresh_line: function(event) {
        var self = this;
        if (!this.locker.locker_global){
            var contract_id = JSON.parse($(event.target).data("contract_id"));
            if (!contract_id || (typeof contract_id == 'number' && !this.locker.locker_byId[contract_id])){
                this.locker.locker_global = true;
                $(event.currentTarget).css('color','red');
                return $.when(this._line_change(event, 'refresh_line')).always(function(){
                    self.locker.locker_global = false;
                    $(event.currentTarget).css('color');
                })
            }
        }
    },
    _lines_cancel_or_done: function(event, func){
        var self = this;
        if (!this.locker.locker_global){
            var contract_id = JSON.parse($(event.target).data("contract_id"));
            if (typeof contract_id == 'number' && !this.locker.locker_byId[contract_id]){
                this.locker.locker_byId[contract_id] = true;
                $(event.currentTarget).css('color','red');
                return $.when(contract_id, this._line_change(event, func)).always(function (id) {
                    self.locker.locker_byId[id] = false;
                    $(event.currentTarget).css('color');
                })
            }
        }
    },
    cancel_line: function(event) {
        return this._lines_cancel_or_done(event, 'cancel_done_line');
    },
    line_single_done: function(event) {
        return this._lines_cancel_or_done(event, 'call_button_single_done');
    },
    _mouse_enter: function(event) {
        var row_n = $(event.target).attr('row');
        // $(event.target).toggleClass("oe_mouse_target", true);
        var str = 'td[row="' + row_n + '"]';
        $(str).each(function(i, element) {
           $(element).addClass("oe_mouse_over");
        });
        var col_n = $(event.target).attr('column');
        var str = 'td[column="' + col_n + '"]';
        $(str).each(function(i, element) {
           $(element).addClass("oe_mouse_over");
        });
        var str = 'th[column="' + col_n + '"]';
        $(str).each(function(i, element) {
           $(element).addClass("oe_mouse_over");
        });
        if (this.mouse_down_start_col != false && this.mouse_down_start_row != false) {
            this.mark_selected_days(this.mouse_down_start_col, this.mouse_down_start_row, col_n, row_n);
        }
    },
    _mouse_leave: function(event) {
        var row_n = $(event.target).attr('row');
        // $(event.target).toggleClass("oe_mouse_target", false);
        var str = 'td[row="' + row_n + '"]';
        $(str).each(function(i, element) {
           $(element).removeClass("oe_mouse_over");
        });
        var col_n = $(event.target).attr('column');
        var str = 'td[column="' + col_n + '"]';
        $(str).each(function(i, element) {
           $(element).removeClass("oe_mouse_over");
        });
        var str = 'th[column="' + col_n + '"]';
        $(str).each(function(i, element) {
           $(element).removeClass("oe_mouse_over");
        });
        if (this.mouse_down_start_col != false || this.mouse_down_start_row != false) {
            this.unmark_selected_days();
        }
    },
    _mouse_down: function(event) {
        this.mouse_down_start_col = false;
        this.mouse_down_start_row = false;
        this.unmark_selected_days()
        if ($(event.target).attr('column') != false && $(event.target).attr('row') != false) {
            this.mouse_down_start_col = $(event.target).attr('column');
            this.mouse_down_start_row = $(event.target).attr('row');
        }
    },
    _mouse_up: function(event) {
        var row_n = $(event.target).attr('row');
        var col_n = $(event.target).attr('column');
        this.mark_selected_days(this.mouse_down_start_col, this.mouse_down_start_row, col_n, row_n);
        this.mouse_down_start_col = false;
        this.mouse_down_start_row = false;
    },
    unmark_selected_days: function() {
        $(".oe_mousedown_selected").each(function(i, element) {
            $(element).removeClass("oe_mousedown_selected");
        });
    },
    mark_selected_days: function(col_s, row_s, col_e, row_e) {
        this.unmark_selected_days()
        if (!col_s && col_e) col_s = col_e;
        if (!col_e && col_s) col_e = col_s;
        if (!row_s && row_e) row_s = row_e;
        if (!row_e && row_s) row_e = row_s;
        if (col_s && row_s && col_e && row_e) {
            var column_start = parseInt(col_s.slice(1));
            var row_start = parseInt(row_s);
            var column_end = parseInt(col_e.slice(1));
            var row_end = parseInt(row_e);
            for (var i=Math.min(column_start, column_end); i<=Math.max(column_start, column_end); i++) {
                for (var j=Math.min(row_start, row_end); j<=Math.max(row_start, row_end); j++) {
                    var str = 'td[column="b' + i + '"][row="' + j + '"]';
                    $(str).addClass("oe_mousedown_selected");
                }
            }
        }
    },
    set_marked_values: function(event) {
        var selected_code = event.target.attributes.code.value;
        var days=[];
        var self = this;
        $(".oe_mousedown_selected").each(function(i, element) {
            days.push(element.attributes['data-id'].value);
        });
        if (selected_code == 'DEL'){
            var r = confirm("Pažymėti įrašai bus ištrinti, ar tikrai norite ištrinti šiuos įrašus?");
            if (r == true) {
                new Model("ziniarastis.day").call("set_marked_values", [selected_code, days]).then(function() {
                    self.fetch_data();
                });
            }
        } else {
            new Model("ziniarastis.day").call("set_marked_values", [selected_code, days]).then(function() {
                self.fetch_data();
            });
        }
    },
    check_all_values: function(event) {
        var self = this;
        var ids = [];
        self.ziniarastis_period_lines.forEach(function (item, index) {
            ids.push(item['id'])
        })
        new Model('ziniarastis.period.line').call("check_dk_constraints", [ids]);
    },
    initialize_field: function() {
        form_common.ReinitializeWidgetMixin.initialize_field.call(this);
    },
    set_holiday_dates: function() {
        // <holidays>
        var self = this;
        var holidays = new Model('sistema.iseigines');
        var holiday = [];

        // var current_date = new Date(this.get("date_from"));
        var current_date = new Date(this.get("date_from"));
        while (current_date <= this.get("date_to"))
        {
            var str = moment(current_date).format('YYYY-MM-DD');
            holiday[str] = false;
            current_date.setDate(current_date.getDate() + 1)
        }

        var def = holidays.query(['date'])
             .filter([['date', '>=', this.get("date_from")], ['date', '<=', this.get("date_to")]])
             .all()
             .then(function (holidays) {
            // do work with users records this.get("date_to")]
                for (var i = 0; i < holidays.length; i++)
                {
                    holiday[holidays[i]['date']] = true
                }
                self.holiday = holiday;
             });
    },
    fetch_data: function() {

        // don't render anything until we have date_to and date_from
        if (!this.get("date_to") || !this.get("date_from")) {
            return;
        }
        // it's important to use those vars to avoid race conditions
        var dates;
        var accounts;
        var default_get;
        //var all_lines = [];
        var self = this;

        var hols = self.set_holiday_dates();
        var date_from = self.get("date_from");
        var date_to = new Date(self.get("date_to"));

        return $.when(hols).then(function(){
            return self.render_drop.add(
                            new Model("ziniarastis.period.line")
                            .call("default_get", [['ziniarastis_period_id','employee_id','contract_id'], new data.CompoundContext({})])
                        )
        }).then(function() {
            dates = function(){
                       var date = new Date(date_from);
                        var days = [];
                         while (date.getMonth() === date_to.getMonth() && date.getDate() <= date_to.getDate() ) {
                            days.push(new Date(date));
                            date.setDate(date.getDate() + 1);
                         }
                         return days;
            }();

            var dates_unique = _.uniq(dates);
            dates_unique.sort(function(a, b){
                return a.getTime() - b.getTime();
            });
            self.dates = dates_unique;

            new Model('ziniarastis.period').call('get_all_data', [date_from, date_to]).then(function (results) {
                self.ziniarastis_period_lines = results;
                self.date_from = date_from;
                self.date_to = date_to;
                self.num_from = 2;
                self.num_to = 15;
                //real rendering
                self.display_data();
            });

        })
    },
    display_data: function() {
        var self = this;
        self.$el.html(QWeb.render("l10n_lt_payroll.MonthlyZiniarastis", {widget: self}));

        // make tables with the same row_height
        var first_table = self.$('.first_table_row'),
            second_table = self.$('.second_table_row'),
            second_table_faktiskai = self.$('.second_table_row_faktiskai');

        var max_height, row_index, $row, find_row_height;

        first_table.each(function(index, row){
            $row = $(row);
            max_height = $row.height();
            row_index = $row.attr('row');
            if (find_row_height = second_table.filter("[row='"+row_index+"']").first().height()){
                if (find_row_height > max_height) {
                    max_height = find_row_height;
                }
            }
            if (find_row_height = second_table_faktiskai.filter("[row='"+row_index+"']").first().height()){
                if (find_row_height > max_height) {
                    max_height = find_row_height;
                }
            }

            $row.height(max_height);
            second_table.filter("[row='"+row_index+"']").first().height(max_height);
            second_table_faktiskai.filter("[row='"+row_index+"']").first().height(max_height);

        })

    },
});


core.form_custom_registry.add('monthly_ziniarastis', MonthlyZiniarastis);

});
