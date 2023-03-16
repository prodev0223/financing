robo.define('robo.reports', function(require) {
"use strict";

var core = require('web.core');
var data_manager = require('web.data_manager');
var session = require('web.session');
var Widget = require('web.Widget');

var _t = core._t;
var QWeb = core.qweb;


var RoboReports = Widget.extend({
    className: 'robo-reports',
    template: 'RoboReports',

    willStart: function(){
        this.action_button_mapping = {
            "robo.open_balance": '.robo_button_balance',
            "sl_general_report.open_cash_flow": '.robo_button_cash',
            "robo.open_profit": '.robo_button_profit',
            "robo.open_debt": '.robo_button_client_debt',
            "robo.open_new_invoices": '.robo_button_new_invoices',
            "robo.account_invoice_report_materialized_action_server": '.robo_button_expenses',
            "robo.open_cashbox_report": '.robo_button_cashier',
            "robo.open_general_ledger_report": '.robo_button_general_ledger',
            "robo.open_payslips_report": '.robo_button_payslips',
            "robo.open_timesheets_report": '.robo_button_timesheets',
            "robo.open_payments_report": '.robo_button_payments',
            "robo.action_open_payable_aml": '.robo_button_all_payables',
            "robo.action_open_other_payments": '.robo_button_employee_other_payments',
            "robo.action_kaupiniu_wizard_front": '.robo_button_employee_holiday_accumulation',
            "robo.action_downtime_report_front": '.robo_button_downtime',
            "l10n_lt_payroll.hr_employee_work_norm_report_export_front_action": '.robo_button_hr_employee_work_norm_report_export',
        }
        var self = this;
        this.robo_reports_general = false;
        this.robo_front_statements = false;
        return $.when(session.user_has_group('robo.robo_reports_general'),
                session.user_has_group('robo_basic.group_robo_hr_manager'),
                session.is_premium_manager(), session.user_has_group('robo.group_front_bank_statements_own'),
                this._super.apply(this, arguments))
            .then(function(robo_reports_general, is_hr_manager, is_premium_manager, robo_front_statements){
                self.is_premium_manager = is_premium_manager;
                self.robo_reports_general = robo_reports_general;
                self.is_hr_manager = is_hr_manager;
                self.robo_front_statements = robo_front_statements;
                return $.when();
        })
    },
    start: function() {
        var self = this;
        var action_button_mapping = this.action_button_mapping;
        var action_xml_ids = Object.keys(action_button_mapping);
        return $.when.apply($, action_xml_ids.map(function(r){return data_manager.load_action(r)}).concat(this._super.apply(this, arguments)))
                .then(function(){

                //Filter only defined actions
                var actions = Array.from(arguments).filter(action => action !== undefined && action_xml_ids.includes(action.xml_id));

                //Build an object of button classes -> actions
                var class_action_mapping = {}
                for (var i in actions) {
                    var action = actions[i];
                    class_action_mapping[action_button_mapping[action.xml_id]] = action;
                }

                if (self.$el.is('.robo_reports_buttons')) {
                    self.$el.on('click', '.reports-box', function(e){
                        var bAction = _(class_action_mapping).find(function(v,k){
                           return $(e.currentTarget).has(k).length > 0
                        });
                        if (_.isObject(bAction)) {
                           self.do_action(bAction,{'clear_breadcrumbs': true});
                        }
                    }).bind(class_action_mapping);
                }
            }.bind(action_xml_ids, action_button_mapping));
    },
    renderElement: function(){
        this._super();
        // ROBO: hide boot screen only after full load
        window.stop_boot.resolve();
    },
});


core.action_registry.add('robo.reports', RoboReports);

return RoboReports;

});