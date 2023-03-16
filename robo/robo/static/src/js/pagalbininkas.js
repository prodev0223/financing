 robo.define('robo.pagalbininkas', function (require) {
    "use strict";


    var config = require('web.config');
    var datepicker = require('web.datepicker');
    var time = require('web.time');
    var roboUtils = require('robo.utils');
    var utils = require('web.utils');


    var session = require('web.session');
    var core = require('web.core');
    var Model = require('web.DataModel');

    var ActionManager = require('web.ActionManager');
    var data = require('web.data');
    var Dialog = require('web.Dialog');
    var FavoriteMenu = require('web.FavoriteMenu');
    var form_common = require('web.form_common');

    var pyeval = require('web.pyeval');
    var ViewManager = require('web.ViewManager');

    var WebClient = require('web.WebClient');
    var Widget = require('web.Widget');

    var MultiDragDrop = require('robo.MultiDragDrop');

    var translation = require('web.translation');
    var _translation = translation._t;

    var _t = core._t;
    var QWeb = core.qweb;

    var NBR_LINKS = 7
    var ACTIVE_MENU_ADDITIONAL_VALUE = 1;
    var ACTIVE_MENU_SEQ_CONDITION = 1;

    var NBR_OF_YEARS_IN_GRAPHS = 3;
    var DATE_FORMAT = 'YYYY-MM-DD';
    // var START_YEAR = moment().startOf('year').format(DATE_FORMAT);
    // var END_YEAR = moment().format(DATE_FORMAT);

    var LT_LOT = {
        Ą: 'A',
        Č: 'C',
        Ę: 'E',
        Ė: 'E',
        Į: 'I',
        Š: 'S',
        Ų: 'U',
        Ū: 'U',
        Ž: 'Z',
    };

    var TOGGLE_SLIDER_METHOD_MAPPING = {
        'forecast-toggle': {'check': 'check_forecast', 'update': 'update_forecast'},
        'income-mode-toggle': {'check': 'check_income_mode', 'update': 'update_income_mode'},
        'invoices-mode-toggle': {'check': 'check_chart_rp_amounts_mode', 'update': 'set_chart_rp_amounts_mode'},
    };
    var CHART_RP_PARAMS = {'clear_breadcrumbs': false, 'additional_context': {}};
    var CHART_TO_ACTION_MAPPING = {
        'overdue': {'default': 'robo.open_extended_due_report', 'expense': 'robo.open_extended_due_report_exp'},
        'all': {'default': 'robo.open_extended_all_report', 'expense': 'robo.open_extended_all_report_exp'},
        'aml': {'default': 'sl_general_report.action_account_move_line_income_chart',
                'expense': 'sl_general_report.action_account_move_line_expense_chart'},
        'forecast': 'robo.action_res_users_chart_settings_forecast'
    };
    var CHART_POSITIVE_COLOR = '#DEF3BA';
    var CHART_NEGATIVE_COLOR = '#FFD3DA';

    function pickChartColor(numericValue){
        /*
        Function that picks color for
        the chart based on the numericValue:
        < 0 - Negative / > 0 - Positive
        */
        if (numericValue > 0){
            return CHART_POSITIVE_COLOR;
        }else{
            return CHART_NEGATIVE_COLOR;
        }
    };

    // rekursinis depth-first per meniu
    function visit(tree, callback, path) {
        path = path || [];
        callback(tree, path);
        _.each(tree.children, function (node) {
            visit(node, callback, path.concat(tree));
        });
    }

   var Pagalbininkas = Widget.extend({
        template: "Pagalbininkas",
        events: {
            'input      input.search-form':                 'on_input_change',
            'click      input.search-form':                 function(){this.$(".results li.main-part.active").removeClass("active");},
            //'click      .o_menuitem':                     'on_menuitem_click',
            'click      .close-icon-container':             'on_icon_close',
            'click      .show-more':                        function(){this.render({show_all: 1});},
            'click      .show-less':                        function(){
                                                                this.render({show_all: 0});
                                                                // this.$("input:visible").focus();
                                                                this.$("input").focus();
                                                            },
            'keydown    input.search-form':                 'on_keydown',
            'mousemove  .results li.main-part':             'on_mouse_li',
            'click  .dropdown-menu .menu-item[data-xml-id]':  'on_new_create',
            'click [class*="js-info-"] .prev_year, [class*="js-info-"] .curr_year, [class*="js-info-"] .before_prev_month, [class*="js-info-"] .prev_month, [class*="js-info-"] .curr_month, [class*="js-info-"] .curr_full_month, [class*="js-info-"] .next_month': 'on_period_toggle_button',
            'click a.o_menuitem.menu_search_field':     'on_menuitem_click',
            'click #invoices-mode-toggle, #income-mode-toggle, #forecast-toggle': 'on_slider_toggle_click',
            'click [class*="js-info-"] .non_accumulated, [class*="js-info-"] .accumulated, [class*="js-info-"] .pie_mode, [class*="js-info-"] .inv_mode': 'chart_mode_toggle',
        },

       /*
       * whichDateInputs: string 'start', 'end', 'start;end'
       * $selector: $(event.currentTarget)
       * dateText: string of dates separated by ;(semicolon)
       * Elements in "whichDateInputs" must correspond to elements in "dateText" after split by ;
       * */
       update_graph : function(whichDateInputs, $selector, datesText){
            var self = this;

            var myChartId, chartType, chartSubtype='', myFreq = {monthly: false, quarterly: false};
            var dateText;
            var use_dates = true;
            whichDateInputs.split(";").forEach(function(whichDateInput, indx){
                dateText = datesText.split(';')[indx];
                if ($selector.closest('.js-info-income').length ||
                   $selector.closest('#income-mode-box').length) {
                    self.chart.dates.income[whichDateInput] = dateText;
                    myChartId = 'income';
                    chartType = 'stackedAreaChart';
                    chartSubtype = 'income'
                }else if ($selector.closest('.js-info-expenses').length) {
                    self.chart.dates.expenses[whichDateInput] = dateText;
                    myChartId = 'expenses';
                    chartType = 'pieChart';
                    chartSubtype = 'expenses';
                }
                else if ($selector.closest('.js-info-incomeCompare').length) {
                    self.chart.dates.incomeCompare[whichDateInput] = dateText;
                    myChartId = 'incomeCompare';
                    chartType = 'pieChart';
                    chartSubtype = 'incomeCompare';
                }
                else if ($selector.closest('.js-info-profit').length) {
                    self.chart.dates.profit[whichDateInput] = dateText;
                    myChartId = 'profit';
                    chartType = 'stackedAreaChart';
                    chartSubtype = 'profit';
                }
                else if ($selector.closest('.js-info-cashflow').length ||
                         $selector.closest('#forecast-toggle-box').length) {
                    self.chart.dates.cashflow[whichDateInput] = dateText;
                    myChartId = 'cashflow';
                    chartType = 'Cashflow';
                    chartSubtype = 'cashflow';
                }
                else if ($selector.closest('.js-info-invoices').length ||
                         $selector.closest('#invoices-mode-box').length){
                    myChartId = 'invoices';
                    chartType = 'bulletChart';
                    chartSubtype = 'invoices';
                    use_dates = false;
                }
                else if ($selector.closest('.js-info-tax-table').length) {
                    self.chart.dates.taxesTable[whichDateInput] = dateText;
                    myChartId = 'taxesTable';
                    chartType = 'taxesTable';
                    chartSubtype = 'taxes';
                };
                if (use_dates) {
                    self.chart.dates[myChartId][whichDateInput] = dateText;
                }
            });

            if (myChartId && chartType) {
                myFreq[self.chart.groupBy[myChartId]] = true;
                self.load_graph("chart-" + myChartId, chartType, {
                    subtype: chartSubtype,
                    freq: myFreq,
                    dates: self.chart.dates[myChartId]
                });
            }
       },
       on_period_toggle_button: _.debounce(function(e){
           var self = this;
           var start, end;
           var $target = $(e.currentTarget)
           new Model('res.company').call('get_fiscal_year_params').then(function(fiscal_year){
               switch ($target.data('name')){
                   case 'prev_year':
                       start = fiscal_year['prev_from'];
                       end = fiscal_year['prev_to'];
                       break;
                   case 'curr_year':
                       start = fiscal_year['curr_from'];
                       end = moment().format(DATE_FORMAT);
                       break;
                   case 'curr_month':
                       start = moment().startOf('month').format(DATE_FORMAT);
                       end = moment().format(DATE_FORMAT);
                       break;
                   case 'before_prev_month':
                       start = moment().subtract(2, "month").startOf('month').format(DATE_FORMAT);
                       end = moment().subtract(2, "month").endOf('month').format(DATE_FORMAT);
                       break;
                   case 'prev_month':
                       start = moment().subtract(1, "month").startOf('month').format(DATE_FORMAT);
                       end = moment().subtract(1, "month").endOf('month').format(DATE_FORMAT);
                       break;
                   case 'curr_full_month':
                       start = moment().startOf('month').format(DATE_FORMAT);
                       end = moment().endOf('month').format(DATE_FORMAT);
                       break;
                   case 'next_month':
                       start = moment().add(1, "month").startOf('month').format(DATE_FORMAT);
                       end = moment().add(1, "month").endOf('month').format(DATE_FORMAT);
                       break;
                   }

                   if (start && end) {
                       self.update_graph('start;end', $target, start+';'+end);
                   }
           });
       },100, true),

       chart_mode_toggle: _.debounce(function(e){
           var mode;
           switch ($(e.currentTarget).data('name')){
               case 'non_accumulated_cashflow':
                   this.graph_mode_cashflow = 'non_accumulated'
                   break;
               case 'accumulated_cashflow':
                    this.graph_mode_cashflow = 'default'
                   break;
               case 'non_accumulated_income':
                    this.graph_mode_income = 'non_accumulated'
                    break;
               case 'accumulated_income':
                    this.graph_mode_income = 'default'
                    break;
               case 'pie_mode_expenses':
                   this.graph_mode_expenses = 'default'
                   break;
               case 'non_accumulated_expenses':
                   this.graph_mode_expenses = 'non_accumulated'
                   break;
               case 'accumulated_expenses':
                   this.graph_mode_expenses = 'accumulated'
                   break;
               case 'non_accumulated_profit':
                   this.graph_mode_profit = 'non_accumulated'
                   break;
               case 'accumulated_profit':
                   this.graph_mode_profit = 'default'
                   break;
              case 'income_invoices':
                   this.graph_mode_invoices = 'default'
                   break;
              case 'expense_invoices':
                   this.graph_mode_invoices = 'expense'
                   break;
           }
           this.update_graph('start;end', $(e.currentTarget), this.start_year+';'+this.end_year);
       },100, true),
       on_slider_toggle_click: _.debounce(function(e){
           var start, end;
           var self = this;
           var slider_el = $(e.currentTarget);
           var methods = TOGGLE_SLIDER_METHOD_MAPPING[slider_el['context'].id]
           var is_checked = slider_el.is(":checked");
           new Model('res.users').call(methods['check']).then(function(user_mode){
                if ((user_mode != true && is_checked) || (user_mode == true && !is_checked)){
                    start = moment().startOf('year').startOf('month').format(DATE_FORMAT);
                    end = moment().format(DATE_FORMAT);
                    new Model('res.users').call(methods['update'], [is_checked]).then(function(){
                        self.update_graph('start;end', slider_el, start+';'+end);
                    });
                }
            });
       },100, true),
       on_new_create: function(e){
           e.stopPropagation();
           e.preventDefault();
           var xml_id = $(e.currentTarget).data('xml-id');
           if (!_.isString(xml_id)) return;
           this.do_action(xml_id);
        },

       load_menus: function () {
            var Menus = new Model('ir.ui.menu');
            return Menus.call('load_menus_withTags', [core.debug], {context: session.user_context}).then(function (menu_data) {
                // Compute action_id if not defined on a top menu item
                for (var i = 0; i < menu_data.children.length; i++) {
                    var child = menu_data.children[i];
                    if (child.action === false) {
                        while (child.children && child.children.length) {
                            child = child.children[0];
                            if (child.action) {
                                menu_data.children[i].action = child.action;
                                break;
                            }
                        }
                    }
                }
                return menu_data;
            });
        },
        convert_to_latin_name: function(x){
             var latin_name = '';
            _.str.chars(x).forEach(function(letter){
                if (LT_LOT[letter] !== undefined){
                    latin_name += LT_LOT[letter];
                }
                else{
                    latin_name += letter;
                }
            });
            return latin_name;
        },
        process_menu_data: function (menu_data) {
            var self = this;

            var result = [];
            visit(menu_data, function (menu_item, parents) {
                if (!menu_item.id || !menu_item.action) {
                    return;
                }
                var item = {
                    label: _.pluck(parents.slice(1), 'name').concat(menu_item.name).join(' / '),
                    id: menu_item.id,
                    xmlid: menu_item.xmlid,
                    action: menu_item.action ? menu_item.action.split(',')[1] : '',
                    is_app: !menu_item.parent_id,
                    web_icon: menu_item.web_icon,
                    name: menu_item.name,
                    tags: _.isString(menu_item.tags) ? menu_item.tags.toUpperCase().split(',').sort().join(' '): menu_item.tags,
                    searchable: menu_item.searchable,
                    seq: menu_item.sequence === ACTIVE_MENU_SEQ_CONDITION ? ACTIVE_MENU_ADDITIONAL_VALUE : 0,
                };

                item.search_data = [];
                if (_.isString(menu_item.name)){
                    item.search_data = _.uniq(menu_item.name.toUpperCase().split(/[ ,/]+/g));
                }
                if (_.isString(item.tags)){
                    var normalized_tags = _.uniq(item.tags.toUpperCase().split(/[ ,/]+/g));
                    item.search_data = _.uniq(normalized_tags.concat(item.search_data));
                }
                item.search_data = item.search_data.sort();
                if (item.searchable) {
                    _.uniq(item.search_data).forEach(function (x) {
                        self.search_menu_words.push({
                            id: menu_item.id,
                            name: self.convert_to_latin_name(x),
                        });
                    });
                }

                if (!menu_item.parent_id) {
                    if (menu_item.web_icon_data) {
                        item.web_icon_data = 'data:image/png;base64,' + menu_item.web_icon_data;
                    } else if (item.web_icon) {
                        var icon_data = item.web_icon.split(',');
                        var $icon = $('<div>')
                            .addClass('o_app_icon')
                            .css('background-color', icon_data[2])
                            .append(
                                $('<i>')
                                    .addClass(icon_data[0])
                                    .css('color', icon_data[1])
                            );
                        item.web_icon = $icon[0].outerHTML;
                    } else {
                        item.web_icon_data = '/robo/static/src/img/default_icon_app.png';
                    }
                } else {
                    item.menu_id = parents[1].id;
                }
                result.push(item);
            });
            return result;
        },
        get_initial_state: function () {
            return {
                apps: _.where(this.menu_data, {is_app: true}),
                menu_items: [],
                focus: null,  // index of focused element
                is_searching: true,
            };
        },
        get_popup_date_format: function(date_str) {
            if (date_str.substring(11, 20) == '00:00:00') return 'YYYY-MM-DD';
            return 'YYYY-MM-DD HH:mm';
        },
        init: function (parent, data) {
            var self = this;
            this.robo_manager_rights = false;
            this.show_piechart_switch_buttons = false;
            this.u_all_income = false;
            this.u_analytics = false;
            this.is_salesman = false;
            this.show_comparison_chart = false;
            this._super.apply(this, arguments);
            this.search_menu_words = [];
            this.date_popup_data = [];
            // this.chart = {
            //     groupBy: {income: 'monthly', profit: 'monthly', cashflow: 'monthly'},
            //     dates: {
            //             income: {start: START_YEAR, end: END_YEAR},
            //             expenses: {start: START_YEAR, end: END_YEAR},
            //             profit: {start: START_YEAR, end: END_YEAR},
            //             cashflow: {start: START_YEAR, end: END_YEAR},
            //            }
            //  };
            this.to_remove = [];
            var time = new Date();
            this.curr_year = time.getFullYear();
            this.prev_year = time.getFullYear()-1;
            this.curr_month = moment().format("MMM");
            this.before_prev_month = moment().subtract(2, "month").format("MMM");
            this.prev_month = moment().subtract(1, "month").format("MMM");
            this.next_month = moment().add(1, "month").format("MMM");

            this.say_hello = 'Robo Vadovas';
            if (session.name) {
                var full_name = session.name.trim();
                var split_index = [full_name.indexOf(' '), full_name.indexOf(','), full_name.indexOf('-')].reduce(
                    function(acc, curr){
                        if ((~acc) && (~curr)){
                            return Math.min(acc, curr)
                        }
                        else{
                            return Math.max(acc, curr)
                        }
                    }
                );
                var name;
                if (~split_index){
                    name = full_name.substring(0, split_index);
                }

                this.say_hello = _t('Sveiki, ') + roboUtils.kas_to_sauksm(name || full_name);
            }

        },
        willStart: function(){
            var self = this;
            var no_menu_action_id = undefined;
            this.robo_alias_model = new Model('res.company');
            var def = self.robo_alias_model.query(['robo_alias'])
                            .filter([['id', '=', session.company_id]])
                            .limit(1)
                            .all();
            return $.when(
                        def,
                        session.is_premium_manager(),//user_has_group('robo_basic.group_robo_premium_manager'),
                        session.is_free_manager(),//user_has_group('robo_basic.group_robo_free_manager'),
                        session.user_has_group('robo_basic.group_robo_see_income'),
                        session.user_has_group('robo.group_robo_see_all_incomes'),
                        session.user_has_group('robo.group_robo_see_all_expenses'),
                        session.user_has_group('robo.group_menu_kita_analitika'),
                        session.user_has_group('robo_basic.group_view_income_compare_chart'),
                        session.user_has_group('robo_basic.group_robo_premium_user'),
                        session.user_has_group('robo_basic.robo_show_full_receivables_graph'),
                        self.load_menus(),
                        self.rpc("/graph/get_default_dates"),
                        self.rpc("/graph/get_default_comparison_dates"),
                        self.rpc("/web/action/load", { action_id: "robo.robo_client_ticket_wizard_action"})
                            .done(function(result) {
                                 if (_.isObject(result)) {
                                    no_menu_action_id = result.id;
                                    self.issue_action = result;
                                 }
                            })
                    ).then(function (r, premium_manager, free_manager, is_salesman, u_all_income, all_expenses, u_analytics,
                    show_comparison_chart, show_expense, show_full_receivables_graph, menu, date, date2) {
                        self.robo_alias = r[0].robo_alias;
                        date = JSON.parse(date);
                        date2 = JSON.parse(date2);
                        var date3 = {
                            start: date2.start,
                            end: moment(date2.end).endOf('month').format(DATE_FORMAT)
                        };
                        self.start_year = date.start;
                        self.end_year = date.end;
                        self.is_salesman = is_salesman;
                        self.u_all_income = u_all_income;
                        self.u_analytics = u_analytics;
                        self.show_expense = show_expense
                        self.graph_mode_cashflow = 'default'
                        self.graph_mode_income = 'default'
                        self.graph_mode_expenses = 'default'
                        self.graph_mode_invoices = 'default'
                        self.graph_mode_profit = 'default'

                        self.show_comparison_chart = show_comparison_chart;
                        self.chart = {
                            groupBy: {income: 'monthly', profit: 'monthly', cashflow: 'monthly'},
                            dates: {
                                    income: {start: date.start, end: date.end},
                                    incomeCompare: {start: date2.start, end: date2.end},
                                    expenses: {start: date.start, end: date.end},
                                    profit: {start: date.start, end: date.end},
                                    cashflow: {start: date.start, end: date.end},
                                    taxesTable: {start: date3.start, end: date3.end},
                                   }
                         };

                        if (premium_manager || free_manager){
                            self.robo_manager_rights = true;
                        }

                        if (premium_manager || free_manager || show_full_receivables_graph || all_expenses){
                            self.show_piechart_switch_buttons = true;
                        }

                        var all_menu_data = self.process_menu_data(menu);
                        self.menu_data = _.where(all_menu_data,{searchable: true});
                        self.no_menu_data = _.where(all_menu_data, {action: no_menu_action_id.toString()})[0];
//                        self.no_menu_data = self.issue_action;
                        self.state = self.get_initial_state();

                        if (self.robo_manager_rights || is_salesman || show_comparison_chart || show_expense){
                            return $.when(
                                self.rpc("/graph/cashflow/last_statement_closed_date")
                            ).then(function(uDate){
                                uDate = JSON.parse(uDate);
                                if (_.isObject(uDate)){
                                    var format = self.get_popup_date_format(uDate.display_date.date)
                                    var toBrowserTime = time.auto_str_to_date(uDate.display_date.date);
                                    self.last_statement_closed_date = moment(toBrowserTime).format(format);
                                    self.statement_old = (Math.abs(moment(toBrowserTime).diff(new Date(), 'days')) > 30)
                                    uDate.popup_data.forEach(function(element) {
                                      var format = self.get_popup_date_format(element.date)
                                      var toBrowserTime = time.auto_str_to_date(element.date);
                                      date = moment(toBrowserTime).format(format);
                                      element.date = date;
                                    });
                                    self.date_popup_data = uDate.popup_data;
                                }
                            });
                        }
                        else{
                            return $.when();
                        }
                    });

        },

        start: function () {
            var action_due_invoices = 'robo.open_extended_due_report';
            var action_all_invoices = 'robo.open_extended_all_report';
            var action_due_invoices_exp = 'robo.open_extended_due_report_exp';
            var action_forecast_chart_settings = 'robo.action_res_users_chart_settings_forecast';
            var action_all_invoices_exp = 'robo.open_extended_all_report_exp';
            var action_inc_aml = 'sl_general_report.action_account_move_line_income_chart';
            var action_exp_aml = 'sl_general_report.action_account_move_line_expense_chart';
            var self = this;
            self.attach_tooltip();
            self.attach_tooltip_aml_extra();
            return $.when(this._super.apply(this, arguments))
                .then(function(){
                    self.dragDropZone = new MultiDragDrop(self);
                    // var $dropPlace = self.$('.charts');
                    // return $.when(self.dragDropZone.insertBefore($dropPlace));
                    var $dropPlace = self.$('.robo-search'); //no security restrictions
                    return $.when(self.dragDropZone.insertAfter($dropPlace));
                })
                .then(function(){
                    // this.$input = this.$('input:visible');
                    var defs = [];
                    self.$input = self.$el.find('input');
                    self.$menu_search = self.$el.find('.search-box');
                    self.$menu_results = self.$el.find('.results > .list-unstyled');
                    //total_charts
                    self.$total_chartInvoices = self.$el.find('#chart-invoices .total-outstanding');
                    self.$total_chartIncome = self.$el.find('#chart-income .total-outstanding');
                    self.$total_chartIncomeCompare = self.$el.find('#chart-incomeCompare .total-outstanding');
                    self.$total_chartexpenses = self.$el.find('#chart-expenses .total-outstanding');
                    self.$total_chartProfit = self.$el.find('#chart-profit .total-outstanding');
                    self.$total_chartCashflow = self.$el.find('#chart-cashflow .total-outstanding');
                    self.$total_chartCashflow_forecast = self.$el.find('#chart-cashflow .total-outstanding-forecast');

                    defs.push(self.load_graph("chart-invoices", "bulletChart", {subtype: "invoices"}));
                    defs.push(self.load_graph("chart-income", "stackedAreaChart", {subtype: "income", freq: {monthly: true, quarterly: false}, dates: self.chart.dates.income}));
                    defs.push(self.load_graph("chart-incomeCompare", "pieChart", {subtype: "incomeCompare", dates: self.chart.dates.incomeCompare}));
                    defs.push(self.load_graph("chart-expenses", "pieChart", {subtype: "expenses", dates: self.chart.dates.expenses}));
                    defs.push(self.load_graph("chart-profit", "stackedAreaChart", {subtype: "profit", freq: {monthly: true, quarterly: false}, dates: self.chart.dates.profit}));
                    defs.push(self.load_graph("chart-cashflow", "Cashflow", {subtype: "cashflow" ,freq: {monthly: true, quarterly: false}, dates: self.chart.dates.cashflow}));
                    defs.push(self.load_graph("chart-taxesTable", "taxesTable", {subtype: "taxes", dates: self.chart.dates.taxesTable}));

                    self.$el.on('click', '#cashflow_settings', function(){
                        self.rpc("/web/action/load", { action_id: action_forecast_chart_settings}).done(function(result) {
                        if (_.isObject(result)) {
                            self.do_action(result,
                                {'clear_breadcrumbs': false,
                                on_close: function() {
                                    var start = moment().startOf('year').startOf('month').format(DATE_FORMAT);
                                    var end = moment().format(DATE_FORMAT);
                                    var selector = $('.js-info-cashflow')
                                    self.update_graph('start;end', selector, start+';'+end);
                                    },
                                });
                            }
                        });
                    });
                    self.$el.on('click', '.o_other_invoices.overdue', function(){
                        self.do_action(CHART_TO_ACTION_MAPPING['overdue'][self.graph_mode_invoices], CHART_RP_PARAMS)
                    });
                    self.$el.on('click', '.o_other_invoices.all', function(){
                        self.do_action(CHART_TO_ACTION_MAPPING['all'][self.graph_mode_invoices], CHART_RP_PARAMS)
                    });
                    self.$el.on('click', '.o_other_aml', function(){
                        self.do_action(CHART_TO_ACTION_MAPPING['aml'][self.graph_mode_invoices], CHART_RP_PARAMS)
                    });
                    self.$el.on('click', '.o_no_menu_data', function(e){
                                if (self.issue_action){
                                    e.preventDefault();
                                    self.issue_action.context = _.extend(pyeval.eval('context',self.issue_action.context), {'subject': self.$el.find('.search-form').val(), 'reason': 'edoc'});
                                    self.do_action(self.issue_action, {'clear_breadcrumbs': false});
                                }
                    });
                    self.preparePopover();
                    return $.when.apply($, defs);
            }).then(function(){
                // self.dragDropZone = new MultiDragDrop(self);
                // var $dropPlace = self.$('.charts');
                // return $.when(self.dragDropZone.insertBefore($dropPlace));
                    self.$('.search-box input').focusin();
            });
        },

        load_tax_table: function (data, format) {
            var futureTaxesTable = this.$el.find("#future_taxes_table");
            if (!futureTaxesTable) {
                return;
            }

            var month_names = [
                _t('January'),
                _t('February'),
                _t('March'),
                _t('April'),
                _t('May'),
                _t('June'),
                _t('July'),
                _t('August'),
                _t('September'),
                _t('October'),
                _t('November'),
                _t('December'),
            ];

            var today = new Date();

            for (var i = 0; i < data.length; i++) {
                var date = data[i].date;
                date = new Date(date);

                var day = date.getDate();
                var month = date.getMonth();
                var year = date.getFullYear();
                var month_name = month_names[month];
                var date_string = month_name + " " + year;

                data[i].date_string = date_string;
                data[i].day = day;

                var amount = format(data[i].amount.toFixed(2));

                if (data[i].currency_position == "after") {
                    var amount_string = amount + " " + data[i].currency_symbol;
                } else {
                    var amount_string = data[i].currency_symbol + " " + amount;
                }

                data[i].amount_string = amount_string;

                var time_difference = date.getTime() - today.getTime();
                var day_difference = time_difference / (1000 * 3600 * 24);

                day_difference = Math.round(day_difference);


                if (day_difference < 0) {
                    day_difference = Math.abs(day_difference);
                    var days_left_string = _t("Prieš") + " " + day_difference + " ";

                    if ((day_difference > 10 && day_difference < 20) || (day_difference % 10 === 0)) {
                        days_left_string += _t("dienų");
                    } else if (day_difference % 10 === 1) {
                        days_left_string += _t("dieną");
                    } else {
                        days_left_string += _t("dienas");
                    }
                } else if (day_difference > 0) {
                    var days_left_string = _t("Liko") + " " + day_difference + " ";

                    if ((day_difference > 10 && day_difference < 20) || (day_difference % 10 === 0)) {
                        days_left_string += _t("dienų");
                    } else if (day_difference % 10 === 1) {
                        days_left_string += _t("diena");
                    } else {
                        days_left_string += _t("dienos");
                    }
                } else {
                    var days_left_string = _t("Šiandien");
                }

                data[i].days_left_string = days_left_string;
            }

            futureTaxesTable.html(QWeb.render("futureTaxesTable", {
                tax_events: data,
                widget: this,
            }));
        },

        _tooltip_html: function(){
            return QWeb.render('bank-account-update.popup', {
            bank_accounts: this.date_popup_data,
            });
        },
        attach_tooltip: function(){
            var self = this;
            self.$el.find('.update-info').tooltip({
                html: true,
                delay: { show: 50, hide: 1000 },
                placement: 'right',
                container: '.update-info',
                title: function(){
                    return self._tooltip_html();
                },
            });
        },
        attach_tooltip_aml_extra: function(){
            var self = this;
            self.$el.find('.extra-expense-income-info').tooltip({
                html: true,
                delay: { show: 50, hide: 1000 },
                container: '.extra-expense-income-info',
                title: '',
            });
        },
        preparePopover: function(){
            var self = this;

            this.$el.find("[data-toggle=popover]").popover({
                title: _t('Pasirinkite laikotarpį'),
                placement: 'top',
                trigger: 'manual',
                html: true,
                template: '<div class="popover my-Popover" id="filter-popover"><div class="arrow"></div><div class="popover-title"></div><div class="popover-content"></div></div>'
            }).on('hide.bs.popover', function(){
                if (self.$el.find('#robo_datetimepicker1').data("DateTimePicker")){
                    self.$el.find('#robo_datetimepicker1').data("DateTimePicker").destroy();
                }
                if (self.$el.find('#robo_datetimepicker2').data("DateTimePicker")){
                    self.$el.find('#robo_datetimepicker2').data("DateTimePicker").destroy();
                }
            }).on('shown.bs.popover', function(){
                var dataTimePickerOptions = {
                    pickDate: true,
                    pickTime: false,
                    useMinutes: false,
                    useSeconds: false,
                    useCurrent: true,
                    calendarWeeks: true,
                    // minuteStepping: 1,
                    minDate: moment().subtract(NBR_OF_YEARS_IN_GRAPHS,'y'),
                    maxDate: moment().add(1,'y'),
                    showToday: true,
                    collapse: true,
                    language: moment.locale(),
                    // defaultDate: moment(),
                    disabledDates: false,
                    enabledDates: false,
                    icons: {},
                    useStrict: false,
                    direction: 'auto',
                    sideBySide: false,
                    daysOfWeekDisabled: [],
                     // widgetParent: '.pagalbininkas',
                    format: DATE_FORMAT,
                    pickerPosition: "bottom-left",
                };

                // var update_graph = function(whichDateInput, $selector, dateText){
                //     var myChartId, chartType, chartSubtype='', myFreq = {monthly: false, quarterly: false};
                //     if ($selector.closest('.js-info-income').length) {
                //         self.chart.dates.income[whichDateInput] = dateText;
                //         myChartId = 'income';
                //         chartType = 'stackedAreaChart';
                //         chartSubtype = 'income'
                //     }else if ($selector.closest('.js-info-expenses').length) {
                //         self.chart.dates.expenses[whichDateInput] = dateText;
                //         myChartId = 'expenses';
                //         chartType = 'pieChart';
                //     }else if ($selector.closest('.js-info-profit').length) {
                //         self.chart.dates.profit[whichDateInput] = dateText;
                //         myChartId = 'profit';
                //         chartType = 'stackedAreaChart';
                //     }
                //     else if ($selector.closest('.js-info-cashflow').length) {
                //         self.chart.dates.cashflow[whichDateInput] = dateText;
                //         myChartId = 'cashflow';
                //         chartType = 'Cashflow';
                //     }
                //
                //     self.chart.dates[myChartId][whichDateInput] = dateText;
                //     myFreq[self.chart.groupBy[myChartId]] = true;
                //     self.load_graph("chart-"+myChartId, chartType, {subtype: chartSubtype, freq: myFreq, dates: self.chart.dates[myChartId]});
                // }
                self.$el.find('#robo_datetimepicker1').datetimepicker(_.defaults({maxDate: self.end_year}, dataTimePickerOptions)).on('dp.change', function (selected) {
                    self.$el.find('#robo_datetimepicker2').data("DateTimePicker").setMinDate(selected.date);
                    self.update_graph('start', $(selected.currentTarget), selected.date.format(DATE_FORMAT));
                });
                 //Important! See issue #1075
                self.$el.find('#robo_datetimepicker2').datetimepicker(_.defaults({
                    minDate: self.start_year, //START_YEAR,
                    useCurrent: false
                }, dataTimePickerOptions)).on('dp.change', function (selected) {
                    self.$el.find('#robo_datetimepicker1').data("DateTimePicker").setMaxDate(selected.date);
                    self.update_graph('end', $(selected.currentTarget), selected.date.format(DATE_FORMAT));
                });
            }).on('click', function(e){
                e.stopPropagation(); //we must stop bubbling
                e.preventDefault();
                //kill other popovers
                var myId = this.id;
                self.$el.find("[data-toggle=popover]").each(function(){
                    if (this.id !== myId){
                        $(this).popover('hide');
                    }
                });

                var defaultSelection = {monthly: false, quarterly: false};
                defaultSelection[self.chart.groupBy[myId]] = true;
                if ($(e.target).closest('#income').length){
                  $(e.target).closest('[data-toggle=popover]').attr("data-content", QWeb.render('Chart.popover', {popover:
                      {
                          name:"income",
                          dates: true,
                          group: true,
                          defaultRadio: defaultSelection,
                          defaultDates: self.chart.dates[myId]
                      }}));
                }
                else if($(e.target).closest('#incomeCompare').length){
                    $(e.target).closest('[data-toggle=popover]').attr("data-content", QWeb.render('Chart.popover', {popover:
                        {
                            name:"incomeCompare",
                            dates: true,
                            group: false,
                            defaultRadio: defaultSelection,
                            defaultDates: self.chart.dates[myId]
                        }}));
                }
                else if($(e.target).closest('#profit').length){
                    $(e.target).closest('[data-toggle=popover]').attr("data-content", QWeb.render('Chart.popover', {popover:
                        {
                            name:"profit",
                            dates: true,
                            group: true,
                            defaultRadio: defaultSelection,
                            defaultDates: self.chart.dates[myId]
                        }}));
                }
                else if($(e.target).closest('#expenses').length){
                    $(e.target).closest('[data-toggle=popover]').attr("data-content", QWeb.render('Chart.popover', {popover:
                        {
                            name:"expenses",
                            dates: true,
                            group: false,
                            defaultDates: self.chart.dates[myId]
                        }}));
                }
                else if($(e.target).closest('#cashflow').length){
                    $(e.target).closest('[data-toggle=popover]').attr("data-content", QWeb.render('Chart.popover', {popover:
                        {
                            name:"cashflow",
                            dates: true,
                            group: true,
                            defaultRadio: defaultSelection,
                            defaultDates: self.chart.dates[myId]
                        }}));
                }

                $(this).popover('show');

            });
            self.$el.find('.js-popover-inside').on('change','.popover input[type=radio]',function(){
                var chartTypesList = ['income', 'profit', 'cashflow']
                var myChartId;
                myChartId = $(this).val();
                if (chartTypesList.includes(myChartId)){
                    var myFreq = {monthly: false, quarterly: false};
                    myFreq[this.id] = true;
                    self.chart.groupBy[myChartId] = this.id;
                    var chartName = myChartId == 'cashflow' ? 'Cashflow' : 'stackedAreaChart'
                    self.load_graph("chart-"+myChartId, chartName, {subtype: myChartId, freq: myFreq, dates: self.chart.dates[myChartId]});
                }
            });

            //hide popover on click not inside popover
            self.$el.on('click', function (e) {
                var $popover, $target = $(e.target);
                //do nothing if there was a click on popover content
                if ($target.hasClass('popover') || $target.closest('.popover').length) {
                    return;
                }
                self.$el.find('[data-toggle="popover"]').each(function () {
                    $popover = $(this);
                    //--new version
                    $popover.popover('hide');
                    //---old version: 2017-04-05
                    // if (!$popover.is(e.target) &&
                    //     $popover.has(e.target).length === 0 &&
                    //     self.$el.find('.popover').has(e.target).length === 0)
                    // {
                    //     $popover.popover('hide');
                    // } else {
                    //     $popover.popover('toggle');
                    // }
                });
            });
        },
        on_icon_close: function(e){
            //grandfather contains all search objects - two inputs for mobile and normal view
            this.$input.val('');
            this.$("input.search-form").trigger('input');

        },
        on_input_change: _.debounce(function (e) {
            if (!e.target.value) {
                this.$el.find(".search-container").removeClass("show-results");
                this.state = this.get_initial_state();
                this.state.is_searching = true;
            }
            else{
                this.$el.find(".search-container").removeClass("show-results").addClass("show-results");
            }
            this.$('.results .show-more').css('display', 'none');
            this.$('.results .show-less').css('display', 'none');

            this.update({search: e.target.value, focus: 0});
        },100),
        update: function (data) {
            var self = this;
            if (data.search) {
                // var options = {
                //     extract: function (el) {
                //         return el.label;
                //     }
                // };
                //var search_results = fuzzy.filter(data.search, this.menu_data, options);

                var options = {
                  include: ["score"],
                  // shouldSort: true,
                  // tokenize: true,
                  // matchAllTokens: true,
                  // findAllMatches: true,
                  threshold: 0.3,
                  location: 0,
                  distance: 20,
                  maxPatternLength: 50,
                  minMatchCharLength: 1,
                  // tokenSeparator:   /[ ,/]+/g,
                  keys: [
                      'name',
                  ]
                };

                //keep pattern not longer than
                data.search = self.convert_to_latin_name(data.search.toUpperCase());
                if (data.search.trim().length > 0) {
                    data.search = _.str.chop(data.search.trim(), options.maxPatternLength)[0];
                }
                data.search = _.uniq(data.search.toUpperCase().split(/[ ,/]+/g).sort());

                var search_results={};

                _.uniq(data.search).forEach(function(v, i){
                    var fuse = new Fuse(self.search_menu_words, options);
                    var current_search = fuse.search(v);
                    search_results[v]  =  {};
                    current_search.forEach(function(r, i){
                        var name = r.item.name,
                            id = r.item.id,
                            score = r.score;

                        if (search_results[v][id] === undefined){
                            search_results[v][id] = {name: name, score: score};
                        }
                        else{
                            if (search_results[v][id].score < score){
                                search_results[v][id] = {name: name, score: score};
                            }
                        }
                    });
                });

                var final_result = {};
                _.keys(search_results).forEach(function(pattern){
                    _.keys(search_results[pattern]).forEach(function(id){
                        if (final_result[id] === undefined){
                            final_result[id] = [search_results[pattern][id].name];
                        }
                        else{
                             final_result[id] = _.union([search_results[pattern][id].name], final_result[id]);
                        }
                    })
                });

                this.menu_data.forEach(function(m){
                   var id = m.id;
                   if (final_result[id] === undefined){
                      m.score = 0;
                   }
                   else {
                       m.score = final_result[id].length + m.seq;
                   }
                });

                var search_results = this.menu_data
                    .filter(function(x){return x.score > 0})
                    .sort(function(a,b){
                        return  b.score - a.score;
                    });

                // var results = _.map(search_results, function (result) {
                //     return self.menu_data[result.index];
                // });

                var results = search_results;

                if (results.length > 0) {
                    self.$el.find('.results').removeClass('nothing-found');
                    _.each(self.$el.children, function (el) {

                    });
                } else if(results.length == 0){
                    self.$el.find('.results').addClass('nothing-found');
                }

                this.state = _.extend(this.state, {
                    apps: _.where(results, {is_app: true}),
                    menu_items: _.where(results, {is_app: false}),
                    focus: results.length ? 0 : null,
                    is_searching: true,
                });
            }
            this.render();
        },
        render: function (options) {

            var partOfMenu, fullOfMenu;
            if (!options || !options.show_all) {
                if (this.state.menu_items.length > NBR_LINKS) {this.$('.results .show-more').css('display', 'block');}
                this.$('.results .show-less').css('display', 'none');
                fullOfMenu = this.state.menu_items;
                partOfMenu = this.state.menu_items.slice(0, NBR_LINKS);
                this.state = _.extend(this.state, {menu_items: partOfMenu});
                if (this.$menu_results){
                    this.$menu_results.html(QWeb.render('SearchField.Content', {widget: this}));
                }
                this.state = _.extend(this.state, {menu_items: fullOfMenu});
            }
            else{
                this.$('.results .show-more').css('display', 'none');
                this.$('.results .show-less').css('display', 'block');
                if (this.$menu_results.html){
                    this.$menu_results.html(QWeb.render('SearchField.Content', {widget: this}));
                }
            }
        },
        on_menuitem_click: function (e) {
            e.preventDefault();
            var action_id = $(e.currentTarget).data('action-id');
            if (action_id) {
                this.do_action(action_id, {clear_breadcrumbs: true});
            }
            // this.open_menu(_.findWhere(this.menu_data, {id: menu_id}));
        },
        // open_menu: function (menu) {
        //     this.trigger_up(menu.is_app ? 'app_clicked' : 'menu_clicked', {
        //         menu_id: menu.id,
        //         action_id: menu.action,
        //     });
        //     if (!menu.is_app) {
        //         core.bus.trigger('change_menu_section', menu.menu_id);
        //     }
        // },
        on_mouse_li: function(e){
            this.$(".results li.main-part.active").removeClass("active");
            //child start event
            $(e.currentTarget).addClass("active");

            //this.state.focus = $(e.target).index()+1;
        },
        on_keydown: function(event) {

            var class_no_menu_data= '.o_no_menu_data';
            var $listItems = this.$el.find(".results li.main-part");
            var $selected = $listItems.filter(".active");

            // var $no_result = $listItems.filter(class_no_menu_data);
            var $selected_no_menu_item = $selected.has(class_no_menu_data);

            var $current;

            var state = this.state;
            var elem_focused = $selected.length >0;

            if (!$listItems.length) return;

            var $input = this.$input;

            switch (event.which) {
                case $.ui.keyCode.DOWN:
                    event.preventDefault();
                    //$(window).scrollTop();
                    $listItems.removeClass('active');
                    if ( ! $selected.length || $selected.is(':last-child') ) {
                        $current = $listItems.eq(0);
                    }
                    else {
                        $current = $selected.next();
                    }
                    $current.addClass('active');
                    $current[0].scrollIntoView(false);
                    break;
                case $.ui.keyCode.TAB:
                    //event.preventDefault();
                    //var f = elem_focused ? (event.shiftKey ? -1 : 1) : 0;
                    //this.update({focus: f});
                    break;
                case $.ui.keyCode.UP:
                    event.preventDefault();
                    //$(window).scrollTop();
                    $listItems.removeClass('active');
                    if ( ! $selected.length || $selected.is(':first-child') ) {
                        //$current = $listItems.last();
                        this.$input.focus();
                    }
                    else {
                        $current = $selected.prev();
                        $current.addClass('active');
                        $current[0].scrollIntoView(false);
                    }

                    break;
                case $.ui.keyCode.ENTER:
                    if (!elem_focused && $listItems.length > 0){ //if enter pressed inside input field, select first item
                        $selected = $listItems.first();
                        $selected_no_menu_item = $selected.has(class_no_menu_data);
                        elem_focused = $selected.length >0;
                    }
                    if (elem_focused && $selected_no_menu_item.length === 0) {
                        var menus = state.menu_items;
                        var index = $($selected[0]).index();
                        // window.location = $selected.first().children().first().attr('href');
                        //ROBO: svarbu click, nes naudoja tip.js, kad persoktu step.
                        if ($selected.first().children().first().length > 0) {
                            $selected.first().children().first()[0].click(); //vanilla js
                        }
                    }else if (elem_focused && $selected_no_menu_item.length > 0){
                        if (this.issue_action){
                            this.issue_action.context = {'subject': this.$el.find('.search-form').val(), 'reason': 'edoc'};
                            this.do_action(this.issue_action, {'clear_breadcrumbs': true});
                        }
                    } else if (!elem_focused){
                        // alert('aha');
                    }
                    event.preventDefault();
                    return;
                case $.ui.keyCode.PAGE_DOWN:
                case $.ui.keyCode.PAGE_UP:
                    break;
                case $.ui.keyCode.ESCAPE:
                    this.$input.val('');
                    $(event.target).trigger("input");
                    break;
                default:
                    if (!this.$input.is(':focus')) {
                        this.$input.focus();
                    }
            }

        },
        paint_bulletChart: function () {
            d3.select("#chart-invoices .nv-range").attr("height", 40);
            d3.select("#chart-invoices .nv-measure").attr("height", 40).attr("y", 0).style('mask', 'url(#mask-stripe)');//.attr('color', '#FA405C');
            d3.select("#chart-invoices .nv-rangeAvg").remove();
            d3.select("#chart-invoices .nv-rangeMin").remove();
            d3.select("#chart-invoices .nv-markerTriangle").remove();
        },
        paint_cashflow: function(pos, div){
            d3.selectAll(pos + ' path.nv-point')
                .each(function(d,i){
                    //Is it possible :)?
                    if(d[0].cumCash< 0){
                        d3.select(this).style({
                            'fill':'#fed9de',
                            'stroke':'#FA405C'
                        });
                    }
                    else{
                       d3.select(this).style({
                            'fill':'white',
                            'stroke':'#85C51F'
                        });
                    }
                });
            d3.select(pos+ ' .nv-areaWrap path.nv-area').style('fill','url(#'+div+'_line-gradient)');
        },
        paint_profitChart: function(pos,div){
            d3.selectAll(pos + ' path.nv-point')
                .each(function(d,i){
                    if(d[0].cumInc - d[0].cumExp < 0){
                        d3.select(this).style({
                            'fill':'#fed9de',
                            'stroke':'#FA405C'
                        });
                    }
                    else{
                       d3.select(this).style({
                            'fill':'white',
                            'stroke':'#85C51F'
                        });
                    }
                });
            d3.select(pos+ ' .nv-areaWrap path.nv-area').style('fill','url(#'+div+'_line-gradient)');
                //.attr('style','fill:url(#'+div+'_line-gradient)');
            //d3.select(pos+ ' .nv-areaWrap path').attr({'fill':'url(#'+div+'_line-gradient)'});

        },
        update_interval_labels: function(){
            this.$('.js-info-income .income-date-interval').text(this.chart.dates.income.start + ' - ' + this.chart.dates.income.end);
            this.$('.js-info-incomeCompare .incomeCompare-date-interval').text(this.chart.dates.incomeCompare.start + ' - ' + this.chart.dates.incomeCompare.end);
            this.$('.js-info-expenses .expenses-date-interval').text(this.chart.dates.expenses.start + ' - ' + this.chart.dates.expenses.end);
            this.$('.js-info-profit .profit-date-interval').text(this.chart.dates.profit.start + ' - ' + this.chart.dates.profit.end);
            this.$('.js-info-cashflow .cashflow-date-interval').text(this.chart.dates.cashflow.start + ' - ' + this.chart.dates.cashflow.end);
            this.$('.js-info-tax-table .tax-table-date-interval').text(this.chart.dates.taxesTable.start + ' - ' + this.chart.dates.taxesTable.end);

        },
        load_graph: synchronized(function (div, chart_name, param) {

            var self = this;
            var def = $.Deferred();

            var margin = {top: 40, right: 50, bottom: 65, left: 40};
            var  is_screen_big = (config.device.size_class > config.device.SIZES.XS) || false;

            this.update_interval_labels();
            //number formats
            var SIprefix = '.3s';
            var separator=',.2f';
            var languageNumberSeparator = _translation.database.parameters.decimal_point;
            var languageNumberThousandsSeparator = _translation.database.parameters.thousands_sep;

            var spaceSeparatorFormat = function(number){
                var r = d3.format(separator)(number);
                if (r === undefined) return '';
                return r.replace(/,/g,languageNumberThousandsSeparator).replace(/\./g,languageNumberSeparator);
            }

            self.rpc('/pagalbininkas/get_graph_data', {
                chart_type: chart_name,
                chart_filter: {
                    subtype: param.subtype || '',
                    dates: param.dates || '',
                    expense_mode: this.graph_mode_expenses,
                    invoice_mode: this.graph_mode_invoices
                },
                is_screen_big: is_screen_big,
            }).done(function (r) {
                if (r && r!="false") {
                    var data = JSON.parse(r);
                    switch (chart_name) {
                        case "bulletChart":
                            new Model('res.users').call('check_chart_rp_amounts_mode').then(function(mode){
                                $('#invoices-mode-toggle').prop('checked', mode);
                            });
                            CHART_RP_PARAMS['additional_context'] = data.info.additional_context;
                            var height = 132;
                            if (self.graph_mode_invoices == 'default'){
                                self.$el.find('#chart-invoices .invoice_expense_outstanding').hide();
                                self.$el.find('#chart-invoices .invoice_income_outstanding').show();
                                self.$el.find('.invoice_expense_header').hide();
                                self.$el.find('.invoice_income_header').show();
                            }else{
                                self.$el.find('#chart-invoices .invoice_income_outstanding').hide();
                                self.$el.find('#chart-invoices .invoice_expense_outstanding').show();
                                self.$el.find('.invoice_income_header').hide();
                                self.$el.find('.invoice_expense_header').show();
                            }
                            self.$total_chartInvoices.html(QWeb.render('chart.total', {
                                total: roboUtils.human_value(data.info.total_outstanding, 1),
                                currency: data.info.currency
                            }));

                            if (data.info.show_aml_data){
                                self.$el.find('#chart-invoices .extra-expense-income-info').show();
                                self.$el.find('.extra-expense-income-info').tooltip().attr(
                                'data-original-title', QWeb.render('chart-invoices-extra.popup', {
                                                        name : data.info.aml_tooltip_header,
                                                        total: data.info.total_sum_ex,
                                                        currency: data.info.currency,
                                                        format: spaceSeparatorFormat,
                                                        nbrOfamls : data.info.total_count_ex,
                                                        is_screen_big : (config.device.size_class > config.device.SIZES.XS) || false,
                                                        }));
                            }else{
                                self.$el.find('#chart-invoices .extra-expense-income-info').hide();
                            }
                            if (!self.show_piechart_switch_buttons) {
                                self.$el.find('.js-info-invoices .btn-group').hide();
                            }
                            nv.addGraph(function () {

                                var chart = nv.models.roboBulletChart()
                                    .color('#FA405C')
                                    .margin(margin)
                                    .height(height)
                                    .ticks(3)
                                    .tickFormat(function(d){return d3.format("s")(d)})
                                    .noData("")
                                    // .duration(2000)
                                    ;

                                // chart.tooltip = nv.models.tooltip_robo_bullet();
                                chart.tooltip.chartContainer('#chart-invoices');
                                chart.tooltip.hideDelay(2000);
                                chart.tooltip.classes('robo-bullet-pointer');

                                chart.tooltip.contentGenerator(function (d) {
                                    var myProperty = d.label[1];
                                    var total_count;
                                    if (myProperty === 'overdue'){
                                        total_count = data.info.overdue_count;
                                    }
                                    else {
                                        total_count = data.info.total_count;
                                    }
                                    var myFilteredData = _.filter(data.info.invoices,
                                                                            function(x){
                                                                                return x[myProperty];
                                                                            }).sort(function(a,b){return b.sum-a.sum});

                                     var bottomLineCompare = function(a,b){
                                        if (a.bottom_line){
                                            return 1
                                        }
                                        else{
                                            return b.sum - a.sum
                                        }
                                    };

                                    return QWeb.render('chart-invoices.popup', {
                                                                        invoices: myFilteredData.slice(0,6).sort(bottomLineCompare),
                                                                        name : d.label[0],
                                                                        total: d.label[2],
                                                                        currency: data.info.currency,
                                                                        format: spaceSeparatorFormat,
                                                                        nbrOfInvoices : total_count,
                                                                        type: myProperty,
                                                                        }
                                            );
                                });

                                chart.tooltip.gravity("robo_center");
                                chart.tooltip.position(function() {
                                    var nvRangeNode = d3.select("#chart-invoices rect.nv-range").node();
                                    var left_middle, svgRect, top_down;
                                    if (nvRangeNode) {
                                        svgRect = nvRangeNode.getBoundingClientRect();
                                    }
                                    if (svgRect) {
                                       left_middle = svgRect.right/ 2 + svgRect.left / 2;
                                       top_down = svgRect.top;
                                    }
                                    return {
                                        left: d3.event !== null ? left_middle : 0,
                                        top: d3.event !== null ? top_down : 0
                                    };
                                });

                                var svg = d3.select("#" + div + " svg");

                                svg.datum(data.chart_data);
                                svg.transition(0).duration(100);
                                chart(svg);

                                self.paint_bulletChart();
                                if (self.to_remove[0]){
                                    nv.utils.offWindowResize(self.to_remove[0]);
                                }
                                self.to_remove[0] = chart.update;

                                nv.utils.offWindowResize(self.paint_bulletChart);

                                nv.utils.onWindowResize(chart.update);
                                nv.utils.onWindowResize(self.paint_bulletChart);

                                return chart;
                            });
                            break;
                        case "pieChart":
                            if (param.subtype && param.subtype == 'expenses') {

                                if (self.graph_mode_expenses == 'default'){
                                self.$el.find('#chart-expenses .pieChart-legend').html(
                                QWeb.render('pieChart.legend', {
                                    expenses: data.chart_data,
                                    currency: data.info.currency,
                                    // format: function(f){
                                    //         var r = d3.format(SIprefix)(f);
                                    //         if (r === undefined) return '';
                                    //         return r.replace(".",languageNumberSeparator);
                                    // },
                                    format: function(value){
                                        return roboUtils.human_value(value, 1);
                                    },
                                    is_screen_big: is_screen_big,
                                })
                            );
                            //tooltips for classes of expences
                            self.$el.find("#chart-expenses .pieChart-legend i[class^='icon-']").each(function(i,el){
                                $(el).off();
                                $(el).tooltip();
                            });
                            self.$el.find("#forecast-toggle-box").each(function(i,el){
                                $(el).off();
                                $(el).tooltip();
                            });

                            self.$el.on('click', "#chart-expenses div[class^='legend-item']", function(k){
                                    var date_str = $("h4.expenses-date-interval").text();
                                    var cat_id = $(this).attr('data-id');
                                    if (cat_id != 'Other'){
                                        return (new Model('account.invoice')).call('get_invoice_front_action', [cat_id, date_str]).then(function(action){
                                        self.do_action(action, {'clear_breadcrumbs': false});
                                        });
                                    }
                            });

                            self.$total_chartexpenses.html(QWeb.render('chart.total', {
                                    // total: d3.format(SIprefix)(data.info.total).replace(".",languageNumberSeparator),
                                    total: roboUtils.human_value(data.info.total, 2),
                                    currency: data.info.currency
                            }));

                                nv.addGraph(function () {
                                var chart = nv.models.pieChart()
                                    .x(function (d) {
                                        return d.label
                                    })
                                    .y(function (d) {
                                        return d.value
                                    })
                                    .showLabels(false)     //Display pie labels
                                    .labelThreshold(.05)  //Configure the minimum slice size for labels to show up
                                    .labelType("percent") //Configure what type of data to show in the label. Can be "key", "value" or "percent"
                                    .donut(true)          //Turn on Donut mode. Makes pie chart look tasty!
                                    .donutRatio(0.60)     //Configure how big you want the donut hole size to be.
                                   // .height(300)
                                    .width(300)
                                    .showLegend(false)
                                     .margin({top: 0, right: 50, bottom: 0, left: 0})
                                    .noData("")
                                    .duration(500)
                                    ;

                                chart.tooltip.contentGenerator(function (d) {
                                    return QWeb.render('chart-expenses.popup',
                                        {
                                           color: d.data.color,
                                           name : d.data.name,
                                           value: d.data.value,
                                           currency: data.info.currency,
                                           format: spaceSeparatorFormat,
                                        }
                                    );
                                });
                                chart.tooltip.valueFormatter(spaceSeparatorFormat);
                                chart.tooltip.chartContainer('#chart-expenses');


                                $("#" + div + " svg").html('<defs> </defs>');
                                $('.pieChart').css('float', 'left');
                                $("#" + div).removeClass('expenses-bars');
                                var svg = d3.select("#" + div + " svg");
                                svg.datum(_.filter(data.chart_data, function(r){ return (r.value) && (r.value > 0)}));
                                svg.transition().duration(500);
                                chart(svg);
                                $("#" + div + " svg").addClass('income_pie');
                                if (self.to_remove[2]){
                                    nv.utils.offWindowResize(self.to_remove[2]);
                                }
                                self.to_remove[2] = chart.update;

                                nv.utils.onWindowResize(chart.update);
                                // nv.utils.onWindowResize(function(){
                                //     chart.update();
                                // });

                                return chart;
                            });

                                }

                                else if (self.graph_mode_expenses == 'accumulated'){


                                    var marginX = {top: 40, right: 50, bottom: 65, left: 50};
                                    self.$total_chartexpenses.html(QWeb.render('chart.total', {
                                            // total: d3.format(SIprefix)(data.info.total).replace(".",languageNumberSeparator),
                                            total: roboUtils.human_value(data.info.total, 2),
                                            currency: data.info.currency
                                    }));
                                    nv.addGraph(function () {

                                var height = 150;
                                var hasData = data.chart_data[0].values.length;
                                if (hasData) {
                                    height = 350;
                                    self.$("#" + div + " svg").css('height','350px'); // jquery vs d3?
                                }

                                var chart = nv.models.stackedAreaChart()
                                    .x(function (d) {
                                        return d.date
                                    })
                                    .y(function (d) {
                                        return d.cumExp
                                    })
                                    .showLegend(false)
                                    .showControls(false)
                                    .showYAxis(true)
                                    .showXAxis(true)
                                    .margin(marginX)
                                    .height(height)
                                    .duration(500)
                                    .noData("")
                                    // .clipRadius(10)
                                    ;

                                if (param.subtype && param.subtype == 'income') {
                                    chart.tooltip.chartContainer('#chart-income');
                                }
                                else{
                                    chart.tooltip.chartContainer('#chart-profit');
                                }

                                var months = [_t("Sau."), _t("Vas."), _t("Kov."), _t("Bal."), _t("Geg."), _t("Bir."),
                                     _t("Lie."), _t("Rgp."), _t("Rgs."), _t("Spl."), _t("Lap."), _t("Grd.")];

                                var quarters = ['Q1','Q2','Q3','Q4'];

                                chart.xScale(d3.time.scale());

                                var getPeriodName = function(d){
                                        return months[(new Date(d)).getMonth()]
                                }

                                chart.tooltip.contentGenerator(function (d) {

                                    return QWeb.render(div+'.popup-accumulated', {                                                       income_YTD: d.point.cumInc,
                                                        expenses_curr: d.point.exp,
                                                        expenses_YTD: d.point.cumExp,
                                                        curr_date: getPeriodName(d.point.date),
                                                        YTD_date: getPeriodName(d.series[0].values[0].date), //get first by date element in graph. Data sorted before.
                                                        currency: data.info.currency,
                                                        format: spaceSeparatorFormat
                                            });
                                });

                                _.each(data.chart_data[0].values.sort(function(a, b){return a.date-b.date;}),
                                        function(element, index, list){
                                            if (index) {
                                                    element.cumExp = list[index-1].cumExp + element.exp;
                                            }
                                            else {
                                                element.cumExp = element.exp;
                                            }
                                            element.color = CHART_POSITIVE_COLOR;
                                        }
                                )

                                //to color
                                var max = 0, min=0;
                                _.each(data.chart_data[0].values,
                                    function(element){
                                        if (min > element.cumInc - element.cumExp){
                                            min = element.cumInc - element.cumExp
                                        }
                                        if (max < element.cumInc - element.cumExp){
                                            max = element.cumInc - element.cumExp
                                        }
                                    }
                                )

                                var gradData, coef;

                                if (min >= 0){
                                    gradData = [
                                        {offset: "0", class: "positive"},
                                        {offset: "100%", class: "positive"}
                                    ]
                                }
                                else{
                                    if (max <= 0){
                                        gradData = [
                                            {offset: "0", class: "negative"},
                                            {offset: "100%", class: "negative"}
                                        ]
                                    }
                                    else{
                                        coef = (100*max/(max-min)).toFixed(2);
                                        gradData = [
                                            {offset: "0", class: "positive"},
                                            {offset: coef+"%", class: "positive"},
                                            {offset: coef+"%", class: "negative"},
                                            {offset: "100%", class: "negative"}
                                        ]
                                    }
                                }

                                chart.yAxis
                                    .showMaxMin(false)
                                    .tickFormat( function(d) {
                                        return d3.format("s")(d)
                                    })
                                    .tickPadding(10)
                                    .ticks(3);
                                chart.xAxis
                                    .tickFormat(function(d) {
                                        //return d3.time.format('%y-%m')(new Date(d)); //2016-01 format
                                        return getPeriodName(d);
                                    });

                                //area positive - negative
                                // if (!type) {
                                    //remove previous linearGradient

                                    $("#" + div + " svg").html('<defs> </defs>');
                                    self.$el.find('#chart-expenses .pieChart-legend').html('');
                                    $('#chart-expenses svg.nvd3-svg').css('width', '');
                                    $('.pieChart').css('float', '');

                                    $("#" + div).addClass('expenses-bars');
                                    d3.select("#" + div + " svg defs")
                                        .append('linearGradient') //remove previous gradient
                                        .attr("id", div +"_line-gradient")
                                        .attr("x1", '0%').attr("y1", '0%')
                                        .attr("x2", '0%').attr("y2", '100%')
                                        .selectAll("stop")
                                        .data(gradData)
                                        .enter().append("stop")
                                        .attr("offset", function (d) {
                                            return d.offset;
                                        })
                                        .attr("class", function (d) {
                                            return d.class;
                                        });
                                // }

                                //on chart click repaint linear gradient
                                chart.dispatch.on = function(){
                                   self.paint_profitChart("#" + div + " svg", div);
                                };
                                // self.paint_profitChart("#" + div + " svg", div);

                                var svg = d3.select("#" + div + " svg");
                                svg.datum(data.chart_data);
                                svg.transition().duration(500);
                                chart(svg);
                                // d3.select("#" + div + " svg")
                                //     .datum(data.chart_data)
                                //     .call(chart);

                               // if (param.doNotPushForResize){ return chart;}
                               var i = 1;//income
                               if (!param.subtype) {i =3};//profit

                               if (self.to_remove[i]){
                                    nv.utils.offWindowResize(self.to_remove[i]);
                               }
                               self.to_remove[i] = chart.update;
                               // nv.utils.offWindowResize(self.paint_profitChart);


                               nv.utils.onWindowResize(chart.update);


                               //  nv.utils.onWindowResize(function(){
                               //      chart.update();
                               //      // self.paint_profitChart("#" + div + " svg", div);
                               //  });

                                return chart;
                            });
                                }

                                else{

                                    var marginX = {top: 40, right: 50, bottom: 65, left: 50};
                                    self.$total_chartexpenses.html(QWeb.render('chart.total', {
                                            // total: d3.format(SIprefix)(data.info.total).replace(".",languageNumberSeparator),
                                            total: roboUtils.human_value(data.info.total, 2),
                                            currency: data.info.currency
                                    }));
                                    nv.addGraph(function () {

                                var height = 150;
                                var hasData = data.chart_data[0].values.length;
                                if (hasData) {
                                    height = 350;
                                    self.$("#" + div + " svg").css('height','350px'); // jquery vs d3?
                                }

                                var chart = nv.models.discreteBarChart()
                                    .x(function (d) {
                                        return d.date
                                    })
                                    .y(function (d) {
                                        return d.cumExp
                                    })
                                    .showYAxis(true)
                                    .showXAxis(true)
                                    .margin(marginX)
                                    .height(height)
                                    .duration(500)
                                    .noData("")
                                    ;


                                chart.tooltip.chartContainer('#chart-expenses');

                                var months = [_t("Sau."), _t("Vas."), _t("Kov."), _t("Bal."), _t("Geg."), _t("Bir."),
                                     _t("Lie."), _t("Rgp."), _t("Rgs."), _t("Spl."), _t("Lap."), _t("Grd.")];

                                var quarters = ['Q1','Q2','Q3','Q4'];

                                var getPeriodName = function(d){
                                   return months[(new Date(d)).getMonth()]

                                }

                                chart.tooltip.contentGenerator(function (d) {

                                    return QWeb.render(div+'.popup-non-accumulated', {
                                                        expenses_YTD: d.data.cumExp,
                                                        curr_date: getPeriodName(d.data.date),
                                                        currency: data.info.currency,
                                                        format: spaceSeparatorFormat,
                                                        percentage: d.data.percentage,
                                            });
                                });

                                _.each(data.chart_data[0].values.sort(function(a, b){return a.date-b.date;}),
                                        function(element, index, list){
                                                element.cumExp = element.exp;
                                                element.color = CHART_POSITIVE_COLOR;
                                        }
                                )

                                //to color
                                var max = 0, min=0;
                                _.each(data.chart_data[0].values,
                                    function(element){
                                        if (min > element.cumInc - element.cumExp){
                                            min = element.cumInc - element.cumExp
                                        }
                                        if (max < element.cumInc - element.cumExp){
                                            max = element.cumInc - element.cumExp
                                        }
                                    }
                                )

                                var gradData, coef;

                                if (min >= 0){
                                    gradData = [
                                        {offset: "0", class: "positive"},
                                        {offset: "100%", class: "positive"}
                                    ]
                                }
                                else{
                                    if (max <= 0){
                                        gradData = [
                                            {offset: "0", class: "negative"},
                                            {offset: "100%", class: "negative"}
                                        ]
                                    }
                                    else{
                                        coef = (100*max/(max-min)).toFixed(2);
                                        gradData = [
                                            {offset: "0", class: "positive"},
                                            {offset: coef+"%", class: "positive"},
                                            {offset: coef+"%", class: "negative"},
                                            {offset: "100%", class: "negative"}
                                        ]
                                    }
                                }

                                chart.yAxis
                                    .showMaxMin(false)
                                    .tickFormat( function(d) {
                                        return d3.format("s")(d)
                                    })
                                    .tickPadding(10)
                                    .ticks(3);
                                chart.xAxis
                                    .tickFormat(function(d) {
                                        //return d3.time.format('%y-%m')(new Date(d)); //2016-01 format
                                        return getPeriodName(d);
                                    });

                                //area positive - negative
                                // if (!type) {
                                    //remove previous linearGradient

                                    $("#" + div + " svg").html('<defs> </defs>');
                                    self.$el.find('#chart-expenses .pieChart-legend').html('');
                                    $('#chart-expenses svg.nvd3-svg').css('width', '');
                                    $('.pieChart').css('float', '');
                                    $("#" + div).addClass('expenses-bars');

                                    d3.select("#" + div + " svg defs")
                                        .append('linearGradient') //remove previous gradient
                                        .attr("id", div +"_line-gradient")
                                        .attr("x1", '0%').attr("y1", '0%')
                                        .attr("x2", '0%').attr("y2", '100%')
                                        .selectAll("stop")
                                        .data(gradData)
                                        .enter().append("stop")
                                        .attr("offset", function (d) {
                                            return d.offset;
                                        })
                                        .attr("class", function (d) {
                                            return d.class;
                                        });
                                // }

                                //on chart click repaint linear gradient
                                chart.dispatch.on = function(){
                                   self.paint_profitChart("#" + div + " svg", div);
                                };
                                // self.paint_profitChart("#" + div + " svg", div);

                                var svg = d3.select("#" + div + " svg");
                                svg.datum(data.chart_data);
                                svg.transition().duration(500);
                                chart(svg);
                                // d3.select("#" + div + " svg")
                                //     .datum(data.chart_data)
                                //     .call(chart);

                               // if (param.doNotPushForResize){ return chart;}
                               var i = 1;//income
                               if (!param.subtype) {i =3};//profit

                               if (self.to_remove[i]){
                                    nv.utils.offWindowResize(self.to_remove[i]);
                               }
                               self.to_remove[i] = chart.update;
                               // nv.utils.offWindowResize(self.paint_profitChart);


                               nv.utils.onWindowResize(chart.update);


                               //  nv.utils.onWindowResize(function(){
                               //      chart.update();
                               //      // self.paint_profitChart("#" + div + " svg", div);
                               //  });

                                return chart;
                            });

                                }

                            }
                            else if (param.subtype && param.subtype == 'incomeCompare') {
                                self.$el.find('#chart-incomeCompare .pieChart-legend-2').html(
                                    QWeb.render('pieChart.legend.2', {
                                        expenses: data.chart_data,
                                        currency: data.info.currency,
                                        format: function(value){
                                            return roboUtils.human_value(value, 1);
                                        },
                                        is_screen_big: is_screen_big,
                                    })
                                );
                                //tooltips for classes of expences
                                self.$el.find("#chart-incomeCompare .pieChart-legend-2 i[class^='icon-']").each(function(i,el){
                                    $(el).off();
                                    $(el).tooltip();
                                });
                                self.$el.find("#forecast-toggle-box").each(function(i,el){
                                    $(el).off();
                                    $(el).tooltip();
                                });

                                self.$total_chartIncomeCompare.html(QWeb.render('chart.total', {
                                        total: roboUtils.human_value(data.info.total, 2),
                                        currency: data.info.currency
                                }));

                                nv.addGraph(function () {
                                    var chart = nv.models.pieChart()
                                        .x(function (d) {
                                            return d.label
                                        })
                                        .y(function (d) {
                                            return d.value
                                        })
                                        .showLabels(false)     //Display pie labels
                                        .labelThreshold(.05)  //Configure the minimum slice size for labels to show up
                                        .labelType("percent") //Configure what type of data to show in the label. Can be "key", "value" or "percent"
                                        .donut(true)          //Turn on Donut mode. Makes pie chart look tasty!
                                        .donutRatio(0.60)     //Configure how big you want the donut hole size to be.
                                        .width(300)
                                        .showLegend(false)
                                         .margin({top: 0, right: 50, bottom: 0, left: 0})
                                        .noData("")
                                        .duration(500)
                                        ;

                                    chart.tooltip.contentGenerator(function (d) {
                                        return QWeb.render('chart-incomeCompare.popup',
                                            {
                                               color: d.data.color,
                                               name : d.data.name,
                                               value: d.data.value,
                                               currency: data.info.currency,
                                               format: spaceSeparatorFormat,
                                            }
                                        );
                                    });
                                    chart.tooltip.valueFormatter(spaceSeparatorFormat);
                                    chart.tooltip.chartContainer('#chart-incomeCompare');

                                    var svg = d3.select("#" + div + " svg");
                                    svg.datum(_.filter(data.chart_data, function(r){ return (r.value) && (r.value > 0)}));
                                    svg.transition().duration(500);
                                    chart(svg);

                                    if (self.to_remove[2]){
                                        nv.utils.offWindowResize(self.to_remove[2]);
                                    }
                                    self.to_remove[2] = chart.update;

                                    nv.utils.onWindowResize(chart.update);

                                    return chart;
                                });
                            }
                            break;
                        case "stackedAreaChart":
                            new Model('res.users').call('check_income_mode').then(function(income_mode){
                                $('#income-mode-toggle').prop('checked', income_mode);
                            });
                            var marginX = {top: 40, right: 50, bottom: 65, left: 50};
                            var show_profit;
                            //type - Income or Profit : subtype === true ==> income
                            if (param.subtype && param.subtype == 'income') {
                                show_profit = false;
                                self.$total_chartIncome.html(QWeb.render('chart.total', {
                                    // total: d3.format(SIprefix)(data.info.total_income).replace(".",languageNumberSeparator),
                                    total: roboUtils.human_value(data.info.total_income,1),
                                    currency: data.info.currency
                                }));

                                if (self.graph_mode_income == 'non_accumulated'){
                                    var non_accumulated = true;
                                }
                                else{
                                    var non_accumulated = false;
                                }

                            }
                            else {
                                show_profit = true;
                                self.$total_chartProfit.html(QWeb.render('chart.total', {
                                    // total: d3.format(SIprefix)(data.info.total_profit).replace(".",languageNumberSeparator),
                                    total: roboUtils.human_value(data.info.total_profit,1),
                                    currency: data.info.currency
                                }));


                                if (self.graph_mode_profit == 'non_accumulated'){
                                    var non_accumulated = true;
                                }
                                else{
                                    var non_accumulated = false;
                                }
                            }

                            if (non_accumulated){

                                nv.addGraph(function () {

                                var height = 150;
                                var hasData = data.chart_data[0].values.length;
                                if (hasData) {
                                    height = 350;
                                    self.$("#" + div + " svg").css('height','350px'); // jquery vs d3?
                                }

                                var chart = nv.models.discreteBarChart()
                                    .x(function (d) {
                                        return d.date
                                    })
                                    .y(function (d) {
                                        return d.cumInc - d.cumExp
                                    })
                                    .showYAxis(true)
                                    .showXAxis(true)
                                    .margin(marginX)
                                    .height(height)
                                    .duration(500)
                                    .noData("")
                                    ;

                                if (param.subtype && param.subtype == 'income') {
                                    chart.tooltip.chartContainer('#chart-income');
                                }
                                else{
                                    chart.tooltip.chartContainer('#chart-profit');
                                }

                                var months = [_t("Sau."), _t("Vas."), _t("Kov."), _t("Bal."), _t("Geg."), _t("Bir."),
                                     _t("Lie."), _t("Rgp."), _t("Rgs."), _t("Spl."), _t("Lap."), _t("Grd.")];

                                var quarters = ['Q1','Q2','Q3','Q4'];

                                var getPeriodName = function(d){
                                    if (param.freq.monthly){
                                        return months[(new Date(d)).getMonth()]
                                    }
                                    else if(param.freq.quarterly){
                                        return quarters[Math.floor((new Date(d)).getMonth() / 3)];
                                    }
                                }

                                chart.tooltip.contentGenerator(function (d) {

                                    return QWeb.render(div+'.popup-non-accumulated', {
                                                        income_YTD: d.data.cumInc,
                                                        expenses_YTD: d.data.cumExp,
                                                        profit: d.data.cumInc - d.data.cumExp,
                                                        curr_date: getPeriodName(d.data.date),
                                                        currency: data.info.currency,
                                                        format: spaceSeparatorFormat,
                                                        percentage: d.data.percentage,

                                            });
                                });

                                 //regroup data quarterly if needed
                                if (param.freq.quarterly){
                                        var newValues=[], newIndex;
                                        var quarter;
                                       _.each(data.chart_data[0].values,
                                            function(element,index){
                                                if (index){
                                                    if(quarter !== getPeriodName(element.date)) {
                                                        newValues.push(element);
                                                        newIndex++;
                                                        quarter = getPeriodName(element.date);
                                                    }
                                                    else{
                                                        newValues[newIndex].inc += element.inc;
                                                        newValues[newIndex].exp += element.exp;
                                                    }
                                                }
                                                else{
                                                    newValues.push(element);
                                                    quarter = getPeriodName(element.date);
                                                    newIndex = 0;
                                                }
                                        });

                                        data.chart_data[0].values = newValues;
                                }
                                //sortBy data, and prepare acumulated sum for display
                                _.each(data.chart_data[0].values.sort(function(a, b){return a.date-b.date;}),
                                        function(element, index, list){
                                        element.cumInc = element.inc;
                                        element.cumExp = element.exp;

                                        if (param.subtype && param.subtype == 'income'){
                                            element.color = pickChartColor(element.cumInc);
                                        }
                                        else{
                                            element.color = pickChartColor(element.cumInc - element.cumExp);
                                        }
                                    }
                                )

                                //to color
                                var max = 0, min=0;
                                _.each(data.chart_data[0].values,
                                    function(element){
                                        if (min > element.cumInc - element.cumExp){
                                            min = element.cumInc - element.cumExp
                                        }
                                        if (max < element.cumInc - element.cumExp){
                                            max = element.cumInc - element.cumExp
                                        }
                                    }
                                )

                                var gradData, coef;

                                if (min >= 0){
                                    gradData = [
                                        {offset: "0", class: "positive"},
                                        {offset: "100%", class: "positive"}
                                    ]
                                }
                                else{
                                    if (max <= 0){
                                        gradData = [
                                            {offset: "0", class: "negative"},
                                            {offset: "100%", class: "negative"}
                                        ]
                                    }
                                    else{
                                        coef = (100*max/(max-min)).toFixed(2);
                                        gradData = [
                                            {offset: "0", class: "positive"},
                                            {offset: coef+"%", class: "positive"},
                                            {offset: coef+"%", class: "negative"},
                                            {offset: "100%", class: "negative"}
                                        ]
                                    }
                                }

                                chart.yAxis
                                    .showMaxMin(false)
                                    .tickFormat( function(d) {
                                        return d3.format("s")(d)
                                    })
                                    .tickPadding(10)
                                    .ticks(3);
                                chart.xAxis
                                    .tickFormat(function(d) {
                                        return getPeriodName(d);
                                    });

                                    $("#" + div + " svg").html('<defs> </defs>');

                                    d3.select("#" + div + " svg defs")
                                        .append('linearGradient') //remove previous gradient
                                        .attr("id", div +"_line-gradient")
                                        .attr("x1", '0%').attr("y1", '0%')
                                        .attr("x2", '0%').attr("y2", '100%')
                                        .selectAll("stop")
                                        .data(gradData)
                                        .enter().append("stop")
                                        .attr("offset", function (d) {
                                            return d.offset;
                                        })
                                        .attr("class", function (d) {
                                            return d.class;
                                        });
                                chart.dispatch.on = function(){
                                   self.paint_profitChart("#" + div + " svg", div);
                                };

                                var svg = d3.select("#" + div + " svg");
                                svg.datum(data.chart_data);
                                svg.transition().duration(500);
                                chart(svg);

                               var i = 1;
                               if (!param.subtype) {i =3};
                               if (self.to_remove[i]){
                                    nv.utils.offWindowResize(self.to_remove[i]);
                               }
                               self.to_remove[i] = chart.update;


                               nv.utils.onWindowResize(chart.update);
                                return chart;

                            });

                                }else{

                            nv.addGraph(function () {

                                var height = 150;
                                var hasData = data.chart_data[0].values.length;
                                if (hasData) {
                                    height = 350;
                                    self.$("#" + div + " svg").css('height','350px'); // jquery vs d3?
                                }

                                var chart = nv.models.stackedAreaChart()
                                    .x(function (d) {
                                        return d.date
                                    })
                                    .y(function (d) {
                                        return d.cumInc - d.cumExp
                                    })
                                    .showLegend(false)
                                    .showControls(false)
                                    .showYAxis(true)
                                    .showXAxis(true)
                                    .margin(marginX)
                                    .height(height)
                                    .duration(500)
                                    .noData("")
                                    // .clipRadius(10)
                                    ;

                                if (param.subtype && param.subtype == 'income') {
                                    chart.tooltip.chartContainer('#chart-income');
                                }
                                else{
                                    chart.tooltip.chartContainer('#chart-profit');
                                }

                                var months = [_t("Sau."), _t("Vas."), _t("Kov."), _t("Bal."), _t("Geg."), _t("Bir."),
                                     _t("Lie."), _t("Rgp."), _t("Rgs."), _t("Spl."), _t("Lap."), _t("Grd.")];

                                var quarters = ['Q1','Q2','Q3','Q4'];

                                chart.xScale(d3.time.scale());

                                var getPeriodName = function(d){
                                    if (param.freq.monthly){
                                        return months[(new Date(d)).getMonth()]
                                    }
                                    else if(param.freq.quarterly){
                                        return quarters[Math.floor((new Date(d)).getMonth() / 3)];
                                    }
                                }

                                chart.tooltip.contentGenerator(function (d) {

                                    return QWeb.render(div+'.popup', {
                                                        income_curr: d.point.inc,
                                                        income_YTD: d.point.cumInc,
                                                        expenses_curr: d.point.exp,
                                                        expenses_YTD: d.point.cumExp,
                                                        show_profit: show_profit,
                                                        curr_date: getPeriodName(d.point.date),
                                                        YTD_date: getPeriodName(d.series[0].values[0].date), //get first by date element in graph. Data sorted before.
                                                        currency: data.info.currency,
                                                        format: spaceSeparatorFormat
                                            });
                                });

                                //regroup data quarterly if needed
                                if (param.freq.quarterly){
                                        var newValues=[], newIndex;
                                        var quarter;
                                       _.each(data.chart_data[0].values,
                                            function(element,index){
                                                if (index){
                                                    if(quarter !== getPeriodName(element.date)) {
                                                        newValues.push(element);
                                                        newIndex++;
                                                        quarter = getPeriodName(element.date);
                                                    }
                                                    else{
                                                        newValues[newIndex].inc += element.inc;
                                                        newValues[newIndex].exp += element.exp;
                                                    }
                                                }
                                                else{
                                                    newValues.push(element);
                                                    quarter = getPeriodName(element.date);
                                                    newIndex = 0;
                                                }
                                        });

                                        data.chart_data[0].values = newValues;
                                }
                                //sortBy data, and prepare acumulated sum for display
                                _.each(data.chart_data[0].values.sort(function(a, b){return a.date-b.date;}),
                                        function(element, index, list){
                                            if (index) {
                                                    element.cumInc = list[index-1].cumInc + element.inc;
                                                    element.cumExp = list[index-1].cumExp + element.exp;
                                            }
                                            else {
                                                element.cumInc = element.inc;
                                                element.cumExp = element.exp;
                                            }
                                        }
                                )

                                //to color
                                var max = 0, min=0;
                                _.each(data.chart_data[0].values,
                                    function(element){
                                        if (min > element.cumInc - element.cumExp){
                                            min = element.cumInc - element.cumExp
                                        }
                                        if (max < element.cumInc - element.cumExp){
                                            max = element.cumInc - element.cumExp
                                        }
                                    }
                                )

                                var gradData, coef;

                                if (min >= 0){
                                    gradData = [
                                        {offset: "0", class: "positive"},
                                        {offset: "100%", class: "positive"}
                                    ]
                                }
                                else{
                                    if (max <= 0){
                                        gradData = [
                                            {offset: "0", class: "negative"},
                                            {offset: "100%", class: "negative"}
                                        ]
                                    }
                                    else{
                                        coef = (100*max/(max-min)).toFixed(2);
                                        gradData = [
                                            {offset: "0", class: "positive"},
                                            {offset: coef+"%", class: "positive"},
                                            {offset: coef+"%", class: "negative"},
                                            {offset: "100%", class: "negative"}
                                        ]
                                    }
                                }

                                chart.yAxis
                                    .showMaxMin(false)
                                    .tickFormat( function(d) {
                                        return d3.format("s")(d)
                                    })
                                    .tickPadding(10)
                                    .ticks(3);
                                chart.xAxis
                                    .tickFormat(function(d) {
                                        //return d3.time.format('%y-%m')(new Date(d)); //2016-01 format
                                        return getPeriodName(d);
                                    });

                                //area positive - negative
                                // if (!type) {
                                    //remove previous linearGradient
                                    $("#" + div + " svg").html('<defs> </defs>');

                                    d3.select("#" + div + " svg defs")
                                        .append('linearGradient') //remove previous gradient
                                        .attr("id", div +"_line-gradient")
                                        .attr("x1", '0%').attr("y1", '0%')
                                        .attr("x2", '0%').attr("y2", '100%')
                                        .selectAll("stop")
                                        .data(gradData)
                                        .enter().append("stop")
                                        .attr("offset", function (d) {
                                            return d.offset;
                                        })
                                        .attr("class", function (d) {
                                            return d.class;
                                        });
                                // }

                                //on chart click repaint linear gradient
                                chart.dispatch.on = function(){
                                   self.paint_profitChart("#" + div + " svg", div);
                                };
                                // self.paint_profitChart("#" + div + " svg", div);

                                var svg = d3.select("#" + div + " svg");
                                svg.datum(data.chart_data);
                                svg.transition().duration(500);
                                chart(svg);
                                // d3.select("#" + div + " svg")
                                //     .datum(data.chart_data)
                                //     .call(chart);

                               // if (param.doNotPushForResize){ return chart;}
                               var i = 1;//income
                               if (!param.subtype) {i =3};//profit

                               if (self.to_remove[i]){
                                    nv.utils.offWindowResize(self.to_remove[i]);
                               }
                               self.to_remove[i] = chart.update;
                               // nv.utils.offWindowResize(self.paint_profitChart);


                               nv.utils.onWindowResize(chart.update);
                               //  nv.utils.onWindowResize(function(){
                               //      chart.update();
                               //      // self.paint_profitChart("#" + div + " svg", div);
                               //  });

                                return chart;
                            });
                            }
                            break;

                        case "Cashflow":
                            new Model('res.users').call('check_forecast').then(function(checked){
                                $('#forecast-toggle').prop('checked', checked);
                            });
                            var marginX = {top: 40, right: 50, bottom: 65, left: 50};
                            var forecast_info = self.$el.find('#chart-cashflow .total-outstanding-info-forecast');
                            var total_info = self.$el.find('#chart-cashflow .total-outstanding-info');
                            self.$total_chartCashflow.html(QWeb.render('chart.total', {
                                // total: d3.format(SIprefix)(data.info.end_cash).replace(".",languageNumberSeparator),
                                total: roboUtils.human_value(data.info.end_cash, 2),
                                currency: data.info.currency
                            }));
                            var show_forecast = false;
                            if (typeof data.info.forecast_balance !== 'undefined'){
                                show_forecast = true;
                                forecast_info.show();
                                self.$total_chartCashflow_forecast.show();
                                total_info.hide();
                                self.$total_chartCashflow.hide();
                                self.$total_chartCashflow_forecast.html(QWeb.render('chart.total', {
                                total: roboUtils.human_value(data.info.forecast_balance, 2),
                                currency: data.info.currency
                            }));
                            }
                            else{
                                forecast_info.hide();
                                self.$total_chartCashflow_forecast.hide();
                                total_info.show();
                                self.$total_chartCashflow.show();
                            }

                            if (self.graph_mode_cashflow == 'non_accumulated'){

                                var non_accumulated = true;
                                }
                                else{
                                var non_accumulated = false;
                                }

                            if (non_accumulated){

                                nv.addGraph(function () {

                                var height = 150;
                                var hasData = data.chart_data[0].values.length;
                                if (hasData) {
                                    height = 350;
                                    self.$("#" + div + " svg").css('height','350px'); // jquery vs d3?
                                }

                                var chart = nv.models.discreteBarChart()
                                    .x(function (d) {
                                        return d.date
                                    })
                                    .y(function (d) {
                                        return d.cumCash
                                    })
                                    .showYAxis(true)
                                    .showXAxis(true)
                                    .margin(marginX)
                                    .height(height)
                                    .duration(500)
                                    .noData("")
                                    ;
                                chart.tooltip.chartContainer('#chart-cashflow');

                                var months = [_t("Sau."), _t("Vas."), _t("Kov."), _t("Bal."), _t("Geg."), _t("Bir."),
                                     _t("Lie."), _t("Rgp."), _t("Rgs."), _t("Spl."), _t("Lap."), _t("Grd.")];

                                var quarters = ['Q1','Q2','Q3','Q4'];

                                var getPeriodName = function(d){
                                    if (param.freq.monthly){
                                        return months[(new Date(d)).getMonth()]
                                    }
                                    else if(param.freq.quarterly){
                                        return quarters[Math.floor((new Date(d)).getMonth() / 3)];
                                    }
                                }

                                                                chart.tooltip.contentGenerator(function (d) {

                                    return QWeb.render(div+'.popup-non-accumulated', {
                                                        cashflow_YTD: d.data.cumCash,
                                                        percentage: d.data.percentage,
                                                        curr_date: getPeriodName(d.data.date),
                                                        currency: data.info.currency,
                                                        format: spaceSeparatorFormat,

                                            });
                                });

                                //regroup data quarterly if needed
                                if (param.freq.quarterly){
                                        var newValues=[], newIndex;
                                        var quarter;
                                       _.each(data.chart_data[0].values,
                                            function(element,index){
                                                if (index){
                                                    if(quarter !== getPeriodName(element.date)) {
                                                        newValues.push(element);
                                                        newIndex++;
                                                        quarter = getPeriodName(element.date);
                                                    }
                                                    else{
                                                        newValues[newIndex].cashflow += element.cashflow;
                                                        newValues[newIndex].incomeflow += element.incomeflow;
                                                        newValues[newIndex].expenseflow += element.expenseflow;
                                                        newValues[newIndex].diffflow += element.diffflow;
                                                    }
                                                }
                                                else{
                                                    newValues.push(element);
                                                    quarter = getPeriodName(element.date);
                                                    newIndex = 0;
                                                }
                                        });

                                        data.chart_data[0].values = newValues;
                                }
                                //sortBy data, and prepare acumulated sum for display
                                _.each(data.chart_data[0].values.sort(function(a, b){return a.date-b.date;}),
                                        function(element, index, list){
                                                element.cumCash = element.cashflow;
                                                element.cumIncome = element.incomeflow;
                                                element.cumExpense = element.expenseflow;
                                                element.cumDiff = element.diffflow;
                                                element.color = pickChartColor(element.cumCash);
                                        }
                                )

                                //to color
                                var max = 0, min=0;
                                _.each(data.chart_data[0].values,
                                    function(element){
                                        if (min > element.cumCash){
                                            min = element.cumCash
                                        }
                                        if (max < element.cumCash){
                                            max = element.cumCash
                                        }
                                    }
                                )


                                var gradData, coef;
                                if (min >= 0){
                                    gradData = [
                                        {offset: "0"},
                                        {offset: "100%"}
                                    ]
                                }
                                else{
                                    if (max <= 0){
                                        gradData = [
                                            {offset: "0"},
                                            {offset: "100%"}
                                        ]
                                    }
                                    else{
                                        coef = (100*max/(max-min)).toFixed(2);
                                        gradData = [
                                            {offset: "0"},
                                            {offset: coef+"%"},
                                            {offset: coef+"%"},
                                            {offset: "100%"}
                                        ]
                                    }
                                }

                                chart.yAxis
                                    .showMaxMin(false)
                                    .tickFormat( function(d) {
                                        return d3.format("s")(d)
                                    })
                                    .tickPadding(10)
                                    .ticks(3);
                                chart.xAxis
                                    .tickFormat(function(d) {

                                        return getPeriodName(d);
                                    });

                                    $("#" + div + " svg").html('<defs> </defs>');

                                    d3.select("#" + div + " svg defs")
                                        .append('linearGradient') //remove previous gradient
                                        .attr("id", div +"_line-gradient")
                                        .attr("x1", '0%').attr("y1", '0%')
                                        .attr("x2", '0%').attr("y2", '100%')
                                        .selectAll("stop")
                                        .data(gradData)
                                        .enter().append("stop")
                                        .attr("offset", function (d) {
                                            return d.offset;
                                        })
                                        .attr("class", function (d) {
                                            return d.class;
                                        });
                                // }

                                chart.dispatch.on = function(){
                                   self.paint_cashflow("#" + div + " svg", div);
                                };

                                var svg = d3.select("#" + div + " svg");
                                svg.datum(data.chart_data);
                                svg.transition().duration(500);
                                chart(svg);

                               if (self.to_remove[4]){
                                    nv.utils.offWindowResize(self.to_remove[4]);
                               }
                               self.to_remove[4] = chart.update;

                               nv.utils.onWindowResize(chart.update);
                                return chart;
                            });
                            }
                            else{
                                nv.addGraph(function () {

                                var height = 150;
                                var hasData = data.chart_data[0].values.length;
                                if (hasData) {
                                    height = 350;
                                    self.$("#" + div + " svg").css('height','350px'); // jquery vs d3?
                                }

                                var chart = nv.models.stackedAreaChart()
                                    .x(function (d) {
                                        return d.date
                                    })
                                    .y(function (d) {
                                        return d.cumCash
                                    })
                                    .showLegend(false)
                                    .showControls(false)
                                    .showYAxis(true)
                                    .showXAxis(true)
                                    .margin(marginX)
                                    .height(height)
                                    .duration(500)
                                    .noData("")
                                    // .clipRadius(10)
                                    ;

                                chart.tooltip.chartContainer('#chart-cashflow');

                                var months = [_t("Sau."), _t("Vas."), _t("Kov."), _t("Bal."), _t("Geg."), _t("Bir."),
                                     _t("Lie."), _t("Rgp."), _t("Rgs."), _t("Spl."), _t("Lap."), _t("Grd.")];

                                var quarters = ['Q1','Q2','Q3','Q4'];

                                chart.xScale(d3.time.scale());

                                var getPeriodName = function(d){
                                    if (param.freq.monthly){
                                        return months[(new Date(d)).getMonth()]
                                    }
                                    else if(param.freq.quarterly){
                                        return quarters[Math.floor((new Date(d)).getMonth() / 3)];
                                    }
                                }

                                chart.tooltip.contentGenerator(function (d) {

                                    return QWeb.render(div+'.popup', {
                                                        cashflow_curr: d.point.cashflow,
                                                        cashflow_YTD: d.point.cumCash,
                                                        income_curr: d.point.incomeflow,
                                                        income_YTD: d.point.cumIncome,
                                                        expenses_curr: d.point.expenseflow,
                                                        expenses_YTD: d.point.cumExpense,
                                                        exp_inc_diff_curr: d.point.diffflow,
                                                        exp_inc_diff_YTD: d.point.cumDiff,
                                                        curr_date: getPeriodName(d.point.date),
                                                        YTD_date: getPeriodName(d.series[0].values[0].date),
                                                        currency: data.info.currency,
                                                        format: spaceSeparatorFormat,
                                                        show_forecast: show_forecast,
                                                        payable_taxes: d.point.payable_taxes,
                                                        average_factual_taxes: d.point.average_factual_taxes,
                                                        forecast_budget_sum: d.point.forecast_budget_sum,
                                                        expense_du: d.point.expense_du,
                                                        expense_other: d.point.expense_other

                                            });
                                });


                                //regroup data quarterly if needed
                                if (param.freq.quarterly){
                                        var newValues=[], newIndex;
                                        var quarter;
                                       _.each(data.chart_data[0].values,
                                            function(element,index){
                                                if (index){
                                                    if(quarter !== getPeriodName(element.date)) {
                                                        newValues.push(element);
                                                        newIndex++;
                                                        quarter = getPeriodName(element.date);
                                                    }
                                                    else{
                                                        newValues[newIndex].cashflow += element.cashflow;
                                                        newValues[newIndex].incomeflow += element.incomeflow;
                                                        newValues[newIndex].expenseflow += element.expenseflow;
                                                        newValues[newIndex].diffflow += element.diffflow;
                                                    }
                                                }
                                                else{
                                                    newValues.push(element);
                                                    quarter = getPeriodName(element.date);
                                                    newIndex = 0;
                                                }
                                        });

                                        data.chart_data[0].values = newValues;
                                }
                                //sortBy data, and prepare acumulated sum for display
                                _.each(data.chart_data[0].values.sort(function(a, b){return a.date-b.date;}),
                                        function(element, index, list){
                                            if (index) {
                                                    element.cumCash = list[index-1].cumCash + element.cashflow;
                                                    element.cumIncome = list[index-1].cumIncome + element.incomeflow;
                                                    element.cumExpense = list[index-1].cumExpense + element.expenseflow;
                                                    element.cumDiff = list[index-1].cumDiff + element.diffflow;
                                            }
                                            else {
                                                element.cumCash = element.cashflow;
                                                element.cumIncome = element.incomeflow;
                                                element.cumExpense = element.expenseflow;
                                                element.cumDiff = element.diffflow;
                                            }
                                        }
                                )

                                //to color
                                var max = 0, min=0, forecast=false;
                                _.each(data.chart_data[0].values,
                                    function(element){
                                        if (min > element.cumCash){
                                            min = element.cumCash
                                        }
                                        if (max < element.cumCash){
                                            max = element.cumCash
                                        }
                                        if (typeof element.forecast !== 'undefined'){
                                            forecast = true;
                                        }
                                    }
                                )


                                var gradData, coef;
                                if (forecast === true){
                                if (min >= 0){
                                    gradData = [
                                        {offset: "0", class: "positive-forecast"},
                                        {offset: "100%", class: "positive-forecast"}
                                    ]
                                }
                                else{
                                    if (max <= 0){
                                        gradData = [
                                            {offset: "0", class: "negative-forecast"},
                                            {offset: "100%", class: "negative-forecast"}
                                        ]
                                    }
                                    else{
                                        coef = (100*max/(max-min)).toFixed(2);
                                        gradData = [
                                            {offset: "0", class: "positive-forecast"},
                                            {offset: coef+"%", class: "positive-forecast"},
                                            {offset: coef+"%", class: "negative-forecast"},
                                            {offset: "100%", class: "negative-forecast"}
                                        ]
                                    }
                                }

                            }else{

                                if (min >= 0){
                                    gradData = [
                                        {offset: "0", class: "positive"},
                                        {offset: "100%", class: "positive"}
                                    ]
                                }
                                else{
                                    if (max <= 0){
                                        gradData = [
                                            {offset: "0", class: "negative"},
                                            {offset: "100%", class: "negative"}
                                        ]
                                    }
                                    else{
                                        coef = (100*max/(max-min)).toFixed(2);
                                        gradData = [
                                            {offset: "0", class: "positive"},
                                            {offset: coef+"%", class: "positive"},
                                            {offset: coef+"%", class: "negative"},
                                            {offset: "100%", class: "negative"}
                                        ]
                                    }
                                }
                                }

                                chart.yAxis
                                    .showMaxMin(false)
                                    .tickFormat( function(d) {
                                        return d3.format("s")(d)
                                    })
                                    .tickPadding(10)
                                    .ticks(3);
                                chart.xAxis
                                    .tickFormat(function(d) {
                                        //return d3.time.format('%y-%m')(new Date(d)); //2016-01 format
                                        return getPeriodName(d);
                                    });

                                //area positive - negative
                                // if (!type) {
                                    //remove previous linearGradient
                                    $("#" + div + " svg").html('<defs> </defs>');

                                    d3.select("#" + div + " svg defs")
                                        .append('linearGradient') //remove previous gradient
                                        .attr("id", div +"_line-gradient")
                                        .attr("x1", '0%').attr("y1", '0%')
                                        .attr("x2", '0%').attr("y2", '100%')
                                        .selectAll("stop")
                                        .data(gradData)
                                        .enter().append("stop")
                                        .attr("offset", function (d) {
                                            return d.offset;
                                        })
                                        .attr("class", function (d) {
                                            return d.class;
                                        });
                                // }

                                //on chart click repaint linear gradient
                                chart.dispatch.on = function(){
                                   self.paint_cashflow("#" + div + " svg", div);
                                };
                                // self.paint_profitChart("#" + div + " svg", div);

                                var svg = d3.select("#" + div + " svg");
                                svg.datum(data.chart_data);
                                svg.transition().duration(500);
                                chart(svg);

                               if (self.to_remove[4]){
                                    nv.utils.offWindowResize(self.to_remove[4]);
                               }
                               self.to_remove[4] = chart.update;

                               nv.utils.onWindowResize(chart.update);
                               // nv.utils.onWindowResize(function(){
                               //      chart.update();
                               //  });
                                return chart;
                            });
                            }

                            break;

                        case "taxesTable":

                            self.load_tax_table(data, spaceSeparatorFormat);

                            self.$el.on('click', "#future_taxes_table div[class^='future-taxes-table-row']", function(k){
                                    var date_str = $("h4.tax-table-date-interval").text();
                                    var category = $(this).attr('categ');
                                    var preliminary = $(this).attr('prelim');

                                    return (new Model('account.move.line')).call('get_account_move_line_front_action',
                                    [category, date_str, preliminary]).then(function(action){
                                    self.do_action(action, {'clear_breadcrumbs': false});
                                    });
                            });

                            break;
                    }
                }
            }).always(def.resolve());
            // ROBO: hide boot screen only after full load
            window.stop_boot.resolve();
            return def;
        }),

        destroy: function(){
            var self = this;
            if (self.$el.find('#robo_datetimepicker1').data("DateTimePicker")){
                self.$el.find('#robo_datetimepicker1').data("DateTimePicker").destroy();
            }
            if (self.$el.find('#robo_datetimepicker2').data("DateTimePicker")){
                self.$el.find('#robo_datetimepicker2').data("DateTimePicker").destroy();
            }
            this.to_remove.forEach(function(el){
                if (el) {
                    nv.utils.offWindowResize(el);
                }
            });
            nv.utils.offWindowResize(self.paint_bulletChart);
            nv.utils.offWindowResize(self.paint_profitChart);

            self.$el.find("#chart-expenses .pieChart-legend i[class^='icon-']").each(function(i,el){
                $(el).off();
            });

            self.$el.find("#chart-incomeCompare .pieChart-legend-2 i[class^='icon-']").each(function(i,el){
                $(el).off();
            });

            this._super();
        }
    });

    // core.form_tag_registry.add('pagalbininkas', Pagalbininkas);
    core.action_registry.add('robo.Vadovas', Pagalbininkas);

    function synchronized(fn) {
        // return function(){
        //     fn.apply(this, arguments);
        // }
        var fn_mutex = new utils.Mutex();
        return function () {
            var obj = this;
            var args = _.toArray(arguments);
            return fn_mutex.exec(function () {
                if (obj.isDestroyed()) { return $.when(); }
                return fn.apply(obj, args);
            });
        };
    }

});