robo.define('robo_dynamic_reports.robo_reports', function(require) {
"use strict";

var RoboReports = require('robo.reports');

return RoboReports.include({
    start: function() {
        // Account asset
        var account_asset_id = "robo_dynamic_reports.account_asset_dynamic_report_front_end_wizard_action";
        this.action_button_mapping[account_asset_id] = '.robo_button_account_asset_dynamic_report';

        // General ledger
        var general_ledger_id = "robo_dynamic_reports.general_ledger_dynamic_report_front_end_wizard_action";
        this.action_button_mapping[general_ledger_id] = '.robo_button_general_ledger';

        // Invoice registry
        var invoice_registry_id = "robo_dynamic_reports.invoice_registry_dynamic_report_front_end_wizard_action";
        this.action_button_mapping[invoice_registry_id] = '.robo_button_new_invoices';

        // Invoice registry
        var account_aged_trial_balance_id = "robo_dynamic_reports.account_aged_trial_balance_dynamic_report_action";
        this.action_button_mapping[account_aged_trial_balance_id] = '.robo_button_client_debt';

        // Cash flow
        var account_aged_trial_balance_id = "robo_dynamic_reports.dynamic_cash_flow_action";
        this.action_button_mapping[account_aged_trial_balance_id] = '.robo_button_cash';

        return this._super();
    },
});

});