robo.define('robo_dynamic_reports.DynamicCashFlowReports', function(require) {
    'use strict';
    var core = require('web.core');
    var QWeb = core.qweb
    var DynamicReports = require('account_dynamic_reports.DynamicReportController');
    var DynamicDataController = require('account_dynamic_reports.DynamicReportDataController');
    var _t = core._t;

    var DynamicCashFlowReport = DynamicReports.extend({
        widgetModel: 'account.cashflow.report',
        init: function (view, code) {
            this._super(view, code);
            this.enableReportSettings = false;
        },
    });

    DynamicDataController.include({
        isCashFlowReport: function() {
            return this.widgetModel == 'account.cashflow.report';
        },
        setSortByCaret: function() {
            if (this.isCashFlowReport()) { return }  // Disable sorting
            return this._super();
        },
        updateSortingOrder: async function(event) {
            if (this.isCashFlowReport()) { return }  // Disable sorting
            return this._super(event);
        },
    });

    core.action_registry.add('dynamic.cashflow', DynamicCashFlowReport);

});