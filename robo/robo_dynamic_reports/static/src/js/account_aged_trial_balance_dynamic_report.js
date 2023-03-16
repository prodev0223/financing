robo.define('robo_dynamic_reports.DynamicAccountAgedTrialBalanceReport', function(require) {
    'use strict';
    var core = require('web.core');
    var DynamicReports = require('account_dynamic_reports.DynamicReportController');
    var DynamicReportHeaderController = require('account_dynamic_reports.DynamicReportHeaderController');
    var _t = core._t;

    var DynamicAATBMain = DynamicReports.extend({
        widgetModel: 'account.aged.trial.balance',
    });

    DynamicReportHeaderController.include({
        adjustShownFilterSelection: function(event) {
            this._super();
            var currentlySelectedValues = this.$el.val() || event.currentTarget.value;
            if (event.added && event.added.id === 'invoices_only') {
                var showAccountSelection = false;
            } else {
                if (Array.isArray(currentlySelectedValues) && currentlySelectedValues.includes('invoices_only') &&
                    (!event.removed || event.removed.id !== 'invoices_only')) {
                    var showAccountSelection = false;
                } else if (currentlySelectedValues === "invoices_only") {
                    var showAccountSelection = false;
                } else {
                    var showAccountSelection = true;
                }
            }
            let accountSelection = $('.py-search-account_ids')
            if (accountSelection && accountSelection.length > 0) {
                $(accountSelection).toggleClass('hidden', !showAccountSelection)
            }
        },
    });

    core.action_registry.add('dynamic.aatb', DynamicAATBMain);

});